from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from convivial_medicine.adapters.pmc.bioc import (
    PMC_BIOC_ENDPOINT_ROOT,
    build_bioc_request,
    infer_bioc_identifier_type,
    process_bioc_response_bytes,
    run_bioc,
)
from convivial_medicine.adapters.pmc.errors import PmcHTTPStatusError
from convivial_medicine.adapters.pmc.persistence import (
    source_snapshot_db_values_from_pmc_bioc,
)
from convivial_medicine.storage.artifacts import LocalArtifactStore

FIXTURE_PATH = Path("tests/fixtures/pmc/bioc_vitamin_d_ms_seed.json")


def test_bioc_identifier_normalization_and_id_type_inference() -> None:
    request = build_bioc_request(" PMC1111111 ")

    assert request.requested_id == "PMC1111111"
    assert request.requested_id_type == "pmcid"
    assert infer_bioc_identifier_type("11111111") == "pmid"
    assert infer_bioc_identifier_type(" PMC1111111 ") == "pmcid"


def test_bioc_rejects_empty_identifier_and_invalid_id_type() -> None:
    with pytest.raises(ValueError, match="PMID or PMCID"):
        build_bioc_request(" ")

    with pytest.raises(ValueError, match="pmid or pmcid"):
        build_bioc_request("11111111", id_type="doi")


def test_bioc_request_construction_uses_official_json_unicode_path() -> None:
    request = build_bioc_request("11111111", id_type="pmid")

    assert request.endpoint == (f"{PMC_BIOC_ENDPOINT_ROOT}/BioC_json/11111111/unicode")
    assert request.request_params == {
        "requested_id": "11111111",
        "requested_id_type": "pmid",
        "format": "json",
        "encoding": "unicode",
    }


def test_fixture_response_is_stored_before_parsed_result_is_returned(tmp_path: Path) -> None:
    raw_bytes = FIXTURE_PATH.read_bytes()
    request = build_bioc_request("PMC1111111")

    result = process_bioc_response_bytes(
        raw_bytes=raw_bytes,
        artifact_store=LocalArtifactStore(tmp_path),
        request=request,
        http_status=200,
        content_type="application/json",
    )

    assert result.raw_artifact.path.exists()
    assert result.raw_artifact.path.read_bytes() == raw_bytes
    assert result.parsed.raw_payload_hash == result.raw_artifact.artifact_hash
    assert result.provider_payload["source"] == "PMC"


def test_fixture_parsing_captures_minimal_bioc_structure(tmp_path: Path) -> None:
    result = process_bioc_response_bytes(
        raw_bytes=FIXTURE_PATH.read_bytes(),
        artifact_store=LocalArtifactStore(tmp_path),
        request=build_bioc_request("PMC1111111"),
        http_status=200,
        content_type="application/json",
    )

    assert result.parsed.requested_id == "PMC1111111"
    assert result.parsed.requested_id_type == "pmcid"
    assert result.parsed.collection_source == "PMC"
    assert result.parsed.document_detected is True
    assert result.parsed.document_count == 1
    assert result.parsed.document_ids == ("PMC1111111",)
    assert result.parsed.passage_count == 3
    assert result.parsed.section_labels == (
        "ABSTRACT",
        "METHODS",
        "TITLE",
        "abstract",
        "paragraph",
        "title",
    )


def test_source_snapshot_manifest_includes_pmc_bioc_metadata(tmp_path: Path) -> None:
    request = build_bioc_request("PMC1111111")
    result = process_bioc_response_bytes(
        raw_bytes=FIXTURE_PATH.read_bytes(),
        artifact_store=LocalArtifactStore(tmp_path),
        request=request,
        http_status=200,
        content_type="application/json; charset=UTF-8",
    )

    metadata = result.source_snapshot_manifest.metadata

    assert result.source_snapshot_manifest.payload_hash == result.raw_artifact.artifact_hash
    assert metadata["source_name"] == "pmc"
    assert metadata["operation"] == "bioc"
    assert metadata["endpoint"] == request.endpoint
    assert metadata["requested_identifier"] == "PMC1111111"
    assert metadata["requested_identifier_type"] == "pmcid"
    assert metadata["format"] == "json"
    assert metadata["encoding"] == "unicode"
    assert metadata["http_status"] == 200
    assert metadata["content_type"] == "application/json; charset=UTF-8"
    assert metadata["request_fingerprint"].startswith("sha256:")


def test_bioc_persistence_mapping_populates_source_snapshot_values(tmp_path: Path) -> None:
    result = process_bioc_response_bytes(
        raw_bytes=FIXTURE_PATH.read_bytes(),
        artifact_store=LocalArtifactStore(tmp_path),
        request=build_bioc_request("PMC1111111"),
        http_status=200,
        content_type="application/json",
    )

    values = source_snapshot_db_values_from_pmc_bioc(result)

    assert values["snapshot_hash"] == result.raw_artifact.artifact_hash
    assert values["source_name"] == "pmc"
    assert values["operation"] == "bioc"
    assert values["request_metadata"]["params"]["requested_id"] == "PMC1111111"
    assert values["response_metadata"]["document_detected"] is True
    assert values["response_metadata"]["document_count"] == 1
    assert values["response_metadata"]["passage_count"] == 3


def test_run_bioc_uses_injected_httpx_client_without_live_network(tmp_path: Path) -> None:
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

    result = run_bioc(
        identifier="PMC1111111",
        artifact_store=LocalArtifactStore(tmp_path),
        client=client,
    )

    assert seen_request is not None
    assert str(seen_request.url) == f"{PMC_BIOC_ENDPOINT_ROOT}/BioC_json/PMC1111111/unicode"
    assert result.parsed.document_detected is True


def test_run_bioc_accepts_injected_transport_without_live_network(tmp_path: Path) -> None:
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

    result = run_bioc(
        identifier="11111111",
        id_type="pmid",
        artifact_store=LocalArtifactStore(tmp_path),
        transport=httpx.MockTransport(handler),
    )

    assert seen_request is not None
    assert str(seen_request.url) == f"{PMC_BIOC_ENDPOINT_ROOT}/BioC_json/11111111/unicode"
    assert result.parsed.requested_id_type == "pmid"
    assert result.parsed.document_count == 1


def test_run_bioc_preserves_non_2xx_response_before_raising(tmp_path: Path) -> None:
    raw_bytes = b"PMC BioC entry not found"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=404,
            content=raw_bytes,
            headers={"content-type": "text/plain"},
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(PmcHTTPStatusError) as exc_info:
        run_bioc(
            identifier="PMC0000000",
            artifact_store=LocalArtifactStore(tmp_path),
            client=client,
        )

    exc = exc_info.value
    assert exc.operation == "bioc"
    assert exc.http_status == 404
    assert exc.content_type == "text/plain"
    assert exc.raw_payload_hash.startswith("sha256:")
    assert exc.raw_artifact_uri.startswith("artifact://sha256/")
    assert exc.source_snapshot_manifest_hash.startswith("sha256:")
    assert exc.request_metadata["params"]["requested_id"] == "PMC0000000"
    assert LocalArtifactStore(tmp_path).read_bytes(exc.raw_payload_hash) == raw_bytes
