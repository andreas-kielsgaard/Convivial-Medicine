from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from convivial_medicine.adapters.openalex.work import OpenAlexWorkAdapterResult
from convivial_medicine.adapters.pmc.bioc import PmcBioCAdapterResult
from convivial_medicine.adapters.pmc.models import PmcIdConverterRecord
from convivial_medicine.adapters.pubmed.models import PubMedSummaryEntry
from convivial_medicine.config import Settings
from convivial_medicine.domain.identifiers import normalize_doi
from convivial_medicine.domain.manifests import QueryManifest
from convivial_medicine.orchestration.seed import (
    SeedFixturePaths,
    SeedRunResults,
    persist_seed_build_results,
    run_seed_build,
)
from convivial_medicine.storage import models
from convivial_medicine.storage.artifacts import LocalArtifactStore
from convivial_medicine.storage.constants import IdentifierNamespace, WorkStatus

FIXTURE_WORK_PROJECTION_VERSION = "fixture-normalized-work-v1"


@dataclass(frozen=True)
class FixtureWorkProjectionSummary:
    works: int
    identifiers: int
    source_links: int
    db_persisted: bool


@dataclass(frozen=True)
class FixtureWorkProjectionCounts:
    works: int
    identifiers: int
    source_links: int


@dataclass(frozen=True)
class IdentifierProjection:
    namespace: str
    value: str
    source_snapshot_hash: str
    source_snapshot_manifest_hash: str
    is_primary: bool = False


@dataclass(frozen=True)
class SourceLinkProjection:
    source_name: str
    operation: str
    source_snapshot_hash: str
    source_snapshot_manifest_hash: str
    source_record_id: str | None
    source_projection: dict[str, Any]


@dataclass(frozen=True)
class WorkProjection:
    pmid: str
    title: str | None
    publication_year: int | None
    published_at: date | None
    primary_doi: str | None
    current_manifest_hash: str
    identifiers: tuple[IdentifierProjection, ...]
    source_links: tuple[SourceLinkProjection, ...]


def persist_fixture_normalized_works(
    session: Session,
    *,
    query_manifest: QueryManifest,
    artifact_root: Path,
    fixture_paths: SeedFixturePaths,
) -> FixtureWorkProjectionSummary:
    """Project the validated fixture seed build into the narrow work tables."""
    seed_summary = run_seed_build(
        query_manifest=query_manifest,
        artifact_store=LocalArtifactStore(artifact_root),
        settings=Settings(),
        live=False,
        fixture_paths=fixture_paths,
    )
    persist_seed_build_results(
        session,
        query_manifest=query_manifest,
        results=seed_summary.results,
    )

    work_count = 0
    identifier_count = 0
    source_link_count = 0
    for pmid in seed_summary.results.pubmed_esearch.parsed.pmids:
        projection = _work_projection(
            pmid=pmid,
            manifest_name=query_manifest.name,
            results=seed_summary.results,
        )
        work = _get_or_create_work_by_pmid(session, pmid)
        _apply_work_projection(work, projection, manifest_name=query_manifest.name)
        session.flush()

        for identifier in projection.identifiers:
            _upsert_work_identifier(session, work=work, identifier=identifier)
            identifier_count += 1

        for source_link in projection.source_links:
            _upsert_work_source(session, work=work, source_link=source_link)
            source_link_count += 1

        work_count += 1

    session.flush()
    return FixtureWorkProjectionSummary(
        works=work_count,
        identifiers=identifier_count,
        source_links=source_link_count,
        db_persisted=True,
    )


def expected_fixture_work_projection_counts(
    *,
    query_manifest: QueryManifest,
    fixture_paths: SeedFixturePaths,
) -> FixtureWorkProjectionCounts:
    """Compute fixture projection counts without touching the database."""
    with TemporaryDirectory() as temp_root:
        seed_summary = run_seed_build(
            query_manifest=query_manifest,
            artifact_store=LocalArtifactStore(Path(temp_root) / "expected-work-projection"),
            settings=Settings(),
            live=False,
            fixture_paths=fixture_paths,
        )

    work_count = 0
    identifier_count = 0
    source_link_count = 0
    for pmid in seed_summary.results.pubmed_esearch.parsed.pmids:
        projection = _work_projection(
            pmid=pmid,
            manifest_name=query_manifest.name,
            results=seed_summary.results,
        )
        work_count += 1
        identifier_count += len(projection.identifiers)
        source_link_count += len(projection.source_links)

    return FixtureWorkProjectionCounts(
        works=work_count,
        identifiers=identifier_count,
        source_links=source_link_count,
    )


