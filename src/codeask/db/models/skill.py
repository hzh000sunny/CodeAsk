"""Prompt skills injected globally or per feature."""

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from codeask.db.base import Base, TimestampMixin


class Skill(Base, TimestampMixin):
    """Prompt template injected into agent context."""

    __tablename__ = "skills"
    __table_args__ = (
        CheckConstraint("scope IN ('global', 'feature')", name="ck_skills_scope"),
        CheckConstraint(
            "(scope = 'global' AND feature_id IS NULL) OR "
            "(scope = 'feature' AND feature_id IS NOT NULL)",
            name="ck_skills_scope_feature_consistency",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    feature_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("features.id", ondelete="CASCADE"),
        nullable=True,
    )
    stage: Mapped[str] = mapped_column(String(64), nullable=False, default="all")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    prompt_template: Mapped[str] = mapped_column(Text, nullable=False)
