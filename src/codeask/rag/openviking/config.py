"""OpenViking runtime configuration and ov.conf generation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class OpenVikingEmbeddingRuntimeConfig:
    provider: str = "local"
    model: str = "bge-small-zh-v1.5-f16"
    base_url: str | None = None
    api_key: str | None = None
    dimension: int | None = 512
    input: str = "text"
    extra: dict[str, Any] | None = None


@dataclass(frozen=True)
class OpenVikingVLMRuntimeConfig:
    enabled: bool = False
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    temperature: float = 0.0
    max_retries: int = 3
    timeout: float = 60.0
    extra: dict[str, Any] | None = None


@dataclass(frozen=True)
class OpenVikingRuntimeConfig:
    data_dir: Path
    host: str = "127.0.0.1"
    port: int = 1933
    embedding: OpenVikingEmbeddingRuntimeConfig | None = None
    vlm: OpenVikingVLMRuntimeConfig | None = None
    ollama_base_url: str = "http://127.0.0.1:11434"
    embedding_model: str = "bge-small-zh-v1.5-f16"
    embedding_dimension: int = 512
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
    """Build the OpenViking server config used by CodeAsk."""
    legacy_ollama = config.embedding_model != "bge-small-zh-v1.5-f16"
    embedding = config.embedding or OpenVikingEmbeddingRuntimeConfig(
        provider="ollama" if legacy_ollama else "local",
        model=config.embedding_model,
        base_url=config.ollama_base_url if legacy_ollama else None,
        dimension=config.embedding_dimension,
    )
    dense = _embedding_dense_config(embedding)
    ov_conf: dict[str, Any] = {
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
            "dense": dense,
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
    vlm = config.vlm or OpenVikingVLMRuntimeConfig()
    if vlm.enabled and vlm.provider and vlm.model:
        ov_conf["vlm"] = _vlm_config(vlm)
    return ov_conf


def _embedding_dense_config(embedding: OpenVikingEmbeddingRuntimeConfig) -> dict[str, Any]:
    dense: dict[str, Any] = {
        "provider": embedding.provider,
        "model": embedding.model,
    }
    if embedding.base_url:
        dense["api_base"] = _embedding_api_base(embedding)
    if embedding.api_key:
        dense["api_key"] = embedding.api_key
    if embedding.dimension is not None:
        dense["dimension"] = embedding.dimension
    if embedding.input:
        dense["input"] = embedding.input
    if embedding.extra:
        dense.update({key: value for key, value in embedding.extra.items() if value is not None})
    return dense


def _embedding_api_base(embedding: OpenVikingEmbeddingRuntimeConfig) -> str:
    if embedding.provider == "ollama" and embedding.base_url:
        return f"{embedding.base_url.rstrip('/')}/v1"
    return embedding.base_url or ""


def _vlm_config(vlm: OpenVikingVLMRuntimeConfig) -> dict[str, Any]:
    data: dict[str, Any] = {
        "provider": vlm.provider,
        "model": vlm.model,
        "temperature": vlm.temperature,
        "max_retries": vlm.max_retries,
        "timeout": vlm.timeout,
    }
    if vlm.base_url:
        data["api_base"] = vlm.base_url
    if vlm.api_key:
        data["api_key"] = vlm.api_key
    if vlm.extra:
        data.update({key: value for key, value in vlm.extra.items() if value is not None})
    return data


def write_ov_conf(config: OpenVikingRuntimeConfig) -> Path:
    config.root_dir.mkdir(parents=True, exist_ok=True)
    config.workspace_dir.mkdir(parents=True, exist_ok=True)
    config.log_dir.mkdir(parents=True, exist_ok=True)
    config.config_path.write_text(
        json.dumps(build_ov_conf(config), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return config.config_path
