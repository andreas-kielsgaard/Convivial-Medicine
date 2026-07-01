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
from convivial_medicine.orchestration.work_normalization import FIXTURE_WORK_PROJECTION_VERSION

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="set RUN_DB_TESTS=1 to run Postgres work normalization integration tests",
)

SEED_MANIFEST_PATH = Path("manifests/vitamin_D_ms_seed_v1.json")


def test_fixture_work_projection_creates_expected_rows(tmp_path: Path) -> None:
    get_settings.cache_clear()
    command.upgrade(Config("alembic.ini"), "head")

    engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    try:
        _delete_fixture_projection_rows(engine)

        artifact_root = tmp_path / "artifacts"
        runner = CliRunner()
        build_result = runner.invoke(
            app,
            [
                "build",
                "seed",
                "--manifest",
                str(SEED_MANIFEST_PATH),
                "--artifact-root",
                str(artifact_root),
            ],
        )
        assert build_result.exit_code == 0, build_result.output

        result = runner.invoke(
            app,
            [
                "build",
                "normalize-works",
                "--manifest",
                str(SEED_MANIFEST_PATH),
                "--artifact-root",
                str(artifact_root),
                "--persist-db",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "works: 3" in result.output
        assert "identifiers: 8" in result.output
        assert "source_links: 14" in result.output
        assert "db_persisted: True" in result.output

        with engine.connect() as connection:
            first_counts = _fixture_projection_counts(connection)

        repeat_result = runner.invoke(
            app,
            [
                "build",
                "normalize-works",
                "--manifest",
                str(SEED_MANIFEST_PATH),
                "--artifact-root",
                str(artifact_root),
                "--persist-db",
            ],
        )

        assert repeat_result.exit_code == 0, repeat_result.output
        assert "works: 3" in repeat_result.output
        assert "identifiers: 8" in repeat_result.output
        assert "source_links: 14" in repeat_result.output
        assert "db_persisted: True" in repeat_result.output

        with engine.connect() as connection:
            repeat_counts = _fixture_projection_counts(connection)
            works = (
                connection.execute(
                    text(
                        "select normalized_payload->>'pmid' as pmid, title, publication_year, "
                        "primary_doi from works "
                        "where normalized_payload->>'projection_version' = :version "
                        "order by normalized_payload->>'pmid'"
                    ),
                    {"version": FIXTURE_WORK_PROJECTION_VERSION},
                )
                .mappings()
                .all()
            )
            identifiers = (
                connection.execute(
                    text(
                        "select wi.id_namespace, wi.id_value from work_identifiers wi "
                        "join works w on w.work_id = wi.work_id "
                        "where w.normalized_payload->>'projection_version' = :version "
                        "order by wi.id_namespace, wi.id_value"
                    ),
                    {"version": FIXTURE_WORK_PROJECTION_VERSION},
                )
                .mappings()
                .all()
            )
            source_links = (
                connection.execute(
                    text(
                        "select ws.source_projection from work_sources ws "
                        "join works w on w.work_id = ws.work_id "
                        "where w.normalized_payload->>'projection_version' = :version"
                    ),
                    {"version": FIXTURE_WORK_PROJECTION_VERSION},
                )
                .mappings()
                .all()
            )
    finally:
        engine.dispose()
        get_settings.cache_clear()

    assert [work["pmid"] for work in works] == ["11111111", "22222222", "33333333"]
    assert works[0]["title"] == "Vitamin D status and multiple sclerosis risk."
    assert works[0]["publication_year"] == 2021
    assert works[0]["primary_doi"] == "10.1000/vitd-ms.2021.001"
    assert works[1]["primary_doi"] == "10.1000/vitd-ms.2022.002"
    assert works[2]["primary_doi"] is None

    identifier_pairs = {(row["id_namespace"], row["id_value"]) for row in identifiers}
    assert identifier_pairs == {
        ("doi", "10.1000/vitd-ms.2021.001"),
        ("doi", "10.1000/vitd-ms.2022.002"),
        ("openalex", "https://openalex.org/W1111111111"),
        ("pmcid", "PMC1111111"),
        ("pmcid", "PMC2222222"),
        ("pmid", "11111111"),
        ("pmid", "22222222"),
        ("pmid", "33333333"),
    }
    assert len(source_links) == 14
    assert all(
        row["source_projection"]["source_snapshot_manifest_hash"].startswith("sha256:")
        for row in source_links
    )
    assert first_counts == {"works": 3, "identifiers": 8, "source_links": 14}
    assert repeat_counts == first_counts


def _fixture_projection_counts(connection) -> dict[str, int]:
    return {
        "works": connection.execute(
            text(
                "select count(*) from works "
                "where normalized_payload->>'projection_version' = :version"
            ),
            {"version": FIXTURE_WORK_PROJECTION_VERSION},
        ).scalar_one(),
        "identifiers": connection.execute(
            text(
                "select count(*) from work_identifiers wi "
                "join works w on w.work_id = wi.work_id "
                "where w.normalized_payload->>'projection_version' = :version"
            ),
            {"version": FIXTURE_WORK_PROJECTION_VERSION},
        ).scalar_one(),
        "source_links": connection.execute(
            text(
                "select count(*) from work_sources ws "
                "join works w on w.work_id = ws.work_id "
                "where w.normalized_payload->>'projection_version' = :version"
            ),
            {"version": FIXTURE_WORK_PROJECTION_VERSION},
        ).scalar_one(),
    }


def _delete_fixture_projection_rows(engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("delete from works where normalized_payload->>'projection_version' = :version"),
            {"version": FIXTURE_WORK_PROJECTION_VERSION},
        )
