"""llm_configs

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-30 00:00:05
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_configs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("protocol", sa.String(length=32), nullable=False),
        sa.Column("base_url", sa.String(length=512), nullable=True),
        sa.Column("api_key_encrypted", sa.String(length=2048), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column(
            "max_tokens",
            sa.Integer(),
            nullable=False,
            server_default="4096",
        ),
        sa.Column(
            "temperature",
            sa.Float(),
            nullable=False,
            server_default="0.2",
        ),
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
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
        sa.CheckConstraint(
            "protocol IN ('openai', 'openai_compatible', 'anthropic')",
            name="ck_llm_configs_protocol",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_llm_configs_name"),
    )
    op.create_index(
        "ix_llm_configs_only_one_default",
        "llm_configs",
        ["is_default"],
        unique=True,
        sqlite_where=sa.text("is_default = 1"),
    )


def downgrade() -> None:
    op.drop_index("ix_llm_configs_only_one_default", table_name="llm_configs")
    op.drop_table("llm_configs")