def _work_projection(
    *,
    pmid: str,
    manifest_name: str,
    results: SeedRunResults,
) -> WorkProjection:
    summary = _summary_by_pmid(results).get(pmid)
    idconv_record = results.pmc_idconv.parsed.records_by_requested_pmid.get(pmid)
    openalex_result = _openalex_result_for_pmid(results, pmid)
    pmcid = idconv_record.pmcid if idconv_record is not None else None
    bioc_result = _bioc_result_for_pmcid(results, pmcid)
    primary_doi = _primary_doi(
        summary=summary,
        idconv_record=idconv_record,
        openalex_result=openalex_result,
    )
    doi_source_name = _primary_doi_source_name(
        summary=summary,
        idconv_record=idconv_record,
        openalex_result=openalex_result,
    )
    source_links = _source_links_for_work(
        pmid=pmid,
        manifest_name=manifest_name,
        results=results,
        summary=summary,
        idconv_record=idconv_record,
        bioc_result=bioc_result,
        openalex_result=openalex_result,
    )
    identifiers = _identifiers_for_work(
        pmid=pmid,
        primary_doi=primary_doi,
        pmcid=pmcid,
        openalex_result=openalex_result,
        results=results,
        doi_source_name=doi_source_name,
    )
    return WorkProjection(
        pmid=pmid,
        title=_title(summary=summary, openalex_result=openalex_result),
        publication_year=_publication_year(summary=summary, openalex_result=openalex_result),
        published_at=_published_at(openalex_result),
        primary_doi=primary_doi,
        current_manifest_hash=results.pubmed_esummary.source_snapshot_manifest.manifest_hash(),
        identifiers=identifiers,
        source_links=source_links,
    )


def _summary_by_pmid(results: SeedRunResults) -> dict[str, PubMedSummaryEntry]:
    return {summary.pmid: summary for summary in results.pubmed_esummary.parsed.summaries}


def _openalex_result_for_pmid(
    results: SeedRunResults,
    pmid: str,
) -> OpenAlexWorkAdapterResult | None:
    parsed = results.openalex_work.parsed
    if parsed.pmid == pmid or (
        parsed.requested_id_type == IdentifierNamespace.PMID.value and parsed.requested_id == pmid
    ):
        return results.openalex_work
    return None


def _bioc_result_for_pmcid(
    results: SeedRunResults,
    pmcid: str | None,
) -> PmcBioCAdapterResult | None:
    if pmcid is None:
        return None
    for result in results.pmc_bioc:
        if result.parsed.requested_id == pmcid:
            return result
    return None


def _primary_doi(
    *,
    summary: PubMedSummaryEntry | None,
    idconv_record: PmcIdConverterRecord | None,
    openalex_result: OpenAlexWorkAdapterResult | None,
) -> str | None:
    for value in (
        summary.doi if summary is not None else None,
        idconv_record.doi if idconv_record is not None else None,
        openalex_result.parsed.doi if openalex_result is not None else None,
    ):
        normalized = normalize_doi(value)
        if normalized is not None:
            return normalized
    return None


def _primary_doi_source_name(
    *,
    summary: PubMedSummaryEntry | None,
    idconv_record: PmcIdConverterRecord | None,
    openalex_result: OpenAlexWorkAdapterResult | None,
) -> str | None:
    doi_sources = (
        ("pubmed_esummary", summary.doi if summary is not None else None),
        ("pmc_idconv", idconv_record.doi if idconv_record is not None else None),
        ("openalex_work", openalex_result.parsed.doi if openalex_result is not None else None),
    )
    for source_name, value in doi_sources:
        if normalize_doi(value) is not None:
            return source_name
    return None


