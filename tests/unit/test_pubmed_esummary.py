from __future__ import annotations

import json
from pathlib import Path

import httpx

from convivial_medicine.adapters.pubmed.esummary import (
    PUBMED_ESUMMARY_ENDPOINT,
    build_esummary_params,
    process_esummary_response_bytes,
    run_esummary,
)
from convivial_medicine.adapters.pubmed.persistence import (
    source_snapshot_db_values_from_pubmed_esummary,
)
from convivial_medicine.adapters.pubmed.request_fingerprint import (
    request_fingerprint,
    request_fingerprint_payload,
)
from convivial_medicine.config import Settings
from convivial_medicine.storage.artifacts import LocalArtifactStore

FIXTURE_PATH = Path("tests/fixtures/pubmed/esummary_vitamin_d_ms_seed.json")
PMIDS = ("11111111", "22222222", "33333333")


def test_esummary_params_are_built_from_explicit_pmids() -> None:
    settings = Settings(
        NCBI_TOOL="convivial-test",
        NCBI_EMAIL="curator@example.org",
        NCBI_API_KEY="secret-api-key",
    )

    params = build_esummary_params(PMIDS, settings=settings)

    assert params["db"] == "pubmed"
    assert params["id"] == "11111111,22222222,33333333"
    assert params["retmode"] == "json"
    assert params["version"] == "2.0"
    assert params["tool"] == "convivial-test"
    assert params["email"] == "curator@example.org"
    assert params["api_key"] == "secret-api-key"


def test_esummary_request_fingerprint_is_independent_of_param_order() -> None:
    first = request_fingerprint(
        method="GET",
        endpoint=PUBMED_ESUMMARY_ENDPOINT,
        params={"db": "pubmed", "id": "11111111,22222222", "retmode": "json"},
    )
    second = request_fingerprint(
        method="get",
        endpoint=PUBMED_ESUMMARY_ENDPOINT,
        params={"retmode": "json", "id": "11111111,22222222", "db": "pubmed"},
    )

    assert first == second


def test_esummary_request_fingerprint_payload_excludes_api_key() -> None:
    payload = request_fingerprint_payload(
        method="GET",
        endpoint=PUBMED_ESUMMARY_ENDPOINT,
        params={"db": "pubmed", "id": "11111111", "api_key": "secret-api-key"},
    )

    assert "api_key" not in payload["params"]
    assert "secret-api-key" not in json.dumps(payload, sort_keys=True)


def test_fixture_response_is_stored_before_parsed_result_is_returned(tmp_path: Path) -> None:
    raw_bytes = FIXTURE_PATH.read_bytes()

    result = process_esummary_response_bytes(
        raw_bytes=raw_bytes,
        artifact_store=LocalArtifactStore(tmp_path),
        endpoint=PUBMED_ESUMMARY_ENDPOINT,
        request_params=build_esummary_params(PMIDS),
        requested_pmids=PMIDS,
        http_status=200,
        content_type="application/json",
    )

    assert result.raw_artifact.path.exists()
    assert result.raw_artifact.path.read_bytes() == raw_bytes
    assert result.parsed.raw_payload_hash == result.raw_artifact.artifact_hash
    assert result.parsed.requested_pmids == PMIDS
    assert result.parsed.returned_pmids == PMIDS
    assert result.parsed.summaries_returned == 3
    assert result.parsed.summaries[0].title == "Vitamin D status and multiple sclerosis risk."
    assert result.parsed.summaries[0].source == "Neurology"
    assert result.parsed.summaries[0].pub_year == 2021
    assert result.parsed.summaries[0].doi == "10.1000/vitd-ms.2021.001"


def test_source_snapshot_manifest_includes_pubmed_esummary_metadata(tmp_path: Path) -> None:
    result = process_esummary_response_bytes(
        raw_bytes=FIXTURE_PATH.read_bytes(),
        artifact_store=LocalArtifactStore(tmp_path),
        endpoint=PUBMED_ESUMMARY_ENDPOINT,
        request_params=build_esummary_params(PMIDS),
        requested_pmids=PMIDS,
        http_status=200,
        content_type="application/json; charset=UTF-8",
    )

    metadata = result.source_snapshot_manifest.metadata

    assert result.source_snapshot_manifest.payload_hash == result.raw_artifact.artifact_hash
    assert metadata["source_name"] == "pubmed"
    assert metadata["operation"] == "esummary"
    assert metadata["endpoint"] == PUBMED_ESUMMARY_ENDPOINT
    assert metadata["http_status"] == 200
    assert metadata["content_type"] == "application/json; charset=UTF-8"
    assert metadata["request_params"]["id"] == "11111111,22222222,33333333"
    assert metadata["request_fingerprint"].startswith("sha256:")


def test_esummary_persistence_mapping_redacts_secret_request_values(tmp_path: Path) -> None:
    params = build_esummary_params(
        PMIDS,
        settings=Settings(
            NCBI_TOOL="convivial-test",
            NCBI_EMAIL="curator@example.org",
            NCBI_API_KEY="secret-api-key",
        ),
    )
    result = process_esummary_response_bytes(
        raw_bytes=FIXTURE_PATH.read_bytes(),
        artifact_store=LocalArtifactStore(tmp_path),
        endpoint=PUBMED_ESUMMARY_ENDPOINT,
        request_params=params,
        requested_pmids=PMIDS,
        http_status=200,
        content_type="application/json",
    )

    values = source_snapshot_db_values_from_pubmed_esummary(result)
    persisted_json = json.dumps(values["request_metadata"], sort_keys=True)

    assert "secret-api-key" not in persisted_json
    assert values["request_metadata"]["params"]["api_key"] == "<redacted>"


def test_run_esummary_uses_injected_httpx_client_without_live_network(tmp_path: Path) -> None:
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

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    result = run_esummary(
        pmids=PMIDS,
        artifact_store=LocalArtifactStore(tmp_path),
        settings=Settings(NCBI_TOOL="convivial-test", NCBI_EMAIL="curator@example.org"),
        client=client,
    )

    assert seen_request is not None
    assert seen_request.url.params["db"] == "pubmed"
    assert seen_request.url.params["id"] == "11111111,22222222,33333333"
    assert seen_request.url.params["tool"] == "convivial-test"
    assert seen_request.url.params["email"] == "curator@example.org"
    assert result.parsed.summaries_returned == 3
