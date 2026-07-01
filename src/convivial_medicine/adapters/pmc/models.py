from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PmcIdConverterRecord(BaseModel):
    requested_id: str
    pmid: str | None = None
    pmcid: str | None = None
    doi: str | None = None
    mid: str | None = None
    live: bool | None = None
    release_date: str | None = None
    error_message: str | None = None


class PmcIdConverterResult(BaseModel):
    requested_pmids: tuple[str, ...]
    records_returned: int
    records: tuple[PmcIdConverterRecord, ...] = Field(default_factory=tuple)
    records_by_requested_pmid: dict[str, PmcIdConverterRecord] = Field(default_factory=dict)
    returned_pmids: tuple[str, ...]
    pmcids_returned: int
    missing_pmids: tuple[str, ...]
    source_snapshot_manifest_hash: str
    raw_payload_hash: str

    @classmethod
    def from_provider_payload(
        cls,
        payload: dict[str, Any],
        *,
        requested_pmids: tuple[str, ...],
        source_snapshot_manifest_hash: str,
        raw_payload_hash: str,
    ) -> PmcIdConverterResult:
        records_payload = payload.get("records", [])
        if not isinstance(records_payload, list):
            raise ValueError("PMC ID Converter response records must be a list")

        records = tuple(
            record
            for item in records_payload
            if isinstance(item, dict)
            for record in (_record_from_payload(item),)
        )
        records_by_requested_pmid = {
            record.requested_id: record for record in records if record.requested_id
        }
        missing_pmids = tuple(
            pmid for pmid in requested_pmids if pmid not in records_by_requested_pmid
        )
        returned_pmids = tuple(
            record.pmid for record in records if record.pmid is not None and record.pmid
        )
        pmcids_returned = sum(1 for record in records if record.pmcid)

        return cls(
            requested_pmids=requested_pmids,
            records_returned=len(records),
            records=records,
            records_by_requested_pmid=records_by_requested_pmid,
            returned_pmids=returned_pmids,
            pmcids_returned=pmcids_returned,
            missing_pmids=missing_pmids,
            source_snapshot_manifest_hash=source_snapshot_manifest_hash,
            raw_payload_hash=raw_payload_hash,
        )


class PmcIdConverterRequestEcho(BaseModel):
    model_config = ConfigDict(extra="allow")

    format: str | None = None
    idtype: str | None = None
    ids: list[str] | None = None


class PmcIdConverterProviderPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str | None = None
    request: PmcIdConverterRequestEcho | None = None
    records: list[dict[str, Any]] = Field(default_factory=list)


def validate_idconv_provider_payload(payload: dict[str, Any]) -> None:
    PmcIdConverterProviderPayload.model_validate(payload)


class PmcBioCDocumentSummary(BaseModel):
    document_id: str | None = None
    passage_count: int
    section_labels: tuple[str, ...] = Field(default_factory=tuple)


class PmcBioCResult(BaseModel):
    requested_id: str
    requested_id_type: str
    collection_source: str | None = None
    document_detected: bool
    document_count: int
    passage_count: int
    document_ids: tuple[str, ...] = Field(default_factory=tuple)
    section_labels: tuple[str, ...] = Field(default_factory=tuple)
    documents: tuple[PmcBioCDocumentSummary, ...] = Field(default_factory=tuple)
    source_snapshot_manifest_hash: str
    raw_payload_hash: str

    @classmethod
    def from_provider_payload(
        cls,
        payload: dict[str, Any],
        *,
        requested_id: str,
        requested_id_type: str,
        source_snapshot_manifest_hash: str,
        raw_payload_hash: str,
    ) -> PmcBioCResult:
        documents_payload = payload.get("documents", [])
        if not isinstance(documents_payload, list):
            raise ValueError("PMC BioC response documents must be a list")

        documents = tuple(
            _bioc_document_summary_from_payload(item)
            for item in documents_payload
            if isinstance(item, dict)
        )
        document_ids = tuple(
            document.document_id for document in documents if document.document_id is not None
        )
        section_labels = tuple(
            sorted({label for document in documents for label in document.section_labels})
        )
        passage_count = sum(document.passage_count for document in documents)

        return cls(
            requested_id=requested_id,
            requested_id_type=requested_id_type,
            collection_source=_optional_string(payload.get("source")),
            document_detected=bool(documents),
            document_count=len(documents),
            passage_count=passage_count,
            document_ids=document_ids,
            section_labels=section_labels,
            documents=documents,
            source_snapshot_manifest_hash=source_snapshot_manifest_hash,
            raw_payload_hash=raw_payload_hash,
        )


class PmcBioCProviderPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str | None = None
    documents: list[dict[str, Any]] = Field(default_factory=list)


def validate_bioc_provider_payload(payload: dict[str, Any]) -> None:
    PmcBioCProviderPayload.model_validate(payload)


def _record_from_payload(payload: dict[str, Any]) -> PmcIdConverterRecord:
    pmid = _optional_string(payload.get("pmid"))
    requested_id = _optional_string(payload.get("requested-id")) or pmid
    if requested_id is None:
        raise ValueError("PMC ID Converter record is missing requested-id and pmid")

    return PmcIdConverterRecord(
        requested_id=requested_id,
        pmid=pmid,
        pmcid=_optional_string(payload.get("pmcid")),
        doi=_optional_string(payload.get("doi")),
        mid=_optional_string(payload.get("mid")),
        live=_optional_bool(payload.get("live")),
        release_date=_optional_string(payload.get("release-date")),
        error_message=_error_message_from_payload(payload),
    )


def _optional_string(value: object) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, int):
        return str(value)
    return None


def _optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1"}:
            return True
        if normalized in {"false", "no", "0"}:
            return False
    return None


def _error_message_from_payload(payload: dict[str, Any]) -> str | None:
    for key in ("error-message", "errormsg", "errmsg", "error", "ErrorMessage"):
        value = _optional_string(payload.get(key))
        if value is not None:
            return value
    return None


def _bioc_document_summary_from_payload(payload: dict[str, Any]) -> PmcBioCDocumentSummary:
    passages_payload = payload.get("passages", [])
    if not isinstance(passages_payload, list):
        passages_payload = []
    section_labels = tuple(
        sorted(
            {
                label
                for item in passages_payload
                if isinstance(item, dict)
                for label in _section_labels_from_bioc_passage(item)
            }
        )
    )
    return PmcBioCDocumentSummary(
        document_id=_optional_string(payload.get("id")),
        passage_count=sum(1 for item in passages_payload if isinstance(item, dict)),
        section_labels=section_labels,
    )


def _section_labels_from_bioc_passage(payload: dict[str, Any]) -> tuple[str, ...]:
    infons = payload.get("infons")
    if not isinstance(infons, dict):
        return ()
    labels: list[str] = []
    for key in ("section_type", "type"):
        value = _optional_string(infons.get(key))
        if value is not None:
            labels.append(value)
    return tuple(labels)
