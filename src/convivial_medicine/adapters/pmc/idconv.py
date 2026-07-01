from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from convivial_medicine.adapters.pmc.models import (
    PmcIdConverterResult,
    validate_idconv_provider_payload,
)
from convivial_medicine.adapters.pmc.source_response import (
    PmcStoredSourceResponse,
    pmc_http_status_error,
    preserve_pmc_source_response,
)
from convivial_medicine.config import Settings, get_settings
from convivial_medicine.domain.manifests import SourceSnapshotManifest
from convivial_medicine.storage.artifacts import LocalArtifactStore, StoredArtifact

PMC_IDCONV_ENDPOINT = "https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/"
PMC_IDCONV_OPERATION = "idconv"
PMC_IDCONV_SCHEMA_VERSION = "pmc-idconv-v1"
PMC_IDCONV_MAX_IDS = 200
DEFAULT_NCBI_TOOL = "convivial-medicine"
DEFAULT_TIMEOUT_SECONDS = 20.0


@dataclass(frozen=True)
class PmcIdConverterAdapterResult:
    raw_artifact: StoredArtifact
    source_snapshot_manifest: SourceSnapshotManifest
    parsed: PmcIdConverterResult
    endpoint: str
    request_fingerprint: str
    request_metadata: dict[str, Any]
    http_status: int
    content_type: str
    provider_payload: dict[str, Any]
    response_metadata: dict[str, Any]
    retrieved_at: datetime


def normalize_pmids(pmids: tuple[str, ...]) -> tuple[str, ...]:
    normalized_pmids = tuple(pmid.strip() for pmid in pmids if pmid.strip())
    if not normalized_pmids:
        raise ValueError("At least one PMID is required for PMC ID Converter")
    if len(normalized_pmids) > PMC_IDCONV_MAX_IDS:
        raise ValueError(
            f"PMC ID Converter requests support at most {PMC_IDCONV_MAX_IDS} IDs per call"
        )
    return normalized_pmids


def build_idconv_params(
    pmids: tuple[str, ...],
    *,
    settings: Settings | None = None,
) -> dict[str, str]:
    normalized_pmids = normalize_pmids(pmids)
    params = {
        "ids": ",".join(normalized_pmids),
        "idtype": "pmid",
        "format": "json",
        "tool": (settings.ncbi_tool if settings and settings.ncbi_tool else DEFAULT_NCBI_TOOL),
    }
    if settings is not None and settings.ncbi_email:
        params["email"] = settings.ncbi_email
    return params


def process_idconv_response_bytes(
    *,
    raw_bytes: bytes,
    artifact_store: LocalArtifactStore,
    endpoint: str,
    request_params: dict[str, str],
    requested_pmids: tuple[str, ...],
    http_status: int,
    content_type: str | None,
    retrieved_at: datetime | None = None,
) -> PmcIdConverterAdapterResult:
    normalized_pmids = normalize_pmids(requested_pmids)
    stored_response = preserve_pmc_source_response(
        raw_bytes=raw_bytes,
        artifact_store=artifact_store,
        endpoint=endpoint,
        request_params=request_params,
        operation=PMC_IDCONV_OPERATION,
        schema_version=PMC_IDCONV_SCHEMA_VERSION,
        http_status=http_status,
        content_type=content_type,
        retrieved_at=retrieved_at,
    )
    return _parse_stored_idconv_response(
        raw_bytes=raw_bytes,
        requested_pmids=normalized_pmids,
        stored_response=stored_response,
    )


def _parse_stored_idconv_response(
    *,
    raw_bytes: bytes,
    requested_pmids: tuple[str, ...],
    stored_response: PmcStoredSourceResponse,
) -> PmcIdConverterAdapterResult:
    manifest = stored_response.source_snapshot_manifest
    raw_artifact = stored_response.raw_artifact
    provider_payload = _parse_json_bytes(raw_bytes)
    validate_idconv_provider_payload(provider_payload)
    parsed = PmcIdConverterResult.from_provider_payload(
        provider_payload,
        requested_pmids=requested_pmids,
        source_snapshot_manifest_hash=manifest.manifest_hash(),
        raw_payload_hash=raw_artifact.artifact_hash,
    )
    response_metadata = {
        "pmids_requested": len(parsed.requested_pmids),
        "records_returned": parsed.records_returned,
        "pmcids_returned": parsed.pmcids_returned,
        "missing_pmids": list(parsed.missing_pmids),
    }
    return PmcIdConverterAdapterResult(
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


def run_idconv(
    *,
    pmids: tuple[str, ...],
    artifact_store: LocalArtifactStore,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
    transport: httpx.BaseTransport | None = None,
    endpoint: str = PMC_IDCONV_ENDPOINT,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> PmcIdConverterAdapterResult:
    resolved_settings = settings or get_settings()
    if not resolved_settings.ncbi_email:
        raise ValueError("NCBI_EMAIL is required for PMC ID Converter calls")
    normalized_pmids = normalize_pmids(pmids)
    params = build_idconv_params(normalized_pmids, settings=resolved_settings)
    if client is not None:
        response = client.get(endpoint, params=params, timeout=timeout)
    else:
        with httpx.Client(transport=transport, timeout=timeout) as owned_client:
            response = owned_client.get(endpoint, params=params)

    stored_response = preserve_pmc_source_response(
        raw_bytes=response.content,
        artifact_store=artifact_store,
        endpoint=endpoint,
        request_params=params,
        operation=PMC_IDCONV_OPERATION,
        schema_version=PMC_IDCONV_SCHEMA_VERSION,
        http_status=response.status_code,
        content_type=response.headers.get("content-type"),
    )
    if not 200 <= response.status_code < 300:
        raise pmc_http_status_error(
            operation=PMC_IDCONV_OPERATION,
            response=response,
            stored_response=stored_response,
        )
    return _parse_stored_idconv_response(
        raw_bytes=response.content,
        requested_pmids=normalized_pmids,
        stored_response=stored_response,
    )


def _parse_json_bytes(raw_bytes: bytes) -> dict[str, Any]:
    payload = json.loads(raw_bytes.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("PMC ID Converter response must be a JSON object")
    return payload
