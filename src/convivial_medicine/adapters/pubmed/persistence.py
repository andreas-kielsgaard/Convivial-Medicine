from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from convivial_medicine.adapters.pubmed.efetch import (
    PUBMED_EFETCH_OPERATION,
    PubMedEFetchAdapterResult,
)
from convivial_medicine.adapters.pubmed.esearch import (
    PUBMED_ESEARCH_OPERATION,
    PUBMED_SOURCE_NAME,
    PubMedESearchAdapterResult,
)
from convivial_medicine.adapters.pubmed.esummary import (
    PUBMED_ESUMMARY_OPERATION,
    PubMedESummaryAdapterResult,
)
from convivial_medicine.domain.manifests import QueryManifest
from convivial_medicine.storage.repositories import (
    persist_query_manifest,
    persist_snapshot_manifest,
    persist_source_snapshot,
)


def source_snapshot_db_values_from_pubmed_result(
    *,
    result: Any,
    operation: str,
) -> dict[str, Any]:
    return {
        "snapshot_hash": result.raw_artifact.artifact_hash,
        "source_name": PUBMED_SOURCE_NAME,
        "operation": operation,
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


def source_snapshot_db_values_from_pubmed_esearch(
    result: PubMedESearchAdapterResult,
) -> dict[str, Any]:
    return source_snapshot_db_values_from_pubmed_result(
        result=result,
        operation=PUBMED_ESEARCH_OPERATION,
    )


def source_snapshot_db_values_from_pubmed_efetch(
    result: PubMedEFetchAdapterResult,
) -> dict[str, Any]:
    return source_snapshot_db_values_from_pubmed_result(
        result=result,
        operation=PUBMED_EFETCH_OPERATION,
    )


def source_snapshot_db_values_from_pubmed_esummary(
    result: PubMedESummaryAdapterResult,
) -> dict[str, Any]:
    return source_snapshot_db_values_from_pubmed_result(
        result=result,
        operation=PUBMED_ESUMMARY_OPERATION,
    )


def persist_pubmed_esearch_result(
    session: Session,
    *,
    query_manifest: QueryManifest,
    result: PubMedESearchAdapterResult,
) -> None:
    persist_query_manifest(session, query_manifest)
    persist_source_snapshot(session, source_snapshot_db_values_from_pubmed_esearch(result))
    persist_snapshot_manifest(session, result.source_snapshot_manifest)


def persist_pubmed_esummary_result(
    session: Session,
    *,
    result: PubMedESummaryAdapterResult,
) -> None:
    persist_source_snapshot(session, source_snapshot_db_values_from_pubmed_esummary(result))
    persist_snapshot_manifest(session, result.source_snapshot_manifest)


def persist_pubmed_efetch_result(
    session: Session,
    *,
    result: PubMedEFetchAdapterResult,
) -> None:
    persist_source_snapshot(session, source_snapshot_db_values_from_pubmed_efetch(result))
    persist_snapshot_manifest(session, result.source_snapshot_manifest)
