from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from convivial_medicine.adapters.pubmed.models import PubMedESearchResult
from convivial_medicine.adapters.pubmed.request_fingerprint import (
    redacted_request_params,
    request_fingerprint,
)
from convivial_medicine.config import Settings, get_settings
from convivial_medicine.domain.manifests import QueryManifest, SourceSnapshotManifest
from convivial_medicine.storage.artifacts import LocalArtifactStore, StoredArtifact

PUBMED_ESEARCH_ENDPOINT = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_SOURCE_NAME = "pubmed"
PUBMED_ESEARCH_OPERATION = "esearch"
PUBMED_ESEARCH_SCHEMA_VERSION = "pubmed-esearch-v1"
DEFAULT_TIMEOUT_SECONDS = 20.0


@dataclass(frozen=True)
class PubMedESearchAdapterResult:
    raw_artifact: StoredArtifact
    source_snapshot_manifest: SourceSnapshotManifest
    parsed: PubMedESearchResult


def build_esearch_params(
    manifest: QueryManifest,
    *,
    settings: Settings | None = None,
) -> dict[str, str]:
    params = {
        "db": manifest.db,
        "term": manifest.term,
        "retmode": manifest.retmode,
        "retmax": str(manifest.retmax),
        "usehistory": "y" if manifest.usehistory else "n",
    }
    if settings is not None:
        if settings.ncbi_tool:
            params["tool"] = settings.ncbi_tool
        if settings.ncbi_email:
            params["email"] = settings.ncbi_email
        if settings.ncbi_api_key:
            params["api_key"] = settings.ncbi_api_key
    return params


def process_esearch_response_bytes(
    *,
    raw_bytes: bytes,
    artifact_store: LocalArtifactStore,
    endpoint: str,
    request_params: dict[str, str],
    http_status: int,
    content_type: str | None,
) -> PubMedESearchAdapterResult:
    raw_artifact = artifact_store.write_bytes(raw_bytes)
    manifest = _build_source_snapshot_manifest(
        raw_payload_hash=raw_artifact.artifact_hash,
        endpoint=endpoint,
        request_params=request_params,
        http_status=http_status,
        content_type=content_type,
    )
    provider_payload = _parse_json_bytes(raw_bytes)
    parsed = PubMedESearchResult.from_provider_payload(
        provider_payload,
        source_snapshot_manifest_hash=manifest.manifest_hash(),
        raw_payload_hash=raw_artifact.artifact_hash,
    )
    return PubMedESearchAdapterResult(
        raw_artifact=raw_artifact,
        source_snapshot_manifest=manifest,
        parsed=parsed,
    )


def run_esearch(
    *,
    manifest: QueryManifest,
    artifact_store: LocalArtifactStore,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
    endpoint: str = PUBMED_ESEARCH_ENDPOINT,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> PubMedESearchAdapterResult:
    resolved_settings = settings or get_settings()
    params = build_esearch_params(manifest, settings=resolved_settings)
    if client is None:
        with httpx.Client(timeout=timeout) as owned_client:
            response = owned_client.get(endpoint, params=params)
    else:
        response = client.get(endpoint, params=params, timeout=timeout)
    response.raise_for_status()
    return process_esearch_response_bytes(
        raw_bytes=response.content,
        artifact_store=artifact_store,
        endpoint=endpoint,
        request_params=params,
        http_status=response.status_code,
        content_type=response.headers.get("content-type"),
    )


def _build_source_snapshot_manifest(
    *,
    raw_payload_hash: str,
    endpoint: str,
    request_params: dict[str, str],
    http_status: int,
    content_type: str | None,
) -> SourceSnapshotManifest:
    return SourceSnapshotManifest(
        manifest_version="1",
        schema_version=PUBMED_ESEARCH_SCHEMA_VERSION,
        payload_hash=raw_payload_hash,
        metadata={
            "source_name": PUBMED_SOURCE_NAME,
            "operation": PUBMED_ESEARCH_OPERATION,
            "endpoint": endpoint,
            "request_method": "GET",
            "request_params": redacted_request_params(request_params),
            "request_fingerprint": request_fingerprint(
                method="GET",
                endpoint=endpoint,
                params=request_params,
            ),
            "http_status": http_status,
            "content_type": content_type,
        },
    )


def _parse_json_bytes(raw_bytes: bytes) -> dict[str, Any]:
    payload = json.loads(raw_bytes.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("PubMed ESearch response must be a JSON object")
    return payload
