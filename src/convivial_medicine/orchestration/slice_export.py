from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from convivial_medicine.adapters.pmc.models import PmcBioCResult
from convivial_medicine.config import Settings
from convivial_medicine.domain.canonical_json import canonical_json_text
from convivial_medicine.domain.manifests import QueryManifest
from convivial_medicine.orchestration.build_report import SeedBuildReport
from convivial_medicine.orchestration.seed import (
    SeedFixturePaths,
    SeedRunSummary,
    run_seed_build,
)
from convivial_medicine.orchestration.validation import (
    BuildValidationReport,
    validate_fixture_seed_build,
)
from convivial_medicine.storage.artifacts import LocalArtifactStore

FIXTURE_SLICE_EXPORT_SCHEMA_VERSION = "fixture-slice-export-v1"


@dataclass(frozen=True)
class WrittenFixtureSliceExport:
    path: Path
    payload: dict[str, Any]
    validation_report: BuildValidationReport


class FixtureSliceValidationError(RuntimeError):
    def __init__(self, report: BuildValidationReport) -> None:
        super().__init__("Fixture seed build validation failed.")
        self.report = report


def write_fixture_slice_export(
    *,
    query_manifest: QueryManifest,
    artifact_root: Path,
    output: Path,
    fixture_paths: SeedFixturePaths,
) -> WrittenFixtureSliceExport:
    validation_report = validate_fixture_seed_build(
        query_manifest=query_manifest,
        artifact_root=artifact_root,
        fixture_paths=fixture_paths,
    )
    if not validation_report.ok:
        raise FixtureSliceValidationError(validation_report)

    actual_report = validation_report.actual_report
    if actual_report is None:
        raise FixtureSliceValidationError(validation_report)

    payload = _fixture_slice_export_payload(
        query_manifest=query_manifest,
        fixture_paths=fixture_paths,
        build_report=actual_report,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(canonical_json_text(payload) + "\n", encoding="utf-8")
    return WrittenFixtureSliceExport(
        path=output,
        payload=payload,
        validation_report=validation_report,
    )


def _fixture_slice_export_payload(
    *,
    query_manifest: QueryManifest,
    fixture_paths: SeedFixturePaths,
    build_report: SeedBuildReport,
) -> dict[str, Any]:
    with TemporaryDirectory() as temp_root:
        summary = run_seed_build(
            query_manifest=query_manifest,
            artifact_store=LocalArtifactStore(Path(temp_root) / "slice-export-fixtures"),
            settings=Settings(),
            live=False,
            fixture_paths=fixture_paths,
        )
        return _export_payload_from_summary(build_report=build_report, summary=summary)


def _export_payload_from_summary(
    *,
    build_report: SeedBuildReport,
    summary: SeedRunSummary,
) -> dict[str, Any]:
    return {
        "schema_version": FIXTURE_SLICE_EXPORT_SCHEMA_VERSION,
        "manifest": {
            "name": build_report.manifest_name,
            "hash": build_report.manifest_hash,
        },
        "build_report": {
            "mode": build_report.mode,
            "step_order": list(build_report.step_order),
            "counts": build_report.counts.model_dump(mode="json"),
            "db_persisted": build_report.db_persisted,
        },
        "source_steps": _source_steps(summary),
        "raw_artifact_hashes": list(build_report.raw_artifact_hashes),
        "source_snapshot_manifest_hashes": list(build_report.source_snapshot_manifest_hashes),
    }


def _source_steps(summary: SeedRunSummary) -> list[dict[str, Any]]:
    results = summary.results
    return [
        _source_step(
            name="pubmed_esearch",
            raw_artifact_hashes=(results.pubmed_esearch.raw_artifact.artifact_hash,),
            source_snapshot_manifest_hashes=(
                results.pubmed_esearch.source_snapshot_manifest.manifest_hash(),
            ),
            parsed_summary=_pubmed_esearch_summary(summary),
        ),
        _source_step(
            name="pubmed_esummary",
            raw_artifact_hashes=(results.pubmed_esummary.raw_artifact.artifact_hash,),
            source_snapshot_manifest_hashes=(
                results.pubmed_esummary.source_snapshot_manifest.manifest_hash(),
            ),
            parsed_summary=_pubmed_esummary_summary(summary),
        ),
        _source_step(
            name="pubmed_efetch",
            raw_artifact_hashes=(results.pubmed_efetch.raw_artifact.artifact_hash,),
            source_snapshot_manifest_hashes=(
                results.pubmed_efetch.source_snapshot_manifest.manifest_hash(),
            ),
            parsed_summary=_pubmed_efetch_summary(summary),
        ),
        _source_step(
            name="pmc_idconv",
            raw_artifact_hashes=(results.pmc_idconv.raw_artifact.artifact_hash,),
            source_snapshot_manifest_hashes=(
                results.pmc_idconv.source_snapshot_manifest.manifest_hash(),
            ),
            parsed_summary=_pmc_idconv_summary(summary),
        ),
        _source_step(
            name="pmc_bioc",
            raw_artifact_hashes=tuple(
                result.raw_artifact.artifact_hash for result in results.pmc_bioc
            ),
            source_snapshot_manifest_hashes=tuple(
                result.source_snapshot_manifest.manifest_hash() for result in results.pmc_bioc
            ),
            parsed_summary=_pmc_bioc_summary(summary),
        ),
        _source_step(
            name="openalex_work",
            raw_artifact_hashes=(results.openalex_work.raw_artifact.artifact_hash,),
            source_snapshot_manifest_hashes=(
                results.openalex_work.source_snapshot_manifest.manifest_hash(),
            ),
            parsed_summary=_openalex_work_summary(summary),
        ),
    ]


def _source_step(
    *,
    name: str,
    raw_artifact_hashes: tuple[str, ...],
    source_snapshot_manifest_hashes: tuple[str, ...],
    parsed_summary: dict[str, Any],
) -> dict[str, Any]:
    return {
        "name": name,
        "raw_artifact_hashes": list(raw_artifact_hashes),
        "source_snapshot_manifest_hashes": list(source_snapshot_manifest_hashes),
        "parsed_summary": parsed_summary,
    }


def _pubmed_esearch_summary(summary: SeedRunSummary) -> dict[str, Any]:
    parsed = summary.results.pubmed_esearch.parsed
    return {
        "count": parsed.count,
        "pmids": list(parsed.pmids),
        "pmids_returned": len(parsed.pmids),
        "query_key_present": parsed.query_key is not None,
        "retmax": parsed.retmax,
        "webenv_present": parsed.webenv is not None,
    }


def _pubmed_esummary_summary(summary: SeedRunSummary) -> dict[str, Any]:
    parsed = summary.results.pubmed_esummary.parsed
    return {
        "pmids_requested": len(parsed.requested_pmids),
        "pmids_returned": len(parsed.returned_pmids),
        "summaries_returned": parsed.summaries_returned,
        "articles": [
            {
                "pmid": article.pmid,
                "title": article.title,
                "source": article.source,
                "pubdate": article.pubdate,
                "pub_year": article.pub_year,
                "doi": article.doi,
            }
            for article in parsed.summaries
        ],
    }


def _pubmed_efetch_summary(summary: SeedRunSummary) -> dict[str, Any]:
    parsed = summary.results.pubmed_efetch.parsed
    return {
        "pmids_requested": len(parsed.requested_pmids),
        "pmids_returned": len(parsed.returned_pmids),
        "records_returned": parsed.records_returned,
        "returned_pmids": list(parsed.returned_pmids),
    }


def _pmc_idconv_summary(summary: SeedRunSummary) -> dict[str, Any]:
    parsed = summary.results.pmc_idconv.parsed
    return {
        "pmids_requested": len(parsed.requested_pmids),
        "records_returned": parsed.records_returned,
        "pmcids_returned": parsed.pmcids_returned,
        "missing_pmids": list(parsed.missing_pmids),
        "records": [
            {
                "requested_id": record.requested_id,
                "pmid": record.pmid,
                "pmcid": record.pmcid,
                "doi": record.doi,
                "live": record.live,
                "release_date": record.release_date,
                "error_message": record.error_message,
            }
            for record in parsed.records
        ],
    }


def _pmc_bioc_summary(summary: SeedRunSummary) -> dict[str, Any]:
    parsed_results = tuple(result.parsed for result in summary.results.pmc_bioc)
    return {
        "requests": len(parsed_results),
        "document_count": sum(parsed.document_count for parsed in parsed_results),
        "passage_count": sum(parsed.passage_count for parsed in parsed_results),
        "responses": [_pmc_bioc_response_summary(parsed) for parsed in parsed_results],
    }


def _pmc_bioc_response_summary(parsed: PmcBioCResult) -> dict[str, Any]:
    return {
        "requested_id": parsed.requested_id,
        "requested_id_type": parsed.requested_id_type,
        "collection_source": parsed.collection_source,
        "document_detected": parsed.document_detected,
        "document_count": parsed.document_count,
        "passage_count": parsed.passage_count,
        "document_ids": list(parsed.document_ids),
        "section_labels": list(parsed.section_labels),
        "documents": [
            {
                "document_id": document.document_id,
                "passage_count": document.passage_count,
                "section_labels": list(document.section_labels),
            }
            for document in parsed.documents
        ],
    }


def _openalex_work_summary(summary: SeedRunSummary) -> dict[str, Any]:
    parsed = summary.results.openalex_work.parsed
    return {
        "requested_id": parsed.requested_id,
        "requested_id_type": parsed.requested_id_type,
        "openalex_id": parsed.openalex_id,
        "doi": parsed.doi,
        "pmid": parsed.pmid,
        "title": parsed.title,
        "publication_year": parsed.publication_year,
        "publication_date": parsed.publication_date,
        "type": parsed.type,
        "cited_by_count": parsed.cited_by_count,
        "is_retracted": parsed.is_retracted,
        "open_access": (
            parsed.open_access.model_dump(mode="json", exclude_none=True)
            if parsed.open_access is not None
            else None
        ),
        "primary_location": (
            parsed.primary_location.model_dump(mode="json", exclude_none=True)
            if parsed.primary_location is not None
            else None
        ),
    }
