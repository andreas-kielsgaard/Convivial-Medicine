from __future__ import annotations

from pathlib import Path

from pytest import MonkeyPatch
from typer.testing import CliRunner

from convivial_medicine.adapters.pmc.errors import PmcHTTPStatusError
from convivial_medicine.adapters.pubmed.errors import PubMedHTTPStatusError
from convivial_medicine.cli.main import app
from convivial_medicine.config import get_settings

runner = CliRunner()
FIXTURE_PATH = Path("tests/fixtures/pubmed/esearch_vitamin_d_ms_seed.json")
ESUMMARY_FIXTURE_PATH = Path("tests/fixtures/pubmed/esummary_vitamin_d_ms_seed.json")
EFETCH_FIXTURE_PATH = Path("tests/fixtures/pubmed/efetch_vitamin_d_ms_seed.xml")
PMC_IDCONV_FIXTURE_PATH = Path("tests/fixtures/pmc/idconv_vitamin_d_ms_seed.json")


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
    assert "db_persisted: False" in result.output
    assert any((tmp_path / "sha256").glob("*/*"))


def test_pubmed_summary_default_does_not_call_network() -> None:
    result = runner.invoke(app, ["fetch", "pubmed-summary"])

    assert result.exit_code == 0
    assert "No PubMed summary fetch run" in result.output
    assert "--fixture PATH" in result.output
    assert "--live" in result.output


def test_pubmed_summary_fixture_mode_prints_summary(tmp_path) -> None:
    result = runner.invoke(
        app,
        [
            "fetch",
            "pubmed-summary",
            "--pmids",
            "11111111,22222222,33333333",
            "--fixture",
            str(ESUMMARY_FIXTURE_PATH),
            "--artifact-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert "summaries_returned: 3" in result.output
    assert "pmids_returned: 3" in result.output
    assert "raw_payload_hash: sha256:" in result.output
    assert "manifest_hash: sha256:" in result.output
    assert "db_persisted: False" in result.output
    assert any((tmp_path / "sha256").glob("*/*"))


def test_pubmed_records_default_does_not_call_network() -> None:
    result = runner.invoke(app, ["fetch", "pubmed-records"])

    assert result.exit_code == 0
    assert "No PubMed record fetch run" in result.output
    assert "--fixture PATH" in result.output
    assert "--live" in result.output


def test_pubmed_records_fixture_mode_prints_summary(tmp_path) -> None:
    result = runner.invoke(
        app,
        [
            "fetch",
            "pubmed-records",
            "--pmids",
            "11111111,22222222,33333333",
            "--fixture",
            str(EFETCH_FIXTURE_PATH),
            "--artifact-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert "records_returned: 3" in result.output
    assert "pmids_returned: 3" in result.output
    assert "raw_payload_hash: sha256:" in result.output
    assert "manifest_hash: sha256:" in result.output
    assert "db_persisted: False" in result.output
    assert any((tmp_path / "sha256").glob("*/*"))


def test_pmc_idconv_default_does_not_call_network() -> None:
    result = runner.invoke(app, ["enrich", "pmc-idconv"])

    assert result.exit_code == 0
    assert "No PMC ID Converter enrichment run" in result.output
    assert "--fixture PATH" in result.output
    assert "--live" in result.output


def test_pmc_idconv_fixture_mode_prints_summary(tmp_path) -> None:
    result = runner.invoke(
        app,
        [
            "enrich",
            "pmc-idconv",
            "--pmids",
            "11111111,22222222,33333333",
            "--fixture",
            str(PMC_IDCONV_FIXTURE_PATH),
            "--artifact-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert "records_returned: 2" in result.output
    assert "pmcids_returned: 2" in result.output
    assert "missing_pmids: 33333333" in result.output
    assert "raw_payload_hash: sha256:" in result.output
    assert "manifest_hash: sha256:" in result.output
    assert "db_persisted: False" in result.output
    assert any((tmp_path / "sha256").glob("*/*"))


def test_pubmed_query_live_http_error_exits_nonzero_with_artifact_details(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    def fail_esearch(**_: object) -> object:
        raise PubMedHTTPStatusError(
            operation="esearch",
            endpoint="https://example.test/esearch.fcgi",
            http_status=429,
            content_type="text/plain",
            raw_payload_hash="sha256:" + "a" * 64,
            raw_artifact_uri="artifact://sha256/aa/" + "a" * 64,
            source_snapshot_manifest_hash="sha256:" + "b" * 64,
            request_fingerprint="sha256:" + "c" * 64,
            request_metadata={"params": {"api_key": "<redacted>"}},
            original_http_message="Too Many Requests",
        )

    monkeypatch.setenv("NCBI_EMAIL", "curator@example.org")
    get_settings.cache_clear()
    monkeypatch.setattr("convivial_medicine.cli.main.run_esearch", fail_esearch)

    result = runner.invoke(
        app,
        [
            "query",
            "pubmed",
            "--live",
            "--artifact-root",
            str(tmp_path),
        ],
    )

    get_settings.cache_clear()
    assert result.exit_code == 1
    assert "PubMed esearch failed with HTTP 429" in result.output
    assert "raw_payload_hash=sha256:" in result.output
    assert "manifest_hash=sha256:" in result.output
    assert "raw_artifact_uri=artifact://sha256/" in result.output


def test_pmc_idconv_live_http_error_exits_nonzero_with_artifact_details(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    def fail_idconv(**_: object) -> object:
        raise PmcHTTPStatusError(
            operation="idconv",
            endpoint="https://example.test/idconv",
            http_status=503,
            content_type="application/json",
            raw_payload_hash="sha256:" + "a" * 64,
            raw_artifact_uri="artifact://sha256/aa/" + "a" * 64,
            source_snapshot_manifest_hash="sha256:" + "b" * 64,
            request_fingerprint="sha256:" + "c" * 64,
            request_metadata={"params": {}},
            original_http_message="Service Unavailable",
        )

    monkeypatch.setenv("NCBI_EMAIL", "curator@example.org")
    get_settings.cache_clear()
    monkeypatch.setattr("convivial_medicine.cli.main.run_idconv", fail_idconv)

    result = runner.invoke(
        app,
        [
            "enrich",
            "pmc-idconv",
            "--pmids",
            "11111111",
            "--live",
            "--artifact-root",
            str(tmp_path),
        ],
    )

    get_settings.cache_clear()
    assert result.exit_code == 1
    assert "PMC idconv failed with HTTP 503" in result.output
    assert "raw_payload_hash=sha256:" in result.output
    assert "manifest_hash=sha256:" in result.output
    assert "raw_artifact_uri=artifact://sha256/" in result.output
