"""opencode explicit provider profile selection

Revision ID: 0028
Revises: 0027
Create Date: 2026-05-14 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("llm_configs") as batch_op:
        batch_op.alter_column(
            "opencode_profile_id",
            new_column_name="opencode_provider_profile",
            existing_type=sa.String(length=128),
            nullable=True,
        )
        batch_op.alter_column(
            "opencode_profile_status",
            new_column_name="opencode_provider_status",
            existing_type=sa.String(length=16),
            existing_server_default="unknown",
            nullable=False,
        )
        batch_op.alter_column(
            "opencode_profile_tested_at",
            new_column_name="opencode_provider_tested_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=True,
        )
        batch_op.alter_column(
            "opencode_profile_error",
            new_column_name="opencode_provider_error",
            existing_type=sa.Text(),
            nullable=True,
        )
        batch_op.alter_column(
            "opencode_profile_attempts_json",
            new_column_name="opencode_provider_test_result_json",
            existing_type=sa.JSON(),
            nullable=True,
        )
    op.execute(
        "UPDATE llm_configs SET opencode_provider_profile = 'default' "
        "WHERE opencode_provider_profile IS NULL OR opencode_provider_profile = ''"
    )
    with op.batch_alter_table("llm_configs") as batch_op:
        batch_op.alter_column(
            "opencode_provider_profile",
            existing_type=sa.String(length=128),
            server_default="default",
            nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("llm_configs") as batch_op:
        batch_op.alter_column(
            "opencode_provider_test_result_json",
            new_column_name="opencode_profile_attempts_json",
            existing_type=sa.JSON(),
            nullable=True,
        )
        batch_op.alter_column(
            "opencode_provider_error",
            new_column_name="opencode_profile_error",
            existing_type=sa.Text(),
            nullable=True,
        )
        batch_op.alter_column(
            "opencode_provider_tested_at",
            new_column_name="opencode_profile_tested_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=True,
        )
        batch_op.alter_column(
            "opencode_provider_status",
            new_column_name="opencode_profile_status",
            existing_type=sa.String(length=16),
            existing_server_default="unknown",
            nullable=False,
        )
        batch_op.alter_column(
            "opencode_provider_profile",
            new_column_name="opencode_profile_id",
            existing_type=sa.String(length=128),
            nullable=True,
        )
