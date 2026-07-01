from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from convivial_medicine.config import Settings
from convivial_medicine.domain.hashes import validate_sha256_uri
from convivial_medicine.domain.manifests import QueryManifest
from convivial_medicine.orchestration.seed import (
    SeedFixturePaths,
    SeedRunResults,
    run_seed_build,
)
from convivial_medicine.storage.artifacts import LocalArtifactStore

EXPECTED_FIXTURE_STEP_COUNT = 6
EXPECTED_FIXTURE_SOURCE_SNAPSHOT_COUNT = 6


@dataclass(frozen=True)
class BuildValidationReport:
    manifest_name: str
    manifest_hash: str
    artifact_root: Path
    expected_step_count: int
    actual_step_count: int
    expected_source_snapshot_count: int
    actual_source_snapshot_count: int
    raw_artifact_hashes: tuple[str, ...]
    present_raw_artifact_hashes: tuple[str, ...]
    missing_raw_artifact_hashes: tuple[str, ...]
    source_snapshot_manifest_hashes: tuple[str, ...]
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
    with TemporaryDirectory() as temp_root:
        expected_summary = run_seed_build(
            query_manifest=query_manifest,
            artifact_store=LocalArtifactStore(Path(temp_root) / "expected-artifacts"),
            settings=Settings(),
            live=False,
            fixture_paths=fixture_paths,
        )

    artifact_store = LocalArtifactStore(artifact_root)
    raw_artifact_hashes = expected_summary.raw_artifact_hashes
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
    actual_step_count = _seed_source_step_count(expected_summary.results)
    actual_source_snapshot_count = expected_summary.source_snapshot_count
    source_snapshot_manifest_hashes = _source_snapshot_manifest_hashes(expected_summary.results)

    errors = _validation_errors(
        artifact_root=artifact_root,
        expected_step_count=EXPECTED_FIXTURE_STEP_COUNT,
        actual_step_count=actual_step_count,
        expected_source_snapshot_count=EXPECTED_FIXTURE_SOURCE_SNAPSHOT_COUNT,
        actual_source_snapshot_count=actual_source_snapshot_count,
        missing_raw_artifact_hashes=missing_raw_artifact_hashes,
        source_snapshot_manifest_hashes=source_snapshot_manifest_hashes,
    )
    return BuildValidationReport(
        manifest_name=expected_summary.manifest_name,
        manifest_hash=expected_summary.manifest_hash,
        artifact_root=artifact_root,
        expected_step_count=EXPECTED_FIXTURE_STEP_COUNT,
        actual_step_count=actual_step_count,
        expected_source_snapshot_count=EXPECTED_FIXTURE_SOURCE_SNAPSHOT_COUNT,
        actual_source_snapshot_count=actual_source_snapshot_count,
        raw_artifact_hashes=raw_artifact_hashes,
        present_raw_artifact_hashes=present_raw_artifact_hashes,
        missing_raw_artifact_hashes=missing_raw_artifact_hashes,
        source_snapshot_manifest_hashes=source_snapshot_manifest_hashes,
        errors=errors,
    )


def _validation_errors(
    *,
    artifact_root: Path,
    expected_step_count: int,
    actual_step_count: int,
    expected_source_snapshot_count: int,
    actual_source_snapshot_count: int,
    missing_raw_artifact_hashes: tuple[str, ...],
    source_snapshot_manifest_hashes: tuple[str, ...],
) -> tuple[str, ...]:
    errors: list[str] = []
    if not artifact_root.is_dir():
        errors.append(f"artifact root is missing: {artifact_root}")
    if actual_step_count != expected_step_count:
        errors.append(
            f"step count mismatch: expected {expected_step_count}, got {actual_step_count}"
        )
    if actual_source_snapshot_count != expected_source_snapshot_count:
        errors.append(
            "source snapshot count mismatch: "
            f"expected {expected_source_snapshot_count}, got {actual_source_snapshot_count}"
        )
    if missing_raw_artifact_hashes:
        errors.append(f"missing raw artifacts: {len(missing_raw_artifact_hashes)}")
    if len(source_snapshot_manifest_hashes) != expected_source_snapshot_count:
        errors.append(
            "manifest hash count mismatch: "
            f"expected {expected_source_snapshot_count}, got {len(source_snapshot_manifest_hashes)}"
        )
    return tuple(errors)


def _seed_source_step_count(results: SeedRunResults) -> int:
    return 5 + len(results.pmc_bioc)


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
