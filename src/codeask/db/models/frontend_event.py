"""Frontend telemetry events used by alpha metrics."""

from typing import Any

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from codeask.db.base import Base, TimestampMixin


class FrontendEvent(Base, TimestampMixin):
    """Raw frontend event row. Event-type validation happens at the API layer."""

    __tablename__ = "frontend_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    subject_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
