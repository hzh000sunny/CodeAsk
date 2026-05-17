"""Application settings (env-driven)."""

from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from codeask.data_key import resolve_data_key


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CODEASK_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_key: str = Field(
        default="",
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
    frontend_dist: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parents[2] / "frontend" / "dist",
        description="Path to compiled SPA served from / when index.html exists.",
    )
    admin_username: str = Field(
        default="admin",
        description="Bootstrap admin username until the production auth backend is added.",
    )
    admin_password: str = Field(
        default="admin",
        description="Bootstrap admin password until the production auth backend is added.",
    )
    admin_session_ttl_hours: int = Field(
        default=12,
        ge=1,
        description="Lifetime of the signed admin session cookie.",
    )
    auth_cookie_name: str = "codeask_admin_session"
    llm_timeout_seconds: int = Field(
        default=600,
        ge=30,
        description="Timeout applied to each outbound LLM request in seconds.",
    )
    model_context_window_tokens: int = Field(
        default=200_000,
        ge=1_000,
        description=(
            "Default model context window shown in session runtime state. "
            "Used as the fallback when provider metadata does not expose a window."
        ),
    )
    opencode_bin: str = Field(
        default="opencode",
        description="OpenCode executable used by the v1.0.4 compatibility backend.",
    )
    opencode_port_range: str = Field(
        default="4100-4199",
        description="Local port range used by the shared opencode serve process.",
    )
    opencode_server_username: str = Field(
        default="codeask",
        description="Basic auth username for the shared opencode serve process.",
    )
    opencode_server_password: str = Field(
        default="codeask",
        description="Basic auth password for the shared opencode serve process.",
    )
    opencode_mcp_base_url: str | None = Field(
        default=None,
        description="Base URL reachable by opencode for CodeAsk MCP, without session id.",
    )
    opencode_http_timeout_seconds: int = Field(
        default=60,
        ge=10,
        description="Timeout for CodeAsk requests to the local opencode HTTP server.",
    )
    opencode_keepalive_interval_seconds: int = Field(
        default=30,
        ge=5,
        description="Interval for checking and restarting the shared opencode serve process.",
    )
    opencode_session_idle_ttl_seconds: int = Field(
        default=6 * 60 * 60,
        ge=60,
        description="Age after which inactive opencode session resources may be cleaned.",
    )
    opencode_session_cleanup_interval_seconds: int = Field(
        default=60 * 60,
        ge=60,
        description="Interval for cleaning idle opencode session resources.",
    )
    agent_backend: Literal["opencode", "native"] = Field(
        default="opencode",
        description=(
            "Agent backend used by /sessions/{id}/messages. Production default is opencode; "
            "native is retained for legacy regression tests and compatibility diagnostics."
        ),
    )

    @model_validator(mode="after")
    def _derive_runtime_values(self) -> Self:
        self.data_key = resolve_data_key(self.data_key, self.data_dir)
        if self.database_url is None:
            self.database_url = f"sqlite+aiosqlite:///{self.data_dir / 'data.db'}"
        return self
