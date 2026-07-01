from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from convivial_medicine.adapters.openalex.source_response import OPENALEX_SOURCE_NAME
from convivial_medicine.adapters.openalex.work import (
    OPENALEX_WORK_OPERATION,
    OpenAlexWorkAdapterResult,
)
from convivial_medicine.storage.repositories import (
    persist_snapshot_manifest,
    persist_source_snapshot,
)


def source_snapshot_db_values_from_openalex_work(
    result: OpenAlexWorkAdapterResult,
) -> dict[str, Any]:
    return {
        "snapshot_hash": result.raw_artifact.artifact_hash,
        "source_name": OPENALEX_SOURCE_NAME,
        "operation": OPENALEX_WORK_OPERATION,
        "source_record_id": result.parsed.openalex_id,
        "request_fingerprint": result.request_fingerprint,
        "request_metadata": result.request_metadata,
        "http_status": result.http_status,
        "content_type": result.content_type,
        "provider_payload": result.provider_payload,
        "response_metadata": result.response_metadata,
        "retrieved_at": result.retrieved_at,
        "raw_artifact_uri": result.raw_artifact.uri,
    }


def persist_openalex_work_result(
    session: Session,
    *,
    result: OpenAlexWorkAdapterResult,
) -> None:
    persist_source_snapshot(session, source_snapshot_db_values_from_openalex_work(result))
    persist_snapshot_manifest(session, result.source_snapshot_manifest)
