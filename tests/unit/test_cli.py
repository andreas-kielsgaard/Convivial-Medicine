from __future__ import annotations

from typer.testing import CliRunner

from convivial_medicine.cli.main import app

runner = CliRunner()


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


def test_placeholder_command_message() -> None:
    result = runner.invoke(app, ["query", "pubmed"])

    assert result.exit_code == 0
    assert "not implemented in this bootstrap branch" in result.output
