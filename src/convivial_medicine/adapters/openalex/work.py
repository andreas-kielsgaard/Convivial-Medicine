from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from urllib.parse import quote

import httpx

from convivial_medicine.adapters.openalex.models import (
    OpenAlexWorkResult,
    validate_openalex_work_provider_payload,
)
from convivial_medicine.adapters.openalex.source_response import (
    OpenAlexStoredSourceResponse,
    openalex_http_status_error,
    preserve_openalex_source_response,
)
from convivial_medicine.config import Settings, get_settings
from convivial_medicine.domain.manifests import SourceSnapshotManifest
from convivial_medicine.storage.artifacts import LocalArtifactStore, StoredArtifact

OpenAlexWorkIdentifierType = Literal["doi", "pmid", "openalex_id"]

OPENALEX_WORKS_ENDPOINT_ROOT = "https://api.openalex.org/works"
OPENALEX_WORK_OPERATION = "work"
OPENALEX_WORK_SCHEMA_VERSION = "openalex-work-v1"
DEFAULT_TIMEOUT_SECONDS = 20.0


@dataclass(frozen=True)
class OpenAlexWorkRequest:
    requested_id: str
    requested_id_type: OpenAlexWorkIdentifierType
    openalex_lookup_id: str
    endpoint: str
    request_params: dict[str, str]


@dataclass(frozen=True)
class OpenAlexWorkAdapterResult:
    raw_artifact: StoredArtifact
    source_snapshot_manifest: SourceSnapshotManifest
    parsed: OpenAlexWorkResult
    endpoint: str
    request_fingerprint: str
    request_metadata: dict[str, Any]
    http_status: int
    content_type: str
    provider_payload: dict[str, Any]
    response_metadata: dict[str, Any]
    retrieved_at: datetime


def build_openalex_work_request(
    identifier: str,
    *,
    id_type: OpenAlexWorkIdentifierType,
    settings: Settings | None = None,
    endpoint_root: str = OPENALEX_WORKS_ENDPOINT_ROOT,
) -> OpenAlexWorkRequest:
    requested_id = normalize_openalex_work_identifier(identifier)
    lookup_id = openalex_lookup_id(requested_id, id_type=id_type)
    endpoint = f"{endpoint_root.rstrip('/')}/{quote(lookup_id, safe=':/')}"
    request_params: dict[str, str] = {}
    if settings is not None and settings.openalex_api_key:
        request_params["api_key"] = settings.openalex_api_key
    return OpenAlexWorkRequest(
        requested_id=requested_id,
        requested_id_type=id_type,
        openalex_lookup_id=lookup_id,
        endpoint=endpoint,
        request_params=request_params,
    )


def normalize_openalex_work_identifier(identifier: str) -> str:
    normalized_identifier = identifier.strip()
    if not normalized_identifier:
        raise ValueError("A DOI, PMID, or OpenAlex work ID is required")
    return normalized_identifier


def openalex_lookup_id(
    identifier: str,
    *,
    id_type: OpenAlexWorkIdentifierType,
) -> str:
    normalized_identifier = normalize_openalex_work_identifier(identifier)
    if id_type == "doi":
        return f"doi:{_strip_prefixes(normalized_identifier, ('doi:', 'https://doi.org/'))}"
    if id_type == "pmid":
        return f"pmid:{_strip_prefixes(normalized_identifier, ('pmid:',))}"
    if id_type == "openalex_id":
        return _strip_prefixes(normalized_identifier, ("https://openalex.org/",))
    raise ValueError("id_type must be doi, pmid, or openalex_id")


def process_openalex_work_response_bytes(
    *,
    raw_bytes: bytes,
    artifact_store: LocalArtifactStore,
    request: OpenAlexWorkRequest,
    http_status: int,
    content_type: str | None,
    retrieved_at: datetime | None = None,
) -> OpenAlexWorkAdapterResult:
    stored_response = _preserve_openalex_work_source_response(
        raw_bytes=raw_bytes,
        artifact_store=artifact_store,
        request=request,
        http_status=http_status,
        content_type=content_type,
        retrieved_at=retrieved_at,
    )
    return _parse_stored_openalex_work_response(
        raw_bytes=raw_bytes,
        request=request,
        stored_response=stored_response,
    )


