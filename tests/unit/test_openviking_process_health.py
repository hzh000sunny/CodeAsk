from pathlib import Path

import httpx
import pytest

from codeask.rag.openviking.config import OpenVikingRuntimeConfig
from codeask.rag.openviking.health import (
    OpenVikingHealthStatus,
    check_ollama_models,
    probe_openviking_health,
)
from codeask.rag.openviking.process import OpenVikingProcessManager


def test_process_manager_builds_direct_command_without_unsetting_proxy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_cmd: list[str] = []
    captured_env: dict[str, str] = {}
    monkeypatch.setenv("HTTPS_PROXY", "socks5://127.0.0.1:7890")

    class FakeProcess:
        pid = 1234

        def poll(self) -> int | None:
            return None

        def terminate(self) -> None:
            return None

        def wait(self, timeout: float | None = None) -> int:
            return 0

    def fake_popen(cmd, env):
        nonlocal captured_cmd, captured_env
        captured_cmd = list(cmd)
        captured_env = dict(env)
        return FakeProcess()

    manager = OpenVikingProcessManager(
        data_dir=tmp_path,
        port=1933,
        openviking_bin="/opt/codeask/bin/openviking-server",
        popen_factory=fake_popen,
        version_resolver=lambda: "openviking-server 0.3.17",
        health_probe=lambda _base_url, _timeout: OpenVikingHealthStatus(
            healthy=False,
            version=None,
            error="connection refused",
        ),
    )

    handle = manager.ensure_server()

    assert handle.base_url == "http://127.0.0.1:1933"
    assert captured_cmd == [
        "/opt/codeask/bin/openviking-server",
        "--config",
        str(tmp_path / "openviking" / "ov.conf"),
    ]
    assert captured_env["HTTPS_PROXY"] == "socks5://127.0.0.1:7890"
    assert "--from" not in captured_cmd
    assert "uvx" not in captured_cmd


def test_process_manager_classifies_missing_openviking_binary(tmp_path: Path) -> None:
    manager = OpenVikingProcessManager(
        data_dir=tmp_path,
        port=1933,
        openviking_bin="definitely-missing-openviking-server",
        health_probe=lambda _base_url, _timeout: OpenVikingHealthStatus(
            healthy=False,
            version=None,
            error="connection refused",
        ),
    )

    with pytest.raises(RuntimeError, match="未找到 openviking-server"):
        manager.ensure_server()

    status = manager.describe()
    assert status["running"] is False
    assert status["configured_bin"] == "definitely-missing-openviking-server"
    assert status["resolved_bin"] is None
    assert status["last_error_code"] == "openviking_bin_not_found"


def test_process_manager_adopts_existing_healthy_server_before_spawning(tmp_path: Path) -> None:
    spawned: list[list[str]] = []

    def fake_popen(cmd, env):
        spawned.append(list(cmd))
        raise AssertionError("should not spawn when configured endpoint is already healthy")

    def fake_health_probe(base_url: str, timeout: float) -> OpenVikingHealthStatus:
        assert base_url == "http://127.0.0.1:1933"
        assert timeout == 2.0
        return OpenVikingHealthStatus(healthy=True, version="0.3.17", error=None)

    manager = OpenVikingProcessManager(
        data_dir=tmp_path,
        port=1933,
        popen_factory=fake_popen,
        health_probe=fake_health_probe,
    )

    handle = manager.ensure_server()
    status = manager.describe()

    assert spawned == []
    assert handle.base_url == "http://127.0.0.1:1933"
    assert status["running"] is True
    assert status["available"] is True
    assert status["pid"] is None
    assert status["last_error"] is None


def test_process_manager_does_not_mark_wrapper_available_until_health_passes(
    tmp_path: Path,
) -> None:
    class FakeProcess:
        pid = 1234

        def poll(self) -> int | None:
            return None

        def terminate(self) -> None:
            return None

        def wait(self, timeout: float | None = None) -> int:
            return 0

    def fake_health_probe(base_url: str, timeout: float) -> OpenVikingHealthStatus:
        assert base_url == "http://127.0.0.1:1933"
        assert timeout == 2.0
        return OpenVikingHealthStatus(
            healthy=False,
            version=None,
            error="All connection attempts failed",
        )

    manager = OpenVikingProcessManager(
        data_dir=tmp_path,
        port=1933,
        popen_factory=lambda _cmd, _env: FakeProcess(),
        health_probe=fake_health_probe,
    )

    manager.ensure_server()
    status = manager.describe()

    assert status["running"] is True
    assert status["available"] is False
    assert status["last_error"] == "All connection attempts failed"
    assert status["last_error_code"] == "openviking_health_pending"


