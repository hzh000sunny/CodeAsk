"""ORM models for queue-based wiki import sessions."""

from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from codeask.db.base import Base, TimestampMixin


class WikiImportSession(Base, TimestampMixin):
    __tablename__ = "wiki_import_sessions"
    __table_args__ = (
        CheckConstraint(
            "mode IN ('markdown','directory')",
            name="ck_wiki_import_sessions_mode",
        ),
        CheckConstraint(
            "status IN ('running','completed','failed','cancelled')",
            name="ck_wiki_import_sessions_status",
        ),
        Index("ix_wiki_import_sessions_space_id", "space_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    space_id: Mapped[int] = mapped_column(
        ForeignKey("wiki_spaces.id", ondelete="CASCADE"), nullable=False
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("wiki_nodes.id", ondelete="SET NULL"), nullable=True
    )
    mode: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="running")
    requested_by_subject_id: Mapped[str] = mapped_column(String(128), nullable=False)
    summary_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class WikiImportSessionItem(Base, TimestampMixin):
    __tablename__ = "wiki_import_session_items"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','uploading','uploaded','conflict','failed','ignored','skipped')",
            name="ck_wiki_import_session_items_status",
        ),
        Index("ix_wiki_import_session_items_session_id", "session_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("wiki_import_sessions.id", ondelete="CASCADE"), nullable=False
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    target_node_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    item_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    progress_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