def _preserve_openalex_work_source_response(
    *,
    raw_bytes: bytes,
    artifact_store: LocalArtifactStore,
    request: OpenAlexWorkRequest,
    http_status: int,
    content_type: str | None,
    retrieved_at: datetime | None = None,
) -> OpenAlexStoredSourceResponse:
    return preserve_openalex_source_response(
        raw_bytes=raw_bytes,
        artifact_store=artifact_store,
        endpoint=request.endpoint,
        request_params=request.request_params,
        operation=OPENALEX_WORK_OPERATION,
        schema_version=OPENALEX_WORK_SCHEMA_VERSION,
        http_status=http_status,
        content_type=content_type,
        retrieved_at=retrieved_at,
        extra_metadata={
            "requested_identifier": request.requested_id,
            "requested_identifier_type": request.requested_id_type,
            "openalex_lookup_id": request.openalex_lookup_id,
        },
    )


def _parse_stored_openalex_work_response(
    *,
    raw_bytes: bytes,
    request: OpenAlexWorkRequest,
    stored_response: OpenAlexStoredSourceResponse,
) -> OpenAlexWorkAdapterResult:
    manifest = stored_response.source_snapshot_manifest
    raw_artifact = stored_response.raw_artifact
    provider_payload = _parse_json_bytes(raw_bytes)
    validate_openalex_work_provider_payload(provider_payload)
    parsed = OpenAlexWorkResult.from_provider_payload(
        provider_payload,
        requested_id=request.requested_id,
        requested_id_type=request.requested_id_type,
        source_snapshot_manifest_hash=manifest.manifest_hash(),
        raw_payload_hash=raw_artifact.artifact_hash,
    )
    response_metadata = {
        "requested_id": parsed.requested_id,
        "requested_id_type": parsed.requested_id_type,
        "openalex_id": parsed.openalex_id,
        "doi": parsed.doi,
        "pmid": parsed.pmid,
        "publication_year": parsed.publication_year,
        "type": parsed.type,
        "cited_by_count": parsed.cited_by_count,
        "is_retracted": parsed.is_retracted,
    }
    return OpenAlexWorkAdapterResult(
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


def run_openalex_work(
    *,
    identifier: str,
    id_type: OpenAlexWorkIdentifierType,
    artifact_store: LocalArtifactStore,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
    transport: httpx.BaseTransport | None = None,
    endpoint_root: str = OPENALEX_WORKS_ENDPOINT_ROOT,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> OpenAlexWorkAdapterResult:
    resolved_settings = settings or get_settings()
    if not resolved_settings.openalex_api_key:
        raise ValueError("OPENALEX_API_KEY is required for OpenAlex work calls")
    request = build_openalex_work_request(
        identifier,
        id_type=id_type,
        settings=resolved_settings,
        endpoint_root=endpoint_root,
    )
    if client is not None:
        response = client.get(request.endpoint, params=request.request_params, timeout=timeout)
    else:
        with httpx.Client(transport=transport, timeout=timeout) as owned_client:
            response = owned_client.get(request.endpoint, params=request.request_params)

    stored_response = _preserve_openalex_work_source_response(
        raw_bytes=response.content,
        artifact_store=artifact_store,
        request=request,
        http_status=response.status_code,
        content_type=response.headers.get("content-type"),
    )
    if not 200 <= response.status_code < 300:
        raise openalex_http_status_error(
            operation=OPENALEX_WORK_OPERATION,
            response=response,
            stored_response=stored_response,
        )
    return _parse_stored_openalex_work_response(
        raw_bytes=response.content,
        request=request,
        stored_response=stored_response,
    )


def _strip_prefixes(value: str, prefixes: tuple[str, ...]) -> str:
    stripped = value.strip()
    lowered = stripped.lower()
    for prefix in prefixes:
        if lowered.startswith(prefix):
            return stripped[len(prefix) :].strip()
    return stripped


def _parse_json_bytes(raw_bytes: bytes) -> dict[str, Any]:
    payload = json.loads(raw_bytes.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("OpenAlex work response must be a JSON object")
    return payload
