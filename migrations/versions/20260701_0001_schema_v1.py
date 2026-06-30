"""Create Phase One schema v1.

Revision ID: 20260701_0001
Revises:
Create Date: 2026-07-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260701_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "query_manifests",
        sa.Column("manifest_hash", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("manifest_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_query_manifests_manifest_payload_gin",
        "query_manifests",
        ["manifest_payload"],
        postgresql_using="gin",
    )

    op.create_table(
        "source_snapshots",
        sa.Column("snapshot_hash", sa.Text(), primary_key=True),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("source_record_id", sa.Text()),
        sa.Column("request_fingerprint", sa.Text(), nullable=False),
        sa.Column(
            "request_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("http_status", sa.Integer()),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("provider_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "response_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_artifact_uri", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_source_snapshots_provider_payload_gin",
        "source_snapshots",
        ["provider_payload"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_source_snapshots_request_fingerprint",
        "source_snapshots",
        ["request_fingerprint"],
    )
    op.create_index(
        "ix_source_snapshots_source_operation",
        "source_snapshots",
        ["source_name", "operation"],
    )

    op.create_table(
        "snapshot_manifests",
        sa.Column("manifest_hash", sa.Text(), primary_key=True),
        sa.Column("artifact_type", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.Column(
            "parent_hashes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("manifest_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_snapshot_manifests_artifact_type",
        "snapshot_manifests",
        ["artifact_type"],
    )
    op.create_index(
        "ix_snapshot_manifests_manifest_payload_gin",
        "snapshot_manifests",
        ["manifest_payload"],
        postgresql_using="gin",
    )

    op.create_table(
        "works",
        sa.Column("work_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("current_manifest_hash", sa.Text()),
        sa.Column("title", sa.Text()),
        sa.Column("publication_year", sa.Integer()),
        sa.Column("published_at", sa.Date()),
        sa.Column("primary_doi", sa.Text()),
        sa.Column(
            "normalized_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["current_manifest_hash"],
            ["snapshot_manifests.manifest_hash"],
            ondelete="SET NULL",
        ),
    )

    op.create_table(
        "work_identifiers",
        sa.Column("work_identifier_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("work_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id_namespace", sa.Text(), nullable=False),
        sa.Column("id_value", sa.Text(), nullable=False),
        sa.Column("source_snapshot_hash", sa.Text()),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["work_id"], ["works.work_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_snapshot_hash"],
            ["source_snapshots.snapshot_hash"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "work_id",
            "id_namespace",
            "id_value",
            name="uq_work_identifiers_work_namespace_value",
        ),
    )
    op.create_index(
        "ix_work_identifiers_namespace_value",
        "work_identifiers",
        ["id_namespace", "id_value"],
    )

    op.create_table(
        "work_sources",
        sa.Column("work_source_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("work_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.Column("source_snapshot_hash", sa.Text()),
        sa.Column("source_record_id", sa.Text()),
        sa.Column("source_projection", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "discovered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["work_id"], ["works.work_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_snapshot_hash"],
            ["source_snapshots.snapshot_hash"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_work_sources_projection_gin",
        "work_sources",
        ["source_projection"],
        postgresql_using="gin",
    )
    op.create_index("ix_work_sources_work_source", "work_sources", ["work_id", "source_name"])

    op.create_table(
        "fulltext_assets",
        sa.Column("fulltext_asset_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("work_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.Column("source_snapshot_hash", sa.Text()),
        sa.Column("asset_hash", sa.Text(), nullable=False),
        sa.Column("asset_kind", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("legal_status", sa.Text(), nullable=False),
        sa.Column("license_group", sa.Text()),
        sa.Column(
            "license_observation",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("object_uri", sa.Text()),
        sa.Column(
            "parent_hashes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "asset_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["work_id"], ["works.work_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_snapshot_hash"],
            ["source_snapshots.snapshot_hash"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("asset_hash", name="uq_fulltext_assets_asset_hash"),
    )
    op.create_index(
        "ix_fulltext_assets_asset_metadata_gin",
        "fulltext_assets",
        ["asset_metadata"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_fulltext_assets_work_legal_status",
        "fulltext_assets",
        ["work_id", "legal_status"],
    )

    op.create_table(
        "enrichment_openalex",
        sa.Column("enrichment_openalex_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("work_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("openalex_id", sa.Text(), nullable=False),
        sa.Column("source_snapshot_hash", sa.Text()),
        sa.Column("provider_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("projection", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("enriched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["work_id"], ["works.work_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_snapshot_hash"],
            ["source_snapshots.snapshot_hash"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "work_id",
            "source_snapshot_hash",
            name="uq_enrichment_openalex_work_source_snapshot",
        ),
    )
    op.create_index(
        "ix_enrichment_openalex_openalex_id",
        "enrichment_openalex",
        ["openalex_id"],
    )
    op.create_index(
        "ix_enrichment_openalex_projection_gin",
        "enrichment_openalex",
        ["projection"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_enrichment_openalex_provider_payload_gin",
        "enrichment_openalex",
        ["provider_payload"],
        postgresql_using="gin",
    )

    op.create_table(
        "build_runs",
        sa.Column("build_run_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("query_manifest_hash", sa.Text()),
        sa.Column("snapshot_manifest_hash", sa.Text()),
        sa.Column(
            "parameters",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "parent_hashes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("output_manifest_hash", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["query_manifest_hash"],
            ["query_manifests.manifest_hash"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_manifest_hash"],
            ["snapshot_manifests.manifest_hash"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_build_runs_parameters_gin",
        "build_runs",
        ["parameters"],
        postgresql_using="gin",
    )
    op.create_index("ix_build_runs_status", "build_runs", ["status"])

    op.create_table(
        "slice_members",
        sa.Column("slice_member_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("build_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("work_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("member_manifest_hash", sa.Text()),
        sa.Column("slice_hash", sa.Text(), nullable=False),
        sa.Column("slice_name", sa.Text(), nullable=False),
        sa.Column("rank", sa.Integer()),
        sa.Column(
            "membership_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["build_run_id"],
            ["build_runs.build_run_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["member_manifest_hash"],
            ["snapshot_manifests.manifest_hash"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["work_id"], ["works.work_id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "build_run_id",
            "slice_hash",
            "work_id",
            name="uq_slice_members_build_slice_hash_work",
        ),
    )
    op.create_index(
        "ix_slice_members_metadata_gin",
        "slice_members",
        ["membership_metadata"],
        postgresql_using="gin",
    )
    op.create_index("ix_slice_members_slice_hash", "slice_members", ["slice_hash"])
    op.create_index("ix_slice_members_work_id", "slice_members", ["work_id"])

    op.create_table(
        "review_conflicts",
        sa.Column("review_conflict_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("conflict_type", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("id_namespace", sa.Text()),
        sa.Column("id_value", sa.Text()),
        sa.Column("left_work_id", postgresql.UUID(as_uuid=True)),
        sa.Column("right_work_id", postgresql.UUID(as_uuid=True)),
        sa.Column("source_snapshot_hash", sa.Text()),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("resolution_note", sa.Text()),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["left_work_id"], ["works.work_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["right_work_id"], ["works.work_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["source_snapshot_hash"],
            ["source_snapshots.snapshot_hash"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_review_conflicts_identifier",
        "review_conflicts",
        ["id_namespace", "id_value"],
    )
    op.create_index(
        "ix_review_conflicts_payload_gin",
        "review_conflicts",
        ["payload"],
        postgresql_using="gin",
    )
    op.create_index("ix_review_conflicts_state", "review_conflicts", ["state"])


def downgrade() -> None:
    op.drop_index("ix_review_conflicts_state", table_name="review_conflicts")
    op.drop_index("ix_review_conflicts_payload_gin", table_name="review_conflicts")
    op.drop_index("ix_review_conflicts_identifier", table_name="review_conflicts")
    op.drop_table("review_conflicts")

    op.drop_index("ix_slice_members_work_id", table_name="slice_members")
    op.drop_index("ix_slice_members_slice_hash", table_name="slice_members")
    op.drop_index("ix_slice_members_metadata_gin", table_name="slice_members")
    op.drop_table("slice_members")

    op.drop_index("ix_build_runs_status", table_name="build_runs")
    op.drop_index("ix_build_runs_parameters_gin", table_name="build_runs")
    op.drop_table("build_runs")

    op.drop_index("ix_enrichment_openalex_provider_payload_gin", table_name="enrichment_openalex")
    op.drop_index("ix_enrichment_openalex_projection_gin", table_name="enrichment_openalex")
    op.drop_index("ix_enrichment_openalex_openalex_id", table_name="enrichment_openalex")
    op.drop_table("enrichment_openalex")

    op.drop_index("ix_fulltext_assets_work_legal_status", table_name="fulltext_assets")
    op.drop_index("ix_fulltext_assets_asset_metadata_gin", table_name="fulltext_assets")
    op.drop_table("fulltext_assets")

    op.drop_index("ix_work_sources_work_source", table_name="work_sources")
    op.drop_index("ix_work_sources_projection_gin", table_name="work_sources")
    op.drop_table("work_sources")

    op.drop_index("ix_work_identifiers_namespace_value", table_name="work_identifiers")
    op.drop_table("work_identifiers")

    op.drop_table("works")

    op.drop_index("ix_snapshot_manifests_manifest_payload_gin", table_name="snapshot_manifests")
    op.drop_index("ix_snapshot_manifests_artifact_type", table_name="snapshot_manifests")
    op.drop_table("snapshot_manifests")

    op.drop_index("ix_source_snapshots_source_operation", table_name="source_snapshots")
    op.drop_index("ix_source_snapshots_request_fingerprint", table_name="source_snapshots")
    op.drop_index("ix_source_snapshots_provider_payload_gin", table_name="source_snapshots")
    op.drop_table("source_snapshots")

    op.drop_index("ix_query_manifests_manifest_payload_gin", table_name="query_manifests")
    op.drop_table("query_manifests")
