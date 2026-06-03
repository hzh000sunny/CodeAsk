"""OpenViking and Ollama health probes."""

from __future__ import annotations

import os
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from threading import Lock
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


DoctorCheck = dict[str, bool | str | None]
DoctorReport = dict[str, DoctorCheck]
_DOCTOR_ENV_LOCK = Lock()


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


def run_openviking_doctor(config_path: Path) -> DoctorReport:
    """Run OpenViking's own doctor checks against a specific ov.conf."""

    doctor_module = import_module("openviking_cli.doctor")
    consts_module = import_module("openviking_cli.utils.config.consts")
    check_embedding = cast(
        Callable[[], tuple[bool, str, str | None]],
        doctor_module.check_embedding,
    )
    check_vlm = cast(Callable[[], tuple[bool, str, str | None]], doctor_module.check_vlm)
    check_ollama = cast(Callable[[], tuple[bool, str, str | None]], doctor_module.check_ollama)
    openviking_config_env = cast(str, consts_module.OPENVIKING_CONFIG_ENV)

    checks: dict[str, Callable[[], tuple[bool, str, str | None]]] = {
        "embedding": check_embedding,
        "vlm": check_vlm,
        "ollama": check_ollama,
    }
    with _DOCTOR_ENV_LOCK, _temporary_env(openviking_config_env, str(config_path)):
        return {name: _doctor_tuple_to_dict(check()) for name, check in checks.items()}


def _doctor_tuple_to_dict(result: tuple[bool, str, str | None]) -> DoctorCheck:
    ok, detail, fix = result
    return {"ok": ok, "detail": detail, "fix": fix}


@contextmanager
def _temporary_env(name: str, value: str):
    previous = os.environ.get(name)
    os.environ[name] = value
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = previous
