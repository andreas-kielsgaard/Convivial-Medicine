from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from urllib.parse import quote

import httpx

from convivial_medicine.adapters.pmc.models import (
    PmcBioCResult,
    validate_bioc_provider_payload,
)
from convivial_medicine.adapters.pmc.source_response import (
    PmcStoredSourceResponse,
    pmc_http_status_error,
    preserve_pmc_source_response,
)
from convivial_medicine.domain.manifests import SourceSnapshotManifest
from convivial_medicine.storage.artifacts import LocalArtifactStore, StoredArtifact

PmcBioCIdentifierType = Literal["pmid", "pmcid"]

PMC_BIOC_ENDPOINT_ROOT = "https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi"
PMC_BIOC_OPERATION = "bioc"
PMC_BIOC_SCHEMA_VERSION = "pmc-bioc-v1"
PMC_BIOC_FORMAT = "json"
PMC_BIOC_ENCODING = "unicode"
DEFAULT_TIMEOUT_SECONDS = 20.0


@dataclass(frozen=True)
class PmcBioCRequest:
    requested_id: str
    requested_id_type: PmcBioCIdentifierType
    format: str
    encoding: str
    endpoint: str
    request_params: dict[str, str]


@dataclass(frozen=True)
class PmcBioCAdapterResult:
    raw_artifact: StoredArtifact
    source_snapshot_manifest: SourceSnapshotManifest
    parsed: PmcBioCResult
    endpoint: str
    request_fingerprint: str
    request_metadata: dict[str, Any]
    http_status: int
    content_type: str
    provider_payload: dict[str, Any]
    response_metadata: dict[str, Any]
    retrieved_at: datetime


def normalize_bioc_identifier(identifier: str) -> str:
    normalized_identifier = identifier.strip()
    if not normalized_identifier:
        raise ValueError("A PMID or PMCID is required for PMC BioC")
    return normalized_identifier


def infer_bioc_identifier_type(identifier: str) -> PmcBioCIdentifierType:
    normalized_identifier = normalize_bioc_identifier(identifier)
    if normalized_identifier.upper().startswith("PMC"):
        return "pmcid"
    return "pmid"


def normalize_bioc_identifier_type(
    identifier: str,
    id_type: str | None = None,
) -> PmcBioCIdentifierType:
    if id_type is None:
        return infer_bioc_identifier_type(identifier)
    normalized_id_type = id_type.strip().lower()
    if normalized_id_type == "pmid":
        return "pmid"
    if normalized_id_type == "pmcid":
        return "pmcid"
    raise ValueError("--id-type must be either pmid or pmcid")


def build_bioc_request(
    identifier: str,
    *,
    id_type: str | None = None,
    endpoint_root: str = PMC_BIOC_ENDPOINT_ROOT,
    response_format: str = PMC_BIOC_FORMAT,
    encoding: str = PMC_BIOC_ENCODING,
) -> PmcBioCRequest:
    requested_id = normalize_bioc_identifier(identifier)
    requested_id_type = normalize_bioc_identifier_type(requested_id, id_type)
    if response_format != PMC_BIOC_FORMAT:
        raise ValueError("PMC BioC currently supports format=json only")
    if encoding != PMC_BIOC_ENCODING:
        raise ValueError("PMC BioC currently supports encoding=unicode only")
    endpoint = (
        f"{endpoint_root.rstrip('/')}/BioC_{response_format}/"
        f"{quote(requested_id, safe='')}/{encoding}"
    )
    request_params = {
        "requested_id": requested_id,
        "requested_id_type": requested_id_type,
        "format": response_format,
        "encoding": encoding,
    }
    return PmcBioCRequest(
        requested_id=requested_id,
        requested_id_type=requested_id_type,
        format=response_format,
        encoding=encoding,
        endpoint=endpoint,
        request_params=request_params,
    )