def _title(
    *,
    summary: PubMedSummaryEntry | None,
    openalex_result: OpenAlexWorkAdapterResult | None,
) -> str | None:
    if summary is not None and summary.title is not None:
        return summary.title
    if openalex_result is not None:
        return openalex_result.parsed.title
    return None


def _publication_year(
    *,
    summary: PubMedSummaryEntry | None,
    openalex_result: OpenAlexWorkAdapterResult | None,
) -> int | None:
    if summary is not None and summary.pub_year is not None:
        return summary.pub_year
    if openalex_result is not None:
        return openalex_result.parsed.publication_year
    return None


def _published_at(openalex_result: OpenAlexWorkAdapterResult | None) -> date | None:
    if openalex_result is None or openalex_result.parsed.publication_date is None:
        return None
    try:
        return date.fromisoformat(openalex_result.parsed.publication_date)
    except ValueError:
        return None


def _identifiers_for_work(
    *,
    pmid: str,
    primary_doi: str | None,
    pmcid: str | None,
    openalex_result: OpenAlexWorkAdapterResult | None,
    results: SeedRunResults,
    doi_source_name: str | None,
) -> tuple[IdentifierProjection, ...]:
    identifiers = [
        IdentifierProjection(
            namespace=IdentifierNamespace.PMID.value,
            value=pmid,
            source_snapshot_hash=results.pubmed_esearch.raw_artifact.artifact_hash,
            source_snapshot_manifest_hash=(
                results.pubmed_esearch.source_snapshot_manifest.manifest_hash()
            ),
            is_primary=True,
        )
    ]
    if primary_doi is not None:
        doi_hash, doi_manifest_hash = _doi_source_hashes(
            results=results,
            doi_source_name=doi_source_name,
        )
        identifiers.append(
            IdentifierProjection(
                namespace=IdentifierNamespace.DOI.value,
                value=primary_doi,
                source_snapshot_hash=doi_hash,
                source_snapshot_manifest_hash=doi_manifest_hash,
            )
        )
    if pmcid is not None:
        identifiers.append(
            IdentifierProjection(
                namespace=IdentifierNamespace.PMCID.value,
                value=pmcid,
                source_snapshot_hash=results.pmc_idconv.raw_artifact.artifact_hash,
                source_snapshot_manifest_hash=results.pmc_idconv.source_snapshot_manifest.manifest_hash(),
            )
        )
    if openalex_result is not None and openalex_result.parsed.openalex_id is not None:
        identifiers.append(
            IdentifierProjection(
                namespace=IdentifierNamespace.OPENALEX.value,
                value=openalex_result.parsed.openalex_id,
                source_snapshot_hash=openalex_result.raw_artifact.artifact_hash,
                source_snapshot_manifest_hash=openalex_result.source_snapshot_manifest.manifest_hash(),
            )
        )
    return tuple(identifiers)


def _doi_source_hashes(
    *,
    results: SeedRunResults,
    doi_source_name: str | None,
) -> tuple[str, str]:
    if doi_source_name == "pubmed_esummary":
        return (
            results.pubmed_esummary.raw_artifact.artifact_hash,
            results.pubmed_esummary.source_snapshot_manifest.manifest_hash(),
        )
    if doi_source_name == "pmc_idconv":
        return (
            results.pmc_idconv.raw_artifact.artifact_hash,
            results.pmc_idconv.source_snapshot_manifest.manifest_hash(),
        )
    return (
        results.openalex_work.raw_artifact.artifact_hash,
        results.openalex_work.source_snapshot_manifest.manifest_hash(),
    )


