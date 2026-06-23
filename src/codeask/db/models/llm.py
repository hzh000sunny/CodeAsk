"""LLM provider configuration models."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
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
        UniqueConstraint(
            "scope",
            "owner_subject_id",
            "name",
            name="uq_llm_configs_scope_owner_name",
        ),
        CheckConstraint("scope IN ('global', 'user')", name="ck_llm_configs_scope"),
        CheckConstraint("mode IN ('catalog', 'custom')", name="ck_llm_configs_mode"),
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
    mode: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="catalog",
        server_default="catalog",
    )
    provider_id: Mapped[str] = mapped_column(String(128), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    api_key_encrypted: Mapped[str] = mapped_column(String(2048), nullable=False)
    headers_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reasoning_profile: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="none",
        server_default="none",
    )
    reasoning_profile_json: Mapped[str | None] = mapped_column(String(4096), nullable=True)
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
