"""sessions

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-30 00:00:07
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("created_by_subject_id", sa.String(length=128), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="active",
        ),
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
        sa.CheckConstraint("status IN ('active', 'archived')", name="ck_sessions_status"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sessions_subject", "sessions", ["created_by_subject_id"])


def downgrade() -> None:
    op.drop_index("ix_sessions_subject", table_name="sessions")
    op.drop_table("sessions")
