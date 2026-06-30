from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from convivial_medicine.storage.constants import (
    BuildStatus,
    ConflictResolutionState,
    LegalFulltextStatus,
    WorkStatus,
)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class QueryManifest(Base):
    __tablename__ = "query_manifests"
    __table_args__ = (
        Index(
            "ix_query_manifests_manifest_payload_gin",
            "manifest_payload",
            postgresql_using="gin",
        ),
    )

    manifest_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SourceSnapshot(Base):
    __tablename__ = "source_snapshots"
    __table_args__ = (
        Index("ix_source_snapshots_source_operation", "source_name", "operation"),
        Index("ix_source_snapshots_request_fingerprint", "request_fingerprint"),
        Index(
            "ix_source_snapshots_provider_payload_gin",
            "provider_payload",
            postgresql_using="gin",
        ),
    )

    snapshot_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    operation: Mapped[str] = mapped_column(Text, nullable=False)
    source_record_id: Mapped[str | None] = mapped_column(Text)
    request_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    request_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    http_status: Mapped[int | None] = mapped_column(Integer)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    provider_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    response_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_artifact_uri: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SnapshotManifest(Base):
    __tablename__ = "snapshot_manifests"
    __table_args__ = (
        Index("ix_snapshot_manifests_artifact_type", "artifact_type"),
        Index(
            "ix_snapshot_manifests_manifest_payload_gin",
            "manifest_payload",
            postgresql_using="gin",
        ),
    )

    manifest_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    artifact_type: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    parent_hashes: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    manifest_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    manifest_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Work(TimestampMixin, Base):
    __tablename__ = "works"

    work_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    status: Mapped[str] = mapped_column(Text, nullable=False, default=WorkStatus.CANDIDATE.value)
    current_manifest_hash: Mapped[str | None] = mapped_column(
        ForeignKey("snapshot_manifests.manifest_hash", ondelete="SET NULL")
    )
    title: Mapped[str | None] = mapped_column(Text)
    publication_year: Mapped[int | None] = mapped_column(Integer)
    published_at: Mapped[date | None] = mapped_column(Date)
    primary_doi: Mapped[str | None] = mapped_column(Text)
    normalized_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class WorkIdentifier(Base):
    __tablename__ = "work_identifiers"
    __table_args__ = (
        UniqueConstraint(
            "work_id",
            "id_namespace",
            "id_value",
            name="uq_work_identifiers_work_namespace_value",
        ),
        Index("ix_work_identifiers_namespace_value", "id_namespace", "id_value"),
    )

    work_identifier_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    work_id: Mapped[UUID] = mapped_column(ForeignKey("works.work_id", ondelete="CASCADE"))
    id_namespace: Mapped[str] = mapped_column(Text, nullable=False)
    id_value: Mapped[str] = mapped_column(Text, nullable=False)
    source_snapshot_hash: Mapped[str | None] = mapped_column(
        ForeignKey("source_snapshots.snapshot_hash", ondelete="SET NULL")
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class WorkSource(Base):
    __tablename__ = "work_sources"
    __table_args__ = (
        Index("ix_work_sources_work_source", "work_id", "source_name"),
        Index("ix_work_sources_projection_gin", "source_projection", postgresql_using="gin"),
    )

    work_source_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    work_id: Mapped[UUID] = mapped_column(ForeignKey("works.work_id", ondelete="CASCADE"))
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_snapshot_hash: Mapped[str | None] = mapped_column(
        ForeignKey("source_snapshots.snapshot_hash", ondelete="SET NULL")
    )
    source_record_id: Mapped[str | None] = mapped_column(Text)
    source_projection: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class FulltextAsset(Base):
    __tablename__ = "fulltext_assets"
    __table_args__ = (
        UniqueConstraint("asset_hash", name="uq_fulltext_assets_asset_hash"),
        Index("ix_fulltext_assets_work_legal_status", "work_id", "legal_status"),
        Index("ix_fulltext_assets_asset_metadata_gin", "asset_metadata", postgresql_using="gin"),
    )

    fulltext_asset_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    work_id: Mapped[UUID] = mapped_column(ForeignKey("works.work_id", ondelete="CASCADE"))
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_snapshot_hash: Mapped[str | None] = mapped_column(
        ForeignKey("source_snapshots.snapshot_hash", ondelete="SET NULL")
    )
    asset_hash: Mapped[str] = mapped_column(Text, nullable=False)
    asset_kind: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    legal_status: Mapped[str] = mapped_column(
        Text, nullable=False, default=LegalFulltextStatus.NOT_CHECKED.value
    )
    license_group: Mapped[str | None] = mapped_column(Text)
    license_observation: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    object_uri: Mapped[str | None] = mapped_column(Text)
    parent_hashes: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    asset_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EnrichmentOpenAlex(TimestampMixin, Base):
    __tablename__ = "enrichment_openalex"
    __table_args__ = (
        UniqueConstraint(
            "work_id",
            "source_snapshot_hash",
            name="uq_enrichment_openalex_work_source_snapshot",
        ),
        Index("ix_enrichment_openalex_openalex_id", "openalex_id"),
        Index(
            "ix_enrichment_openalex_provider_payload_gin",
            "provider_payload",
            postgresql_using="gin",
        ),
        Index("ix_enrichment_openalex_projection_gin", "projection", postgresql_using="gin"),
    )

    enrichment_openalex_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    work_id: Mapped[UUID] = mapped_column(ForeignKey("works.work_id", ondelete="CASCADE"))
    openalex_id: Mapped[str] = mapped_column(Text, nullable=False)
    source_snapshot_hash: Mapped[str | None] = mapped_column(
        ForeignKey("source_snapshots.snapshot_hash", ondelete="SET NULL")
    )
    provider_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    projection: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    enriched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BuildRun(TimestampMixin, Base):
    __tablename__ = "build_runs"
    __table_args__ = (
        Index("ix_build_runs_status", "status"),
        Index("ix_build_runs_parameters_gin", "parameters", postgresql_using="gin"),
    )

    build_run_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    run_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default=BuildStatus.PENDING.value)
    query_manifest_hash: Mapped[str | None] = mapped_column(
        ForeignKey("query_manifests.manifest_hash", ondelete="SET NULL")
    )
    snapshot_manifest_hash: Mapped[str | None] = mapped_column(
        ForeignKey("snapshot_manifests.manifest_hash", ondelete="SET NULL")
    )
    parameters: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    parent_hashes: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    output_manifest_hash: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SliceMember(Base):
    __tablename__ = "slice_members"
    __table_args__ = (
        UniqueConstraint(
            "build_run_id",
            "slice_hash",
            "work_id",
            name="uq_slice_members_build_slice_hash_work",
        ),
        Index("ix_slice_members_slice_hash", "slice_hash"),
        Index("ix_slice_members_work_id", "work_id"),
        Index("ix_slice_members_metadata_gin", "membership_metadata", postgresql_using="gin"),
    )

    slice_member_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    build_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("build_runs.build_run_id", ondelete="CASCADE")
    )
    work_id: Mapped[UUID] = mapped_column(ForeignKey("works.work_id", ondelete="CASCADE"))
    member_manifest_hash: Mapped[str | None] = mapped_column(
        ForeignKey("snapshot_manifests.manifest_hash", ondelete="SET NULL")
    )
    slice_hash: Mapped[str] = mapped_column(Text, nullable=False)
    slice_name: Mapped[str] = mapped_column(Text, nullable=False)
    rank: Mapped[int | None] = mapped_column(Integer)
    membership_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ReviewConflict(TimestampMixin, Base):
    __tablename__ = "review_conflicts"
    __table_args__ = (
        Index("ix_review_conflicts_state", "state"),
        Index("ix_review_conflicts_identifier", "id_namespace", "id_value"),
        Index("ix_review_conflicts_payload_gin", "payload", postgresql_using="gin"),
    )

    review_conflict_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    conflict_type: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(
        Text, nullable=False, default=ConflictResolutionState.OPEN.value
    )
    id_namespace: Mapped[str | None] = mapped_column(Text)
    id_value: Mapped[str | None] = mapped_column(Text)
    left_work_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("works.work_id", ondelete="SET NULL")
    )
    right_work_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("works.work_id", ondelete="SET NULL")
    )
    source_snapshot_hash: Mapped[str | None] = mapped_column(
        ForeignKey("source_snapshots.snapshot_hash", ondelete="SET NULL")
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    resolution_note: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
