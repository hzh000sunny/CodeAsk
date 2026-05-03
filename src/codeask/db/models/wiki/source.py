"""Wiki source ORM model."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from codeask.db.base import Base, TimestampMixin


class WikiSource(Base, TimestampMixin):
    __tablename__ = "wiki_sources"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('manual_upload','directory_import','session_promotion')",
            name="ck_wiki_sources_kind",
        ),
        CheckConstraint(
            "status IN ('active','failed','archived')",
            name="ck_wiki_sources_status",
        ),
        Index("ix_wiki_sources_space_id", "space_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    space_id: Mapped[int] = mapped_column(
        ForeignKey("wiki_spaces.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    uri: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    metadata_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
