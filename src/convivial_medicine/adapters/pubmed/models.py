from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PubMedESearchPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    count: int
    retmax: int
    idlist: tuple[str, ...] = Field(default_factory=tuple)
    webenv: str | None = None
    querykey: str | None = None


class PubMedESearchResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    esearchresult: PubMedESearchPayload


class PubMedESearchResult(BaseModel):
    count: int
    pmids: tuple[str, ...]
    webenv: str | None
    query_key: str | None
    retmax: int
    source_snapshot_manifest_hash: str
    raw_payload_hash: str

    @classmethod
    def from_provider_payload(
        cls,
        payload: dict[str, Any],
        *,
        source_snapshot_manifest_hash: str,
        raw_payload_hash: str,
    ) -> PubMedESearchResult:
        response = PubMedESearchResponse.model_validate(payload)
        esearch = response.esearchresult
        return cls(
            count=esearch.count,
            pmids=esearch.idlist,
            webenv=esearch.webenv,
            query_key=esearch.querykey,
            retmax=esearch.retmax,
            source_snapshot_manifest_hash=source_snapshot_manifest_hash,
            raw_payload_hash=raw_payload_hash,
        )
