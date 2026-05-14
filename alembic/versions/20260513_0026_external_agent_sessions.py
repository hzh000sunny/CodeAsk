"""external agent sessions

Revision ID: 0026
Revises: 0025
Create Date: 2026-05-13 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "external_agent_sessions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("backend_type", sa.String(length=32), nullable=False),
        sa.Column("external_session_key", sa.String(length=128), nullable=False),
        sa.Column("session_dir", sa.String(length=1024), nullable=False),
        sa.Column("workspace_dir", sa.String(length=1024), nullable=False),
        sa.Column("server_url", sa.String(length=256), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("pid", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("config_hash", sa.String(length=128), nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "backend_type IN ('opencode')",
            name="ck_external_agent_sessions_backend_type",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'error', 'cleaned')",
            name="ck_external_agent_sessions_status",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id"),
    )
    op.create_index(
        "ix_external_agent_sessions_session",
        "external_agent_sessions",
        ["session_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_external_agent_sessions_session", table_name="external_agent_sessions")
    op.drop_table("external_agent_sessions")
