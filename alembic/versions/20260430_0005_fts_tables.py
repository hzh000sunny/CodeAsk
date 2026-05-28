"""legacy wiki search virtual table revision kept as a no-op

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-30 00:00:03
"""

from collections.abc import Sequence

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
