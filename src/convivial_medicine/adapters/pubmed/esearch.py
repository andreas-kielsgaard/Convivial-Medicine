from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from convivial_medicine.adapters.pubmed.models import PubMedESearchResult
from convivial_medicine.adapters.pubmed.source_response import (
    PubMedStoredSourceResponse,
    preserve_pubmed_source_response,
    pubmed_http_status_error,
)
from convivial_medicine.config import Settings, get_settings
from convivial_medicine.domain.manifests import QueryManifest, SourceSnapshotManifest
from convivial_medicine.storage.artifacts import LocalArtifactStore, StoredArtifact

PUBMED_ESEARCH_ENDPOINT = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_ESEARCH_OPERATION = "esearch"
PUBMED_ESEARCH_SCHEMA_VERSION = "pubmed-esearch-v1"
DEFAULT_TIMEOUT_SECONDS = 20.0


@dataclass(frozen=True)
class PubMedESearchAdapterResult:
    raw_artifact: StoredArtifact
    source_snapshot_manifest: SourceSnapshotManifest
    parsed: PubMedESearchResult
    endpoint: str
    request_fingerprint: str
    request_metadata: dict[str, Any]
    http_status: int
    content_type: str
    provider_payload: dict[str, Any]
    response_metadata: dict[str, Any]
    retrieved_at: datetime


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
    retrieved_at: datetime | None = None,
) -> PubMedESearchAdapterResult:
    stored_response = preserve_pubmed_source_response(
        raw_bytes=raw_bytes,
        artifact_store=artifact_store,
        endpoint=endpoint,
        request_params=request_params,
        operation=PUBMED_ESEARCH_OPERATION,
        schema_version=PUBMED_ESEARCH_SCHEMA_VERSION,
        http_status=http_status,
        content_type=content_type,
        retrieved_at=retrieved_at,
    )
    return _parse_stored_esearch_response(raw_bytes=raw_bytes, stored_response=stored_response)


def _parse_stored_esearch_response(
    *,
    raw_bytes: bytes,
    stored_response: PubMedStoredSourceResponse,
) -> PubMedESearchAdapterResult:
    manifest = stored_response.source_snapshot_manifest
    raw_artifact = stored_response.raw_artifact
    provider_payload = _parse_json_bytes(raw_bytes)
    parsed = PubMedESearchResult.from_provider_payload(
        provider_payload,
        source_snapshot_manifest_hash=manifest.manifest_hash(),
        raw_payload_hash=raw_artifact.artifact_hash,
    )
    response_metadata = {
        "count": parsed.count,
        "pmids_returned": len(parsed.pmids),
        "query_key_present": parsed.query_key is not None,
        "retmax": parsed.retmax,
        "webenv_present": parsed.webenv is not None,
    }
    return PubMedESearchAdapterResult(
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
    stored_response = preserve_pubmed_source_response(
        raw_bytes=response.content,
        artifact_store=artifact_store,
        endpoint=endpoint,
        request_params=params,
        operation=PUBMED_ESEARCH_OPERATION,
        schema_version=PUBMED_ESEARCH_SCHEMA_VERSION,
        http_status=response.status_code,
        content_type=response.headers.get("content-type"),
    )
    if response.is_error:
        raise pubmed_http_status_error(
            operation=PUBMED_ESEARCH_OPERATION,
            response=response,
            stored_response=stored_response,
        )
    return _parse_stored_esearch_response(
        raw_bytes=response.content,
        stored_response=stored_response,
    )


def _parse_json_bytes(raw_bytes: bytes) -> dict[str, Any]:
    payload = json.loads(raw_bytes.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("PubMed ESearch response must be a JSON object")
    return payload
