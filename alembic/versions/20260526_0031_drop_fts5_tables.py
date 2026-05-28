"""drop legacy wiki FTS5 virtual tables

Revision ID: 0031
Revises: 0030
Create Date: 2026-05-26 00:00:00.000000
"""

from alembic import op


revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS docs_fts")
    op.execute("DROP TABLE IF EXISTS docs_ngram_fts")
    op.execute("DROP TABLE IF EXISTS reports_fts")


def downgrade() -> None:
    raise NotImplementedError("v1.0.5 does not support downgrading to legacy FTS5")
