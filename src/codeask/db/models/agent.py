"""Agent runtime trace models."""

from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from codeask.db.base import Base, TimestampMixin


class AgentTrace(Base, TimestampMixin):
    """Per-stage event log for agent execution."""

    __tablename__ = "agent_traces"
    __table_args__ = (
        Index("ix_agent_traces_turn", "turn_id", "created_at"),
        Index("ix_agent_traces_session_stage", "session_id", "stage"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    turn_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("session_turns.id", ondelete="CASCADE"),
        nullable=False,
    )
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[Any] = mapped_column(JSON, nullable=False)
