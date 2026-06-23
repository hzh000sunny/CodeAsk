"""Live smoke tests for all persisted LLM configs through opencode.

These tests intentionally require an explicit opt-in because they call real
model providers and may consume quota. Run with:

    CODEASK_LIVE_LLM_CONFIG_SMOKE=1 uv run pytest tests/live/test_live_opencode_llm_configs.py -q -s
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import selectinload

from codeask.agent.opencode_compat.config import build_opencode_provider_entry
from codeask.agent.opencode_compat.http import OpenCodeHttpClient
from codeask.agent.opencode_compat.process import OpenCodeProcessManager
from codeask.agent.opencode_compat.profiles import opencode_provider_key
from codeask.crypto import Crypto
from codeask.db.engine import create_engine
from codeask.db.models import LLMConfig, LLMRuntimeAdapter
from codeask.llm.repo import LLMConfigWithSecret, decode_headers
from codeask.settings import Settings


@dataclass(frozen=True)
class SmokeResult:
    config_id: str
    name: str
    provider_id: str
    model_name: str
    enabled: bool
    ok: bool
    text_preview: str = ""
    retries: tuple[str, ...] = ()
    error: str | None = None

    def summary(self) -> str:
        status = "PASS" if self.ok else "FAIL"
        enabled = "enabled" if self.enabled else "disabled"
        retry_text = f" retries={len(self.retries)}" if self.retries else ""
        detail = self.text_preview if self.ok else self.error
        return (
            f"{status} {self.name} ({self.config_id}, {enabled}, "
            f"{self.provider_id}, {self.model_name}){retry_text}: {detail or ''}"
        )


pytestmark = pytest.mark.skipif(
    os.environ.get("CODEASK_LIVE_LLM_CONFIG_SMOKE") != "1",
    reason=("set CODEASK_LIVE_LLM_CONFIG_SMOKE=1 to run real opencode LLM config smoke tests"),
)


@pytest.mark.asyncio
async def test_all_persisted_llm_configs_work_through_opencode(tmp_path: Path) -> None:
    settings = Settings()
    database_path = settings.data_dir / "data.db"
    if not database_path.exists():
        pytest.fail(f"CodeAsk database not found: {database_path}")
    if shutil.which(settings.opencode_bin) is None:
        pytest.fail(f"opencode binary not found: {settings.opencode_bin}")

    configs = await _load_all_llm_configs(settings)
    if not configs:
        pytest.fail("no LLM configs found in CodeAsk database")

    port = _free_port()
    process_manager = OpenCodeProcessManager(
        opencode_bin=settings.opencode_bin,
        data_dir=tmp_path / "opencode-data",
        port_range=str(port),
        username=settings.opencode_server_username,
        password=settings.opencode_server_password,
        log_level="ERROR",
    )
    handle = process_manager.ensure_server()
    client = OpenCodeHttpClient(
        base_url=handle.base_url,
        username=settings.opencode_server_username,
        password=settings.opencode_server_password,
        timeout=settings.opencode_http_timeout_seconds,
    )

    try:
        await _wait_for_opencode(client)
        results: list[SmokeResult] = []
        for index, config in enumerate(configs):
            result = await _smoke_one_config(
                client=client,
                config=config,
                workspace_root=tmp_path / "workspaces",
                index=index,
                timeout_seconds=float(os.environ.get("CODEASK_LIVE_LLM_SMOKE_TIMEOUT", "120")),
            )
            results.append(result)
            print(result.summary())

        failures = [result.summary() for result in results if not result.ok]
        assert not failures, "LLM config smoke failures:\n" + "\n".join(failures)
    finally:
        _shutdown_opencode(process_manager)


async def _load_all_llm_configs(settings: Settings) -> list[LLMConfigWithSecret]:
    engine = create_engine(settings.database_url or "")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    crypto = Crypto(settings.data_key)
    try:
        async with session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(LLMConfig)
                        .options(selectinload(LLMConfig.runtime_adapters))
                        .order_by(
                            LLMConfig.scope,
                            LLMConfig.owner_subject_id,
                            LLMConfig.name,
                        )
                    )
                )
                .scalars()
                .all()
            )
        configs = []
        for row in rows:
            opencode_adapter = _runtime_adapter(row, "opencode")
            configs.append(
                LLMConfigWithSecret(
                    id=row.id,
                    name=row.name,
                    scope=row.scope,
                    owner_subject_id=row.owner_subject_id,
                    mode=row.mode,
                    provider_id=row.provider_id,
                    base_url=row.base_url,
                    api_key=crypto.decrypt(row.api_key_encrypted),
                    headers=decode_headers(row.headers_encrypted, crypto),
                    model_name=row.model_name,
                    is_default=row.is_default,
                    enabled=row.enabled,
                    reasoning_profile=row.reasoning_profile,
                    reasoning_profile_json=row.reasoning_profile_json,
                    agent_runtime_backend="opencode",
                    agent_runtime_status=(
                        opencode_adapter.status
                        if opencode_adapter
                        else row.opencode_provider_status
                    ),
                    agent_runtime_tested_at=(
                        opencode_adapter.tested_at
                        if opencode_adapter
                        else row.opencode_provider_tested_at
                    ),
                    agent_runtime_error=(
                        opencode_adapter.error if opencode_adapter else row.opencode_provider_error
                    ),
                    agent_runtime_test_result_json=(
                        opencode_adapter.test_result_json
                        if opencode_adapter
                        else row.opencode_provider_test_result_json
                    ),
                    opencode_provider_status=(
                        opencode_adapter.status
                        if opencode_adapter
                        else row.opencode_provider_status
                    ),
                    opencode_provider_tested_at=(
                        opencode_adapter.tested_at
                        if opencode_adapter
                        else row.opencode_provider_tested_at
                    ),
                    opencode_provider_error=(
                        opencode_adapter.error if opencode_adapter else row.opencode_provider_error
                    ),
                    opencode_provider_test_result_json=(
                        opencode_adapter.test_result_json
                        if opencode_adapter
                        else row.opencode_provider_test_result_json
                    ),
                )
            )
        return configs
    finally:
        await engine.dispose()


def _runtime_adapter(row: LLMConfig, runtime_backend: str) -> LLMRuntimeAdapter | None:
    for adapter in row.runtime_adapters:
        if adapter.runtime_backend == runtime_backend:
            return adapter
    return None


async def _wait_for_opencode(client: OpenCodeHttpClient) -> None:
    last_error: Exception | None = None
    for _ in range(60):
        try:
            await client.health()
            return
        except Exception as exc:
            last_error = exc
            await asyncio.sleep(0.5)
    raise AssertionError(f"opencode did not become healthy: {last_error}")


async def _smoke_one_config(
    *,
    client: OpenCodeHttpClient,
    config: LLMConfigWithSecret,
    workspace_root: Path,
    index: int,
    timeout_seconds: float,
) -> SmokeResult:
    provider_id = opencode_provider_key(config)
    workspace = workspace_root / f"{index:02d}-{_safe_name(config.id)}-{_safe_name(provider_id)}"
    workspace.mkdir(parents=True, exist_ok=True)
    _write_provider_only_opencode_config(workspace / "opencode.json", config)

    try:
        external_session_id = await client.create_session(directory=str(workspace))
        await client.prompt_async(
            session_id=external_session_id,
            directory=str(workspace),
            provider_id=provider_id,
            model_id=config.model_name,
            text="请只回答 OK 两个字母，不要解释，不要调用工具。",
            system="You are a smoke-test assistant. Reply with exactly: OK",
        )
        text, retries = await _wait_for_turn_result(
            client=client,
            directory=str(workspace),
            session_id=external_session_id,
            timeout_seconds=timeout_seconds,
        )
        if text.strip():
            return SmokeResult(
                config_id=config.id,
                name=config.name,
                provider_id=config.provider_id,
                model_name=config.model_name,
                enabled=config.enabled,
                ok=True,
                text_preview=_preview(text),
                retries=tuple(retries),
            )
        error = "opencode reached idle without visible text"
    except Exception as exc:
        error = _preview(f"{type(exc).__name__}: {exc}", limit=400)
    return SmokeResult(
        config_id=config.id,
        name=config.name,
        provider_id=config.provider_id,
        model_name=config.model_name,
        enabled=config.enabled,
        ok=False,
        error=error,
    )


def _write_provider_only_opencode_config(
    path: Path,
    config: LLMConfigWithSecret,
) -> None:
    provider_id = opencode_provider_key(config)
    payload: dict[str, Any] = {
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            provider_id: build_opencode_provider_entry(
                config,
                name_prefix="CodeAsk Smoke",
                tool_call=False,
            )
        },
        "permission": {
            "bash": "deny",
            "edit": "deny",
            "write": "deny",
            "read": "allow",
            "grep": "allow",
            "glob": "allow",
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


async def _wait_for_turn_result(
    *,
    client: OpenCodeHttpClient,
    directory: str,
    session_id: str,
    timeout_seconds: float,
) -> tuple[str, list[str]]:
    part_types: dict[str, str] = {}
    text_by_part: dict[str, str] = {}
    retries: list[str] = []

    async with asyncio.timeout(timeout_seconds):
        async for event in client.stream_global_events(directory=directory):
            payload = event.get("payload")
            if not isinstance(payload, dict):
                continue
            properties = payload.get("properties")
            if not isinstance(properties, dict) or properties.get("sessionID") != session_id:
                continue

            event_type = payload.get("type")
            if event_type == "session.status":
                status = properties.get("status")
                if isinstance(status, dict):
                    status_type = status.get("type")
                    if status_type == "retry":
                        retries.append(_preview(str(status.get("message") or status), limit=200))
                    elif status_type == "idle":
                        return "\n".join(text_by_part.values()), retries

            if event_type == "session.error":
                raise AssertionError(str(properties.get("error") or "opencode session error"))

            if event_type == "message.part.updated":
                part = properties.get("part")
                if isinstance(part, dict):
                    part_id = part.get("id")
                    part_type = part.get("type")
                    if isinstance(part_id, str) and isinstance(part_type, str):
                        part_types[part_id] = part_type
                        if part_type == "text" and isinstance(part.get("text"), str):
                            text_by_part[part_id] = part["text"]

            if event_type == "message.part.delta":
                part_id = properties.get("partID")
                delta = properties.get("delta")
                if (
                    isinstance(part_id, str)
                    and part_types.get(part_id) == "text"
                    and isinstance(delta, str)
                ):
                    text_by_part[part_id] = text_by_part.get(part_id, "") + delta

    return "\n".join(text_by_part.values()), retries


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _shutdown_opencode(process_manager: OpenCodeProcessManager) -> None:
    try:
        process_manager.shutdown()
        return
    except subprocess.TimeoutExpired:
        process = getattr(process_manager, "_process", None)
        kill = getattr(process, "kill", None)
        wait = getattr(process, "wait", None)
        if callable(kill):
            kill()
        if callable(wait):
            wait(timeout=5)


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value)


def _preview(value: str, *, limit: int = 120) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 3]}..."
