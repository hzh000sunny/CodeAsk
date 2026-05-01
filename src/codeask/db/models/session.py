"""Session and related binding tables."""

from pathlib import Path
from typing import Any

from sqlalchemy import JSON, Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text
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
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


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


class SessionTurn(Base, TimestampMixin):
    """One user or agent message in a session."""

    __tablename__ = "session_turns"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'agent')", name="ck_session_turns_role"),
        Index("ix_session_turns_session", "session_id", "turn_index"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[Any | None] = mapped_column(JSON, nullable=True)


class SessionAttachment(Base, TimestampMixin):
    """File attachment associated with a session."""

    __tablename__ = "session_attachments"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('log', 'image', 'doc', 'other')",
            name="ck_session_attachments_kind",
        ),
        Index("ix_session_attachments_session", "session_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(256), nullable=False)
    aliases_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    @property
    def aliases(self) -> list[str]:
        """Human-facing names that may be used to refer to the attachment."""

        return _unique_non_empty(
            [
                *(self.aliases_json or []),
                self.original_filename,
                self.display_name,
            ]
        )

    @property
    def reference_names(self) -> list[str]:
        """Stable id plus every filename-like handle the user or agent may mention."""

        return _unique_non_empty(
            [
                self.id,
                self.display_name,
                *self.aliases,
                self.original_filename,
                Path(self.file_path).name,
            ]
        )


def _unique_non_empty(values: list[str | None]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = str(value or "").strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result
