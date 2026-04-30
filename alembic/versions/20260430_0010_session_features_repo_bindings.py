"""session_features + session_repo_bindings

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-30 00:00:08
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "session_features",
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("feature_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(["feature_id"], ["features.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "source IN ('auto', 'manual')",
            name="ck_session_features_source",
        ),
        sa.PrimaryKeyConstraint("session_id", "feature_id"),
    )
    op.create_table(
        "session_repo_bindings",
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("repo_id", sa.String(length=64), nullable=False),
        sa.Column("commit_sha", sa.String(length=64), nullable=False),
        sa.Column("worktree_path", sa.String(length=1024), nullable=False),
        sa.ForeignKeyConstraint(["repo_id"], ["repos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("session_id", "repo_id", "commit_sha"),
    )


def downgrade() -> None:
    op.drop_table("session_repo_bindings")
    op.drop_table("session_features")
