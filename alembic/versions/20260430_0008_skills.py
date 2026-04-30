"""skills

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-30 00:00:06
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "skills",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("feature_id", sa.Integer(), nullable=True),
        sa.Column("prompt_template", sa.Text(), nullable=False),
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
        sa.ForeignKeyConstraint(["feature_id"], ["features.id"], ondelete="CASCADE"),
        sa.CheckConstraint("scope IN ('global', 'feature')", name="ck_skills_scope"),
        sa.CheckConstraint(
            "(scope = 'global' AND feature_id IS NULL) OR "
            "(scope = 'feature' AND feature_id IS NOT NULL)",
            name="ck_skills_scope_feature_consistency",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_skills_feature", "skills", ["feature_id"])


def downgrade() -> None:
    op.drop_index("ix_skills_feature", table_name="skills")
    op.drop_table("skills")
