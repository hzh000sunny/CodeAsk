"""Wiki event/audit ORM model."""

from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from codeask.db.base import Base, TimestampMixin


class WikiNodeEvent(Base, TimestampMixin):
    __tablename__ = "wiki_node_events"
    __table_args__ = (Index("ix_wiki_node_events_node_id", "node_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    node_id: Mapped[int] = mapped_column(
        ForeignKey("wiki_nodes.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payload_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
