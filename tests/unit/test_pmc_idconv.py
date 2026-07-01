from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from convivial_medicine.adapters.pmc.errors import PmcHTTPStatusError
from convivial_medicine.adapters.pmc.idconv import (
    PMC_IDCONV_ENDPOINT,
    build_idconv_params,
    process_idconv_response_bytes,
    run_idconv,
)
from convivial_medicine.adapters.pmc.persistence import (
    source_snapshot_db_values_from_pmc_idconv,
)
from convivial_medicine.adapters.pmc.request_fingerprint import (
    request_fingerprint,
    request_fingerprint_payload,
)
from convivial_medicine.config import Settings
from convivial_medicine.storage.artifacts import LocalArtifactStore

FIXTURE_PATH = Path("tests/fixtures/pmc/idconv_vitamin_d_ms_seed.json")
PMIDS = ("11111111", "22222222", "33333333")


def test_idconv_params_are_built_from_explicit_pmids() -> None:
    settings = Settings(NCBI_TOOL="convivial-test", NCBI_EMAIL="curator@example.org")

    params = build_idconv_params((" 11111111 ", "22222222", "33333333 "), settings=settings)

    assert params["ids"] == "11111111,22222222,33333333"
    assert params["idtype"] == "pmid"
    assert params["format"] == "json"
    assert params["tool"] == "convivial-test"
    assert params["email"] == "curator@example.org"
    assert "api_key" not in params


def test_idconv_params_reject_empty_pmids() -> None:
    with pytest.raises(ValueError, match="At least one PMID"):
        build_idconv_params((" ", ""))


def test_idconv_params_reject_more_than_200_pmids() -> None:
    pmids = tuple(str(index) for index in range(201))

    with pytest.raises(ValueError, match="at most 200 IDs"):
        build_idconv_params(pmids)


def test_idconv_request_fingerprint_is_deterministic_and_excludes_secrets() -> None:
    first = request_fingerprint(
        method="GET",
        endpoint=PMC_IDCONV_ENDPOINT,
        params={
            "ids": "11111111,22222222",
            "idtype": "pmid",
            "format": "json",
            "api_key": "secret-api-key",
        },
    )
    second = request_fingerprint(
        method="get",
        endpoint=PMC_IDCONV_ENDPOINT,
        params={
            "api_key": "different-secret-api-key",
            "format": "json",
            "idtype": "pmid",
            "ids": "11111111,22222222",
        },
    )
    payload = request_fingerprint_payload(
        method="GET",
        endpoint=PMC_IDCONV_ENDPOINT,
        params={
            "ids": "11111111",
            "idtype": "pmid",
            "format": "json",
            "api_key": "secret-api-key",
        },
    )

    assert first == second
    assert "api_key" not in payload["params"]
    assert "secret-api-key" not in json.dumps(payload, sort_keys=True)


def test_fixture_response_is_stored_before_parsed_result_is_returned(tmp_path: Path) -> None:
    raw_bytes = FIXTURE_PATH.read_bytes()

    result = process_idconv_response_bytes(
        raw_bytes=raw_bytes,
        artifact_store=LocalArtifactStore(tmp_path),
        endpoint=PMC_IDCONV_ENDPOINT,
        request_params=build_idconv_params(PMIDS),
        requested_pmids=PMIDS,
        http_status=200,
        content_type="application/json",
    )

    assert result.raw_artifact.path.exists()
    assert result.raw_artifact.path.read_bytes() == raw_bytes
    assert result.parsed.raw_payload_hash == result.raw_artifact.artifact_hash
    assert result.parsed.requested_pmids == PMIDS
    assert result.parsed.records_returned == 2
    assert result.parsed.pmcids_returned == 2
    assert result.parsed.returned_pmids == ("11111111", "22222222")
    assert result.parsed.missing_pmids == ("33333333",)
    assert result.provider_payload["status"] == "ok"


def test_fixture_parsing_captures_provider_fields_and_missing_pmids(tmp_path: Path) -> None:
    result = process_idconv_response_bytes(
        raw_bytes=FIXTURE_PATH.read_bytes(),
        artifact_store=LocalArtifactStore(tmp_path),
        endpoint=PMC_IDCONV_ENDPOINT,
        request_params=build_idconv_params(PMIDS),
        requested_pmids=PMIDS,
        http_status=200,
        content_type="application/json",
    )

    first = result.parsed.records_by_requested_pmid["11111111"]
    second = result.parsed.records_by_requested_pmid["22222222"]

    assert first.pmid == "11111111"
    assert first.pmcid == "PMC1111111"
    assert first.doi == "10.1000/vitd-ms.2021.001"
    assert first.live is True
    assert second.mid == "NIHMS222222"
    assert second.live is False
    assert second.release_date == "2026-12-15"
    assert "33333333" not in result.parsed.records_by_requested_pmid
    assert result.parsed.missing_pmids == ("33333333",)


