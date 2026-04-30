"""ORM models for the global repo pool and feature repo associations."""

from datetime import datetime
from typing import ClassVar

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from codeask.db.base import Base, TimestampMixin


class Repo(Base, TimestampMixin):
    """Repository cached in the global code index pool."""

    __tablename__ = "repos"
    __table_args__ = (
        CheckConstraint(
            "status IN ('registered','cloning','ready','failed')",
            name="ck_repos_status",
        ),
        CheckConstraint("source IN ('git','local_dir')", name="ck_repos_source"),
        Index("ix_repos_status", "status"),
    )

    STATUS_REGISTERED: ClassVar[str] = "registered"
    STATUS_CLONING: ClassVar[str] = "cloning"
    STATUS_READY: ClassVar[str] = "ready"
    STATUS_FAILED: ClassVar[str] = "failed"

    SOURCE_GIT: ClassVar[str] = "git"
    SOURCE_LOCAL_DIR: ClassVar[str] = "local_dir"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    local_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    bare_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=STATUS_REGISTERED,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class FeatureRepo(Base):
    """Many-to-many association between features and global repos."""

    __tablename__ = "feature_repos"
    __table_args__ = (Index("ix_feature_repos_repo_id", "repo_id"),)

    feature_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("features.id", ondelete="CASCADE"),
        primary_key=True,
    )
    repo_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("repos.id", ondelete="CASCADE"),
        primary_key=True,
    )
