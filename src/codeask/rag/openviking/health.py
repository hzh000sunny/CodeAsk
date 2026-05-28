"""OpenViking and Ollama health probes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import httpx


@dataclass(frozen=True)
class OpenVikingHealthStatus:
    healthy: bool
    version: str | None
    error: str | None


@dataclass(frozen=True)
class OllamaModelStatus:
    healthy: bool
    model_available: bool
    models: list[str]
    error: str | None = None


async def probe_openviking_health(
    base_url: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    timeout: float = 5.0,
) -> OpenVikingHealthStatus:
    try:
        async with httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            transport=transport,
            trust_env=False,
        ) as client:
            response = await client.get("/health")
            response.raise_for_status()
            response_data = response.json()
    except Exception as exc:
        return OpenVikingHealthStatus(healthy=False, version=None, error=str(exc))
    data = cast(dict[str, Any], response_data) if isinstance(response_data, dict) else {}
    version = data.get("version")
    return OpenVikingHealthStatus(
        healthy=bool(data.get("healthy", data.get("status") == "ok")),
        version=version if isinstance(version, str) else None,
        error=None,
    )


async def check_ollama_models(
    base_url: str,
    *,
    required_model: str,
    transport: httpx.AsyncBaseTransport | None = None,
    timeout: float = 5.0,
) -> OllamaModelStatus:
    try:
        async with httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            transport=transport,
            trust_env=False,
        ) as client:
            response = await client.get("/api/tags")
            response.raise_for_status()
            response_data = response.json()
    except Exception as exc:
        return OllamaModelStatus(
            healthy=False,
            model_available=False,
            models=[],
            error=str(exc),
        )
    data = cast(dict[str, Any], response_data) if isinstance(response_data, dict) else {}
    raw_models = data.get("models")
    models: list[str] = []
    if isinstance(raw_models, list):
        for raw_item in cast(list[object], raw_models):
            if not isinstance(raw_item, dict):
                continue
            item = cast(dict[str, Any], raw_item)
            model_name = item.get("name") or item.get("model")
            if model_name:
                models.append(str(model_name))
    expected = required_model if ":" in required_model else f"{required_model}:latest"
    return OllamaModelStatus(
        healthy=True,
        model_available=required_model in models or expected in models,
        models=models,
        error=None,
    )
