from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from convivial_medicine.domain.canonical_json import canonical_json_bytes
from convivial_medicine.domain.hashes import (
    is_sha256_uri,
    sha256_hex,
    sha256_uri,
    validate_sha256_uri,
)
from convivial_medicine.domain.identifiers import normalize_doi
from convivial_medicine.domain.manifests import (
    ArtifactManifest,
    DerivedArtifactManifest,
    SourceSnapshotManifest,
    compute_manifest_hash,
    load_manifest,
)


def test_sha256_hex_is_deterministic() -> None:
    assert sha256_hex(b"convivial") == (
        "1a27e7bf2aca65b749bfa313e4a9b774377a96b548f2539bebe3a2be99b883c2"
    )


def test_sha256_uri_uses_canonical_prefix() -> None:
    assert sha256_uri(b"convivial") == (
        "sha256:1a27e7bf2aca65b749bfa313e4a9b774377a96b548f2539bebe3a2be99b883c2"
    )


def test_sha256_uri_validation_rejects_malformed_hashes() -> None:
    valid_hash = sha256_uri(b"convivial")

    assert is_sha256_uri(valid_hash)
    assert validate_sha256_uri(valid_hash) == valid_hash
    assert not is_sha256_uri(valid_hash.upper())
    with pytest.raises(ValueError, match="expected canonical"):
        validate_sha256_uri("sha256:not-a-real-hash")


def test_canonical_json_ignores_dict_insertion_order() -> None:
    left = {"b": 2, "a": 1}
    right = {"a": 1, "b": 2}

    assert canonical_json_bytes(left) == b'{"a":1,"b":2}'
    assert canonical_json_bytes(left) == canonical_json_bytes(right)
    assert compute_manifest_hash(left) == compute_manifest_hash(right)


def test_canonical_json_serializes_nested_values_deterministically() -> None:
    payload = {
        "items": [{"z": None, "a": True}, {"value": 1.5}],
        "name": "D vitamin",
    }

    assert canonical_json_bytes(payload) == (
        b'{"items":[{"a":true,"z":null},{"value":1.5}],"name":"D vitamin"}'
    )


def test_canonical_json_rejects_unsupported_values_clearly() -> None:
    with pytest.raises(TypeError, match="unsupported JSON value type set"):
        canonical_json_bytes({"bad": {"set-values"}})


def test_normalize_doi_strips_url_prefix_and_lowercases() -> None:
    assert normalize_doi(" https://doi.org/10.1000/ABC.Def ") == "10.1000/abc.def"


def test_normalize_doi_returns_none_for_blank_values() -> None:
    assert normalize_doi("   ") is None
    assert normalize_doi(None) is None


def test_load_seed_manifest() -> None:
    manifest = load_manifest(Path("manifests/vitamin_D_ms_seed_v1.json"))

    assert manifest.manifest_version == "1"
    assert manifest.name == "vitamin_D_ms_seed_v1"
    assert manifest.db == "pubmed"
    assert manifest.retmax == 50


def test_seed_manifest_exposes_stable_db_values() -> None:
    manifest = load_manifest(Path("manifests/vitamin_D_ms_seed_v1.json"))
    db_values = manifest.to_db_values()

    assert db_values["manifest_hash"] == manifest.manifest_hash()
    assert db_values["source_name"] == "pubmed"
    assert db_values["query"] == manifest.term
    assert db_values["manifest_payload"] == manifest.manifest_payload()


def test_logically_identical_artifact_manifests_hash_the_same() -> None:
    payload_hash = sha256_uri(b"payload")
    parent_a = sha256_uri(b"parent-a")
    parent_b = sha256_uri(b"parent-b")
    left = ArtifactManifest(
        manifest_version="1",
        artifact_type="raw_source_bytes",
        schema_version="1",
        payload_hash=payload_hash,
        parent_hashes=[parent_b, parent_a, parent_b],
        metadata={"source": "pubmed"},
    )
    right = ArtifactManifest(
        manifest_version="1",
        artifact_type="raw_source_bytes",
        schema_version="1",
        payload_hash=payload_hash,
        parent_hashes=[parent_a, parent_b],
        metadata={"source": "pubmed"},
    )

    assert left.parent_hashes == tuple(sorted([parent_a, parent_b]))
    assert right.parent_hashes == tuple(sorted([parent_a, parent_b]))
    assert left.manifest_hash() == right.manifest_hash()


def test_changing_payload_hash_changes_manifest_hash() -> None:
    first = SourceSnapshotManifest(
        manifest_version="1",
        schema_version="1",
        payload_hash=sha256_uri(b"first"),
    )
    second = SourceSnapshotManifest(
        manifest_version="1",
        schema_version="1",
        payload_hash=sha256_uri(b"second"),
    )

    assert first.manifest_hash() != second.manifest_hash()


def test_artifact_manifest_rejects_malformed_parent_hash() -> None:
    with pytest.raises(ValidationError, match="expected canonical"):
        ArtifactManifest(
            manifest_version="1",
            artifact_type="raw_source_bytes",
            schema_version="1",
            payload_hash=sha256_uri(b"payload"),
            parent_hashes=["sha256:NOPE"],
        )


def test_artifact_manifest_db_values_align_with_snapshot_manifest_columns() -> None:
    manifest = DerivedArtifactManifest(
        manifest_version="1",
        schema_version="1",
        payload_hash=sha256_uri(b"payload"),
        metadata={"stage": "normalize"},
    )

    db_values = manifest.to_db_values()

    assert db_values["artifact_type"] == "derived_artifact"
    assert db_values["manifest_hash"] == manifest.manifest_hash()
    assert db_values["manifest_payload"] == manifest.manifest_payload()
    assert db_values["metadata"] == {"stage": "normalize"}
