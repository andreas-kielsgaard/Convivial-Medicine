from __future__ import annotations

from sqlalchemy import UniqueConstraint

from convivial_medicine.storage.models import Base

EXPECTED_TABLES = {
    "query_manifests",
    "source_snapshots",
    "snapshot_manifests",
    "works",
    "work_identifiers",
    "work_sources",
    "fulltext_assets",
    "enrichment_openalex",
    "build_runs",
    "slice_members",
    "review_conflicts",
}


def test_model_metadata_contains_schema_v1_tables() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_hash_identity_tables_use_hash_primary_keys() -> None:
    assert list(Base.metadata.tables["query_manifests"].primary_key.columns.keys()) == [
        "manifest_hash"
    ]
    assert list(Base.metadata.tables["source_snapshots"].primary_key.columns.keys()) == [
        "snapshot_hash"
    ]
    assert list(Base.metadata.tables["snapshot_manifests"].primary_key.columns.keys()) == [
        "manifest_hash"
    ]


def test_snapshot_manifests_has_content_addressed_columns() -> None:
    table = Base.metadata.tables["snapshot_manifests"]

    assert {
        "manifest_hash",
        "artifact_type",
        "schema_version",
        "payload_hash",
        "parent_hashes",
        "manifest_payload",
        "metadata",
    }.issubset(table.columns.keys())
    assert "snapshot_manifest_hash" not in table.columns


def test_source_snapshots_has_attempt_traceability_columns() -> None:
    table = Base.metadata.tables["source_snapshots"]

    assert {"request_fingerprint", "request_metadata", "http_status"}.issubset(table.columns.keys())
    assert "ix_source_snapshots_request_fingerprint" in {index.name for index in table.indexes}


def test_works_has_normalized_payload_and_current_manifest() -> None:
    table = Base.metadata.tables["works"]

    assert {"normalized_payload", "current_manifest_hash"}.issubset(table.columns.keys())


def test_fulltext_assets_has_license_observation_columns() -> None:
    table = Base.metadata.tables["fulltext_assets"]

    assert {"license_group", "license_observation"}.issubset(table.columns.keys())


def test_slice_members_has_hash_and_member_manifest_columns() -> None:
    table = Base.metadata.tables["slice_members"]

    assert {"slice_hash", "member_manifest_hash"}.issubset(table.columns.keys())
    assert "ix_slice_members_slice_hash" in {index.name for index in table.indexes}


def test_openalex_enrichment_is_append_friendly_per_work() -> None:
    table = Base.metadata.tables["enrichment_openalex"]
    unique_constraints = {
        constraint.name: tuple(constraint.columns.keys())
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert ("work_id",) not in unique_constraints.values()
    assert unique_constraints["uq_enrichment_openalex_work_source_snapshot"] == (
        "work_id",
        "source_snapshot_hash",
    )
    assert "ix_enrichment_openalex_openalex_id" in {index.name for index in table.indexes}


def test_work_identifier_uniqueness_and_lookup_index() -> None:
    table = Base.metadata.tables["work_identifiers"]
    unique_constraints = {
        constraint.name: tuple(constraint.columns.keys())
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert unique_constraints["uq_work_identifiers_work_namespace_value"] == (
        "work_id",
        "id_namespace",
        "id_value",
    )
    assert "ix_work_identifiers_namespace_value" in {index.name for index in table.indexes}


def test_requested_operational_indexes_exist() -> None:
    source_snapshot_indexes = {
        index.name for index in Base.metadata.tables["source_snapshots"].indexes
    }
    build_run_indexes = {index.name for index in Base.metadata.tables["build_runs"].indexes}

    assert "ix_source_snapshots_source_operation" in source_snapshot_indexes
    assert "ix_build_runs_status" in build_run_indexes


def test_major_jsonb_indexes_use_gin() -> None:
    gin_index_names = {
        index.name
        for table in Base.metadata.tables.values()
        for index in table.indexes
        if index.dialect_options["postgresql"].get("using") == "gin"
    }

    assert "ix_source_snapshots_provider_payload_gin" in gin_index_names
    assert "ix_enrichment_openalex_projection_gin" in gin_index_names
