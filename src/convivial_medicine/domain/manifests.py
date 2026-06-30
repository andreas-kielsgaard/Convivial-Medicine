from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from convivial_medicine.domain.canonical_json import canonical_json_bytes
from convivial_medicine.domain.hashes import sha256_uri, validate_sha256_uri


def compute_manifest_hash(payload: dict[str, Any]) -> str:
    return sha256_uri(canonical_json_bytes(payload))


def normalize_parent_hashes(parent_hashes: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({validate_sha256_uri(parent_hash) for parent_hash in parent_hashes}))


class QueryManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifest_version: str = Field(min_length=1)
    name: str = Field(min_length=1)
    db: str = Field(min_length=1)
    term: str = Field(min_length=1)
    usehistory: bool
    retmax: int = Field(gt=0)
    retmode: str = Field(default="json", min_length=1)
    notes: str | None = None

    def manifest_payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json", exclude_none=True)
        canonical_json_bytes(payload)
        return payload

    def manifest_hash(self) -> str:
        return compute_manifest_hash(self.manifest_payload())

    def to_db_values(self) -> dict[str, Any]:
        return {
            "manifest_hash": self.manifest_hash(),
            "name": self.name,
            "source_name": self.db,
            "query": self.term,
            "manifest_payload": self.manifest_payload(),
            "notes": self.notes,
        }


class ArtifactManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifest_version: str = Field(min_length=1)
    artifact_type: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    payload_hash: str
    parent_hashes: tuple[str, ...] = Field(default_factory=tuple)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None

    @field_validator("payload_hash")
    @classmethod
    def _validate_payload_hash(cls, value: str) -> str:
        return validate_sha256_uri(value)

    @field_validator("parent_hashes", mode="before")
    @classmethod
    def _normalize_parent_hashes(cls, value: object) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str) or not isinstance(value, Iterable):
            raise ValueError("parent_hashes must be an iterable of sha256 URIs")
        parents: list[str] = []
        for parent_hash in value:
            if not isinstance(parent_hash, str):
                raise ValueError("parent_hashes must contain only sha256 URIs")
            parents.append(parent_hash)
        return normalize_parent_hashes(parents)

    @field_validator("metadata")
    @classmethod
    def _validate_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        try:
            canonical_json_bytes(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"metadata must be canonical JSON-compatible: {exc}") from exc
        return value

    def manifest_payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json", exclude_none=True)
        canonical_json_bytes(payload)
        return payload

    def manifest_hash(self) -> str:
        return compute_manifest_hash(self.manifest_payload())

    def to_db_values(self) -> dict[str, Any]:
        values: dict[str, Any] = {
            "manifest_hash": self.manifest_hash(),
            "artifact_type": self.artifact_type,
            "schema_version": self.schema_version,
            "payload_hash": self.payload_hash,
            "parent_hashes": list(self.parent_hashes),
            "manifest_payload": self.manifest_payload(),
            "metadata": self.metadata,
        }
        if self.created_at is not None:
            values["created_at"] = self.created_at
        return values


class SourceSnapshotManifest(ArtifactManifest):
    artifact_type: str = Field(default="source_snapshot", min_length=1)


class DerivedArtifactManifest(ArtifactManifest):
    artifact_type: str = Field(default="derived_artifact", min_length=1)


def load_query_manifest(path: Path) -> QueryManifest:
    return QueryManifest.model_validate_json(path.read_text(encoding="utf-8"))


def load_manifest(path: Path) -> QueryManifest:
    return load_query_manifest(path)
