"""Wiki space ORM model."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from codeask.db.base import Base, TimestampMixin


class WikiSpace(Base, TimestampMixin):
    __tablename__ = "wiki_spaces"
    __table_args__ = (
        CheckConstraint("scope IN ('current','history')", name="ck_wiki_spaces_scope"),
        CheckConstraint("status IN ('active','archived')", name="ck_wiki_spaces_status"),
        Index("ix_wiki_spaces_feature_scope", "feature_id", "scope", unique=True),
        Index("ix_wiki_spaces_feature_id", "feature_id"),
        Index("ix_wiki_spaces_slug", "slug"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    feature_id: Mapped[int] = mapped_column(
        ForeignKey("features.id", ondelete="CASCADE"), nullable=False
    )
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by_subject_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
