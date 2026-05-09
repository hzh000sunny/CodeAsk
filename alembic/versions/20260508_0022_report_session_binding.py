"""report session binding

Revision ID: 0022
Revises: 0021
Create Date: 2026-05-08 11:40:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("reports") as batch_op:
        batch_op.add_column(sa.Column("session_id", sa.String(length=64), nullable=True))
        batch_op.create_foreign_key(
            "fk_reports_session_id_sessions",
            "sessions",
            ["session_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_reports_session_id", ["session_id"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("reports") as batch_op:
        batch_op.drop_index("ix_reports_session_id")
        batch_op.drop_constraint("fk_reports_session_id_sessions", type_="foreignkey")
        batch_op.drop_column("session_id")
