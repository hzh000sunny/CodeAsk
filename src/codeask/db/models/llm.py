"""LLM provider configuration models."""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from codeask.db.base import Base, TimestampMixin


class LLMConfig(Base, TimestampMixin):
    """Provider-neutral LLM configuration with encrypted API key."""

    __tablename__ = "llm_configs"
    __table_args__ = (
        UniqueConstraint("name", name="uq_llm_configs_name"),
        CheckConstraint("scope IN ('global', 'user')", name="ck_llm_configs_scope"),
        Index(
            "ix_llm_configs_global_default",
            "is_default",
            unique=True,
            sqlite_where=text("is_default = 1 AND scope = 'global'"),
        ),
        Index(
            "ix_llm_configs_user_default",
            "owner_subject_id",
            unique=True,
            sqlite_where=text("is_default = 1 AND scope = 'user'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False, default="global")
    owner_subject_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    protocol: Mapped[str] = mapped_column(String(32), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    api_key_encrypted: Mapped[str] = mapped_column(String(2048), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=4096)
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.2)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    rpm_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quota_remaining: Mapped[float | None] = mapped_column(Float, nullable=True)
