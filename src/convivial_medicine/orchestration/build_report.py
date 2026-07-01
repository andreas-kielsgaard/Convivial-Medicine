from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from convivial_medicine.domain.hashes import validate_sha256_uri
from convivial_medicine.orchestration.seed import SeedRunMode, SeedRunResults, SeedRunSummary

SEED_BUILD_STEP_ORDER = (
    "pubmed_esearch",
    "pubmed_esummary",
    "pubmed_efetch",
    "pmc_idconv",
    "pmc_bioc",
    "openalex_work",
)


class SeedBuildReportCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steps: int = Field(ge=0)
    source_snapshots: int = Field(ge=0)
    raw_artifacts: int = Field(ge=0)


class SeedBuildReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifest_name: str = Field(min_length=1)
    manifest_hash: str
    mode: SeedRunMode
    step_order: tuple[str, ...]
    source_snapshot_manifest_hashes: tuple[str, ...]
    raw_artifact_hashes: tuple[str, ...]
    counts: SeedBuildReportCounts
    db_persisted: bool

    @field_validator("manifest_hash")
    @classmethod
    def _validate_manifest_hash(cls, value: str) -> str:
        return validate_sha256_uri(value)

    @field_validator("source_snapshot_manifest_hashes", "raw_artifact_hashes")
    @classmethod
    def _validate_hashes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(validate_sha256_uri(item) for item in value)


@dataclass(frozen=True)
class WrittenSeedBuildReport:
    report: SeedBuildReport
    path: Path


def seed_build_report_path(artifact_root: Path, manifest_name: str) -> Path:
    return artifact_root / "build-reports" / f"{manifest_name}.json"


def seed_build_report_from_summary(summary: SeedRunSummary) -> SeedBuildReport:
    source_snapshot_manifest_hashes = _source_snapshot_manifest_hashes(summary.results)
    return SeedBuildReport(
        manifest_name=summary.manifest_name,
        manifest_hash=summary.manifest_hash,
        mode=summary.mode,
        step_order=SEED_BUILD_STEP_ORDER,
        source_snapshot_manifest_hashes=source_snapshot_manifest_hashes,
        raw_artifact_hashes=summary.raw_artifact_hashes,
        counts=SeedBuildReportCounts(
            steps=len(SEED_BUILD_STEP_ORDER),
            source_snapshots=summary.source_snapshot_count,
            raw_artifacts=len(summary.raw_artifact_hashes),
        ),
        db_persisted=summary.db_persisted,
    )


def write_seed_build_report(
    *,
    artifact_root: Path,
    summary: SeedRunSummary,
) -> WrittenSeedBuildReport:
    report = seed_build_report_from_summary(summary)
    path = seed_build_report_path(artifact_root, summary.manifest_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_report_json(report), encoding="utf-8")
    return WrittenSeedBuildReport(report=report, path=path)


def read_seed_build_report(path: Path) -> SeedBuildReport:
    return SeedBuildReport.model_validate_json(path.read_text(encoding="utf-8"))


def _report_json(report: SeedBuildReport) -> str:
    payload = report.model_dump(mode="json")
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _source_snapshot_manifest_hashes(results: SeedRunResults) -> tuple[str, ...]:
    hashes = (
        results.pubmed_esearch.source_snapshot_manifest.manifest_hash(),
        results.pubmed_esummary.source_snapshot_manifest.manifest_hash(),
        results.pubmed_efetch.source_snapshot_manifest.manifest_hash(),
        results.pmc_idconv.source_snapshot_manifest.manifest_hash(),
        *(result.source_snapshot_manifest.manifest_hash() for result in results.pmc_bioc),
        results.openalex_work.source_snapshot_manifest.manifest_hash(),
    )
    return tuple(validate_sha256_uri(manifest_hash) for manifest_hash in hashes)
