from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy.orm import Session

from convivial_medicine.adapters.openalex.persistence import persist_openalex_work_result
from convivial_medicine.adapters.openalex.work import (
    OpenAlexWorkAdapterResult,
    build_openalex_work_request,
    process_openalex_work_response_bytes,
    run_openalex_work,
)
from convivial_medicine.adapters.pmc.bioc import (
    PmcBioCAdapterResult,
    build_bioc_request,
    process_bioc_response_bytes,
    run_bioc,
)
from convivial_medicine.adapters.pmc.idconv import (
    PMC_IDCONV_ENDPOINT,
    PmcIdConverterAdapterResult,
    build_idconv_params,
    process_idconv_response_bytes,
    run_idconv,
)
from convivial_medicine.adapters.pmc.persistence import (
    persist_pmc_bioc_result,
    persist_pmc_idconv_result,
)
from convivial_medicine.adapters.pubmed.efetch import (
    PUBMED_EFETCH_ENDPOINT,
    PubMedEFetchAdapterResult,
    build_efetch_params,
    process_efetch_response_bytes,
    run_efetch,
)
from convivial_medicine.adapters.pubmed.esearch import (
    PUBMED_ESEARCH_ENDPOINT,
    PubMedESearchAdapterResult,
    build_esearch_params,
    process_esearch_response_bytes,
    run_esearch,
)
from convivial_medicine.adapters.pubmed.esummary import (
    PUBMED_ESUMMARY_ENDPOINT,
    PubMedESummaryAdapterResult,
    build_esummary_params,
    process_esummary_response_bytes,
    run_esummary,
)
from convivial_medicine.adapters.pubmed.persistence import (
    persist_pubmed_efetch_result,
    persist_pubmed_esearch_result,
    persist_pubmed_esummary_result,
)
from convivial_medicine.config import Settings
from convivial_medicine.domain.manifests import QueryManifest
from convivial_medicine.storage.artifacts import LocalArtifactStore

SeedRunMode = Literal["fixture", "live"]


@dataclass(frozen=True)
class SeedFixturePaths:
    pubmed_esearch: Path
    pubmed_esummary: Path
    pubmed_efetch: Path
    pmc_idconv: Path
    pmc_bioc: Path
    openalex_work: Path

    @classmethod
    def from_root(cls, root: Path) -> SeedFixturePaths:
        return cls(
            pubmed_esearch=root / "pubmed" / "esearch_vitamin_d_ms_seed.json",
            pubmed_esummary=root / "pubmed" / "esummary_vitamin_d_ms_seed.json",
            pubmed_efetch=root / "pubmed" / "efetch_vitamin_d_ms_seed.xml",
            pmc_idconv=root / "pmc" / "idconv_vitamin_d_ms_seed.json",
            pmc_bioc=root / "pmc" / "bioc_vitamin_d_ms_seed.json",
            openalex_work=root / "openalex" / "work_vitamin_d_ms_seed.json",
        )


@dataclass(frozen=True)
class SeedRunResults:
    pubmed_esearch: PubMedESearchAdapterResult
    pubmed_esummary: PubMedESummaryAdapterResult
    pubmed_efetch: PubMedEFetchAdapterResult
    pmc_idconv: PmcIdConverterAdapterResult
    pmc_bioc: tuple[PmcBioCAdapterResult, ...]
    openalex_work: OpenAlexWorkAdapterResult


@dataclass(frozen=True)
class SeedRunSummary:
    manifest_name: str
    manifest_hash: str
    mode: SeedRunMode
    results: SeedRunResults
    db_persisted: bool

    @property
    def source_snapshot_count(self) -> int:
        return 5 + len(self.results.pmc_bioc)

    @property
    def raw_artifact_hashes(self) -> tuple[str, ...]:
        hashes = [
            self.results.pubmed_esearch.raw_artifact.artifact_hash,
            self.results.pubmed_esummary.raw_artifact.artifact_hash,
            self.results.pubmed_efetch.raw_artifact.artifact_hash,
            self.results.pmc_idconv.raw_artifact.artifact_hash,
            *(result.raw_artifact.artifact_hash for result in self.results.pmc_bioc),
            self.results.openalex_work.raw_artifact.artifact_hash,
        ]
        return tuple(dict.fromkeys(hashes))


def run_seed_build(
    *,
    query_manifest: QueryManifest,
    artifact_store: LocalArtifactStore,
    settings: Settings,
    live: bool,
    fixture_paths: SeedFixturePaths,
    persist_db_session: Session | None = None,
) -> SeedRunSummary:
    mode: SeedRunMode = "live" if live else "fixture"
    if live:
        _validate_live_settings(settings)
        results = _run_live_seed_build(
            query_manifest=query_manifest,
            artifact_store=artifact_store,
            settings=settings,
        )
    else:
        _validate_fixture_paths(fixture_paths)
        results = _run_fixture_seed_build(
            query_manifest=query_manifest,
            artifact_store=artifact_store,
            fixture_paths=fixture_paths,
        )

    db_persisted = persist_db_session is not None
    if persist_db_session is not None:
        persist_seed_build_results(
            persist_db_session,
            query_manifest=query_manifest,
            results=results,
        )

    return SeedRunSummary(
        manifest_name=query_manifest.name,
        manifest_hash=query_manifest.manifest_hash(),
        mode=mode,
        results=results,
        db_persisted=db_persisted,
    )


