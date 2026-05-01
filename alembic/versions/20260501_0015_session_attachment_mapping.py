"""session attachment stable mapping

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-01 00:00:02
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "session_attachments",
        sa.Column(
            "aliases_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.add_column(
        "session_attachments",
        sa.Column("description", sa.Text(), nullable=True),
    )

    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, display_name, original_filename FROM session_attachments")
    ).mappings()
    for row in rows:
        aliases = _unique_non_empty(
            [
                str(row["original_filename"] or ""),
                str(row["display_name"] or ""),
            ]
        )
        connection.execute(
            sa.text(
                """
                UPDATE session_attachments
                SET aliases_json = :aliases_json
                WHERE id = :id
                """
            ),
            {"id": row["id"], "aliases_json": json.dumps(aliases, ensure_ascii=False)},
        )


def downgrade() -> None:
    op.drop_column("session_attachments", "description")
    op.drop_column("session_attachments", "aliases_json")


def _unique_non_empty(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = value.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result
