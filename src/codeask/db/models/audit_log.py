"""Audit log for report, document, LLM config, and skill state changes."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from codeask.db.base import Base


class AuditLog(Base):
    """Append-only audit row for state transitions and admin writes."""

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_entity", "entity_type", "entity_id", "at"),
        Index("ix_audit_log_subject_at", "subject_id", "at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