def persist_seed_build_results(
    session: Session,
    *,
    query_manifest: QueryManifest,
    results: SeedRunResults,
) -> None:
    persist_pubmed_esearch_result(
        session,
        query_manifest=query_manifest,
        result=results.pubmed_esearch,
    )
    persist_pubmed_esummary_result(session, result=results.pubmed_esummary)
    persist_pubmed_efetch_result(session, result=results.pubmed_efetch)
    persist_pmc_idconv_result(session, result=results.pmc_idconv)
    for bioc_result in results.pmc_bioc:
        persist_pmc_bioc_result(session, result=bioc_result)
    persist_openalex_work_result(session, result=results.openalex_work)


def _run_fixture_seed_build(
    *,
    query_manifest: QueryManifest,
    artifact_store: LocalArtifactStore,
    fixture_paths: SeedFixturePaths,
) -> SeedRunResults:
    esearch_result = process_esearch_response_bytes(
        raw_bytes=fixture_paths.pubmed_esearch.read_bytes(),
        artifact_store=artifact_store,
        endpoint=PUBMED_ESEARCH_ENDPOINT,
        request_params=build_esearch_params(query_manifest),
        http_status=200,
        content_type="application/json",
    )
    pmids = esearch_result.parsed.pmids
    _require_seed_pmids(pmids)

    esummary_result = process_esummary_response_bytes(
        raw_bytes=fixture_paths.pubmed_esummary.read_bytes(),
        artifact_store=artifact_store,
        endpoint=PUBMED_ESUMMARY_ENDPOINT,
        request_params=build_esummary_params(pmids),
        requested_pmids=pmids,
        http_status=200,
        content_type="application/json",
    )
    efetch_result = process_efetch_response_bytes(
        raw_bytes=fixture_paths.pubmed_efetch.read_bytes(),
        artifact_store=artifact_store,
        endpoint=PUBMED_EFETCH_ENDPOINT,
        request_params=build_efetch_params(pmids),
        requested_pmids=pmids,
        http_status=200,
        content_type="application/xml",
    )
    idconv_result = process_idconv_response_bytes(
        raw_bytes=fixture_paths.pmc_idconv.read_bytes(),
        artifact_store=artifact_store,
        endpoint=PMC_IDCONV_ENDPOINT,
        request_params=build_idconv_params(pmids),
        requested_pmids=pmids,
        http_status=200,
        content_type="application/json",
    )
    pmcids = _available_pmcids(idconv_result)
    bioc_results = tuple(
        process_bioc_response_bytes(
            raw_bytes=fixture_paths.pmc_bioc.read_bytes(),
            artifact_store=artifact_store,
            request=build_bioc_request(pmcid),
            http_status=200,
            content_type="application/json",
        )
        for pmcid in pmcids
    )
    openalex_request = build_openalex_work_request(pmids[0], id_type="pmid")
    openalex_result = process_openalex_work_response_bytes(
        raw_bytes=fixture_paths.openalex_work.read_bytes(),
        artifact_store=artifact_store,
        request=openalex_request,
        http_status=200,
        content_type="application/json",
    )
    return SeedRunResults(
        pubmed_esearch=esearch_result,
        pubmed_esummary=esummary_result,
        pubmed_efetch=efetch_result,
        pmc_idconv=idconv_result,
        pmc_bioc=bioc_results,
        openalex_work=openalex_result,
    )


def _run_live_seed_build(
    *,
    query_manifest: QueryManifest,
    artifact_store: LocalArtifactStore,
    settings: Settings,
) -> SeedRunResults:
    esearch_result = run_esearch(
        manifest=query_manifest,
        artifact_store=artifact_store,
        settings=settings,
    )
    pmids = esearch_result.parsed.pmids
    _require_seed_pmids(pmids)

    esummary_result = run_esummary(
        pmids=pmids,
        artifact_store=artifact_store,
        settings=settings,
    )
    efetch_result = run_efetch(
        pmids=pmids,
        artifact_store=artifact_store,
        settings=settings,
    )
    idconv_result = run_idconv(
        pmids=pmids,
        artifact_store=artifact_store,
        settings=settings,
    )
    bioc_results = tuple(
        run_bioc(identifier=pmcid, artifact_store=artifact_store)
        for pmcid in _available_pmcids(idconv_result)
    )
    openalex_result = run_openalex_work(
        identifier=pmids[0],
        id_type="pmid",
        artifact_store=artifact_store,
        settings=settings,
    )
    return SeedRunResults(
        pubmed_esearch=esearch_result,
        pubmed_esummary=esummary_result,
        pubmed_efetch=efetch_result,
        pmc_idconv=idconv_result,
        pmc_bioc=bioc_results,
        openalex_work=openalex_result,
    )


def _available_pmcids(result: PmcIdConverterAdapterResult) -> tuple[str, ...]:
    return tuple(
        record.pmcid
        for record in result.parsed.records
        if record.pmcid is not None and record.live is not False
    )


def _require_seed_pmids(pmids: tuple[str, ...]) -> None:
    if not pmids:
        raise ValueError("Seed PubMed ESearch returned no PMIDs.")


def _validate_live_settings(settings: Settings) -> None:
    if not settings.ncbi_email:
        raise ValueError("NCBI_EMAIL is required for --live seed builds.")
    if not settings.openalex_api_key:
        raise ValueError("OPENALEX_API_KEY is required for --live seed builds.")


def _validate_fixture_paths(fixture_paths: SeedFixturePaths) -> None:
    missing_paths = [
        path
        for path in (
            fixture_paths.pubmed_esearch,
            fixture_paths.pubmed_esummary,
            fixture_paths.pubmed_efetch,
            fixture_paths.pmc_idconv,
            fixture_paths.pmc_bioc,
            fixture_paths.openalex_work,
        )
        if not path.is_file()
    ]
    if missing_paths:
        formatted_paths = ", ".join(str(path) for path in missing_paths)
        raise ValueError(f"Seed fixture file(s) are missing: {formatted_paths}")
