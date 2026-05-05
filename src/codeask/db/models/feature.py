"""Feature ORM model."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from codeask.db.base import Base, TimestampMixin


class Feature(Base, TimestampMixin):
    """User-defined knowledge collection with a social owner."""

    __tablename__ = "features"
    __table_args__ = (
        CheckConstraint("status IN ('active','archived')", name="ck_features_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_subject_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by_subject_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    navigation_index_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
