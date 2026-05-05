"""wiki import sessions

Revision ID: 0019
Revises: 0018
Create Date: 2026-05-05 00:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column[object]]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "wiki_import_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("space_id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("mode", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="running"),
        sa.Column("requested_by_subject_id", sa.String(length=128), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "mode IN ('markdown','directory')",
            name="ck_wiki_import_sessions_mode",
        ),
        sa.CheckConstraint(
            "status IN ('running','completed','failed','cancelled')",
            name="ck_wiki_import_sessions_status",
        ),
        sa.ForeignKeyConstraint(["parent_id"], ["wiki_nodes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["space_id"], ["wiki_spaces.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_wiki_import_sessions_space_id", "wiki_import_sessions", ["space_id"])

    op.create_table(
        "wiki_import_session_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_path", sa.String(length=2048), nullable=False),
        sa.Column("target_node_path", sa.String(length=2048), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("item_kind", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('pending','uploading','uploaded','conflict','failed','ignored','skipped')",
            name="ck_wiki_import_session_items_status",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["wiki_import_sessions.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_wiki_import_session_items_session_id",
        "wiki_import_session_items",
        ["session_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_wiki_import_session_items_session_id", table_name="wiki_import_session_items")
    op.drop_table("wiki_import_session_items")

    op.drop_index("ix_wiki_import_sessions_space_id", table_name="wiki_import_sessions")
    op.drop_table("wiki_import_sessions")