def test_source_snapshot_manifest_includes_pmc_idconv_metadata(tmp_path: Path) -> None:
    result = process_idconv_response_bytes(
        raw_bytes=FIXTURE_PATH.read_bytes(),
        artifact_store=LocalArtifactStore(tmp_path),
        endpoint=PMC_IDCONV_ENDPOINT,
        request_params=build_idconv_params(PMIDS),
        requested_pmids=PMIDS,
        http_status=200,
        content_type="application/json; charset=UTF-8",
    )

    metadata = result.source_snapshot_manifest.metadata

    assert result.source_snapshot_manifest.payload_hash == result.raw_artifact.artifact_hash
    assert metadata["source_name"] == "pmc"
    assert metadata["operation"] == "idconv"
    assert metadata["endpoint"] == PMC_IDCONV_ENDPOINT
    assert metadata["http_status"] == 200
    assert metadata["content_type"] == "application/json; charset=UTF-8"
    assert metadata["request_params"]["ids"] == "11111111,22222222,33333333"
    assert metadata["request_params"]["idtype"] == "pmid"
    assert metadata["request_params"]["format"] == "json"
    assert metadata["request_fingerprint"].startswith("sha256:")


def test_idconv_persistence_mapping_redacts_secret_request_values(tmp_path: Path) -> None:
    params = {
        **build_idconv_params(
            PMIDS,
            settings=Settings(NCBI_TOOL="convivial-test", NCBI_EMAIL="curator@example.org"),
        ),
        "api_key": "secret-api-key",
    }
    result = process_idconv_response_bytes(
        raw_bytes=FIXTURE_PATH.read_bytes(),
        artifact_store=LocalArtifactStore(tmp_path),
        endpoint=PMC_IDCONV_ENDPOINT,
        request_params=params,
        requested_pmids=PMIDS,
        http_status=200,
        content_type="application/json",
    )

    values = source_snapshot_db_values_from_pmc_idconv(result)
    persisted_json = json.dumps(values["request_metadata"], sort_keys=True)

    assert "secret-api-key" not in persisted_json
    assert values["request_metadata"]["params"]["api_key"] == "<redacted>"
    assert values["source_name"] == "pmc"
    assert values["operation"] == "idconv"
    assert values["response_metadata"]["missing_pmids"] == ["33333333"]


def test_run_idconv_uses_injected_httpx_client_without_live_network(tmp_path: Path) -> None:
    raw_bytes = FIXTURE_PATH.read_bytes()
    seen_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_request
        seen_request = request
        return httpx.Response(
            status_code=200,
            content=raw_bytes,
            headers={"content-type": "application/json"},
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))

    result = run_idconv(
        pmids=PMIDS,
        artifact_store=LocalArtifactStore(tmp_path),
        settings=Settings(NCBI_TOOL="convivial-test", NCBI_EMAIL="curator@example.org"),
        client=client,
    )

    assert seen_request is not None
    assert seen_request.url.params["ids"] == "11111111,22222222,33333333"
    assert seen_request.url.params["idtype"] == "pmid"
    assert seen_request.url.params["format"] == "json"
    assert seen_request.url.params["tool"] == "convivial-test"
    assert seen_request.url.params["email"] == "curator@example.org"
    assert result.parsed.records_returned == 2


def test_run_idconv_accepts_injected_transport_without_live_network(tmp_path: Path) -> None:
    raw_bytes = FIXTURE_PATH.read_bytes()
    seen_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_request
        seen_request = request
        return httpx.Response(
            status_code=200,
            content=raw_bytes,
            headers={"content-type": "application/json"},
            request=request,
        )

    result = run_idconv(
        pmids=PMIDS,
        artifact_store=LocalArtifactStore(tmp_path),
        settings=Settings(NCBI_TOOL="convivial-test", NCBI_EMAIL="curator@example.org"),
        transport=httpx.MockTransport(handler),
    )

    assert seen_request is not None
    assert seen_request.url.params["ids"] == "11111111,22222222,33333333"
    assert result.parsed.missing_pmids == ("33333333",)


def test_run_idconv_preserves_non_2xx_response_before_raising(tmp_path: Path) -> None:
    raw_bytes = b'{"status": "error", "message": "temporarily unavailable"}'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=503,
            content=raw_bytes,
            headers={"content-type": "application/json"},
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(PmcHTTPStatusError) as exc_info:
        run_idconv(
            pmids=PMIDS,
            artifact_store=LocalArtifactStore(tmp_path),
            settings=Settings(NCBI_TOOL="convivial-test", NCBI_EMAIL="curator@example.org"),
            client=client,
        )

    exc = exc_info.value
    assert exc.operation == "idconv"
    assert exc.http_status == 503
    assert exc.content_type == "application/json"
    assert exc.raw_payload_hash.startswith("sha256:")
    assert exc.raw_artifact_uri.startswith("artifact://sha256/")
    assert exc.source_snapshot_manifest_hash.startswith("sha256:")
    assert LocalArtifactStore(tmp_path).read_bytes(exc.raw_payload_hash) == raw_bytes
