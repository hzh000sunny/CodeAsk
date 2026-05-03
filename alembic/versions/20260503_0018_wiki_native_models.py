"""wiki native models

Revision ID: 0018
Revises: 0017
Create Date: 2026-05-03 00:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column[object]]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "wiki_spaces",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("feature_id", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by_subject_id", sa.String(length=128), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("scope IN ('current','history')", name="ck_wiki_spaces_scope"),
        sa.CheckConstraint("status IN ('active','archived')", name="ck_wiki_spaces_status"),
        sa.ForeignKeyConstraint(["feature_id"], ["features.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_wiki_spaces_feature_id", "wiki_spaces", ["feature_id"])
    op.create_index(
        "ix_wiki_spaces_feature_scope",
        "wiki_spaces",
        ["feature_id", "scope"],
        unique=True,
    )
    op.create_index("ix_wiki_spaces_slug", "wiki_spaces", ["slug"])

    op.create_table(
        "wiki_nodes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("space_id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("path", sa.String(length=2048), nullable=False),
        sa.Column("system_role", sa.String(length=64), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_subject_id", sa.String(length=128), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "type IN ('folder','document','asset','report_ref')",
            name="ck_wiki_nodes_type",
        ),
        sa.ForeignKeyConstraint(["parent_id"], ["wiki_nodes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["space_id"], ["wiki_spaces.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_wiki_nodes_parent_id", "wiki_nodes", ["parent_id"])
    op.create_index(
        "ix_wiki_nodes_space_path",
        "wiki_nodes",
        ["space_id", "path"],
        unique=True,
        sqlite_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "wiki_documents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("node_id", sa.Integer(), nullable=False),
        sa.Column("legacy_document_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("current_version_id", sa.Integer(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("index_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("broken_refs_json", sa.JSON(), nullable=True),
        sa.Column("provenance_json", sa.JSON(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["node_id"], ["wiki_nodes.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_wiki_documents_node_id", "wiki_documents", ["node_id"], unique=True)
    op.create_index(
        "ix_wiki_documents_legacy_document_id",
        "wiki_documents",
        ["legacy_document_id"],
        unique=True,
    )

    op.create_table(
        "wiki_document_versions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("body_markdown", sa.Text(), nullable=False),
        sa.Column("created_by_subject_id", sa.String(length=128), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["document_id"], ["wiki_documents.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_wiki_document_versions_doc_version",
        "wiki_document_versions",
        ["document_id", "version_no"],
        unique=True,
    )

    op.create_table(
        "wiki_document_drafts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.String(length=128), nullable=False),
        sa.Column("body_markdown", sa.Text(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["document_id"], ["wiki_documents.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_wiki_document_drafts_doc_subject",
        "wiki_document_drafts",
        ["document_id", "subject_id"],
        unique=True,
    )

    op.create_table(
        "wiki_assets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("node_id", sa.Integer(), nullable=False),
        sa.Column("original_name", sa.String(length=512), nullable=False),
        sa.Column("file_name", sa.String(length=512), nullable=False),
        sa.Column("storage_path", sa.String(length=1024), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("provenance_json", sa.JSON(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["node_id"], ["wiki_nodes.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_wiki_assets_node_id", "wiki_assets", ["node_id"])

    op.create_table(
        "wiki_sources",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("space_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("uri", sa.String(length=2048), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "kind IN ('manual_upload','directory_import','session_promotion')",
            name="ck_wiki_sources_kind",
        ),
        sa.CheckConstraint(
            "status IN ('active','failed','archived')",
            name="ck_wiki_sources_status",
        ),
        sa.ForeignKeyConstraint(["space_id"], ["wiki_spaces.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_wiki_sources_space_id", "wiki_sources", ["space_id"])

    op.create_table(
        "wiki_report_refs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("node_id", sa.Integer(), nullable=False),
        sa.Column("report_id", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["node_id"], ["wiki_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["report_id"], ["reports.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("node_id", name="uq_wiki_report_refs_node_id"),
    )
    op.create_index("ix_wiki_report_refs_report_id", "wiki_report_refs", ["report_id"], unique=True)

    op.create_table(
        "wiki_node_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("node_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("subject_id", sa.String(length=128), nullable=True),
        sa.Column("from_status", sa.String(length=32), nullable=True),
        sa.Column("to_status", sa.String(length=32), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["node_id"], ["wiki_nodes.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_wiki_node_events_node_id", "wiki_node_events", ["node_id"])

    op.create_table(
        "wiki_import_jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("space_id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("requested_by_subject_id", sa.String(length=128), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('queued','running','succeeded','failed')",
            name="ck_wiki_import_jobs_status",
        ),
        sa.ForeignKeyConstraint(["source_id"], ["wiki_sources.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["space_id"], ["wiki_spaces.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_wiki_import_jobs_space_id", "wiki_import_jobs", ["space_id"])

    op.create_table(
        "wiki_import_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("source_path", sa.String(length=2048), nullable=False),
        sa.Column("target_node_path", sa.String(length=2048), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('pending','imported','conflict','failed')",
            name="ck_wiki_import_items_status",
        ),
        sa.ForeignKeyConstraint(["job_id"], ["wiki_import_jobs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_wiki_import_items_job_id", "wiki_import_items", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_wiki_import_items_job_id", table_name="wiki_import_items")
    op.drop_table("wiki_import_items")

    op.drop_index("ix_wiki_import_jobs_space_id", table_name="wiki_import_jobs")
    op.drop_table("wiki_import_jobs")

    op.drop_index("ix_wiki_node_events_node_id", table_name="wiki_node_events")
    op.drop_table("wiki_node_events")

    op.drop_index("ix_wiki_report_refs_report_id", table_name="wiki_report_refs")
    op.drop_table("wiki_report_refs")

    op.drop_index("ix_wiki_sources_space_id", table_name="wiki_sources")
    op.drop_table("wiki_sources")

    op.drop_index("ix_wiki_assets_node_id", table_name="wiki_assets")
    op.drop_table("wiki_assets")

    op.drop_index(
        "ix_wiki_document_drafts_doc_subject",
        table_name="wiki_document_drafts",
    )
    op.drop_table("wiki_document_drafts")

    op.drop_index(
        "ix_wiki_document_versions_doc_version",
        table_name="wiki_document_versions",
    )
    op.drop_table("wiki_document_versions")

    op.drop_index("ix_wiki_documents_node_id", table_name="wiki_documents")
    op.drop_index("ix_wiki_documents_legacy_document_id", table_name="wiki_documents")
    op.drop_table("wiki_documents")

    op.drop_index("ix_wiki_nodes_space_path", table_name="wiki_nodes")
    op.drop_index("ix_wiki_nodes_parent_id", table_name="wiki_nodes")
    op.drop_table("wiki_nodes")

    op.drop_index("ix_wiki_spaces_slug", table_name="wiki_spaces")
    op.drop_index("ix_wiki_spaces_feature_scope", table_name="wiki_spaces")
    op.drop_index("ix_wiki_spaces_feature_id", table_name="wiki_spaces")
    op.drop_table("wiki_spaces")
