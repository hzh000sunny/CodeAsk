"""session attachment metadata

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-01 00:00:01
"""

from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "session_attachments",
        sa.Column("display_name", sa.String(length=256), nullable=False, server_default=""),
    )
    op.add_column(
        "session_attachments",
        sa.Column(
            "original_filename",
            sa.String(length=256),
            nullable=False,
            server_default="",
        ),
    )
    op.add_column("session_attachments", sa.Column("size_bytes", sa.Integer(), nullable=True))

    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, file_path FROM session_attachments")).mappings()
    for row in rows:
        fallback_name = Path(str(row["file_path"])).name or str(row["id"])
        connection.execute(
            sa.text(
                """
                UPDATE session_attachments
                SET display_name = :display_name,
                    original_filename = :original_filename,
                    size_bytes = COALESCE(size_bytes, 0)
                WHERE id = :id
                """
            ),
            {
                "id": row["id"],
                "display_name": fallback_name,
                "original_filename": fallback_name,
            },
        )


def downgrade() -> None:
    op.drop_column("session_attachments", "size_bytes")
    op.drop_column("session_attachments", "original_filename")
    op.drop_column("session_attachments", "display_name")
