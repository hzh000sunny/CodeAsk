"""code_index: repos + feature_repos

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-30 00:00:04
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "repos",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("url", sa.String(length=1024), nullable=True),
        sa.Column("local_path", sa.String(length=1024), nullable=True),
        sa.Column("bare_path", sa.String(length=1024), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="registered",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
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
            "status IN ('registered','cloning','ready','failed')",
            name="ck_repos_status",
        ),
        sa.CheckConstraint("source IN ('git','local_dir')", name="ck_repos_source"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_repos_status", "repos", ["status"])

    op.create_table(
        "feature_repos",
        sa.Column("feature_id", sa.Integer(), nullable=False),
        sa.Column("repo_id", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["feature_id"], ["features.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["repo_id"], ["repos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("feature_id", "repo_id"),
    )
    op.create_index("ix_feature_repos_repo_id", "feature_repos", ["repo_id"])


def downgrade() -> None:
    op.drop_index("ix_feature_repos_repo_id", table_name="feature_repos")
    op.drop_table("feature_repos")
    op.drop_index("ix_repos_status", table_name="repos")
    op.drop_table("repos")
