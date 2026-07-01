from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from typer.testing import CliRunner

from convivial_medicine.adapters.pubmed.esearch import (
    PUBMED_ESEARCH_ENDPOINT,
    build_esearch_params,
    process_esearch_response_bytes,
)
from convivial_medicine.cli.main import app
from convivial_medicine.config import get_settings
from convivial_medicine.domain.hashes import sha256_uri
from convivial_medicine.domain.manifests import load_query_manifest
from convivial_medicine.storage.artifacts import LocalArtifactStore

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="set RUN_DB_TESTS=1 to run Postgres persistence integration tests",
)

SEED_MANIFEST_PATH = Path("manifests/vitamin_D_ms_seed_v1.json")
FIXTURE_PATH = Path("tests/fixtures/pubmed/esearch_vitamin_d_ms_seed.json")


def test_fixture_mode_esearch_persistence_creates_manifest_and_snapshot_rows(
    tmp_path: Path,
) -> None:
    get_settings.cache_clear()
    command.upgrade(Config("alembic.ini"), "head")

    query_manifest = load_query_manifest(SEED_MANIFEST_PATH)
    expected_result = process_esearch_response_bytes(
        raw_bytes=FIXTURE_PATH.read_bytes(),
        artifact_store=LocalArtifactStore(tmp_path / "expected-artifacts"),
        endpoint=PUBMED_ESEARCH_ENDPOINT,
        request_params=build_esearch_params(query_manifest),
        http_status=200,
        content_type="application/json",
    )
    raw_hash = sha256_uri(FIXTURE_PATH.read_bytes())
    snapshot_manifest_hash = expected_result.source_snapshot_manifest.manifest_hash()

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "query",
            "pubmed",
            "--fixture",
            str(FIXTURE_PATH),
            "--artifact-root",
            str(tmp_path / "cli-artifacts"),
            "--persist-db",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "db_persisted: True" in result.output

    engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            query_count = connection.execute(
                text("select count(*) from query_manifests where manifest_hash = :manifest_hash"),
                {"manifest_hash": query_manifest.manifest_hash()},
            ).scalar_one()
            source_count = connection.execute(
                text("select count(*) from source_snapshots where snapshot_hash = :snapshot_hash"),
                {"snapshot_hash": raw_hash},
            ).scalar_one()
            snapshot_manifest_count = connection.execute(
                text(
                    "select count(*) from snapshot_manifests where manifest_hash = :manifest_hash"
                ),
                {"manifest_hash": snapshot_manifest_hash},
            ).scalar_one()
    finally:
        engine.dispose()

    assert query_count == 1
    assert source_count == 1
    assert snapshot_manifest_count == 1
