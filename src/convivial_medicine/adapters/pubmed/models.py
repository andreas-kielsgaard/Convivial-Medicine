from __future__ import annotations

import re
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


class PubMedArticleId(BaseModel):
    idtype: str
    value: str


class PubMedSummaryEntry(BaseModel):
    pmid: str
    title: str | None
    source: str | None
    pubdate: str | None
    pub_year: int | None
    article_ids: tuple[PubMedArticleId, ...] = Field(default_factory=tuple)
    doi: str | None = None


class PubMedESummaryResult(BaseModel):
    requested_pmids: tuple[str, ...]
    returned_pmids: tuple[str, ...]
    summaries_returned: int
    summaries: tuple[PubMedSummaryEntry, ...]
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
    ) -> PubMedESummaryResult:
        result_payload = payload.get("result")
        if not isinstance(result_payload, dict):
            raise ValueError("PubMed ESummary response must contain a result object")

        uids = result_payload.get("uids", [])
        if not isinstance(uids, list) or not all(isinstance(uid, str) for uid in uids):
            raise ValueError("PubMed ESummary result.uids must be a list of PMID strings")

        summaries = tuple(
            _summary_entry_from_payload(uid, result_payload[uid])
            for uid in uids
            if isinstance(result_payload.get(uid), dict)
        )
        return cls(
            requested_pmids=requested_pmids,
            returned_pmids=tuple(uids),
            summaries_returned=len(summaries),
            summaries=summaries,
            source_snapshot_manifest_hash=source_snapshot_manifest_hash,
            raw_payload_hash=raw_payload_hash,
        )


def _summary_entry_from_payload(uid: str, payload: dict[str, Any]) -> PubMedSummaryEntry:
    article_ids = tuple(_article_ids_from_payload(payload.get("articleids", [])))
    return PubMedSummaryEntry(
        pmid=str(payload.get("uid") or uid),
        title=_optional_string(payload.get("title")),
        source=_optional_string(payload.get("source") or payload.get("fulljournalname")),
        pubdate=_optional_string(payload.get("pubdate") or payload.get("epubdate")),
        pub_year=_publication_year(payload),
        article_ids=article_ids,
        doi=_doi_from_article_ids(article_ids),
    )


def _article_ids_from_payload(payload: object) -> tuple[PubMedArticleId, ...]:
    if not isinstance(payload, list):
        return ()
    article_ids: list[PubMedArticleId] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        idtype = item.get("idtype")
        value = item.get("value")
        if isinstance(idtype, str) and isinstance(value, str):
            article_ids.append(PubMedArticleId(idtype=idtype, value=value))
    return tuple(article_ids)


def _doi_from_article_ids(article_ids: tuple[PubMedArticleId, ...]) -> str | None:
    for article_id in article_ids:
        if article_id.idtype.lower() == "doi":
            return article_id.value
    return None


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _publication_year(payload: dict[str, Any]) -> int | None:
    for key in ("pubdate", "epubdate", "sortpubdate"):
        value = payload.get(key)
        if not isinstance(value, str):
            continue
        match = re.search(r"\b(18|19|20)\d{2}\b", value)
        if match:
            return int(match.group(0))
    return None
