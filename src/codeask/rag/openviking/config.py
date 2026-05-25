"""OpenViking runtime configuration and ov.conf generation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class OpenVikingRuntimeConfig:
    data_dir: Path
    host: str = "127.0.0.1"
    port: int = 1933
    ollama_base_url: str = "http://127.0.0.1:11434"
    embedding_model: str = "bge-m3"
    embedding_dimension: int = 1024
    embedding_max_concurrent: int = 1
    max_input_tokens: int = 4096
    max_retries: int = 3
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_reset_timeout: int = 60

    @property
    def root_dir(self) -> Path:
        return self.data_dir / "openviking"

    @property
    def config_path(self) -> Path:
        return self.root_dir / "ov.conf"

    @property
    def workspace_dir(self) -> Path:
        return self.root_dir / "workspace"

    @property
    def log_dir(self) -> Path:
        return self.root_dir / "logs"


def build_ov_conf(config: OpenVikingRuntimeConfig) -> dict[str, Any]:
    """Build the OpenViking 0.3.17 server config used by CodeAsk."""

    return {
        "storage": {
            "workspace": str(config.workspace_dir),
            "vectordb": {"name": "context", "backend": "local"},
            "agfs": {"backend": "local"},
        },
        "server": {
            "host": config.host,
            "port": config.port,
            "auth_mode": "trusted",
            "cors_origins": ["http://127.0.0.1:5173"],
            "temp_upload": {"default_mode": "local"},
        },
        "embedding": {
            "dense": {
                "provider": "ollama",
                "api_base": f"{config.ollama_base_url.rstrip('/')}/v1",
                "model": config.embedding_model,
                "dimension": config.embedding_dimension,
                "input": "text",
            },
            "text_source": "content_only",
            "max_input_tokens": config.max_input_tokens,
            "max_concurrent": config.embedding_max_concurrent,
            "max_retries": config.max_retries,
            "circuit_breaker": {
                "failure_threshold": config.circuit_breaker_failure_threshold,
                "reset_timeout": config.circuit_breaker_reset_timeout,
            },
        },
        "auto_generate_l0": False,
        "auto_generate_l1": False,
    }


def write_ov_conf(config: OpenVikingRuntimeConfig) -> Path:
    config.root_dir.mkdir(parents=True, exist_ok=True)
    config.workspace_dir.mkdir(parents=True, exist_ok=True)
    config.log_dir.mkdir(parents=True, exist_ok=True)
    config.config_path.write_text(
        json.dumps(build_ov_conf(config), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return config.config_path
