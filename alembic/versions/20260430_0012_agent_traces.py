"""agent_traces

Revision ID: 0012
Revises: 0011
Create Date: 2026-04-30 00:00:10
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_traces",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("turn_id", sa.String(length=64), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
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
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["turn_id"], ["session_turns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_traces_turn",
        "agent_traces",
        ["turn_id", "created_at"],
    )
    op.create_index(
        "ix_agent_traces_session_stage",
        "agent_traces",
        ["session_id", "stage"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_traces_session_stage", table_name="agent_traces")
    op.drop_index("ix_agent_traces_turn", table_name="agent_traces")
    op.drop_table("agent_traces")
