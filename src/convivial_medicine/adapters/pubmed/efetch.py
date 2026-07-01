from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from convivial_medicine.adapters.pubmed.esearch import PUBMED_SOURCE_NAME
from convivial_medicine.adapters.pubmed.models import (
    PubMedEFetchResult,
    pubmed_xml_provider_payload,
)
from convivial_medicine.adapters.pubmed.request_fingerprint import (
    redacted_request_params,
    request_fingerprint,
)
from convivial_medicine.config import Settings, get_settings
from convivial_medicine.domain.manifests import SourceSnapshotManifest
from convivial_medicine.storage.artifacts import LocalArtifactStore, StoredArtifact

PUBMED_EFETCH_ENDPOINT = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
PUBMED_EFETCH_OPERATION = "efetch"
PUBMED_EFETCH_SCHEMA_VERSION = "pubmed-efetch-v1"
DEFAULT_TIMEOUT_SECONDS = 20.0


@dataclass(frozen=True)
class PubMedEFetchAdapterResult:
    raw_artifact: StoredArtifact
    source_snapshot_manifest: SourceSnapshotManifest
    parsed: PubMedEFetchResult
    endpoint: str
    request_fingerprint: str
    request_metadata: dict[str, Any]
    http_status: int
    content_type: str
    provider_payload: dict[str, Any]
    response_metadata: dict[str, Any]
    retrieved_at: datetime


def build_efetch_params(
    pmids: tuple[str, ...],
    *,
    settings: Settings | None = None,
) -> dict[str, str]:
    normalized_pmids = tuple(pmid.strip() for pmid in pmids if pmid.strip())
    if not normalized_pmids:
        raise ValueError("At least one PMID is required for PubMed EFetch")

    params = {
        "db": "pubmed",
        "id": ",".join(normalized_pmids),
        "retmode": "xml",
    }
    if settings is not None:
        if settings.ncbi_tool:
            params["tool"] = settings.ncbi_tool
        if settings.ncbi_email:
            params["email"] = settings.ncbi_email
        if settings.ncbi_api_key:
            params["api_key"] = settings.ncbi_api_key
    return params


def process_efetch_response_bytes(
    *,
    raw_bytes: bytes,
    artifact_store: LocalArtifactStore,
    endpoint: str,
    request_params: dict[str, str],
    requested_pmids: tuple[str, ...],
    http_status: int,
    content_type: str | None,
    retrieved_at: datetime | None = None,
) -> PubMedEFetchAdapterResult:
    resolved_retrieved_at = retrieved_at or datetime.now(UTC)
    resolved_content_type = content_type or "application/octet-stream"
    resolved_request_fingerprint = request_fingerprint(
        method="GET",
        endpoint=endpoint,
        params=request_params,
    )
    request_metadata = {
        "endpoint": endpoint,
        "method": "GET",
        "params": redacted_request_params(request_params),
    }
    raw_artifact = artifact_store.write_bytes(raw_bytes)
    manifest = _build_source_snapshot_manifest(
        raw_payload_hash=raw_artifact.artifact_hash,
        endpoint=endpoint,
        request_params=request_params,
        http_status=http_status,
        content_type=resolved_content_type,
        resolved_request_fingerprint=resolved_request_fingerprint,
    )
    provider_payload = pubmed_xml_provider_payload(raw_bytes)
    parsed = PubMedEFetchResult.from_xml_bytes(
        raw_bytes,
        requested_pmids=requested_pmids,
        source_snapshot_manifest_hash=manifest.manifest_hash(),
        raw_payload_hash=raw_artifact.artifact_hash,
    )
    response_metadata = {
        "pmids_requested": len(parsed.requested_pmids),
        "pmids_returned": len(parsed.returned_pmids),
        "records_returned": parsed.records_returned,
    }
    return PubMedEFetchAdapterResult(
        raw_artifact=raw_artifact,
        source_snapshot_manifest=manifest,
        parsed=parsed,
        endpoint=endpoint,
        request_fingerprint=resolved_request_fingerprint,
        request_metadata=request_metadata,
        http_status=http_status,
        content_type=resolved_content_type,
        provider_payload=provider_payload,
        response_metadata=response_metadata,
        retrieved_at=resolved_retrieved_at,
    )


def run_efetch(
    *,
    pmids: tuple[str, ...],
    artifact_store: LocalArtifactStore,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
    endpoint: str = PUBMED_EFETCH_ENDPOINT,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> PubMedEFetchAdapterResult:
    resolved_settings = settings or get_settings()
    normalized_pmids = tuple(pmid.strip() for pmid in pmids if pmid.strip())
    params = build_efetch_params(normalized_pmids, settings=resolved_settings)
    if client is None:
        with httpx.Client(timeout=timeout) as owned_client:
            response = owned_client.get(endpoint, params=params)
    else:
        response = client.get(endpoint, params=params, timeout=timeout)
    response.raise_for_status()
    return process_efetch_response_bytes(
        raw_bytes=response.content,
        artifact_store=artifact_store,
        endpoint=endpoint,
        request_params=params,
        requested_pmids=normalized_pmids,
        http_status=response.status_code,
        content_type=response.headers.get("content-type"),
    )


def _build_source_snapshot_manifest(
    *,
    raw_payload_hash: str,
    endpoint: str,
    request_params: dict[str, str],
    http_status: int,
    content_type: str,
    resolved_request_fingerprint: str,
) -> SourceSnapshotManifest:
    return SourceSnapshotManifest(
        manifest_version="1",
        schema_version=PUBMED_EFETCH_SCHEMA_VERSION,
        payload_hash=raw_payload_hash,
        metadata={
            "source_name": PUBMED_SOURCE_NAME,
            "operation": PUBMED_EFETCH_OPERATION,
            "endpoint": endpoint,
            "request_method": "GET",
            "request_params": redacted_request_params(request_params),
            "request_fingerprint": resolved_request_fingerprint,
            "http_status": http_status,
            "content_type": content_type,
        },
    )
