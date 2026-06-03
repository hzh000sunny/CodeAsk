"""openviking model configuration

Revision ID: 0033
Revises: 0032
Create Date: 2026-06-02 00:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "openviking_embedding_settings",
        sa.Column("input", sa.String(length=32), nullable=False, server_default="text"),
    )
    op.add_column(
        "openviking_embedding_settings",
        sa.Column("api_key_encrypted", sa.String(length=2048), nullable=True),
    )
    op.add_column(
        "openviking_embedding_settings",
        sa.Column("extra", sa.JSON(), nullable=True),
    )
    op.create_table(
        "openviking_vlm_settings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("base_url", sa.String(length=256), nullable=True),
        sa.Column("api_key_encrypted", sa.String(length=2048), nullable=True),
        sa.Column("temperature", sa.String(length=32), nullable=False, server_default="0.0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("timeout", sa.String(length=32), nullable=False, server_default="60.0"),
        sa.Column("extra", sa.JSON(), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_by", sa.String(length=64), nullable=True),
        sa.Column("previous_setting_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("openviking_vlm_settings")
    op.drop_column("openviking_embedding_settings", "extra")
    op.drop_column("openviking_embedding_settings", "api_key_encrypted")
    op.drop_column("openviking_embedding_settings", "input")