def process_bioc_response_bytes(
    *,
    raw_bytes: bytes,
    artifact_store: LocalArtifactStore,
    request: PmcBioCRequest,
    http_status: int,
    content_type: str | None,
    retrieved_at: datetime | None = None,
) -> PmcBioCAdapterResult:
    stored_response = _preserve_bioc_source_response(
        raw_bytes=raw_bytes,
        artifact_store=artifact_store,
        request=request,
        http_status=http_status,
        content_type=content_type,
        retrieved_at=retrieved_at,
    )
    return _parse_stored_bioc_response(
        raw_bytes=raw_bytes, request=request, stored_response=stored_response
    )


def _preserve_bioc_source_response(
    *,
    raw_bytes: bytes,
    artifact_store: LocalArtifactStore,
    request: PmcBioCRequest,
    http_status: int,
    content_type: str | None,
    retrieved_at: datetime | None = None,
) -> PmcStoredSourceResponse:
    return preserve_pmc_source_response(
        raw_bytes=raw_bytes,
        artifact_store=artifact_store,
        endpoint=request.endpoint,
        request_params=request.request_params,
        operation=PMC_BIOC_OPERATION,
        schema_version=PMC_BIOC_SCHEMA_VERSION,
        http_status=http_status,
        content_type=content_type,
        retrieved_at=retrieved_at,
        extra_metadata={
            "requested_identifier": request.requested_id,
            "requested_identifier_type": request.requested_id_type,
            "format": request.format,
            "encoding": request.encoding,
        },
    )


def _parse_stored_bioc_response(
    *,
    raw_bytes: bytes,
    request: PmcBioCRequest,
    stored_response: PmcStoredSourceResponse,
) -> PmcBioCAdapterResult:
    manifest = stored_response.source_snapshot_manifest
    raw_artifact = stored_response.raw_artifact
    provider_payload = _parse_json_bytes(raw_bytes)
    validate_bioc_provider_payload(provider_payload)
    parsed = PmcBioCResult.from_provider_payload(
        provider_payload,
        requested_id=request.requested_id,
        requested_id_type=request.requested_id_type,
        source_snapshot_manifest_hash=manifest.manifest_hash(),
        raw_payload_hash=raw_artifact.artifact_hash,
    )
    response_metadata = {
        "requested_id": parsed.requested_id,
        "requested_id_type": parsed.requested_id_type,
        "document_detected": parsed.document_detected,
        "document_count": parsed.document_count,
        "passage_count": parsed.passage_count,
        "document_ids": list(parsed.document_ids),
        "section_labels": list(parsed.section_labels),
    }
    return PmcBioCAdapterResult(
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


def run_bioc(
    *,
    identifier: str,
    id_type: str | None = None,
    artifact_store: LocalArtifactStore,
    client: httpx.Client | None = None,
    transport: httpx.BaseTransport | None = None,
    endpoint_root: str = PMC_BIOC_ENDPOINT_ROOT,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> PmcBioCAdapterResult:
    request = build_bioc_request(identifier, id_type=id_type, endpoint_root=endpoint_root)
    if client is not None:
        response = client.get(request.endpoint, timeout=timeout)
    else:
        with httpx.Client(transport=transport, timeout=timeout) as owned_client:
            response = owned_client.get(request.endpoint)

    stored_response = _preserve_bioc_source_response(
        raw_bytes=response.content,
        artifact_store=artifact_store,
        request=request,
        http_status=response.status_code,
        content_type=response.headers.get("content-type"),
    )
    if not 200 <= response.status_code < 300:
        raise pmc_http_status_error(
            operation=PMC_BIOC_OPERATION,
            response=response,
            stored_response=stored_response,
        )
    return _parse_stored_bioc_response(
        raw_bytes=response.content,
        request=request,
        stored_response=stored_response,
    )


def _parse_json_bytes(raw_bytes: bytes) -> dict[str, Any]:
    payload = json.loads(raw_bytes.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("PMC BioC response must be a JSON object")
    return payload
