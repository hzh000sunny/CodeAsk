"""llm config aligned to opencode provider catalog

Drop the self-maintained protocol/profile abstraction and the dead tuning
fields; add ``mode`` (catalog|custom), ``provider_id`` (models.dev id or custom
slug) and ``headers_encrypted`` (custom request headers). The ``name`` unique
constraint becomes scope+owner scoped. Per the alignment plan we do not migrate
old rows — both ``llm_configs`` and ``llm_runtime_adapters`` are cleared so users
reconfigure from scratch.

Revision ID: 0034
Revises: 0033
Create Date: 2026-06-23 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Not migrating old data: clear children first (FK), then configs.
    op.execute("DELETE FROM llm_runtime_adapters")
    op.execute("DELETE FROM llm_configs")

    with op.batch_alter_table("llm_configs") as batch_op:
        batch_op.add_column(
            sa.Column(
                "mode",
                sa.String(length=16),
                nullable=False,
                server_default="catalog",
            )
        )
        batch_op.add_column(
            sa.Column(
                "provider_id",
                sa.String(length=128),
                nullable=False,
                server_default="",
            )
        )
        batch_op.add_column(
            sa.Column("headers_encrypted", sa.Text(), nullable=True)
        )
        batch_op.drop_constraint("ck_llm_configs_protocol", type_="check")
        batch_op.drop_column("protocol")
        batch_op.drop_column("opencode_provider_profile")
        batch_op.drop_column("max_tokens")
        batch_op.drop_column("temperature")
        batch_op.drop_column("rpm_limit")
        batch_op.drop_column("quota_remaining")
        batch_op.drop_constraint("uq_llm_configs_name", type_="unique")
        batch_op.create_unique_constraint(
            "uq_llm_configs_scope_owner_name",
            ["scope", "owner_subject_id", "name"],
        )
        batch_op.create_check_constraint(
            "ck_llm_configs_mode",
            "mode IN ('catalog', 'custom')",
        )

    # provider_id has no sensible default at runtime; drop the migration-only
    # placeholder server_default now that the column exists on an empty table.
    with op.batch_alter_table("llm_configs") as batch_op:
        batch_op.alter_column(
            "provider_id",
            existing_type=sa.String(length=128),
            server_default=None,
            nullable=False,
        )


def downgrade() -> None:
    op.execute("DELETE FROM llm_runtime_adapters")
    op.execute("DELETE FROM llm_configs")

    with op.batch_alter_table("llm_configs") as batch_op:
        batch_op.drop_constraint("ck_llm_configs_mode", type_="check")
        batch_op.drop_constraint("uq_llm_configs_scope_owner_name", type_="unique")
        batch_op.create_unique_constraint("uq_llm_configs_name", ["name"])
        batch_op.add_column(
            sa.Column(
                "protocol",
                sa.String(length=32),
                nullable=False,
                server_default="openai",
            )
        )
        batch_op.add_column(
            sa.Column(
                "opencode_provider_profile",
                sa.String(length=128),
                nullable=False,
                server_default="default",
            )
        )
        batch_op.add_column(
            sa.Column(
                "max_tokens",
                sa.Integer(),
                nullable=False,
                server_default="4096",
            )
        )
        batch_op.add_column(
            sa.Column(
                "temperature",
                sa.Float(),
                nullable=False,
                server_default="0.2",
            )
        )
        batch_op.add_column(sa.Column("rpm_limit", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("quota_remaining", sa.Float(), nullable=True))
        batch_op.create_check_constraint(
            "ck_llm_configs_protocol",
            "protocol IN ('openai', 'openai_compatible', 'anthropic')",
        )
        batch_op.drop_column("headers_encrypted")
        batch_op.drop_column("provider_id")
        batch_op.drop_column("mode")
