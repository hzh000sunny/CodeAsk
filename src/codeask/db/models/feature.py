"""Feature ORM model."""

from typing import Any

from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from codeask.db.base import Base, TimestampMixin


class Feature(Base, TimestampMixin):
    """User-defined knowledge collection with a social owner."""

    __tablename__ = "features"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_subject_id: Mapped[str] = mapped_column(String(128), nullable=False)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    navigation_index_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
