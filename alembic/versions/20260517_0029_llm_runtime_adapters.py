"""llm runtime adapters

Revision ID: 0029
Revises: 0028
Create Date: 2026-05-17 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_runtime_adapters",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "llm_config_id",
            sa.String(length=64),
            sa.ForeignKey("llm_configs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("runtime_backend", sa.String(length=64), nullable=False),
        sa.Column(
            "adapter_profile",
            sa.String(length=128),
            nullable=False,
            server_default="default",
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("test_result_json", sa.JSON(), nullable=True),
        sa.Column("config_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('unknown', 'ok', 'failed')",
            name="ck_llm_runtime_adapters_status",
        ),
        sa.UniqueConstraint(
            "llm_config_id",
            "runtime_backend",
            name="uq_llm_runtime_adapters_config_backend",
        ),
    )
    op.execute(
        """
        INSERT INTO llm_runtime_adapters (
            id,
            llm_config_id,
            runtime_backend,
            adapter_profile,
            status,
            tested_at,
            error,
            test_result_json,
            config_fingerprint,
            created_at,
            updated_at
        )
        SELECT
            'adapter_' || id || '_opencode',
            id,
            'opencode',
            COALESCE(NULLIF(opencode_provider_profile, ''), 'default'),
            COALESCE(NULLIF(opencode_provider_status, ''), 'unknown'),
            opencode_provider_tested_at,
            opencode_provider_error,
            opencode_provider_test_result_json,
            NULL,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        FROM llm_configs
        """
    )


def downgrade() -> None:
    op.drop_table("llm_runtime_adapters")
