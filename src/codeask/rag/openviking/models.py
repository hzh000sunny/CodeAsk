"""SQLAlchemy models for OpenViking synchronization and dashboard state."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from codeask.db.base import Base, TimestampMixin


class OpenVikingSyncJob(Base, TimestampMixin):
    __tablename__ = "openviking_sync_jobs"
    __table_args__ = (
        UniqueConstraint("source_type", "source_id", name="uq_openviking_sync_jobs_source"),
        Index("ix_openviking_sync_jobs_status_next_retry", "status", "next_retry_at"),
        CheckConstraint(
            "status IN ('pending', 'running', 'indexed', 'failed', 'cancelled')",
            name="ck_openviking_sync_jobs_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    feature_slug: Mapped[str | None] = mapped_column(String(128), nullable=True)
    viking_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    progress: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class OpenVikingEmbeddingSetting(Base, TimestampMixin):
    __tablename__ = "openviking_embedding_settings"
    __table_args__ = (
        CheckConstraint(
            "rebuild_status IN ('idle', 'rebuilding', 'completed', 'failed', 'pending_pull')",
            name="ck_openviking_embedding_settings_rebuild_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="ollama")
    base_url: Mapped[str] = mapped_column(String(256), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    dimension: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_concurrent: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    activated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    previous_setting_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rebuild_status: Mapped[str] = mapped_column(String(16), nullable=False, default="idle")
    rebuild_progress: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class OpenVikingTuningSetting(Base, TimestampMixin):
    __tablename__ = "openviking_tuning_settings"
    __table_args__ = (Index("ix_openviking_tuning_settings_scope_key_id", "scope", "key", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[str] = mapped_column(String(256), nullable=False)
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    activated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    previous_value: Mapped[str | None] = mapped_column(String(256), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(512), nullable=True)


class OpenVikingDashboardEvent(Base):
    __tablename__ = "openviking_dashboard_events"
    __table_args__ = (
        Index("ix_openviking_dashboard_events_type_id", "event_type", "id"),
        Index("ix_openviking_dashboard_events_created_at", "created_at"),
        CheckConstraint(
            "outcome IN ('info', 'success', 'warning', 'error')",
            name="ck_openviking_dashboard_events_outcome",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sync_job_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    triggered_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False, default="info")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
