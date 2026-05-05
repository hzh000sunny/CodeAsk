"""feature archive status

Revision ID: 0020
Revises: 0019
Create Date: 2026-05-05 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _drop_stale_sqlite_batch_table() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS _alembic_tmp_features"))


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        _drop_stale_sqlite_batch_table()
        op.execute(
            sa.text(
                "ALTER TABLE features "
                "ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT 'active'"
            )
        )
        op.execute(
            sa.text("ALTER TABLE features ADD COLUMN archived_at DATETIME")
        )
        op.execute(
            sa.text("ALTER TABLE features ADD COLUMN archived_by_subject_id VARCHAR(128)")
        )
        return

    op.add_column(
        "features",
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
    )
    op.add_column(
        "features",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "features",
        sa.Column("archived_by_subject_id", sa.String(length=128), nullable=True),
    )
    op.create_check_constraint(
        "ck_features_status",
        "features",
        "status IN ('active','archived')",
    )
    op.alter_column("features", "status", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        _drop_stale_sqlite_batch_table()
        with op.batch_alter_table("features") as batch_op:
            try:
                batch_op.drop_constraint("ck_features_status", type_="check")
            except ValueError:
                pass
            batch_op.drop_column("archived_by_subject_id")
            batch_op.drop_column("archived_at")
            batch_op.drop_column("status")
        return

    op.drop_constraint("ck_features_status", "features", type_="check")
    op.drop_column("features", "archived_by_subject_id")
    op.drop_column("features", "archived_at")
    op.drop_column("features", "status")
