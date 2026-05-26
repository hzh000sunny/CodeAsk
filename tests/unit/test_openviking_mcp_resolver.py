from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from codeask.app import _resolve_openviking_mcp_config
from codeask.rag.openviking.health import OpenVikingHealthStatus
from codeask.settings import Settings

TEST_DATA_KEY = Fernet.generate_key().decode()


class FakeOpenVikingProcessManager:
    def __init__(self, *, running: bool = True) -> None:
        self.running = running

    def describe(self) -> dict[str, object]:
        return {
            "running": self.running,
            "base_url": "http://127.0.0.1:1933",
        }


def _settings(tmp_path: Path, *, enabled: bool = True) -> Settings:
    return Settings(
        data_key=TEST_DATA_KEY,
        data_dir=tmp_path,
        openviking_enabled=enabled,
        openviking_host="127.0.0.1",
        openviking_port=1933,
    )


@pytest.mark.asyncio
async def test_resolve_openviking_mcp_config_returns_trusted_headers_when_healthy(
    tmp_path: Path,
) -> None:
    async def healthy_probe(base_url: str, **_kwargs: object) -> OpenVikingHealthStatus:
        assert base_url == "http://127.0.0.1:1933"
        return OpenVikingHealthStatus(healthy=True, version="0.3.17", error=None)

    config = await _resolve_openviking_mcp_config(
        _settings(tmp_path),
        FakeOpenVikingProcessManager(),
        session_id="sess_openviking",
        health_probe=healthy_probe,
    )

    assert config is not None
    assert config.url == "http://127.0.0.1:1933/mcp"
    assert config.token is None
    assert config.headers == {
        "X-OpenViking-Account": "codeask",
        "X-OpenViking-User": "codeask",
        "X-OpenViking-Agent": "sess_openviking",
    }


@pytest.mark.asyncio
async def test_resolve_openviking_mcp_config_returns_none_when_disabled_or_degraded(
    tmp_path: Path,
) -> None:
    probe_calls = 0

    async def degraded_probe(*_args: object, **_kwargs: object) -> OpenVikingHealthStatus:
        nonlocal probe_calls
        probe_calls += 1
        return OpenVikingHealthStatus(healthy=False, version=None, error="offline")

    disabled = await _resolve_openviking_mcp_config(
        _settings(tmp_path, enabled=False),
        FakeOpenVikingProcessManager(),
        session_id="sess_openviking",
        health_probe=degraded_probe,
    )
    not_running = await _resolve_openviking_mcp_config(
        _settings(tmp_path),
        FakeOpenVikingProcessManager(running=False),
        session_id="sess_openviking",
        health_probe=degraded_probe,
    )
    degraded = await _resolve_openviking_mcp_config(
        _settings(tmp_path),
        FakeOpenVikingProcessManager(),
        session_id="sess_openviking",
        health_probe=degraded_probe,
    )

    assert disabled is None
    assert not_running is None
    assert degraded is None
    assert probe_calls == 1
