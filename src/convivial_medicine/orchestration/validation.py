from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import ValidationError

from convivial_medicine.config import Settings
from convivial_medicine.domain.manifests import QueryManifest
from convivial_medicine.orchestration.build_report import (
    SeedBuildReport,
    read_seed_build_report,
    seed_build_report_from_summary,
    seed_build_report_path,
)
from convivial_medicine.orchestration.seed import (
    SeedFixturePaths,
    run_seed_build,
)
from convivial_medicine.storage.artifacts import LocalArtifactStore


@dataclass(frozen=True)
class BuildValidationReport:
    manifest_name: str
    manifest_hash: str
    artifact_root: Path
    build_report_path: Path
    expected_report: SeedBuildReport
    actual_report: SeedBuildReport | None
    raw_artifact_hashes: tuple[str, ...]
    present_raw_artifact_hashes: tuple[str, ...]
    missing_raw_artifact_hashes: tuple[str, ...]
    errors: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_fixture_seed_build(
    *,
    query_manifest: QueryManifest,
    artifact_root: Path,
    fixture_paths: SeedFixturePaths,
) -> BuildValidationReport:
    expected_report = _expected_fixture_report(
        query_manifest=query_manifest,
        fixture_paths=fixture_paths,
    )
    build_report_path = seed_build_report_path(artifact_root, query_manifest.name)
    actual_report, report_errors = _read_actual_report(build_report_path)
    raw_artifact_hashes = (
        actual_report.raw_artifact_hashes
        if actual_report is not None
        else expected_report.raw_artifact_hashes
    )
    artifact_store = LocalArtifactStore(artifact_root)
    present_raw_artifact_hashes = tuple(
        artifact_hash
        for artifact_hash in raw_artifact_hashes
        if artifact_store.artifact_path(artifact_hash).is_file()
    )
    missing_raw_artifact_hashes = tuple(
        artifact_hash
        for artifact_hash in raw_artifact_hashes
        if artifact_hash not in present_raw_artifact_hashes
    )
    errors = _validation_errors(
        artifact_root=artifact_root,
        expected_report=expected_report,
        actual_report=actual_report,
        report_errors=report_errors,
        missing_raw_artifact_hashes=missing_raw_artifact_hashes,
    )
    return BuildValidationReport(
        manifest_name=expected_report.manifest_name,
        manifest_hash=expected_report.manifest_hash,
        artifact_root=artifact_root,
        build_report_path=build_report_path,
        expected_report=expected_report,
        actual_report=actual_report,
        raw_artifact_hashes=raw_artifact_hashes,
        present_raw_artifact_hashes=present_raw_artifact_hashes,
        missing_raw_artifact_hashes=missing_raw_artifact_hashes,
        errors=errors,
    )


def _expected_fixture_report(
    *,
    query_manifest: QueryManifest,
    fixture_paths: SeedFixturePaths,
) -> SeedBuildReport:
    with TemporaryDirectory() as temp_root:
        expected_summary = run_seed_build(
            query_manifest=query_manifest,
            artifact_store=LocalArtifactStore(Path(temp_root) / "expected-artifacts"),
            settings=Settings(),
            live=False,
            fixture_paths=fixture_paths,
        )
    return seed_build_report_from_summary(expected_summary)


def _read_actual_report(path: Path) -> tuple[SeedBuildReport | None, tuple[str, ...]]:
    if not path.is_file():
        return None, (f"build report is missing: {path}",)
    try:
        return read_seed_build_report(path), ()
    except (OSError, ValidationError, ValueError) as exc:
        return None, (f"build report is invalid: {exc}",)


def _validation_errors(
    *,
    artifact_root: Path,
    expected_report: SeedBuildReport,
    actual_report: SeedBuildReport | None,
    report_errors: tuple[str, ...],
    missing_raw_artifact_hashes: tuple[str, ...],
) -> tuple[str, ...]:
    errors: list[str] = []
    if not artifact_root.is_dir():
        errors.append(f"artifact root is missing: {artifact_root}")
    errors.extend(report_errors)
    if actual_report is not None:
        errors.extend(_report_mismatch_errors(expected_report, actual_report))
    if missing_raw_artifact_hashes:
        errors.append(f"missing raw artifacts: {len(missing_raw_artifact_hashes)}")
    return tuple(errors)


def _report_mismatch_errors(
    expected_report: SeedBuildReport,
    actual_report: SeedBuildReport,
) -> tuple[str, ...]:
    errors: list[str] = []
    if actual_report.manifest_name != expected_report.manifest_name:
        errors.append(
            "manifest name mismatch: "
            f"expected {expected_report.manifest_name}, got {actual_report.manifest_name}"
        )
    if actual_report.manifest_hash != expected_report.manifest_hash:
        errors.append(
            "manifest hash mismatch: "
            f"expected {expected_report.manifest_hash}, got {actual_report.manifest_hash}"
        )
    if actual_report.mode != expected_report.mode:
        errors.append(f"mode mismatch: expected {expected_report.mode}, got {actual_report.mode}")
    if actual_report.step_order != expected_report.step_order:
        errors.append("step order mismatch")
    if actual_report.counts.steps != expected_report.counts.steps:
        errors.append(
            f"step count mismatch: expected {expected_report.counts.steps}, "
            f"got {actual_report.counts.steps}"
        )
    if actual_report.counts.source_snapshots != expected_report.counts.source_snapshots:
        errors.append(
            "source snapshot count mismatch: "
            f"expected {expected_report.counts.source_snapshots}, "
            f"got {actual_report.counts.source_snapshots}"
        )
    if actual_report.counts.raw_artifacts != expected_report.counts.raw_artifacts:
        errors.append(
            "raw artifact count mismatch: "
            f"expected {expected_report.counts.raw_artifacts}, "
            f"got {actual_report.counts.raw_artifacts}"
        )
    if actual_report.source_snapshot_manifest_hashes != (
        expected_report.source_snapshot_manifest_hashes
    ):
        errors.append("source snapshot manifest hash list mismatch")
    if actual_report.raw_artifact_hashes != expected_report.raw_artifact_hashes:
        errors.append("raw artifact hash list mismatch")
    return tuple(errors)
