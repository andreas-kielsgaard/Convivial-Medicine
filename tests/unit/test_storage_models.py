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
        "snapshot_manifest_hash"
    ]


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
