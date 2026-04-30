"""Session and related binding tables."""

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from codeask.db.base import Base, TimestampMixin


class Session(Base, TimestampMixin):
    """Conversation owned by a self-reported subject id."""

    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'archived')", name="ck_sessions_status"),
        Index("ix_sessions_subject", "created_by_subject_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    created_by_subject_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")


class SessionFeature(Base):
    """Feature selected for a session by user choice or scope detection."""

    __tablename__ = "session_features"
    __table_args__ = (
        CheckConstraint(
            "source IN ('auto', 'manual')",
            name="ck_session_features_source",
        ),
    )

    session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    feature_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("features.id", ondelete="CASCADE"),
        primary_key=True,
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False)


class SessionRepoBinding(Base):
    """Repo revision mounted for code investigation within a session."""

    __tablename__ = "session_repo_bindings"

    session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    repo_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("repos.id", ondelete="CASCADE"),
        primary_key=True,
    )
    commit_sha: Mapped[str] = mapped_column(String(64), primary_key=True)
    worktree_path: Mapped[str] = mapped_column(String(1024), nullable=False)