def _source_links_for_work(
    *,
    pmid: str,
    manifest_name: str,
    results: SeedRunResults,
    summary: PubMedSummaryEntry | None,
    idconv_record: PmcIdConverterRecord | None,
    bioc_result: PmcBioCAdapterResult | None,
    openalex_result: OpenAlexWorkAdapterResult | None,
) -> tuple[SourceLinkProjection, ...]:
    links = [
        _source_link(
            source_name="pubmed",
            operation="esearch",
            source_snapshot_hash=results.pubmed_esearch.raw_artifact.artifact_hash,
            source_snapshot_manifest_hash=(
                results.pubmed_esearch.source_snapshot_manifest.manifest_hash()
            ),
            source_record_id=pmid,
            payload={
                "manifest_name": manifest_name,
                "membership": True,
                "pmid": pmid,
                "pmids_returned": len(results.pubmed_esearch.parsed.pmids),
            },
        )
    ]
    if summary is not None:
        links.append(
            _source_link(
                source_name="pubmed",
                operation="esummary",
                source_snapshot_hash=results.pubmed_esummary.raw_artifact.artifact_hash,
                source_snapshot_manifest_hash=(
                    results.pubmed_esummary.source_snapshot_manifest.manifest_hash()
                ),
                source_record_id=pmid,
                payload={
                    "doi": normalize_doi(summary.doi),
                    "pmid": pmid,
                    "pub_year": summary.pub_year,
                    "pubdate": summary.pubdate,
                    "source": summary.source,
                    "title": summary.title,
                },
            )
        )
    if pmid in results.pubmed_efetch.parsed.returned_pmids:
        links.append(
            _source_link(
                source_name="pubmed",
                operation="efetch",
                source_snapshot_hash=results.pubmed_efetch.raw_artifact.artifact_hash,
                source_snapshot_manifest_hash=(
                    results.pubmed_efetch.source_snapshot_manifest.manifest_hash()
                ),
                source_record_id=pmid,
                payload={"pmid": pmid, "record_returned": True},
            )
        )
    links.append(
        _source_link(
            source_name="pmc",
            operation="idconv",
            source_snapshot_hash=results.pmc_idconv.raw_artifact.artifact_hash,
            source_snapshot_manifest_hash=results.pmc_idconv.source_snapshot_manifest.manifest_hash(),
            source_record_id=pmid,
            payload=_idconv_projection(pmid=pmid, record=idconv_record),
        )
    )
    if bioc_result is not None:
        bioc_parsed = bioc_result.parsed
        links.append(
            _source_link(
                source_name="pmc",
                operation="bioc",
                source_snapshot_hash=bioc_result.raw_artifact.artifact_hash,
                source_snapshot_manifest_hash=bioc_result.source_snapshot_manifest.manifest_hash(),
                source_record_id=bioc_parsed.requested_id,
                payload={
                    "document_count": bioc_parsed.document_count,
                    "document_ids": list(bioc_parsed.document_ids),
                    "passage_count": bioc_parsed.passage_count,
                    "pmcid": bioc_parsed.requested_id,
                    "section_labels": list(bioc_parsed.section_labels),
                },
            )
        )
    if openalex_result is not None:
        openalex_parsed = openalex_result.parsed
        links.append(
            _source_link(
                source_name="openalex",
                operation="work",
                source_snapshot_hash=openalex_result.raw_artifact.artifact_hash,
                source_snapshot_manifest_hash=openalex_result.source_snapshot_manifest.manifest_hash(),
                source_record_id=openalex_parsed.openalex_id,
                payload={
                    "cited_by_count": openalex_parsed.cited_by_count,
                    "doi": normalize_doi(openalex_parsed.doi),
                    "is_retracted": openalex_parsed.is_retracted,
                    "openalex_id": openalex_parsed.openalex_id,
                    "pmid": pmid,
                    "publication_year": openalex_parsed.publication_year,
                    "title": openalex_parsed.title,
                    "type": openalex_parsed.type,
                },
            )
        )
    return tuple(links)


def _source_link(
    *,
    source_name: str,
    operation: str,
    source_snapshot_hash: str,
    source_snapshot_manifest_hash: str,
    source_record_id: str | None,
    payload: dict[str, Any],
) -> SourceLinkProjection:
    return SourceLinkProjection(
        source_name=source_name,
        operation=operation,
        source_snapshot_hash=source_snapshot_hash,
        source_snapshot_manifest_hash=source_snapshot_manifest_hash,
        source_record_id=source_record_id,
        source_projection={
            "operation": operation,
            "projection_version": FIXTURE_WORK_PROJECTION_VERSION,
            "source_snapshot_manifest_hash": source_snapshot_manifest_hash,
            **payload,
        },
    )


