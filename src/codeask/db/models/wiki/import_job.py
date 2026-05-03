"""Wiki import job ORM models."""

from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from codeask.db.base import Base, TimestampMixin


class WikiImportJob(Base, TimestampMixin):
    __tablename__ = "wiki_import_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','succeeded','failed')",
            name="ck_wiki_import_jobs_status",
        ),
        Index("ix_wiki_import_jobs_space_id", "space_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    space_id: Mapped[int] = mapped_column(
        ForeignKey("wiki_spaces.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("wiki_sources.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    requested_by_subject_id: Mapped[str] = mapped_column(String(128), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class WikiImportItem(Base, TimestampMixin):
    __tablename__ = "wiki_import_items"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','imported','conflict','failed')",
            name="ck_wiki_import_items_status",
        ),
        Index("ix_wiki_import_items_job_id", "job_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("wiki_import_jobs.id", ondelete="CASCADE"), nullable=False
    )
    source_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    target_node_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    metadata_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
