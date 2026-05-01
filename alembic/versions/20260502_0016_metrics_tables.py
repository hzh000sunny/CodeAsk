"""metrics: feedback / frontend_events / audit_log

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-02 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "feedback",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("session_turn_id", sa.String(length=64), nullable=False),
        sa.Column("feedback", sa.String(length=16), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("subject_id", sa.String(length=128), nullable=False),
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
            "feedback IN ('solved', 'partial', 'wrong')",
            name="ck_feedback_verdict",
        ),
        sa.ForeignKeyConstraint(["session_turn_id"], ["session_turns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_feedback_session_turn_id", "feedback", ["session_turn_id"])
    op.create_index("ix_feedback_subject_id", "feedback", ["subject_id"])

    op.create_table(
        "frontend_events",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("subject_id", sa.String(length=128), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_frontend_events_event_type", "frontend_events", ["event_type"])
    op.create_index("ix_frontend_events_session_id", "frontend_events", ["session_id"])
    op.create_index("ix_frontend_events_subject_id", "frontend_events", ["subject_id"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=True),
        sa.Column("to_status", sa.String(length=32), nullable=True),
        sa.Column("subject_id", sa.String(length=128), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_log_entity", "audit_log", ["entity_type", "entity_id", "at"])
    op.create_index("ix_audit_log_subject_at", "audit_log", ["subject_id", "at"])


def downgrade() -> None:
    op.drop_index("ix_audit_log_subject_at", table_name="audit_log")
    op.drop_index("ix_audit_log_entity", table_name="audit_log")
    op.drop_table("audit_log")

    op.drop_index("ix_frontend_events_subject_id", table_name="frontend_events")
    op.drop_index("ix_frontend_events_session_id", table_name="frontend_events")
    op.drop_index("ix_frontend_events_event_type", table_name="frontend_events")
    op.drop_table("frontend_events")

    op.drop_index("ix_feedback_subject_id", table_name="feedback")
    op.drop_index("ix_feedback_session_turn_id", table_name="feedback")
    op.drop_table("feedback")
