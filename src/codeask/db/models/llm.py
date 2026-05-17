"""LLM provider configuration models."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
    reasoning_profile: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="none",
        server_default="none",
    )
    reasoning_profile_json: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    opencode_provider_profile: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="default",
        server_default="default",
    )
    opencode_provider_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="unknown",
        server_default="unknown",
    )
    opencode_provider_tested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    opencode_provider_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    opencode_provider_test_result_json: Mapped[object | None] = mapped_column(JSON, nullable=True)

    runtime_adapters: Mapped[list["LLMRuntimeAdapter"]] = relationship(
        "LLMRuntimeAdapter",
        back_populates="llm_config",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class LLMRuntimeAdapter(Base, TimestampMixin):
    """Agent-runtime-specific adapter state for an LLM configuration."""

    __tablename__ = "llm_runtime_adapters"
    __table_args__ = (
        UniqueConstraint(
            "llm_config_id",
            "runtime_backend",
            name="uq_llm_runtime_adapters_config_backend",
        ),
        CheckConstraint(
            "status IN ('unknown', 'ok', 'failed')",
            name="ck_llm_runtime_adapters_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    llm_config_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("llm_configs.id", ondelete="CASCADE"),
        nullable=False,
    )
    runtime_backend: Mapped[str] = mapped_column(String(64), nullable=False)
    adapter_profile: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="default",
        server_default="default",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="unknown",
        server_default="unknown",
    )
    tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    test_result_json: Mapped[object | None] = mapped_column(JSON, nullable=True)
    config_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)

    llm_config: Mapped[LLMConfig] = relationship(
        "LLMConfig",
        back_populates="runtime_adapters",
    )
