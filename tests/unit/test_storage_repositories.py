from __future__ import annotations

import inspect
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from convivial_medicine.adapters.pubmed.esearch import (
    PUBMED_ESEARCH_ENDPOINT,
    build_esearch_params,
    process_esearch_response_bytes,
)
from convivial_medicine.adapters.pubmed.persistence import (
    source_snapshot_db_values_from_pubmed_esearch,
)
from convivial_medicine.config import Settings
from convivial_medicine.domain.manifests import load_query_manifest
from convivial_medicine.storage import models, repositories
from convivial_medicine.storage.artifacts import LocalArtifactStore
from convivial_medicine.storage.repositories import (
    PersistenceConflictError,
    persist_query_manifest,
    persist_snapshot_manifest,
    persist_source_snapshot,
    query_manifest_db_values,
    snapshot_manifest_db_values,
)

SEED_MANIFEST_PATH = Path("manifests/vitamin_D_ms_seed_v1.json")
FIXTURE_PATH = Path("tests/fixtures/pubmed/esearch_vitamin_d_ms_seed.json")
RETRIEVED_AT = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)


class RecordingSession:
    def __init__(self) -> None:
        self.records: dict[tuple[type[Any], str], Any] = {}
        self.flush_count = 0

    def get(self, model_cls: type[Any], key: str) -> Any | None:
        return self.records.get((model_cls, key))

    def add(self, obj: Any) -> None:
        key = obj.snapshot_hash if isinstance(obj, models.SourceSnapshot) else obj.manifest_hash
        self.records[(type(obj), key)] = obj

    def flush(self) -> None:
        self.flush_count += 1


def test_query_manifest_mapping_uses_domain_db_values() -> None:
    manifest = load_query_manifest(SEED_MANIFEST_PATH)

    values = query_manifest_db_values(manifest)

    assert values == manifest.to_db_values()
    assert values["manifest_hash"].startswith("sha256:")
    assert values["source_name"] == "pubmed"
    assert values["query"] == manifest.term


def test_storage_repositories_do_not_import_pubmed_adapter_modules() -> None:
    source = inspect.getsource(repositories)

    assert "convivial_medicine.adapters.pubmed" not in source
    assert "convivial_medicine.adapters.pmc" not in source


def test_pubmed_esearch_source_snapshot_mapping_populates_expected_values(tmp_path: Path) -> None:
    result = _fixture_result(tmp_path)

    values = source_snapshot_db_values_from_pubmed_esearch(result)

    assert values["snapshot_hash"] == result.raw_artifact.artifact_hash
    assert values["source_name"] == "pubmed"
    assert values["operation"] == "esearch"
    assert values["request_fingerprint"].startswith("sha256:")
    assert values["request_metadata"]["endpoint"] == PUBMED_ESEARCH_ENDPOINT
    assert values["http_status"] == 200
    assert values["content_type"] == "application/json"
    assert values["provider_payload"] == result.provider_payload
    assert values["response_metadata"]["pmids_returned"] == 3
    assert values["retrieved_at"] == RETRIEVED_AT
    assert values["raw_artifact_uri"] == result.raw_artifact.uri


def test_pubmed_esearch_mapping_redacts_secret_request_values(tmp_path: Path) -> None:
    manifest = load_query_manifest(SEED_MANIFEST_PATH)
    params = build_esearch_params(
        manifest,
        settings=Settings(
            NCBI_TOOL="convivial-test",
            NCBI_EMAIL="curator@example.org",
            NCBI_API_KEY="secret-api-key",
        ),
    )
    result = process_esearch_response_bytes(
        raw_bytes=FIXTURE_PATH.read_bytes(),
        artifact_store=LocalArtifactStore(tmp_path),
        endpoint=PUBMED_ESEARCH_ENDPOINT,
        request_params=params,
        http_status=200,
        content_type="application/json",
        retrieved_at=RETRIEVED_AT,
    )

    values = source_snapshot_db_values_from_pubmed_esearch(result)
    persisted_json = json.dumps(values["request_metadata"], sort_keys=True)

    assert "secret-api-key" not in persisted_json
    assert values["request_metadata"]["params"]["api_key"] == "<redacted>"


def test_snapshot_manifest_mapping_renames_metadata_for_sqlalchemy_model(tmp_path: Path) -> None:
    result = _fixture_result(tmp_path)

    values = snapshot_manifest_db_values(result.source_snapshot_manifest)

    assert "metadata" not in values
    assert values["manifest_metadata"] == result.source_snapshot_manifest.metadata
    assert values["payload_hash"] == result.raw_artifact.artifact_hash


def test_duplicate_same_hash_inserts_are_idempotent(tmp_path: Path) -> None:
    session = RecordingSession()
    manifest = load_query_manifest(SEED_MANIFEST_PATH)
    result = _fixture_result(tmp_path)
    source_values = source_snapshot_db_values_from_pubmed_esearch(result)

    persist_query_manifest(session, manifest)  # type: ignore[arg-type]
    persist_source_snapshot(session, source_values)  # type: ignore[arg-type]
    persist_snapshot_manifest(session, result.source_snapshot_manifest)  # type: ignore[arg-type]
    first_flush_count = session.flush_count

    persist_query_manifest(session, manifest)  # type: ignore[arg-type]
    persist_source_snapshot(session, source_values)  # type: ignore[arg-type]
    persist_snapshot_manifest(session, result.source_snapshot_manifest)  # type: ignore[arg-type]

    assert session.flush_count == first_flush_count


def test_same_hash_with_conflicting_values_raises_clear_exception(tmp_path: Path) -> None:
    session = RecordingSession()
    result = _fixture_result(tmp_path)
    source_values = source_snapshot_db_values_from_pubmed_esearch(result)
    persist_source_snapshot(session, source_values)  # type: ignore[arg-type]

    conflicting_values = dict(source_values)
    conflicting_values["content_type"] = "application/xml"

    with pytest.raises(PersistenceConflictError, match="source_snapshots.*content_type"):
        persist_source_snapshot(session, conflicting_values)  # type: ignore[arg-type]


def _fixture_result(tmp_path: Path):
    manifest = load_query_manifest(SEED_MANIFEST_PATH)
    return process_esearch_response_bytes(
        raw_bytes=FIXTURE_PATH.read_bytes(),
        artifact_store=LocalArtifactStore(tmp_path),
        endpoint=PUBMED_ESEARCH_ENDPOINT,
        request_params=build_esearch_params(manifest),
        http_status=200,
        content_type="application/json",
        retrieved_at=RETRIEVED_AT,
    )
