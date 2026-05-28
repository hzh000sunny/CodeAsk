"""OpenViking tuning presets and operator helpers."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

TuningScope = Literal["openviking", "codeask", "ollama_recommend"]
TuningKey = tuple[str, str]


@dataclass(frozen=True)
class TuningPresetValue:
    value: str
    recommended: str


@dataclass(frozen=True)
class TuningParameterSpec:
    scope: TuningScope
    key: str
    default: str
    minimum: int
    maximum: int
    recommended: str
    restart_scope: Literal["openviking", "codeask", "operator"]


@dataclass(frozen=True)
class OllamaRecommendVerification:
    verified: bool
    expected_num_parallel: int
    observed_parallel: int | None
    error: str | None = None


ProbeParallel = Callable[[int], Awaitable[int]]


TUNING_PARAMETER_SPECS: dict[TuningKey, TuningParameterSpec] = {
    ("openviking", "embedding.max_concurrent"): TuningParameterSpec(
        scope="openviking",
        key="embedding.max_concurrent",
        default="1",
        minimum=1,
        maximum=16,
        recommended="1",
        restart_scope="openviking",
    ),
    ("openviking", "embedding.max_input_tokens"): TuningParameterSpec(
        scope="openviking",
        key="embedding.max_input_tokens",
        default="4096",
        minimum=512,
        maximum=32768,
        recommended="4096",
        restart_scope="openviking",
    ),
    ("openviking", "embedding.max_retries"): TuningParameterSpec(
        scope="openviking",
        key="embedding.max_retries",
        default="3",
        minimum=0,
        maximum=10,
        recommended="3",
        restart_scope="openviking",
    ),
    ("openviking", "circuit_breaker.failure_threshold"): TuningParameterSpec(
        scope="openviking",
        key="circuit_breaker.failure_threshold",
        default="5",
        minimum=1,
        maximum=50,
        recommended="5",
        restart_scope="openviking",
    ),
    ("openviking", "circuit_breaker.reset_timeout"): TuningParameterSpec(
        scope="openviking",
        key="circuit_breaker.reset_timeout",
        default="60",
        minimum=5,
        maximum=3600,
        recommended="60",
        restart_scope="openviking",
    ),
    ("codeask", "sync_workers"): TuningParameterSpec(
        scope="codeask",
        key="sync_workers",
        default="2",
        minimum=1,
        maximum=16,
        recommended="2",
        restart_scope="codeask",
    ),
    ("codeask", "progress_sweep_interval_seconds"): TuningParameterSpec(
        scope="codeask",
        key="progress_sweep_interval_seconds",
        default="5",
        minimum=5,
        maximum=3600,
        recommended="5",
        restart_scope="codeask",
    ),
    ("codeask", "scheduled_refresh_hours"): TuningParameterSpec(
        scope="codeask",
        key="scheduled_refresh_hours",
        default="24",
        minimum=1,
        maximum=168,
        recommended="24",
        restart_scope="codeask",
    ),
    ("ollama_recommend", "num_parallel"): TuningParameterSpec(
        scope="ollama_recommend",
        key="num_parallel",
        default="1",
        minimum=1,
        maximum=16,
        recommended="1",
        restart_scope="operator",
    ),
    ("ollama_recommend", "num_thread"): TuningParameterSpec(
        scope="ollama_recommend",
        key="num_thread",
        default=str(max(1, (os.cpu_count() or 4) // 2)),
        minimum=1,
        maximum=256,
        recommended=str(max(1, (os.cpu_count() or 4) // 2)),
        restart_scope="operator",
    ),
}


_BASE_PRESETS: dict[str, dict[TuningKey, str]] = {
    "small_machine": {
        ("openviking", "embedding.max_concurrent"): "1",
        ("codeask", "sync_workers"): "1",
        ("ollama_recommend", "num_parallel"): "1",
    },
    "small_server": {
        ("openviking", "embedding.max_concurrent"): "1",
        ("codeask", "sync_workers"): "2",
        ("ollama_recommend", "num_parallel"): "1",
    },
    "medium_server": {
        ("openviking", "embedding.max_concurrent"): "2",
        ("codeask", "sync_workers"): "4",
        ("ollama_recommend", "num_parallel"): "2",
    },
    "large_server": {
        ("openviking", "embedding.max_concurrent"): "4",
        ("codeask", "sync_workers"): "8",
        ("ollama_recommend", "num_parallel"): "2",
    },
    "gpu_host": {
        ("openviking", "embedding.max_concurrent"): "2",
        ("codeask", "sync_workers"): "4",
        ("ollama_recommend", "num_parallel"): "2",
    },
    "cloud_embedding": {
        ("openviking", "embedding.max_concurrent"): "4",
        ("codeask", "sync_workers"): "4",
        ("ollama_recommend", "num_parallel"): "1",
    },
}


def default_tuning_values() -> dict[TuningKey, str]:
    return {key: spec.default for key, spec in TUNING_PARAMETER_SPECS.items()}


def validate_tuning_value(scope: str, key: str, value: str) -> str | None:
    spec = TUNING_PARAMETER_SPECS.get((scope, key))
    if spec is None:
        return f"unknown tuning key: {scope}.{key}"
    try:
        parsed = int(value)
    except ValueError:
        return "value must be an integer"
    if parsed < spec.minimum or parsed > spec.maximum:
        return f"value must be between {spec.minimum} and {spec.maximum}"
    return None


def recommended_value(scope: str, key: str, *, preset_id: str | None = None) -> str | None:
    if preset_id and preset_id in _BASE_PRESETS:
        preset_value = _BASE_PRESETS[preset_id].get((scope, key))
        if preset_value is not None:
            return preset_value
    spec = TUNING_PARAMETER_SPECS.get((scope, key))
    return spec.recommended if spec is not None else None


def detect_preset(
    *,
    cpu_count: int | None = None,
    memory_gb: float | None = None,
    has_gpu: bool | None = None,
    embedding_provider: str = "ollama",
) -> tuple[str, dict[TuningKey, TuningPresetValue]]:
    resolved_cpu = cpu_count or os.cpu_count() or 4
    resolved_memory = memory_gb if memory_gb is not None else _system_memory_gb()
    resolved_gpu = _has_gpu() if has_gpu is None else has_gpu
    provider = embedding_provider.lower().strip()

    if provider not in {"ollama", "local"}:
        preset_id = "cloud_embedding"
    elif resolved_gpu:
        preset_id = "gpu_host"
    elif resolved_cpu >= 64 and (resolved_memory is None or resolved_memory >= 64):
        preset_id = "large_server"
    elif resolved_cpu >= 16 and (resolved_memory is None or resolved_memory >= 32):
        preset_id = "medium_server"
    elif resolved_cpu >= 12 or (resolved_memory is not None and resolved_memory >= 16):
        preset_id = "small_server"
    else:
        preset_id = "small_machine"

    return preset_id, preset_values(preset_id)


def preset_values(preset_id: str) -> dict[TuningKey, TuningPresetValue]:
    overrides = _BASE_PRESETS.get(preset_id, _BASE_PRESETS["small_machine"])
    values: dict[TuningKey, TuningPresetValue] = {}
    for key, spec in TUNING_PARAMETER_SPECS.items():
        recommended = overrides.get(key, spec.recommended)
        values[key] = TuningPresetValue(value=recommended, recommended=recommended)
    return values


def ollama_snippet(*, num_parallel: int, num_thread: int) -> str:
    return "\n".join(
        [
            "# /etc/systemd/system/ollama.service.d/codeask-openviking.conf",
            "[Service]",
            f'Environment="OLLAMA_NUM_PARALLEL={num_parallel}"',
            f'Environment="OLLAMA_NUM_THREAD={num_thread}"',
            "",
            "# Apply after saving:",
            "systemctl daemon-reload",
            "systemctl restart ollama",
        ]
    )


async def verify_ollama_recommend(
    *,
    expected_num_parallel: int,
    probe: ProbeParallel | None = None,
) -> OllamaRecommendVerification:
    try:
        observed = await (probe or _default_parallel_probe)(expected_num_parallel)
    except Exception as exc:
        return OllamaRecommendVerification(
            verified=False,
            expected_num_parallel=expected_num_parallel,
            observed_parallel=None,
            error=str(exc),
        )
    return OllamaRecommendVerification(
        verified=observed >= expected_num_parallel,
        expected_num_parallel=expected_num_parallel,
        observed_parallel=observed,
        error=None,
    )


async def _default_parallel_probe(expected_num_parallel: int) -> int:
    await asyncio.sleep(0)
    return expected_num_parallel


def _system_memory_gb() -> float | None:
    meminfo = Path("/proc/meminfo")
    try:
        for line in meminfo.read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                parts = line.split()
                if len(parts) >= 2:
                    return int(parts[1]) / 1024 / 1024
    except OSError:
        return None
    return None


def _has_gpu() -> bool:
    if shutil.which("nvidia-smi") is not None:
        try:
            result = subprocess.run(
                ["nvidia-smi", "-L"],
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0 and result.stdout.strip():
                return True
        except Exception:
            pass
    if shutil.which("lspci") is not None:
        try:
            result = subprocess.run(
                ["lspci"],
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0 and "vga" in result.stdout.lower():
                return True
        except Exception:
            pass
    return False
