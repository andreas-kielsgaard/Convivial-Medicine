from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from convivial_medicine.adapters.pubmed.errors import PubMedHTTPStatusError
from convivial_medicine.adapters.pubmed.esearch import (
    PUBMED_ESEARCH_ENDPOINT,
    build_esearch_params,
    process_esearch_response_bytes,
    run_esearch,
)
from convivial_medicine.adapters.pubmed.request_fingerprint import (
    request_fingerprint,
    request_fingerprint_payload,
)
from convivial_medicine.config import Settings
from convivial_medicine.domain.manifests import load_query_manifest
from convivial_medicine.storage.artifacts import LocalArtifactStore

SEED_MANIFEST_PATH = Path("manifests/vitamin_D_ms_seed_v1.json")
FIXTURE_PATH = Path("tests/fixtures/pubmed/esearch_vitamin_d_ms_seed.json")


def test_esearch_params_are_built_from_seed_manifest() -> None:
    manifest = load_query_manifest(SEED_MANIFEST_PATH)
    settings = Settings(
        NCBI_TOOL="convivial-test",
        NCBI_EMAIL="curator@example.org",
        NCBI_API_KEY="secret-api-key",
    )

    params = build_esearch_params(manifest, settings=settings)

    assert params["db"] == "pubmed"
    assert params["term"] == manifest.term
    assert params["retmode"] == "json"
    assert params["retmax"] == "50"
    assert params["usehistory"] == "y"
    assert params["tool"] == "convivial-test"
    assert params["email"] == "curator@example.org"
    assert params["api_key"] == "secret-api-key"


def test_request_fingerprint_is_independent_of_param_order() -> None:
    first = request_fingerprint(
        method="get",
        endpoint=PUBMED_ESEARCH_ENDPOINT,
        params={"term": "vitamin D", "db": "pubmed", "retmax": "50"},
    )
    second = request_fingerprint(
        method="GET",
        endpoint=PUBMED_ESEARCH_ENDPOINT,
        params={"retmax": "50", "db": "pubmed", "term": "vitamin D"},
    )

    assert first == second


def test_request_fingerprint_changes_when_query_term_changes() -> None:
    first = request_fingerprint(
        method="GET",
        endpoint=PUBMED_ESEARCH_ENDPOINT,
        params={"db": "pubmed", "term": "vitamin D"},
    )
    second = request_fingerprint(
        method="GET",
        endpoint=PUBMED_ESEARCH_ENDPOINT,
        params={"db": "pubmed", "term": "multiple sclerosis"},
    )

    assert first != second


def test_request_fingerprint_payload_excludes_api_key() -> None:
    payload = request_fingerprint_payload(
        method="GET",
        endpoint=PUBMED_ESEARCH_ENDPOINT,
        params={"db": "pubmed", "term": "vitamin D", "api_key": "secret-api-key"},
    )

    assert "api_key" not in payload["params"]
    assert "secret-api-key" not in json.dumps(payload, sort_keys=True)


def test_fixture_response_is_stored_before_parsed_result_is_returned(tmp_path) -> None:
    raw_bytes = FIXTURE_PATH.read_bytes()
    store = LocalArtifactStore(tmp_path)
    manifest = load_query_manifest(SEED_MANIFEST_PATH)
    params = build_esearch_params(manifest)

    result = process_esearch_response_bytes(
        raw_bytes=raw_bytes,
        artifact_store=store,
        endpoint=PUBMED_ESEARCH_ENDPOINT,
        request_params=params,
        http_status=200,
        content_type="application/json",
    )

    assert result.raw_artifact.path.exists()
    assert result.raw_artifact.path.read_bytes() == raw_bytes
    assert result.parsed.raw_payload_hash == result.raw_artifact.artifact_hash
    assert result.parsed.count == 123
    assert result.parsed.pmids == ("11111111", "22222222", "33333333")
    assert result.parsed.webenv == "MCID_00000000000000000000000000"
    assert result.parsed.query_key == "1"


def test_source_snapshot_manifest_includes_pubmed_esearch_metadata(tmp_path) -> None:
    manifest = load_query_manifest(SEED_MANIFEST_PATH)
    params = build_esearch_params(manifest)
    result = process_esearch_response_bytes(
        raw_bytes=FIXTURE_PATH.read_bytes(),
        artifact_store=LocalArtifactStore(tmp_path),
        endpoint=PUBMED_ESEARCH_ENDPOINT,
        request_params=params,
        http_status=200,
        content_type="application/json; charset=UTF-8",
    )

    metadata = result.source_snapshot_manifest.metadata

    assert result.source_snapshot_manifest.payload_hash == result.raw_artifact.artifact_hash
    assert metadata["source_name"] == "pubmed"
    assert metadata["operation"] == "esearch"
    assert metadata["endpoint"] == PUBMED_ESEARCH_ENDPOINT
    assert metadata["http_status"] == 200
    assert metadata["content_type"] == "application/json; charset=UTF-8"
    assert metadata["request_params"]["term"] == manifest.term
    assert metadata["request_fingerprint"].startswith("sha256:")


def test_run_esearch_uses_injected_httpx_client_without_live_network(tmp_path) -> None:
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
    manifest = load_query_manifest(SEED_MANIFEST_PATH)

    result = run_esearch(
        manifest=manifest,
        artifact_store=LocalArtifactStore(tmp_path),
        settings=Settings(NCBI_TOOL="convivial-test", NCBI_EMAIL="curator@example.org"),
        client=client,
    )

    assert seen_request is not None
    assert seen_request.url.params["db"] == "pubmed"
    assert seen_request.url.params["retmax"] == "50"
    assert seen_request.url.params["tool"] == "convivial-test"
    assert seen_request.url.params["email"] == "curator@example.org"
    assert result.parsed.count == 123


def test_run_esearch_preserves_non_2xx_response_before_raising(tmp_path: Path) -> None:
    raw_bytes = b"rate limit exceeded"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=429,
            content=raw_bytes,
            headers={"content-type": "text/plain"},
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    manifest = load_query_manifest(SEED_MANIFEST_PATH)

    with pytest.raises(PubMedHTTPStatusError) as exc_info:
        run_esearch(
            manifest=manifest,
            artifact_store=LocalArtifactStore(tmp_path),
            settings=Settings(
                NCBI_TOOL="convivial-test",
                NCBI_EMAIL="curator@example.org",
                NCBI_API_KEY="secret-api-key",
            ),
            client=client,
        )

    exc = exc_info.value
    assert exc.operation == "esearch"
    assert exc.http_status == 429
    assert exc.content_type == "text/plain"
    assert exc.raw_payload_hash.startswith("sha256:")
    assert exc.raw_artifact_uri.startswith("artifact://sha256/")
    assert exc.source_snapshot_manifest_hash.startswith("sha256:")
    assert exc.request_metadata["params"]["api_key"] == "<redacted>"
    assert "secret-api-key" not in json.dumps(exc.request_metadata, sort_keys=True)
    assert LocalArtifactStore(tmp_path).read_bytes(exc.raw_payload_hash) == raw_bytes
