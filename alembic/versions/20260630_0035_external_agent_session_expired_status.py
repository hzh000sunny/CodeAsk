"""external_agent_sessions: add 'expired' status

Second-tier retention deletes opencode session history (server_data) after a long
idle window and marks the binding ``expired`` (terminal). Extend the status check
constraint to allow it.

Revision ID: 0035
Revises: 0034
Create Date: 2026-06-30 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NAME = "ck_external_agent_sessions_status"


def upgrade() -> None:
    with op.batch_alter_table("external_agent_sessions") as batch_op:
        batch_op.drop_constraint(_NAME, type_="check")
        batch_op.create_check_constraint(
            _NAME,
            "status IN ('active', 'error', 'cleaned', 'expired')",
        )


def downgrade() -> None:
    # Collapse any 'expired' rows back to a value the old constraint allows.
    op.execute("UPDATE external_agent_sessions SET status = 'cleaned' WHERE status = 'expired'")
    with op.batch_alter_table("external_agent_sessions") as batch_op:
        batch_op.drop_constraint(_NAME, type_="check")
        batch_op.create_check_constraint(
            _NAME,
            "status IN ('active', 'error', 'cleaned')",
        )
