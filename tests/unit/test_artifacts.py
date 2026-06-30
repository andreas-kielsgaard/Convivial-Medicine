from __future__ import annotations

import pytest

from convivial_medicine.storage.artifacts import ArtifactCollisionError, LocalArtifactStore


def test_local_artifact_store_write_read_round_trip(tmp_path) -> None:
    store = LocalArtifactStore(tmp_path)

    stored = store.write_bytes(b"raw source bytes")

    assert stored.artifact_hash.startswith("sha256:")
    assert stored.path.exists()
    assert store.read_bytes(stored.artifact_hash) == b"raw source bytes"


def test_local_artifact_store_same_bytes_produce_same_uri(tmp_path) -> None:
    store = LocalArtifactStore(tmp_path)

    first = store.write_bytes(b"same")
    second = store.write_bytes(b"same")

    assert first.artifact_hash == second.artifact_hash
    assert first.uri == second.uri
    assert first.path == second.path


def test_local_artifact_store_different_bytes_produce_different_uris(tmp_path) -> None:
    store = LocalArtifactStore(tmp_path)

    first = store.write_bytes(b"first")
    second = store.write_bytes(b"second")

    assert first.artifact_hash != second.artifact_hash
    assert first.uri != second.uri


def test_local_artifact_store_detects_existing_hash_collision(tmp_path) -> None:
    store = LocalArtifactStore(tmp_path)
    stored = store.write_bytes(b"original")
    stored.path.write_bytes(b"different")

    with pytest.raises(ArtifactCollisionError, match="existing artifact bytes differ"):
        store.write_bytes(b"original")
