"""Wiki tree node ORM models."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from codeask.db.base import Base, TimestampMixin


class WikiNode(Base, TimestampMixin):
    __tablename__ = "wiki_nodes"
    __table_args__ = (
        CheckConstraint(
            "type IN ('folder','document','asset','report_ref')",
            name="ck_wiki_nodes_type",
        ),
        Index("ix_wiki_nodes_parent_id", "parent_id"),
        Index(
            "ix_wiki_nodes_space_path",
            "space_id",
            "path",
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    space_id: Mapped[int] = mapped_column(
        ForeignKey("wiki_spaces.id", ondelete="CASCADE"), nullable=False
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("wiki_nodes.id", ondelete="SET NULL"), nullable=True
    )
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(String(2048), nullable=False)
    system_role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by_subject_id: Mapped[str | None] = mapped_column(String(128), nullable=True)


class WikiReportRef(Base, TimestampMixin):
    __tablename__ = "wiki_report_refs"
    __table_args__ = (
        Index("ix_wiki_report_refs_report_id", "report_id", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    node_id: Mapped[int] = mapped_column(
        ForeignKey("wiki_nodes.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    report_id: Mapped[int] = mapped_column(
        ForeignKey("reports.id", ondelete="CASCADE"), nullable=False
    )
