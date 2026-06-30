from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from convivial_medicine.cli.main import app

runner = CliRunner()
FIXTURE_PATH = Path("tests/fixtures/pubmed/esearch_vitamin_d_ms_seed.json")


def test_root_help() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "doctor" in result.output
    assert "query" in result.output
    assert "build" in result.output


def test_doctor() -> None:
    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "package: convivial_medicine" in result.output
    assert "status: ok" in result.output


def test_nested_command_help() -> None:
    commands = [
        ["query", "pubmed", "--help"],
        ["build", "seed", "--help"],
        ["fetch", "pubmed-summary", "--help"],
        ["fetch", "pubmed-records", "--help"],
        ["enrich", "pmc-idconv", "--help"],
        ["fetch", "pmc-bioc", "--help"],
        ["enrich", "openalex", "--help"],
        ["validate", "build", "--help"],
        ["export", "slice", "--help"],
        ["audit", "lineage", "--help"],
    ]

    for command in commands:
        result = runner.invoke(app, command)
        assert result.exit_code == 0
        assert "Usage" in result.output


def test_pubmed_query_default_does_not_call_network() -> None:
    result = runner.invoke(app, ["query", "pubmed"])

    assert result.exit_code == 0
    assert "No PubMed query run" in result.output
    assert "--fixture PATH" in result.output
    assert "--live" in result.output


def test_pubmed_query_fixture_mode_prints_summary(tmp_path) -> None:
    result = runner.invoke(
        app,
        [
            "query",
            "pubmed",
            "--fixture",
            str(FIXTURE_PATH),
            "--artifact-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert "count: 123" in result.output
    assert "pmids_returned: 3" in result.output
    assert "webenv_present: True" in result.output
    assert "query_key_present: True" in result.output
    assert "raw_payload_hash: sha256:" in result.output
    assert "manifest_hash: sha256:" in result.output
    assert any((tmp_path / "sha256").glob("*/*"))