def _idconv_projection(
    *,
    pmid: str,
    record: PmcIdConverterRecord | None,
) -> dict[str, Any]:
    if record is None:
        return {"missing": True, "pmid": pmid}
    return {
        "doi": normalize_doi(record.doi),
        "error_message": record.error_message,
        "live": record.live,
        "missing": False,
        "pmcid": record.pmcid,
        "pmid": record.pmid or pmid,
        "release_date": record.release_date,
    }


def _get_or_create_work_by_pmid(session: Session, pmid: str) -> models.Work:
    existing_identifier = session.scalars(
        select(models.WorkIdentifier)
        .where(
            models.WorkIdentifier.id_namespace == IdentifierNamespace.PMID.value,
            models.WorkIdentifier.id_value == pmid,
        )
        .order_by(models.WorkIdentifier.created_at)
    ).first()
    if existing_identifier is not None:
        existing_work = session.get(models.Work, existing_identifier.work_id)
        if existing_work is not None:
            return existing_work

    work = models.Work(
        status=WorkStatus.CANDIDATE.value,
        normalized_payload={},
    )
    session.add(work)
    return work


def _apply_work_projection(
    work: models.Work,
    projection: WorkProjection,
    *,
    manifest_name: str,
) -> None:
    work.current_manifest_hash = projection.current_manifest_hash
    work.title = projection.title
    work.publication_year = projection.publication_year
    work.published_at = projection.published_at
    work.primary_doi = projection.primary_doi
    work.normalized_payload = {
        "identifiers": [
            {
                "namespace": identifier.namespace,
                "source_snapshot_manifest_hash": identifier.source_snapshot_manifest_hash,
                "value": identifier.value,
            }
            for identifier in projection.identifiers
        ],
        "manifest_name": manifest_name,
        "pmid": projection.pmid,
        "projection_version": FIXTURE_WORK_PROJECTION_VERSION,
        "source_lineage": [
            {
                "operation": source_link.operation,
                "source_name": source_link.source_name,
                "source_record_id": source_link.source_record_id,
                "source_snapshot_manifest_hash": source_link.source_snapshot_manifest_hash,
            }
            for source_link in projection.source_links
        ],
        "source_snapshot_manifest_hashes": list(
            dict.fromkeys(
                source_link.source_snapshot_manifest_hash for source_link in projection.source_links
            )
        ),
    }


def _upsert_work_identifier(
    session: Session,
    *,
    work: models.Work,
    identifier: IdentifierProjection,
) -> None:
    existing = session.scalars(
        select(models.WorkIdentifier).where(
            models.WorkIdentifier.work_id == work.work_id,
            models.WorkIdentifier.id_namespace == identifier.namespace,
            models.WorkIdentifier.id_value == identifier.value,
        )
    ).first()
    if existing is None:
        session.add(
            models.WorkIdentifier(
                work_id=work.work_id,
                id_namespace=identifier.namespace,
                id_value=identifier.value,
                source_snapshot_hash=identifier.source_snapshot_hash,
                is_primary=identifier.is_primary,
            )
        )
        return

    existing.source_snapshot_hash = identifier.source_snapshot_hash
    existing.is_primary = identifier.is_primary


def _upsert_work_source(
    session: Session,
    *,
    work: models.Work,
    source_link: SourceLinkProjection,
) -> None:
    existing = session.scalars(
        select(models.WorkSource).where(
            models.WorkSource.work_id == work.work_id,
            models.WorkSource.source_name == source_link.source_name,
            models.WorkSource.source_snapshot_hash == source_link.source_snapshot_hash,
            models.WorkSource.source_record_id == source_link.source_record_id,
        )
    ).first()
    if existing is None:
        session.add(
            models.WorkSource(
                work_id=work.work_id,
                source_name=source_link.source_name,
                source_snapshot_hash=source_link.source_snapshot_hash,
                source_record_id=source_link.source_record_id,
                source_projection=source_link.source_projection,
            )
        )
        return

    existing.source_projection = source_link.source_projection
