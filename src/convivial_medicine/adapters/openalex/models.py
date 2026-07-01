from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OpenAlexOpenAccessSummary(BaseModel):
    is_oa: bool | None = None
    oa_status: str | None = None
    oa_url: str | None = None
    any_repository_has_fulltext: bool | None = None


class OpenAlexSourceSummary(BaseModel):
    id: str | None = None
    display_name: str | None = None
    issn_l: str | None = None
    type: str | None = None


class OpenAlexPrimaryLocationSummary(BaseModel):
    is_oa: bool | None = None
    landing_page_url: str | None = None
    pdf_url: str | None = None
    license: str | None = None
    version: str | None = None
    source: OpenAlexSourceSummary | None = None


class OpenAlexWorkResult(BaseModel):
    requested_id: str
    requested_id_type: str
    openalex_id: str | None = None
    doi: str | None = None
    pmid: str | None = None
    title: str | None = None
    publication_year: int | None = None
    publication_date: str | None = None
    type: str | None = None
    cited_by_count: int | None = None
    is_retracted: bool | None = None
    open_access: OpenAlexOpenAccessSummary | None = None
    primary_location: OpenAlexPrimaryLocationSummary | None = None
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
    ) -> OpenAlexWorkResult:
        ids = payload.get("ids")
        if not isinstance(ids, dict):
            ids = {}
        return cls(
            requested_id=requested_id,
            requested_id_type=requested_id_type,
            openalex_id=_optional_string(payload.get("id")),
            doi=_optional_string(payload.get("doi")) or _optional_string(ids.get("doi")),
            pmid=_pmid_from_ids(ids),
            title=_optional_string(payload.get("title"))
            or _optional_string(payload.get("display_name")),
            publication_year=_optional_int(payload.get("publication_year")),
            publication_date=_optional_string(payload.get("publication_date")),
            type=_optional_string(payload.get("type")),
            cited_by_count=_optional_int(payload.get("cited_by_count")),
            is_retracted=_optional_bool(payload.get("is_retracted")),
            open_access=_open_access_from_payload(payload.get("open_access")),
            primary_location=_primary_location_from_payload(payload.get("primary_location")),
            source_snapshot_manifest_hash=source_snapshot_manifest_hash,
            raw_payload_hash=raw_payload_hash,
        )


class OpenAlexWorkProviderPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | None = None
    doi: str | None = None
    ids: dict[str, Any] = Field(default_factory=dict)
    title: str | None = None
    display_name: str | None = None
    publication_year: int | None = None
    publication_date: str | None = None
    type: str | None = None
    cited_by_count: int | None = None
    is_retracted: bool | None = None
    open_access: dict[str, Any] | None = None
    primary_location: dict[str, Any] | None = None


def validate_openalex_work_provider_payload(payload: dict[str, Any]) -> None:
    OpenAlexWorkProviderPayload.model_validate(payload)


def _open_access_from_payload(payload: object) -> OpenAlexOpenAccessSummary | None:
    if not isinstance(payload, dict):
        return None
    return OpenAlexOpenAccessSummary(
        is_oa=_optional_bool(payload.get("is_oa")),
        oa_status=_optional_string(payload.get("oa_status")),
        oa_url=_optional_string(payload.get("oa_url")),
        any_repository_has_fulltext=_optional_bool(payload.get("any_repository_has_fulltext")),
    )


def _primary_location_from_payload(payload: object) -> OpenAlexPrimaryLocationSummary | None:
    if not isinstance(payload, dict):
        return None
    source = payload.get("source")
    return OpenAlexPrimaryLocationSummary(
        is_oa=_optional_bool(payload.get("is_oa")),
        landing_page_url=_optional_string(payload.get("landing_page_url")),
        pdf_url=_optional_string(payload.get("pdf_url")),
        license=_optional_string(payload.get("license")),
        version=_optional_string(payload.get("version")),
        source=_source_from_payload(source),
    )


def _source_from_payload(payload: object) -> OpenAlexSourceSummary | None:
    if not isinstance(payload, dict):
        return None
    return OpenAlexSourceSummary(
        id=_optional_string(payload.get("id")),
        display_name=_optional_string(payload.get("display_name")),
        issn_l=_optional_string(payload.get("issn_l")),
        type=_optional_string(payload.get("type")),
    )


def _pmid_from_ids(ids: dict[str, Any]) -> str | None:
    pmid = _optional_string(ids.get("pmid"))
    if pmid is None:
        return None
    return pmid.removeprefix("https://pubmed.ncbi.nlm.nih.gov/").strip("/")


def _optional_string(value: object) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, int):
        return str(value)
    return None


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdecimal():
            return int(stripped)
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
