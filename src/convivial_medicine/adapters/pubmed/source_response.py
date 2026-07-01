from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from convivial_medicine.adapters.pubmed.errors import PubMedHTTPStatusError
from convivial_medicine.adapters.pubmed.request_fingerprint import (
    redacted_request_params,
    request_fingerprint,
)
from convivial_medicine.domain.manifests import SourceSnapshotManifest
from convivial_medicine.storage.artifacts import LocalArtifactStore, StoredArtifact

PUBMED_SOURCE_NAME = "pubmed"


@dataclass(frozen=True)
class PubMedStoredSourceResponse:
    raw_artifact: StoredArtifact
    source_snapshot_manifest: SourceSnapshotManifest
    endpoint: str
    request_fingerprint: str
    request_metadata: dict[str, Any]
    http_status: int
    content_type: str
    retrieved_at: datetime


def preserve_pubmed_source_response(
    *,
    raw_bytes: bytes,
    artifact_store: LocalArtifactStore,
    endpoint: str,
    request_params: dict[str, str],
    operation: str,
    schema_version: str,
    http_status: int,
    content_type: str | None,
    retrieved_at: datetime | None = None,
) -> PubMedStoredSourceResponse:
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
    manifest = SourceSnapshotManifest(
        manifest_version="1",
        schema_version=schema_version,
        payload_hash=raw_artifact.artifact_hash,
        metadata={
            "source_name": PUBMED_SOURCE_NAME,
            "operation": operation,
            "endpoint": endpoint,
            "request_method": "GET",
            "request_params": redacted_request_params(request_params),
            "request_fingerprint": resolved_request_fingerprint,
            "http_status": http_status,
            "content_type": resolved_content_type,
        },
    )
    return PubMedStoredSourceResponse(
        raw_artifact=raw_artifact,
        source_snapshot_manifest=manifest,
        endpoint=endpoint,
        request_fingerprint=resolved_request_fingerprint,
        request_metadata=request_metadata,
        http_status=http_status,
        content_type=resolved_content_type,
        retrieved_at=resolved_retrieved_at,
    )


def pubmed_http_status_error(
    *,
    operation: str,
    response: httpx.Response,
    stored_response: PubMedStoredSourceResponse,
) -> PubMedHTTPStatusError:
    return PubMedHTTPStatusError(
        operation=operation,
        endpoint=stored_response.endpoint,
        http_status=response.status_code,
        content_type=stored_response.content_type,
        raw_payload_hash=stored_response.raw_artifact.artifact_hash,
        raw_artifact_uri=stored_response.raw_artifact.uri,
        source_snapshot_manifest_hash=stored_response.source_snapshot_manifest.manifest_hash(),
        request_fingerprint=stored_response.request_fingerprint,
        request_metadata=stored_response.request_metadata,
        original_http_message=response.reason_phrase,
    )
