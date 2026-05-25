"""openviking v1.0.5 sync and dashboard tables

Revision ID: 0030
Revises: 0029
Create Date: 2026-05-25 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "openviking_sync_jobs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("feature_slug", sa.String(length=128), nullable=True),
        sa.Column("viking_uri", sa.String(length=512), nullable=True),
        sa.Column("source_hash", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("task_id", sa.String(length=128), nullable=True),
        sa.Column("progress", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'indexed', 'failed', 'cancelled')",
            name="ck_openviking_sync_jobs_status",
        ),
        sa.UniqueConstraint("source_type", "source_id", name="uq_openviking_sync_jobs_source"),
    )
    op.create_index(
        "ix_openviking_sync_jobs_status_next_retry",
        "openviking_sync_jobs",
        ["status", "next_retry_at"],
    )
    op.create_table(
        "openviking_embedding_settings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="ollama"),
        sa.Column("base_url", sa.String(length=256), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("dimension", sa.Integer(), nullable=True),
        sa.Column("max_concurrent", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_by", sa.String(length=64), nullable=True),
        sa.Column("previous_setting_id", sa.Integer(), nullable=True),
        sa.Column("rebuild_status", sa.String(length=16), nullable=False, server_default="idle"),
        sa.Column("rebuild_progress", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "rebuild_status IN ('idle', 'rebuilding', 'completed', 'failed', 'pending_pull')",
            name="ck_openviking_embedding_settings_rebuild_status",
        ),
    )
    op.create_table(
        "openviking_tuning_settings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.String(length=256), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_by", sa.String(length=64), nullable=True),
        sa.Column("previous_value", sa.String(length=256), nullable=True),
        sa.Column("notes", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_openviking_tuning_settings_scope_key_id",
        "openviking_tuning_settings",
        ["scope", "key", "id"],
    )
    op.create_table(
        "openviking_dashboard_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=True),
        sa.Column("source_id", sa.String(length=128), nullable=True),
        sa.Column("sync_job_id", sa.String(length=64), nullable=True),
        sa.Column("triggered_by", sa.String(length=128), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("outcome", sa.String(length=16), nullable=False, server_default="info"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "outcome IN ('info', 'success', 'warning', 'error')",
            name="ck_openviking_dashboard_events_outcome",
        ),
    )
    op.create_index(
        "ix_openviking_dashboard_events_type_id",
        "openviking_dashboard_events",
        ["event_type", "id"],
    )
    op.create_index(
        "ix_openviking_dashboard_events_created_at",
        "openviking_dashboard_events",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_openviking_dashboard_events_created_at", table_name="openviking_dashboard_events")
    op.drop_index("ix_openviking_dashboard_events_type_id", table_name="openviking_dashboard_events")
    op.drop_table("openviking_dashboard_events")
    op.drop_index("ix_openviking_tuning_settings_scope_key_id", table_name="openviking_tuning_settings")
    op.drop_table("openviking_tuning_settings")
    op.drop_table("openviking_embedding_settings")
    op.drop_index("ix_openviking_sync_jobs_status_next_retry", table_name="openviking_sync_jobs")
    op.drop_table("openviking_sync_jobs")
