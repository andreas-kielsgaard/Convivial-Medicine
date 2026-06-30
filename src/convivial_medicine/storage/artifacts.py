from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from convivial_medicine.domain.hashes import sha256_uri, validate_sha256_uri


class ArtifactCollisionError(RuntimeError):
    pass


@dataclass(frozen=True)
class StoredArtifact:
    artifact_hash: str
    uri: str
    path: Path


class LocalArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def write_bytes(self, data: bytes) -> StoredArtifact:
        artifact_hash = sha256_uri(data)
        path = self.artifact_path(artifact_hash)
        if path.exists():
            if path.read_bytes() != data:
                raise ArtifactCollisionError(f"existing artifact bytes differ for {artifact_hash}")
            return self._stored_artifact(artifact_hash)

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return self._stored_artifact(artifact_hash)

    def read_bytes(self, artifact_hash: str) -> bytes:
        return self.artifact_path(artifact_hash).read_bytes()

    def artifact_path(self, artifact_hash: str) -> Path:
        hex_hash = validate_sha256_uri(artifact_hash).removeprefix("sha256:")
        return self.root / "sha256" / hex_hash[:2] / hex_hash

    def artifact_uri(self, artifact_hash: str) -> str:
        hex_hash = validate_sha256_uri(artifact_hash).removeprefix("sha256:")
        return f"artifact://sha256/{hex_hash[:2]}/{hex_hash}"

    def _stored_artifact(self, artifact_hash: str) -> StoredArtifact:
        return StoredArtifact(
            artifact_hash=artifact_hash,
            uri=self.artifact_uri(artifact_hash),
            path=self.artifact_path(artifact_hash),
        )
