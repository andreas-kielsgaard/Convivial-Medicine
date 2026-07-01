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
