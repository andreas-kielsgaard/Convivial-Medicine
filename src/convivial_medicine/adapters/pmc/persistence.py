from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from convivial_medicine.adapters.pmc.idconv import (
    PMC_IDCONV_OPERATION,
    PmcIdConverterAdapterResult,
)
from convivial_medicine.adapters.pmc.source_response import PMC_SOURCE_NAME
from convivial_medicine.storage.repositories import (
    persist_snapshot_manifest,
    persist_source_snapshot,
)


def source_snapshot_db_values_from_pmc_idconv(
    result: PmcIdConverterAdapterResult,
) -> dict[str, Any]:
    return {
        "snapshot_hash": result.raw_artifact.artifact_hash,
        "source_name": PMC_SOURCE_NAME,
        "operation": PMC_IDCONV_OPERATION,
        "source_record_id": None,
        "request_fingerprint": result.request_fingerprint,
        "request_metadata": result.request_metadata,
        "http_status": result.http_status,
        "content_type": result.content_type,
        "provider_payload": result.provider_payload,
        "response_metadata": result.response_metadata,
        "retrieved_at": result.retrieved_at,
        "raw_artifact_uri": result.raw_artifact.uri,
    }


def persist_pmc_idconv_result(
    session: Session,
    *,
    result: PmcIdConverterAdapterResult,
) -> None:
    persist_source_snapshot(session, source_snapshot_db_values_from_pmc_idconv(result))
    persist_snapshot_manifest(session, result.source_snapshot_manifest)
