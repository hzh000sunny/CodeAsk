"""fts5 virtual tables: docs_fts / docs_ngram_fts / reports_fts

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-30 00:00:03
"""

from collections.abc import Sequence
from typing import Union

from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE VIRTUAL TABLE docs_fts USING fts5(
            chunk_id UNINDEXED,
            title,
            heading_path,
            tokenized_text,
            tags,
            path,
            tokenize = "porter unicode61 remove_diacritics 2"
        )
        """
    )
    op.execute(
        """
        CREATE VIRTUAL TABLE docs_ngram_fts USING fts5(
            chunk_id UNINDEXED,
            ngram_text,
            tokenize = "unicode61 remove_diacritics 2"
        )
        """
    )
    op.execute(
        """
        CREATE VIRTUAL TABLE reports_fts USING fts5(
            report_id UNINDEXED,
            title,
            tokenized_text,
            error_signature,
            tags,
            tokenize = "porter unicode61 remove_diacritics 2"
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS reports_fts")
    op.execute("DROP TABLE IF EXISTS docs_ngram_fts")
    op.execute("DROP TABLE IF EXISTS docs_fts")
