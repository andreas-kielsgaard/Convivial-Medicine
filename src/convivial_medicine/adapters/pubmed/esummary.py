from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from convivial_medicine.adapters.pubmed.models import PubMedESummaryResult
from convivial_medicine.adapters.pubmed.source_response import (
    PubMedStoredSourceResponse,
    preserve_pubmed_source_response,
    pubmed_http_status_error,
)
from convivial_medicine.config import Settings, get_settings
from convivial_medicine.domain.manifests import SourceSnapshotManifest
from convivial_medicine.storage.artifacts import LocalArtifactStore, StoredArtifact

PUBMED_ESUMMARY_ENDPOINT = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
PUBMED_ESUMMARY_OPERATION = "esummary"
PUBMED_ESUMMARY_SCHEMA_VERSION = "pubmed-esummary-v1"
DEFAULT_TIMEOUT_SECONDS = 20.0


@dataclass(frozen=True)
class PubMedESummaryAdapterResult:
    raw_artifact: StoredArtifact
    source_snapshot_manifest: SourceSnapshotManifest
    parsed: PubMedESummaryResult
    endpoint: str
    request_fingerprint: str
    request_metadata: dict[str, Any]
    http_status: int
    content_type: str
    provider_payload: dict[str, Any]
    response_metadata: dict[str, Any]
    retrieved_at: datetime


def build_esummary_params(
    pmids: tuple[str, ...],
    *,
    settings: Settings | None = None,
) -> dict[str, str]:
    normalized_pmids = tuple(pmid.strip() for pmid in pmids if pmid.strip())
    if not normalized_pmids:
        raise ValueError("At least one PMID is required for PubMed ESummary")

    params = {
        "db": "pubmed",
        "id": ",".join(normalized_pmids),
        "retmode": "json",
        "version": "2.0",
    }
    if settings is not None:
        if settings.ncbi_tool:
            params["tool"] = settings.ncbi_tool
        if settings.ncbi_email:
            params["email"] = settings.ncbi_email
        if settings.ncbi_api_key:
            params["api_key"] = settings.ncbi_api_key
    return params


def process_esummary_response_bytes(
    *,
    raw_bytes: bytes,
    artifact_store: LocalArtifactStore,
    endpoint: str,
    request_params: dict[str, str],
    requested_pmids: tuple[str, ...],
    http_status: int,
    content_type: str | None,
    retrieved_at: datetime | None = None,
) -> PubMedESummaryAdapterResult:
    stored_response = preserve_pubmed_source_response(
        raw_bytes=raw_bytes,
        artifact_store=artifact_store,
        endpoint=endpoint,
        request_params=request_params,
        operation=PUBMED_ESUMMARY_OPERATION,
        schema_version=PUBMED_ESUMMARY_SCHEMA_VERSION,
        http_status=http_status,
        content_type=content_type,
        retrieved_at=retrieved_at,
    )
    return _parse_stored_esummary_response(
        raw_bytes=raw_bytes,
        requested_pmids=requested_pmids,
        stored_response=stored_response,
    )


def _parse_stored_esummary_response(
    *,
    raw_bytes: bytes,
    requested_pmids: tuple[str, ...],
    stored_response: PubMedStoredSourceResponse,
) -> PubMedESummaryAdapterResult:
    manifest = stored_response.source_snapshot_manifest
    raw_artifact = stored_response.raw_artifact
    provider_payload = _parse_json_bytes(raw_bytes)
    parsed = PubMedESummaryResult.from_provider_payload(
        provider_payload,
        requested_pmids=requested_pmids,
        source_snapshot_manifest_hash=manifest.manifest_hash(),
        raw_payload_hash=raw_artifact.artifact_hash,
    )
    response_metadata = {
        "pmids_requested": len(parsed.requested_pmids),
        "pmids_returned": len(parsed.returned_pmids),
        "summaries_returned": parsed.summaries_returned,
    }
    return PubMedESummaryAdapterResult(
        raw_artifact=raw_artifact,
        source_snapshot_manifest=manifest,
        parsed=parsed,
        endpoint=stored_response.endpoint,
        request_fingerprint=stored_response.request_fingerprint,
        request_metadata=stored_response.request_metadata,
        http_status=stored_response.http_status,
        content_type=stored_response.content_type,
        provider_payload=provider_payload,
        response_metadata=response_metadata,
        retrieved_at=stored_response.retrieved_at,
    )


def run_esummary(
    *,
    pmids: tuple[str, ...],
    artifact_store: LocalArtifactStore,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
    endpoint: str = PUBMED_ESUMMARY_ENDPOINT,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> PubMedESummaryAdapterResult:
    resolved_settings = settings or get_settings()
    normalized_pmids = tuple(pmid.strip() for pmid in pmids if pmid.strip())
    params = build_esummary_params(normalized_pmids, settings=resolved_settings)
    if client is None:
        with httpx.Client(timeout=timeout) as owned_client:
            response = owned_client.get(endpoint, params=params)
    else:
        response = client.get(endpoint, params=params, timeout=timeout)
    stored_response = preserve_pubmed_source_response(
        raw_bytes=response.content,
        artifact_store=artifact_store,
        endpoint=endpoint,
        request_params=params,
        operation=PUBMED_ESUMMARY_OPERATION,
        schema_version=PUBMED_ESUMMARY_SCHEMA_VERSION,
        http_status=response.status_code,
        content_type=response.headers.get("content-type"),
    )
    if response.is_error:
        raise pubmed_http_status_error(
            operation=PUBMED_ESUMMARY_OPERATION,
            response=response,
            stored_response=stored_response,
        )
    return _parse_stored_esummary_response(
        raw_bytes=response.content,
        requested_pmids=normalized_pmids,
        stored_response=stored_response,
    )


def _parse_json_bytes(raw_bytes: bytes) -> dict[str, Any]:
    payload = json.loads(raw_bytes.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("PubMed ESummary response must be a JSON object")
    return payload
