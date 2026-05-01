"""admin rbac + scoped llm configs + pinned sessions

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-01 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_llm_configs_only_one_default", table_name="llm_configs")
    op.add_column(
        "llm_configs",
        sa.Column("scope", sa.String(length=16), nullable=False, server_default="global"),
    )
    op.add_column(
        "llm_configs",
        sa.Column("owner_subject_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "llm_configs",
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column("llm_configs", sa.Column("rpm_limit", sa.Integer(), nullable=True))
    op.add_column("llm_configs", sa.Column("quota_remaining", sa.Float(), nullable=True))
    op.create_index(
        "ix_llm_configs_global_default",
        "llm_configs",
        ["is_default"],
        unique=True,
        sqlite_where=sa.text("is_default = 1 AND scope = 'global'"),
    )
    op.create_index(
        "ix_llm_configs_user_default",
        "llm_configs",
        ["owner_subject_id"],
        unique=True,
        sqlite_where=sa.text("is_default = 1 AND scope = 'user'"),
    )

    op.add_column(
        "sessions",
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("sessions", "pinned")
    op.drop_index("ix_llm_configs_user_default", table_name="llm_configs")
    op.drop_index("ix_llm_configs_global_default", table_name="llm_configs")
    op.drop_column("llm_configs", "quota_remaining")
    op.drop_column("llm_configs", "rpm_limit")
    op.drop_column("llm_configs", "enabled")
    op.drop_column("llm_configs", "owner_subject_id")
    op.drop_column("llm_configs", "scope")
    op.create_index(
        "ix_llm_configs_only_one_default",
        "llm_configs",
        ["is_default"],
        unique=True,
        sqlite_where=sa.text("is_default = 1"),
    )
