import os
import socket
import subprocess
from pathlib import Path

import httpx
import pytest

from codeask.rag.openviking.config import OpenVikingRuntimeConfig
from codeask.rag.openviking.health import (
    OpenVikingHealthStatus,
    check_ollama_models,
    probe_openviking_health,
)
from codeask.rag.openviking.process import OpenVikingProcessManager, _default_pid_resolver


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
        version_resolver=lambda: "openviking-server 0.3.22",
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
        return OpenVikingHealthStatus(healthy=True, version="0.3.22", error=None)

    manager = OpenVikingProcessManager(
        data_dir=tmp_path,
        port=1933,
        popen_factory=fake_popen,
        health_probe=fake_health_probe,
        pid_resolver=lambda _host, _port: 4321,
        version_resolver=lambda: "0.3.99",
    )

    handle = manager.ensure_server()
    status = manager.describe()

    assert spawned == []
    assert handle.base_url == "http://127.0.0.1:1933"
    assert handle.pid == 4321
    assert status["running"] is True
    assert status["available"] is True
    assert status["pid"] == 4321
    assert status["version"] == "0.3.22"
    assert status["installed_version"] == "0.3.99"
    assert status["verified_version"] == "0.3.99"
    assert status["supported_version_range"] == ">=0.3.22,<0.4"
    assert status["last_error"] is None


def test_default_pid_resolver_finds_current_process_listener() -> None:
    if not Path("/proc/net/tcp").exists():
        pytest.skip("/proc TCP tables are not available on this platform")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]

        assert _default_pid_resolver("127.0.0.1", port) == os.getpid()


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


def test_process_manager_surfaces_log_tail_and_crash_loop_on_repeated_exit(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "openviking" / "logs" / "openviking-server.log"

    class FakeExitedProcess:
        pid = 4242

        def poll(self) -> int | None:
            return 1

        def terminate(self) -> None:
            return None

        def wait(self, timeout: float | None = None) -> int:
            return 1

    def fake_popen(_cmd: object, _env: object) -> FakeExitedProcess:
        # Simulate the server writing its real failure reason before crashing.
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write("ERROR: failed to download local embedding model bge-small-zh-v1.5-f16\n")
        return FakeExitedProcess()

    manager = OpenVikingProcessManager(
        data_dir=tmp_path,
        port=1933,
        popen_factory=fake_popen,
        health_probe=lambda _base_url, _timeout: OpenVikingHealthStatus(
            healthy=False,
            version=None,
            error="connection refused",
        ),
        startup_grace_seconds=0,
    )

    # Three ensures: launch → detect exit #1 + relaunch → detect exit #2 + relaunch.
    manager.ensure_server()
    manager.ensure_server()
    status = manager.ensure_server() and manager.describe()
    assert isinstance(status, dict)

    assert status["available"] is False
    assert status["consecutive_failures"] >= 2
    assert status["last_error_code"] == "openviking_crash_loop"
    assert "failed to download local embedding model" in str(status["log_tail"])


def test_process_manager_clears_failure_state_after_recovery(tmp_path: Path) -> None:
    log_path = tmp_path / "openviking" / "logs" / "openviking-server.log"
    alive = [False]

    class FakeProcess:
        _next_pid = 5000

        def __init__(self, exited: bool) -> None:
            self.pid = FakeProcess._next_pid
            FakeProcess._next_pid += 1
            self._exited = exited

        def poll(self) -> int | None:
            return 1 if self._exited else None

        def terminate(self) -> None:
            return None

        def wait(self, timeout: float | None = None) -> int:
            return 1

    def fake_popen(_cmd: object, _env: object) -> FakeProcess:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("ERROR: model download failed\n", encoding="utf-8")
        # Once recovered, the launched process stays alive so the probe can pass.
        return FakeProcess(exited=not alive[0])

    def fake_health_probe(_base_url: str, _timeout: float) -> OpenVikingHealthStatus:
        if alive[0]:
            return OpenVikingHealthStatus(healthy=True, version="0.3.22", error=None)
        return OpenVikingHealthStatus(healthy=False, version=None, error="connection refused")

    manager = OpenVikingProcessManager(
        data_dir=tmp_path,
        port=1933,
        popen_factory=fake_popen,
        health_probe=fake_health_probe,
        startup_grace_seconds=0,
    )

    manager.ensure_server()
    failed = manager.ensure_server() and manager.describe()
    assert isinstance(failed, dict)
    assert failed["consecutive_failures"] >= 1
    assert failed["log_tail"] is not None

    # Next launch comes up healthy → sticky failure state must be cleared.
    alive[0] = True
    manager.ensure_server()
    recovered = manager.describe()
    assert recovered["available"] is True
    assert recovered["consecutive_failures"] == 0
    assert recovered["last_error"] is None
    assert recovered["log_tail"] is None


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


def test_process_manager_kills_existing_process_when_graceful_stop_times_out(
    tmp_path: Path,
) -> None:
    started: list[int] = []
    terminated: list[int] = []
    killed: list[int] = []

    class FakeProcess:
        _next_pid = 3000

        def __init__(self) -> None:
            self.pid = FakeProcess._next_pid
            FakeProcess._next_pid += 1
            self._running = True
            self._wait_calls = 0
            started.append(self.pid)

        def poll(self) -> int | None:
            return None if self._running else 0

        def terminate(self) -> None:
            terminated.append(self.pid)

        def kill(self) -> None:
            killed.append(self.pid)
            self._running = False

        def wait(self, timeout: float | None = None) -> int:
            self._wait_calls += 1
            if self._wait_calls == 1:
                assert timeout is not None
                raise subprocess.TimeoutExpired(cmd="openviking-server", timeout=timeout)
            return 0

    manager = OpenVikingProcessManager(
        data_dir=tmp_path,
        port=1933,
        popen_factory=lambda _cmd, _env: FakeProcess(),
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
    assert killed == [first.pid]
    assert started == [first.pid, second.pid]


@pytest.mark.asyncio
async def test_probe_openviking_health_parses_healthy_response() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        return httpx.Response(200, json={"healthy": True, "version": "0.3.22"})

    transport = httpx.MockTransport(handler)

    status = await probe_openviking_health("http://openviking.local", transport=transport)

    assert status == OpenVikingHealthStatus(
        healthy=True,
        version="0.3.22",
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
