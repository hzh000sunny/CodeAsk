"""Application settings (env-driven)."""

from pathlib import Path
from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CODEASK_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_key: str = Field(
        ...,
        description="Fernet master key (base64-urlsafe, 32 bytes). Encrypts sensitive DB fields.",
    )
    data_dir: Path = Field(
        default_factory=lambda: Path.home() / ".codeask",
        description="Root directory for SQLite + uploads + worktrees + logs.",
    )
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    database_url: str | None = None

    @model_validator(mode="after")
    def _derive_database_url(self) -> Self:
        if self.database_url is None:
            self.database_url = f"sqlite+aiosqlite:///{self.data_dir / 'data.db'}"
        return self
