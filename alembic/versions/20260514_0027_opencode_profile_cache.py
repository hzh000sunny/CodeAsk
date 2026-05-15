"""opencode provider profile cache

Revision ID: 0027
Revises: 0026
Create Date: 2026-05-14 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("llm_configs") as batch_op:
        batch_op.add_column(sa.Column("opencode_profile_id", sa.String(length=128), nullable=True))
        batch_op.add_column(
            sa.Column(
                "opencode_profile_status",
                sa.String(length=16),
                server_default="unknown",
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column("opencode_profile_tested_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(sa.Column("opencode_profile_error", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("opencode_profile_attempts_json", sa.JSON(), nullable=True))

    with op.batch_alter_table("external_agent_sessions") as batch_op:
        batch_op.add_column(
            sa.Column("provider_profile_id", sa.String(length=128), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("external_agent_sessions") as batch_op:
        batch_op.drop_column("provider_profile_id")

    with op.batch_alter_table("llm_configs") as batch_op:
        batch_op.drop_column("opencode_profile_attempts_json")
        batch_op.drop_column("opencode_profile_error")
        batch_op.drop_column("opencode_profile_tested_at")
        batch_op.drop_column("opencode_profile_status")
        batch_op.drop_column("opencode_profile_id")
