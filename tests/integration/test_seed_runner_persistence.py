from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from typer.testing import CliRunner

from convivial_medicine.cli.main import app
from convivial_medicine.config import get_settings
from convivial_medicine.domain.manifests import load_query_manifest
from convivial_medicine.orchestration.seed import SeedFixturePaths, run_seed_build
from convivial_medicine.storage.artifacts import LocalArtifactStore

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="set RUN_DB_TESTS=1 to run Postgres persistence integration tests",
)

SEED_MANIFEST_PATH = Path("manifests/vitamin_D_ms_seed_v1.json")
FIXTURE_ROOT = Path("tests/fixtures")


def test_fixture_seed_build_persistence_creates_all_snapshot_rows(tmp_path: Path) -> None:
    get_settings.cache_clear()
    command.upgrade(Config("alembic.ini"), "head")

    manifest = load_query_manifest(SEED_MANIFEST_PATH)
    expected_summary = run_seed_build(
        query_manifest=manifest,
        artifact_store=LocalArtifactStore(tmp_path / "expected-artifacts"),
        settings=get_settings(),
        live=False,
        fixture_paths=SeedFixturePaths.from_root(FIXTURE_ROOT),
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "build",
            "seed",
            "--manifest",
            str(SEED_MANIFEST_PATH),
            "--artifact-root",
            str(tmp_path / "cli-artifacts"),
            "--persist-db",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "db_persisted: True" in result.output
    assert "source_snapshots: 6" in result.output

    engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            query_count = connection.execute(
                text("select count(*) from query_manifests where manifest_hash = :hash"),
                {"hash": manifest.manifest_hash()},
            ).scalar_one()
            source_count = connection.execute(
                text(
                    "select count(*) from source_snapshots "
                    "where snapshot_hash = any(:snapshot_hashes)"
                ),
                {"snapshot_hashes": list(expected_summary.raw_artifact_hashes)},
            ).scalar_one()
    finally:
        engine.dispose()

    assert query_count == 1
    assert source_count == expected_summary.source_snapshot_count
