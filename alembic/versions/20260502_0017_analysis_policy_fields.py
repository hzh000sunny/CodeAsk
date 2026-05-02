"""analysis policy fields on skills

Revision ID: 0017
Revises: 0016
Create Date: 2026-05-02 22:52:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "skills",
        sa.Column("stage", sa.String(length=64), nullable=False, server_default="all"),
    )
    op.add_column(
        "skills",
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "skills",
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
    )


def downgrade() -> None:
    op.drop_column("skills", "priority")
    op.drop_column("skills", "enabled")
    op.drop_column("skills", "stage")
