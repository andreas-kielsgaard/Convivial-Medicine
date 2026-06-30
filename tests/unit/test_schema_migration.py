from __future__ import annotations

from pathlib import Path

MIGRATION_PATH = Path("migrations/versions/20260701_0001_schema_v1.py")


def test_initial_migration_revision_id_stays_stable() -> None:
    migration = MIGRATION_PATH.read_text(encoding="utf-8")

    assert 'revision: str = "20260701_0001"' in migration


def test_initial_migration_contains_corrected_schema_columns() -> None:
    migration = MIGRATION_PATH.read_text(encoding="utf-8")

    for column_name in (
        "manifest_hash",
        "artifact_type",
        "schema_version",
        "payload_hash",
        "metadata",
        "request_fingerprint",
        "http_status",
        "normalized_payload",
        "current_manifest_hash",
        "license_group",
        "license_observation",
        "slice_hash",
        "member_manifest_hash",
    ):
        assert f'"{column_name}"' in migration

    assert 'sa.Column("snapshot_manifest_hash", sa.Text(), primary_key=True)' not in migration
    assert 'name="uq_enrichment_openalex_work_id"' not in migration
