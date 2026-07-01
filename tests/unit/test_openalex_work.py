from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from convivial_medicine.adapters.openalex.errors import OpenAlexHTTPStatusError
from convivial_medicine.adapters.openalex.persistence import (
    source_snapshot_db_values_from_openalex_work,
)
from convivial_medicine.adapters.openalex.work import (
    OPENALEX_WORKS_ENDPOINT_ROOT,
    build_openalex_work_request,
    openalex_lookup_id,
    process_openalex_work_response_bytes,
    run_openalex_work,
)
from convivial_medicine.config import Settings
from convivial_medicine.storage.artifacts import LocalArtifactStore

FIXTURE_PATH = Path("tests/fixtures/openalex/work_vitamin_d_ms_seed.json")


def test_openalex_lookup_id_normalizes_supported_identifiers() -> None:
    assert openalex_lookup_id(" doi:10.1000/vitd-ms.2021.001 ", id_type="doi") == (
        "doi:10.1000/vitd-ms.2021.001"
    )
    assert openalex_lookup_id("https://doi.org/10.1000/vitd-ms.2021.001", id_type="doi") == (
        "doi:10.1000/vitd-ms.2021.001"
    )
    assert openalex_lookup_id("pmid:11111111", id_type="pmid") == "pmid:11111111"
    assert openalex_lookup_id("https://openalex.org/W1111111111", id_type="openalex_id") == (
        "W1111111111"
    )


def test_openalex_rejects_empty_identifier() -> None:
    with pytest.raises(ValueError, match="DOI, PMID, or OpenAlex"):
        build_openalex_work_request(" ", id_type="doi")


def test_openalex_request_construction_uses_singleton_endpoint_and_api_key() -> None:
    settings = Settings(OPENALEX_API_KEY="secret-test-key")

    request = build_openalex_work_request(
        "10.1000/vitd-ms.2021.001",
        id_type="doi",
        settings=settings,
    )

    assert request.endpoint == (f"{OPENALEX_WORKS_ENDPOINT_ROOT}/doi:10.1000/vitd-ms.2021.001")
    assert request.request_params == {"api_key": "secret-test-key"}
    assert request.openalex_lookup_id == "doi:10.1000/vitd-ms.2021.001"


def test_fixture_response_is_stored_before_parsed_result_is_returned(tmp_path: Path) -> None:
    raw_bytes = FIXTURE_PATH.read_bytes()
    request = build_openalex_work_request("11111111", id_type="pmid")

    result = process_openalex_work_response_bytes(
        raw_bytes=raw_bytes,
        artifact_store=LocalArtifactStore(tmp_path),
        request=request,
        http_status=200,
        content_type="application/json",
    )

    assert result.raw_artifact.path.exists()
    assert result.raw_artifact.path.read_bytes() == raw_bytes
    assert result.parsed.raw_payload_hash == result.raw_artifact.artifact_hash
    assert result.provider_payload["id"] == "https://openalex.org/W1111111111"


def test_fixture_parsing_captures_minimal_work_enrichment(tmp_path: Path) -> None:
    result = process_openalex_work_response_bytes(
        raw_bytes=FIXTURE_PATH.read_bytes(),
        artifact_store=LocalArtifactStore(tmp_path),
        request=build_openalex_work_request("11111111", id_type="pmid"),
        http_status=200,
        content_type="application/json",
    )

    parsed = result.parsed
    assert parsed.requested_id == "11111111"
    assert parsed.requested_id_type == "pmid"
    assert parsed.openalex_id == "https://openalex.org/W1111111111"
    assert parsed.doi == "https://doi.org/10.1000/vitd-ms.2021.001"
    assert parsed.pmid == "11111111"
    assert parsed.title == "Vitamin D status and multiple sclerosis risk."
    assert parsed.publication_year == 2021
    assert parsed.publication_date == "2021-04-15"
    assert parsed.type == "article"
    assert parsed.cited_by_count == 42
    assert parsed.is_retracted is False
    assert parsed.open_access is not None
    assert parsed.open_access.oa_status == "gold"
    assert parsed.primary_location is not None
    assert parsed.primary_location.source is not None
    assert parsed.primary_location.source.display_name == "Fixture Journal of Neurology"


