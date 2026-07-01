from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy.orm import Session

from convivial_medicine.domain.manifests import (
    QueryManifest as DomainQueryManifest,
)
from convivial_medicine.domain.manifests import (
    SourceSnapshotManifest as DomainSourceSnapshotManifest,
)
from convivial_medicine.storage import models


class PersistenceConflictError(RuntimeError):
    """Raised when an existing hash-keyed row has different persisted values."""


def query_manifest_db_values(manifest: DomainQueryManifest) -> dict[str, Any]:
    return manifest.to_db_values()


def snapshot_manifest_db_values(
    manifest: DomainSourceSnapshotManifest,
) -> dict[str, Any]:
    values = manifest.to_db_values()
    values["manifest_metadata"] = values.pop("metadata")
    return values


def persist_query_manifest(session: Session, manifest: DomainQueryManifest) -> str:
    values = query_manifest_db_values(manifest)
    return insert_or_validate(
        session=session,
        model_cls=models.QueryManifest,
        key_field="manifest_hash",
        values=values,
        compare_fields=values.keys(),
    )


def persist_source_snapshot(
    session: Session,
    values: Mapping[str, Any],
) -> str:
    return insert_or_validate(
        session=session,
        model_cls=models.SourceSnapshot,
        key_field="snapshot_hash",
        values=values,
        compare_fields=(
            "snapshot_hash",
            "source_name",
            "operation",
            "source_record_id",
            "request_fingerprint",
            "request_metadata",
            "http_status",
            "content_type",
            "provider_payload",
            "response_metadata",
            "raw_artifact_uri",
        ),
    )


def persist_snapshot_manifest(
    session: Session,
    manifest: DomainSourceSnapshotManifest,
) -> str:
    values = snapshot_manifest_db_values(manifest)
    return insert_or_validate(
        session=session,
        model_cls=models.SnapshotManifest,
        key_field="manifest_hash",
        values=values,
        compare_fields=values.keys(),
    )


def insert_or_validate(
    *,
    session: Session,
    model_cls: type[Any],
    key_field: str,
    values: Mapping[str, Any],
    compare_fields: Iterable[str],
) -> str:
    key = values[key_field]
    if not isinstance(key, str):
        msg = f"{model_cls.__name__}.{key_field} must be a string"
        raise TypeError(msg)

    existing = session.get(model_cls, key)
    if existing is None:
        session.add(model_cls(**dict(values)))
        session.flush()
        return key

    mismatches = [field for field in compare_fields if getattr(existing, field) != values[field]]
    if mismatches:
        field_list = ", ".join(sorted(mismatches))
        msg = f"{model_cls.__tablename__} row for {key} conflicts on: {field_list}"
        raise PersistenceConflictError(msg)

    return key
