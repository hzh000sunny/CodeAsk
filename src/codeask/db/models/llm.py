"""LLM provider configuration models."""

from sqlalchemy import Boolean, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from codeask.db.base import Base, TimestampMixin


class LLMConfig(Base, TimestampMixin):
    """Provider-neutral LLM configuration with encrypted API key."""

    __tablename__ = "llm_configs"
    __table_args__ = (UniqueConstraint("name", name="uq_llm_configs_name"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    protocol: Mapped[str] = mapped_column(String(32), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    api_key_encrypted: Mapped[str] = mapped_column(String(2048), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=4096)
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.2)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