def test_source_snapshot_manifest_includes_openalex_metadata_and_redacts_key(
    tmp_path: Path,
) -> None:
    request = build_openalex_work_request(
        "11111111",
        id_type="pmid",
        settings=Settings(OPENALEX_API_KEY="secret-test-key"),
    )
    result = process_openalex_work_response_bytes(
        raw_bytes=FIXTURE_PATH.read_bytes(),
        artifact_store=LocalArtifactStore(tmp_path),
        request=request,
        http_status=200,
        content_type="application/json; charset=utf-8",
    )

    metadata = result.source_snapshot_manifest.metadata

    assert result.source_snapshot_manifest.payload_hash == result.raw_artifact.artifact_hash
    assert metadata["source_name"] == "openalex"
    assert metadata["operation"] == "work"
    assert metadata["endpoint"] == request.endpoint
    assert metadata["requested_identifier"] == "11111111"
    assert metadata["requested_identifier_type"] == "pmid"
    assert metadata["openalex_lookup_id"] == "pmid:11111111"
    assert metadata["request_params"]["api_key"] == "<redacted>"
    assert result.request_metadata["params"]["api_key"] == "<redacted>"
    assert metadata["http_status"] == 200
    assert metadata["content_type"] == "application/json; charset=utf-8"
    assert metadata["request_fingerprint"].startswith("sha256:")


def test_openalex_persistence_mapping_populates_source_snapshot_values(
    tmp_path: Path,
) -> None:
    result = process_openalex_work_response_bytes(
        raw_bytes=FIXTURE_PATH.read_bytes(),
        artifact_store=LocalArtifactStore(tmp_path),
        request=build_openalex_work_request("11111111", id_type="pmid"),
        http_status=200,
        content_type="application/json",
    )

    values = source_snapshot_db_values_from_openalex_work(result)

    assert values["snapshot_hash"] == result.raw_artifact.artifact_hash
    assert values["source_name"] == "openalex"
    assert values["operation"] == "work"
    assert values["source_record_id"] == "https://openalex.org/W1111111111"
    assert values["request_metadata"]["endpoint"].endswith("/pmid:11111111")
    assert values["response_metadata"]["openalex_id"] == "https://openalex.org/W1111111111"
    assert values["response_metadata"]["pmid"] == "11111111"


def test_run_openalex_work_uses_injected_httpx_client_without_live_network(
    tmp_path: Path,
) -> None:
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

    result = run_openalex_work(
        identifier="11111111",
        id_type="pmid",
        artifact_store=LocalArtifactStore(tmp_path),
        settings=Settings(OPENALEX_API_KEY="secret-test-key"),
        client=client,
    )

    assert seen_request is not None
    assert str(seen_request.url) == (
        f"{OPENALEX_WORKS_ENDPOINT_ROOT}/pmid:11111111?api_key=secret-test-key"
    )
    assert result.parsed.openalex_id == "https://openalex.org/W1111111111"
    assert result.request_metadata["params"]["api_key"] == "<redacted>"


def test_run_openalex_work_requires_api_key_even_with_injected_client(
    tmp_path: Path,
) -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200)))

    with pytest.raises(ValueError, match="OPENALEX_API_KEY"):
        run_openalex_work(
            identifier="11111111",
            id_type="pmid",
            artifact_store=LocalArtifactStore(tmp_path),
            client=client,
        )


def test_run_openalex_work_accepts_injected_transport_without_live_network(
    tmp_path: Path,
) -> None:
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

    result = run_openalex_work(
        identifier="W1111111111",
        id_type="openalex_id",
        artifact_store=LocalArtifactStore(tmp_path),
        settings=Settings(OPENALEX_API_KEY="secret-test-key"),
        transport=httpx.MockTransport(handler),
    )

    assert seen_request is not None
    assert str(seen_request.url) == (
        f"{OPENALEX_WORKS_ENDPOINT_ROOT}/W1111111111?api_key=secret-test-key"
    )
    assert result.parsed.requested_id_type == "openalex_id"
    assert result.parsed.publication_year == 2021


def test_run_openalex_work_preserves_non_2xx_response_before_raising(
    tmp_path: Path,
) -> None:
    raw_bytes = b'{"error":"Not found"}'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=404,
            content=raw_bytes,
            headers={"content-type": "application/json"},
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(OpenAlexHTTPStatusError) as exc_info:
        run_openalex_work(
            identifier="W0000000000",
            id_type="openalex_id",
            artifact_store=LocalArtifactStore(tmp_path),
            settings=Settings(OPENALEX_API_KEY="secret-test-key"),
            client=client,
        )

    exc = exc_info.value
    assert exc.operation == "work"
    assert exc.http_status == 404
    assert exc.content_type == "application/json"
    assert exc.raw_payload_hash.startswith("sha256:")
    assert exc.raw_artifact_uri.startswith("artifact://sha256/")
    assert exc.source_snapshot_manifest_hash.startswith("sha256:")
    assert exc.request_metadata["endpoint"].endswith("/W0000000000")
    assert LocalArtifactStore(tmp_path).read_bytes(exc.raw_payload_hash) == raw_bytes
