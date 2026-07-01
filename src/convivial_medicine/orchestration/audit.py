from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import text
from sqlalchemy.orm import Session

from convivial_medicine.domain.manifests import QueryManifest
from convivial_medicine.orchestration.build_report import seed_build_report_path
from convivial_medicine.orchestration.seed import SeedFixturePaths
from convivial_medicine.orchestration.slice_export import (
    FixtureSliceValidationError,
    write_fixture_slice_export,
)
from convivial_medicine.orchestration.validation import (
    BuildValidationReport,
    validate_fixture_seed_build,
)
from convivial_medicine.orchestration.work_normalization import (
    FIXTURE_WORK_PROJECTION_VERSION,
    FixtureWorkProjectionCounts,
    expected_fixture_work_projection_counts,
)


@dataclass(frozen=True)
class AuditCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class PhaseOneAuditReport:
    checks: tuple[AuditCheck, ...]

    @property
    def ok(self) -> bool:
        return all(check.passed for check in self.checks)


def audit_phase_one_fixture_workflow(
    *,
    query_manifest: QueryManifest,
    artifact_root: Path,
    fixture_paths: SeedFixturePaths,
    check_db: bool = False,
    db_session: Session | None = None,
) -> PhaseOneAuditReport:
    checks = [
        _audit_build_report_exists(
            artifact_root=artifact_root,
            manifest_name=query_manifest.name,
        )
    ]

    validation_report = validate_fixture_seed_build(
        query_manifest=query_manifest,
        artifact_root=artifact_root,
        fixture_paths=fixture_paths,
    )
    checks.append(
        AuditCheck(
            name="validation",
            passed=validation_report.ok,
            detail=_validation_detail(validation_report),
        )
    )
    checks.append(
        _audit_slice_export(
            query_manifest=query_manifest,
            artifact_root=artifact_root,
            fixture_paths=fixture_paths,
        )
    )

    if check_db:
        checks.append(
            _audit_db_projection(
                query_manifest=query_manifest,
                fixture_paths=fixture_paths,
                db_session=db_session,
            )
        )

    return PhaseOneAuditReport(checks=tuple(checks))


def _audit_build_report_exists(
    *,
    artifact_root: Path,
    manifest_name: str,
) -> AuditCheck:
    report_path = seed_build_report_path(artifact_root, manifest_name)
    if report_path.is_file():
        return AuditCheck(name="build_report", passed=True, detail=str(report_path))
    return AuditCheck(name="build_report", passed=False, detail=f"missing {report_path}")


def _validation_detail(report: BuildValidationReport) -> str:
    if report.ok:
        actual_report = report.actual_report
        actual_source_snapshots = (
            actual_report.counts.source_snapshots if actual_report is not None else 0
        )
        return (
            f"raw_artifacts={len(report.present_raw_artifact_hashes)}/"
            f"{len(report.raw_artifact_hashes)} "
            f"source_snapshots={actual_source_snapshots}/"
            f"{report.expected_report.counts.source_snapshots}"
        )
    return "; ".join(report.errors) if report.errors else "failed"


def _audit_slice_export(
    *,
    query_manifest: QueryManifest,
    artifact_root: Path,
    fixture_paths: SeedFixturePaths,
) -> AuditCheck:
    with TemporaryDirectory() as temp_root:
        output = Path(temp_root) / "fixture-slice.json"
        try:
            written_export = write_fixture_slice_export(
                query_manifest=query_manifest,
                artifact_root=artifact_root,
                output=output,
                fixture_paths=fixture_paths,
            )
        except FixtureSliceValidationError:
            return AuditCheck(
                name="slice_export",
                passed=False,
                detail="validation failed",
            )

        payload = written_export.payload
        return AuditCheck(
            name="slice_export",
            passed=written_export.path.is_file(),
            detail=(
                f"source_steps={len(payload['source_steps'])} "
                f"raw_artifacts={len(payload['raw_artifact_hashes'])} "
                f"source_snapshots={len(payload['source_snapshot_manifest_hashes'])}"
            ),
        )


def _audit_db_projection(
    *,
    query_manifest: QueryManifest,
    fixture_paths: SeedFixturePaths,
    db_session: Session | None,
) -> AuditCheck:
    if db_session is None:
        return AuditCheck(
            name="db_projection",
            passed=False,
            detail="database session unavailable",
        )

    expected = expected_fixture_work_projection_counts(
        query_manifest=query_manifest,
        fixture_paths=fixture_paths,
    )
    actual = _fixture_work_projection_counts(db_session)
    passed = actual == expected
    return AuditCheck(
        name="db_projection",
        passed=passed,
        detail=(
            f"works={actual.works}/{expected.works} "
            f"identifiers={actual.identifiers}/{expected.identifiers} "
            f"source_links={actual.source_links}/{expected.source_links}"
        ),
    )


def _fixture_work_projection_counts(session: Session) -> FixtureWorkProjectionCounts:
    return FixtureWorkProjectionCounts(
        works=_projection_count(
            session,
            "select count(*) from works where normalized_payload->>'projection_version' = :version",
        ),
        identifiers=_projection_count(
            session,
            "select count(*) from work_identifiers wi "
            "join works w on w.work_id = wi.work_id "
            "where w.normalized_payload->>'projection_version' = :version",
        ),
        source_links=_projection_count(
            session,
            "select count(*) from work_sources ws "
            "join works w on w.work_id = ws.work_id "
            "where w.normalized_payload->>'projection_version' = :version",
        ),
    )


def _projection_count(session: Session, statement: str) -> int:
    return int(
        session.execute(
            text(statement),
            {"version": FIXTURE_WORK_PROJECTION_VERSION},
        ).scalar_one()
    )
