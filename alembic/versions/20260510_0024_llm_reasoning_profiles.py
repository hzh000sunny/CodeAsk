"""llm reasoning request profiles

Revision ID: 0024
Revises: 0023
Create Date: 2026-05-10 01:18:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("llm_configs") as batch_op:
        batch_op.add_column(
            sa.Column(
                "reasoning_profile",
                sa.String(length=64),
                nullable=False,
                server_default="none",
            )
        )
        batch_op.add_column(
            sa.Column("reasoning_profile_json", sa.String(length=4096), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("llm_configs") as batch_op:
        batch_op.drop_column("reasoning_profile_json")
        batch_op.drop_column("reasoning_profile")
