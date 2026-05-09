"""session title source

Revision ID: 0023
Revises: 0022
Create Date: 2026-05-09 12:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "title_source",
                sa.String(length=16),
                nullable=False,
                server_default="manual",
            )
        )
        batch_op.add_column(sa.Column("title_generated_at", sa.DateTime(timezone=True)))
        batch_op.create_check_constraint(
            "ck_sessions_title_source",
            "title_source IN ('default', 'auto', 'manual')",
        )


def downgrade() -> None:
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.drop_constraint("ck_sessions_title_source", type_="check")
        batch_op.drop_column("title_generated_at")
        batch_op.drop_column("title_source")
