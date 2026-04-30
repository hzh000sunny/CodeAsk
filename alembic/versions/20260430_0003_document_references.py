"""document_references

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-30 00:00:01
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_references",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("target_path", sa.String(length=2048), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_document_references_document_id",
        "document_references",
        ["document_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_references_document_id", table_name="document_references")
    op.drop_table("document_references")