def test_process_manager_restarts_stale_unhealthy_wrapper(tmp_path: Path) -> None:
    terminated: list[int] = []

    class FakeProcess:
        _next_pid = 2000

        def __init__(self) -> None:
            self.pid = FakeProcess._next_pid
            FakeProcess._next_pid += 1
            self._running = True

        def poll(self) -> int | None:
            return None if self._running else 0

        def terminate(self) -> None:
            terminated.append(self.pid)
            self._running = False

        def wait(self, timeout: float | None = None) -> int:
            return 0

    def fake_health_probe(_base_url: str, _timeout: float) -> OpenVikingHealthStatus:
        return OpenVikingHealthStatus(healthy=False, version=None, error="connection refused")

    manager = OpenVikingProcessManager(
        data_dir=tmp_path,
        port=1933,
        popen_factory=lambda _cmd, _env: FakeProcess(),
        health_probe=fake_health_probe,
        startup_grace_seconds=0,
    )

    first = manager.ensure_server()
    second = manager.ensure_server()

    assert first.pid != second.pid
    assert terminated == [first.pid]
    assert manager.describe()["available"] is False
    assert manager.describe()["last_error_code"] == "openviking_health_failed"


def test_process_manager_regenerates_ov_conf_with_updated_runtime_config(tmp_path: Path) -> None:
    manager = OpenVikingProcessManager(data_dir=tmp_path, port=1933)
    config = OpenVikingRuntimeConfig(
        data_dir=tmp_path,
        port=1933,
        embedding_model="bge-m3",
        embedding_max_concurrent=4,
        max_input_tokens=8192,
    )

    config_path = manager.regenerate_ov_conf(config)

    assert config_path == tmp_path / "openviking" / "ov.conf"
    body = config_path.read_text(encoding="utf-8")
    assert '"max_concurrent": 4' in body
    assert '"max_input_tokens": 8192' in body


def test_process_manager_restart_shutdowns_existing_process_and_starts_new(tmp_path: Path) -> None:
    started: list[list[str]] = []
    terminated: list[int] = []

    class FakeProcess:
        _next_pid = 2000

        def __init__(self) -> None:
            self.pid = FakeProcess._next_pid
            FakeProcess._next_pid += 1
            self._running = True

        def poll(self) -> int | None:
            return None if self._running else 0

        def terminate(self) -> None:
            terminated.append(self.pid)
            self._running = False

        def wait(self, timeout: float | None = None) -> int:
            return 0

    def fake_popen(cmd, env):
        started.append(list(cmd))
        return FakeProcess()

    manager = OpenVikingProcessManager(
        data_dir=tmp_path,
        port=1933,
        popen_factory=fake_popen,
        health_probe=lambda _base_url, _timeout: OpenVikingHealthStatus(
            healthy=False,
            version=None,
            error="connection refused",
        ),
    )

    first = manager.ensure_server()
    second = manager.restart_openviking()

    assert first.pid != second.pid
    assert terminated == [first.pid]
    assert len(started) == 2


@pytest.mark.asyncio
async def test_probe_openviking_health_parses_healthy_response() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        return httpx.Response(200, json={"healthy": True, "version": "0.3.17"})

    transport = httpx.MockTransport(handler)

    status = await probe_openviking_health("http://openviking.local", transport=transport)

    assert status == OpenVikingHealthStatus(
        healthy=True,
        version="0.3.17",
        error=None,
    )


@pytest.mark.asyncio
async def test_check_ollama_models_detects_missing_model() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": [{"name": "nomic-embed-text:latest"}]})

    result = await check_ollama_models(
        "http://ollama.local",
        required_model="bge-m3",
        transport=httpx.MockTransport(handler),
    )

    assert result.healthy is True
    assert result.model_available is False
    assert result.models == ["nomic-embed-text:latest"]
