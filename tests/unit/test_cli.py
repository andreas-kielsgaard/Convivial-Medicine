from __future__ import annotations

import json
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
PMC_BIOC_FIXTURE_PATH = Path("tests/fixtures/pmc/bioc_vitamin_d_ms_seed.json")
OPENALEX_FIXTURE_PATH = Path("tests/fixtures/openalex/work_vitamin_d_ms_seed.json")


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
        ["build", "normalize-works", "--help"],
        ["fetch", "pubmed-summary", "--help"],
        ["fetch", "pubmed-records", "--help"],
        ["enrich", "pmc-idconv", "--help"],
        ["fetch", "pmc-bioc", "--help"],
        ["enrich", "openalex", "--help"],
        ["validate", "build", "--help"],
        ["export", "slice", "--help"],
        ["audit", "lineage", "--help"],
        ["audit", "phase-one", "--help"],
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


def test_seed_build_default_uses_fixture_mode_without_network(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    def fail_live_call(**_: object) -> object:
        raise AssertionError("live source call should not run")

    monkeypatch.setattr("convivial_medicine.orchestration.seed.run_esearch", fail_live_call)
    monkeypatch.setattr("convivial_medicine.orchestration.seed.run_esummary", fail_live_call)
    monkeypatch.setattr("convivial_medicine.orchestration.seed.run_efetch", fail_live_call)
    monkeypatch.setattr("convivial_medicine.orchestration.seed.run_idconv", fail_live_call)
    monkeypatch.setattr("convivial_medicine.orchestration.seed.run_bioc", fail_live_call)
    monkeypatch.setattr("convivial_medicine.orchestration.seed.run_openalex_work", fail_live_call)

    result = runner.invoke(
        app,
        [
            "build",
            "seed",
            "--manifest",
            "manifests/vitamin_D_ms_seed_v1.json",
            "--artifact-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "mode: fixture" in result.output
    assert "pubmed_esearch.pmids_returned: 3" in result.output
    assert "pmc_bioc.requests: 1" in result.output
    assert "openalex.requested_id: 11111111" in result.output
    assert "source_snapshots: 6" in result.output
    assert "db_persisted: False" in result.output
    assert (
        f"build_report: {tmp_path / 'build-reports' / 'vitamin_D_ms_seed_v1.json'}" in result.output
    )
    assert any((tmp_path / "sha256").glob("*/*"))


def test_seed_build_writes_report(tmp_path: Path) -> None:
    report_path = tmp_path / "build-reports" / "vitamin_D_ms_seed_v1.json"

    result = runner.invoke(
        app,
        [
            "build",
            "seed",
            "--manifest",
            "manifests/vitamin_D_ms_seed_v1.json",
            "--artifact-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert report_path.is_file()
    assert f"build_report: {report_path}" in result.output
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["manifest_name"] == "vitamin_D_ms_seed_v1"
    assert report["manifest_hash"].startswith("sha256:")
    assert report["mode"] == "fixture"
    assert report["step_order"] == [
        "pubmed_esearch",
        "pubmed_esummary",
        "pubmed_efetch",
        "pmc_idconv",
        "pmc_bioc",
        "openalex_work",
    ]
    assert len(report["source_snapshot_manifest_hashes"]) == 6
    assert len(report["raw_artifact_hashes"]) == 6
    assert report["counts"] == {
        "raw_artifacts": 6,
        "source_snapshots": 6,
        "steps": 6,
    }
    assert report["db_persisted"] is False


def test_seed_build_live_requires_opt_in_credentials(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.delenv("NCBI_EMAIL", raising=False)
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    get_settings.cache_clear()

    result = runner.invoke(
        app,
        [
            "build",
            "seed",
            "--live",
            "--artifact-root",
            str(tmp_path),
        ],
    )

    get_settings.cache_clear()
    assert result.exit_code == 1
    assert "NCBI_EMAIL is required for --live seed builds" in result.output


def test_normalize_works_requires_database_persistence() -> None:
    result = runner.invoke(app, ["build", "normalize-works"])

    assert result.exit_code == 2
    assert "--persist-db is required for corpus build normalize-works" in result.output


def test_normalize_works_fails_if_build_validation_fails(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    def fail_db_check(*_: object) -> object:
        raise AssertionError("database check should not run before validation passes")

    monkeypatch.setattr("convivial_medicine.cli.main.check_database_connection", fail_db_check)

    result = runner.invoke(
        app,
        [
            "build",
            "normalize-works",
            "--manifest",
            "manifests/vitamin_D_ms_seed_v1.json",
            "--artifact-root",
            str(tmp_path / "missing-artifacts"),
            "--persist-db",
        ],
    )

    assert result.exit_code == 1
    assert "Build validation failed; normalization skipped." in result.output
    assert "status: failed" in result.output
    assert "artifact root is missing" in result.output


def test_validate_build_passes_for_completed_fixture_seed(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    build_result = runner.invoke(
        app,
        [
            "build",
            "seed",
            "--manifest",
            "manifests/vitamin_D_ms_seed_v1.json",
            "--artifact-root",
            str(artifact_root),
        ],
    )
    assert build_result.exit_code == 0, build_result.output

    result = runner.invoke(
        app,
        [
            "validate",
            "build",
            "--manifest",
            "manifests/vitamin_D_ms_seed_v1.json",
            "--artifact-root",
            str(artifact_root),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "status: ok" in result.output
    assert (
        f"build_report: {artifact_root / 'build-reports' / 'vitamin_D_ms_seed_v1.json'}"
        in result.output
    )
    assert "build_report_present: True" in result.output
    assert "steps: 6/6" in result.output
    assert "source_snapshots: 6/6" in result.output
    assert "raw_artifacts: 6/6" in result.output
    assert "manifest_hash: sha256:" in result.output
    assert "raw_artifact_hashes: sha256:" in result.output
    assert "source_snapshot_manifest_hashes: sha256:" in result.output
    assert "missing_raw_artifacts: none" in result.output
    assert "errors: none" in result.output


def test_validate_build_fails_when_artifact_root_is_missing(tmp_path: Path) -> None:
    artifact_root = tmp_path / "missing-artifacts"

    result = runner.invoke(
        app,
        [
            "validate",
            "build",
            "--manifest",
            "manifests/vitamin_D_ms_seed_v1.json",
            "--artifact-root",
            str(artifact_root),
        ],
    )

    assert result.exit_code == 1
    assert "status: failed" in result.output
    assert "raw_artifacts: 0/6" in result.output
    assert "missing_raw_artifacts: sha256:" in result.output
    assert "artifact root is missing" in result.output
    assert "missing raw artifacts: 6" in result.output


def test_validate_build_fails_when_report_is_missing(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    build_result = runner.invoke(
        app,
        [
            "build",
            "seed",
            "--manifest",
            "manifests/vitamin_D_ms_seed_v1.json",
            "--artifact-root",
            str(artifact_root),
        ],
    )
    assert build_result.exit_code == 0, build_result.output

    report_path = artifact_root / "build-reports" / "vitamin_D_ms_seed_v1.json"
    report_path.unlink()

    result = runner.invoke(
        app,
        [
            "validate",
            "build",
            "--manifest",
            "manifests/vitamin_D_ms_seed_v1.json",
            "--artifact-root",
            str(artifact_root),
        ],
    )

    assert result.exit_code == 1
    assert "status: failed" in result.output
    assert "build_report_present: False" in result.output
    assert "raw_artifacts: 6/6" in result.output
    assert "build report is missing" in result.output


def test_validate_build_fails_when_artifact_root_is_incomplete(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    build_result = runner.invoke(
        app,
        [
            "build",
            "seed",
            "--manifest",
            "manifests/vitamin_D_ms_seed_v1.json",
            "--artifact-root",
            str(artifact_root),
        ],
    )
    assert build_result.exit_code == 0, build_result.output

    next((artifact_root / "sha256").glob("*/*")).unlink()

    result = runner.invoke(
        app,
        [
            "validate",
            "build",
            "--manifest",
            "manifests/vitamin_D_ms_seed_v1.json",
            "--artifact-root",
            str(artifact_root),
        ],
    )

    assert result.exit_code == 1
    assert "status: failed" in result.output
    assert "raw_artifacts: 5/6" in result.output
    assert "missing_raw_artifacts: sha256:" in result.output
    assert "missing raw artifacts: 1" in result.output


def test_validate_build_fails_when_report_hash_list_disagrees_with_artifacts(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "artifacts"
    build_result = runner.invoke(
        app,
        [
            "build",
            "seed",
            "--manifest",
            "manifests/vitamin_D_ms_seed_v1.json",
            "--artifact-root",
            str(artifact_root),
        ],
    )
    assert build_result.exit_code == 0, build_result.output

    report_path = artifact_root / "build-reports" / "vitamin_D_ms_seed_v1.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["raw_artifact_hashes"][0] = "sha256:" + "f" * 64
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "validate",
            "build",
            "--manifest",
            "manifests/vitamin_D_ms_seed_v1.json",
            "--artifact-root",
            str(artifact_root),
        ],
    )

    assert result.exit_code == 1
    assert "status: failed" in result.output
    assert "build_report_present: True" in result.output
    assert "raw_artifacts: 5/6" in result.output
    assert "missing_raw_artifacts: sha256:" in result.output
    assert "raw artifact hash list mismatch" in result.output
    assert "missing raw artifacts: 1" in result.output


def test_export_slice_succeeds_after_fixture_build(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    output_path = tmp_path / "slice.json"
    build_result = runner.invoke(
        app,
        [
            "build",
            "seed",
            "--manifest",
            "manifests/vitamin_D_ms_seed_v1.json",
            "--artifact-root",
            str(artifact_root),
        ],
    )
    assert build_result.exit_code == 0, build_result.output

    result = runner.invoke(
        app,
        [
            "export",
            "slice",
            "--manifest",
            "manifests/vitamin_D_ms_seed_v1.json",
            "--artifact-root",
            str(artifact_root),
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "status: ok" in result.output
    assert f"output: {output_path}" in result.output
    assert output_path.is_file()

    output_text = output_path.read_text(encoding="utf-8")
    payload = json.loads(output_text)
    assert payload["schema_version"] == "fixture-slice-export-v1"
    assert payload["manifest"]["name"] == "vitamin_D_ms_seed_v1"
    assert payload["manifest"]["hash"].startswith("sha256:")
    assert payload["build_report"]["counts"] == {
        "raw_artifacts": 6,
        "source_snapshots": 6,
        "steps": 6,
    }
    assert [step["name"] for step in payload["source_steps"]] == [
        "pubmed_esearch",
        "pubmed_esummary",
        "pubmed_efetch",
        "pmc_idconv",
        "pmc_bioc",
        "openalex_work",
    ]
    assert len(payload["raw_artifact_hashes"]) == 6
    assert len(payload["source_snapshot_manifest_hashes"]) == 6
    assert payload["source_steps"][0]["parsed_summary"]["pmids"] == [
        "11111111",
        "22222222",
        "33333333",
    ]
    assert payload["source_steps"][4]["parsed_summary"]["passage_count"] == 3
    assert "A short fixture abstract passage" not in output_text


def test_export_slice_fails_if_validation_fails(tmp_path: Path) -> None:
    artifact_root = tmp_path / "missing-artifacts"
    output_path = tmp_path / "slice.json"

    result = runner.invoke(
        app,
        [
            "export",
            "slice",
            "--manifest",
            "manifests/vitamin_D_ms_seed_v1.json",
            "--artifact-root",
            str(artifact_root),
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 1
    assert not output_path.exists()
    assert "Build validation failed; export skipped." in result.output
    assert "status: failed" in result.output
    assert "artifact root is missing" in result.output


def test_export_slice_output_is_stable_for_key_fields(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    first_output_path = tmp_path / "slice-first.json"
    second_output_path = tmp_path / "slice-second.json"
    build_result = runner.invoke(
        app,
        [
            "build",
            "seed",
            "--manifest",
            "manifests/vitamin_D_ms_seed_v1.json",
            "--artifact-root",
            str(artifact_root),
        ],
    )
    assert build_result.exit_code == 0, build_result.output

    for output_path in (first_output_path, second_output_path):
        result = runner.invoke(
            app,
            [
                "export",
                "slice",
                "--manifest",
                "manifests/vitamin_D_ms_seed_v1.json",
                "--artifact-root",
                str(artifact_root),
                "--output",
                str(output_path),
            ],
        )
        assert result.exit_code == 0, result.output

    assert first_output_path.read_text(encoding="utf-8") == second_output_path.read_text(
        encoding="utf-8"
    )
    payload = json.loads(first_output_path.read_text(encoding="utf-8"))
    assert payload["source_steps"][1]["parsed_summary"]["articles"][0] == {
        "doi": "10.1000/vitd-ms.2021.001",
        "pmid": "11111111",
        "pub_year": 2021,
        "pubdate": "2021 Mar",
        "source": "Neurology",
        "title": "Vitamin D status and multiple sclerosis risk.",
    }
    assert payload["source_steps"][5]["parsed_summary"]["openalex_id"] == (
        "https://openalex.org/W1111111111"
    )


def test_audit_phase_one_passes_after_fixture_build(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    build_result = runner.invoke(
        app,
        [
            "build",
            "seed",
            "--manifest",
            "manifests/vitamin_D_ms_seed_v1.json",
            "--artifact-root",
            str(artifact_root),
        ],
    )
    assert build_result.exit_code == 0, build_result.output

    result = runner.invoke(
        app,
        [
            "audit",
            "phase-one",
            "--manifest",
            "manifests/vitamin_D_ms_seed_v1.json",
            "--artifact-root",
            str(artifact_root),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "PASS build_report:" in result.output
    assert "PASS validation: raw_artifacts=6/6 source_snapshots=6/6" in result.output
    assert "PASS slice_export: source_steps=6 raw_artifacts=6 source_snapshots=6" in result.output
    assert "db_projection" not in result.output
    assert "status: ok" in result.output


def test_audit_phase_one_fails_when_artifacts_are_missing(tmp_path: Path) -> None:
    artifact_root = tmp_path / "missing-artifacts"

    result = runner.invoke(
        app,
        [
            "audit",
            "phase-one",
            "--manifest",
            "manifests/vitamin_D_ms_seed_v1.json",
            "--artifact-root",
            str(artifact_root),
        ],
    )

    assert result.exit_code == 1
    assert "FAIL build_report: missing" in result.output
    assert "FAIL validation:" in result.output
    assert "artifact root is missing" in result.output
    assert "build report is missing" in result.output
    assert "FAIL slice_export: validation failed" in result.output
    assert "status: failed" in result.output


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


def test_pmc_bioc_default_does_not_call_network() -> None:
    result = runner.invoke(app, ["fetch", "pmc-bioc"])

    assert result.exit_code == 0
    assert "No PMC BioC fetch run" in result.output
    assert "--fixture PATH" in result.output
    assert "--live" in result.output


def test_pmc_bioc_fixture_mode_prints_summary(tmp_path) -> None:
    result = runner.invoke(
        app,
        [
            "fetch",
            "pmc-bioc",
            "--id",
            "PMC1111111",
            "--fixture",
            str(PMC_BIOC_FIXTURE_PATH),
            "--artifact-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert "document_detected: True" in result.output
    assert "document_count: 1" in result.output
    assert "passage_count: 3" in result.output
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


def test_openalex_default_does_not_call_network() -> None:
    result = runner.invoke(app, ["enrich", "openalex"])

    assert result.exit_code == 0
    assert "No OpenAlex enrichment run" in result.output
    assert "--fixture PATH" in result.output
    assert "--live" in result.output


def test_openalex_requires_exactly_one_identifier_for_fixture_mode() -> None:
    result = runner.invoke(
        app,
        [
            "enrich",
            "openalex",
            "--doi",
            "10.1000/vitd-ms.2021.001",
            "--pmid",
            "11111111",
            "--fixture",
            str(OPENALEX_FIXTURE_PATH),
        ],
    )

    assert result.exit_code == 2
    assert "Pass exactly one of --doi, --pmid, or --openalex-id" in result.output


def test_openalex_fixture_mode_prints_summary(tmp_path) -> None:
    result = runner.invoke(
        app,
        [
            "enrich",
            "openalex",
            "--pmid",
            "11111111",
            "--fixture",
            str(OPENALEX_FIXTURE_PATH),
            "--artifact-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert "openalex_id: https://openalex.org/W1111111111" in result.output
    assert "doi: https://doi.org/10.1000/vitd-ms.2021.001" in result.output
    assert "pmid: 11111111" in result.output
    assert "publication_year: 2021" in result.output
    assert "cited_by_count: 42" in result.output
    assert "is_retracted: False" in result.output
    assert "raw_payload_hash: sha256:" in result.output
    assert "manifest_hash: sha256:" in result.output
    assert "db_persisted: False" in result.output
    assert any((tmp_path / "sha256").glob("*/*"))


def test_openalex_live_requires_api_key(tmp_path) -> None:
    result = runner.invoke(
        app,
        [
            "enrich",
            "openalex",
            "--pmid",
            "11111111",
            "--live",
            "--artifact-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 1
    assert "OPENALEX_API_KEY is required" in result.output


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


def test_openalex_live_http_error_exits_nonzero_with_artifact_details(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    from convivial_medicine.adapters.openalex.errors import OpenAlexHTTPStatusError

    def fail_openalex(**_: object) -> object:
        raise OpenAlexHTTPStatusError(
            operation="work",
            endpoint="https://api.openalex.org/works/W0000000000",
            http_status=404,
            content_type="application/json",
            raw_payload_hash="sha256:" + "a" * 64,
            raw_artifact_uri="artifact://sha256/aa/" + "a" * 64,
            source_snapshot_manifest_hash="sha256:" + "b" * 64,
            request_fingerprint="sha256:" + "c" * 64,
            request_metadata={"params": {"api_key": "<redacted>"}},
            original_http_message="Not Found",
        )

    monkeypatch.setenv("OPENALEX_API_KEY", "secret-test-key")
    get_settings.cache_clear()
    monkeypatch.setattr("convivial_medicine.cli.main.run_openalex_work", fail_openalex)

    result = runner.invoke(
        app,
        [
            "enrich",
            "openalex",
            "--openalex-id",
            "W0000000000",
            "--live",
            "--artifact-root",
            str(tmp_path),
        ],
    )

    get_settings.cache_clear()
    assert result.exit_code == 1
    assert "OpenAlex work failed with HTTP 404" in result.output
    assert "raw_payload_hash=sha256:" in result.output
    assert "manifest_hash=sha256:" in result.output
    assert "raw_artifact_uri=artifact://sha256/" in result.output
