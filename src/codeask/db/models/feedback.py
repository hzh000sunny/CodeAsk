"""User feedback for a single agent turn."""

from typing import Literal

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from codeask.db.base import Base, TimestampMixin

FeedbackVerdict = Literal["solved", "partial", "wrong"]


class Feedback(Base, TimestampMixin):
    """Explicit user feedback used as the deflection-rate gold signal."""

    __tablename__ = "feedback"
    __table_args__ = (
        CheckConstraint(
            "feedback IN ('solved', 'partial', 'wrong')",
            name="ck_feedback_verdict",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_turn_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("session_turns.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    feedback: Mapped[str] = mapped_column(String(16), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    subject_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
