from __future__ import annotations

import subprocess
from contextlib import suppress
from pathlib import Path

import pytest

from codeask.agent.opencode_compat.process import OpenCodeProcessError, OpenCodeProcessManager


class FakeProcess:
    _next_pid = 1000

    def __init__(self, returncode: int | None = None) -> None:
        FakeProcess._next_pid += 1
        self.pid = FakeProcess._next_pid
        self.returncode = returncode
        self.terminated = False

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0

    def wait(self, timeout: float | None = None) -> int:
        self.returncode = 0
        return 0


def test_process_manager_starts_one_shared_server_and_reuses_it(tmp_path: Path) -> None:
    calls: list[tuple[list[str], dict[str, str]]] = []

    def fake_popen(cmd, env):  # type: ignore[no-untyped-def]
        calls.append((list(cmd), dict(env)))
        return FakeProcess()

    manager = OpenCodeProcessManager(
        opencode_bin="opencode",
        data_dir=tmp_path,
        port_range="4100-4102",
        username="codeask",
        password="secret",
        popen_factory=fake_popen,
    )

    first = manager.ensure_server()
    second = manager.ensure_server()

    assert first == second
    assert len(calls) == 1
    assert calls[0][0] == [
        "opencode",
        "serve",
        "--hostname",
        "127.0.0.1",
        "--port",
        "4100",
        "--pure",
        "--log-level",
        "ERROR",
    ]
    assert calls[0][1]["OPENCODE_SERVER_USERNAME"] == "codeask"
    assert calls[0][1]["OPENCODE_SERVER_PASSWORD"] == "secret"
    assert calls[0][1]["HOME"] == str(tmp_path / "agent_sessions" / "opencode" / "server_home")


def test_process_manager_restarts_exited_server_on_next_port(tmp_path: Path) -> None:
    processes: list[FakeProcess] = []

    def fake_popen(cmd, env):  # type: ignore[no-untyped-def]
        proc = FakeProcess()
        processes.append(proc)
        return proc

    manager = OpenCodeProcessManager(
        opencode_bin="opencode",
        data_dir=tmp_path,
        port_range="4100-4102",
        username="codeask",
        password="secret",
        popen_factory=fake_popen,
    )

    first = manager.ensure_server()
    processes[0].returncode = 1
    second = manager.ensure_server()

    assert first.port == 4100
    assert second.port == 4101
    assert first.pid != second.pid


def test_process_manager_describe_reports_running_server(tmp_path: Path) -> None:
    def fake_popen(cmd, env):  # type: ignore[no-untyped-def]
        return FakeProcess()

    manager = OpenCodeProcessManager(
        opencode_bin="opencode",
        data_dir=tmp_path,
        port_range="4100",
        username="codeask",
        password="secret",
        popen_factory=fake_popen,
    )

    handle = manager.ensure_server()
    status = manager.describe()

    assert status["running"] is True
    assert status["base_url"] == handle.base_url
    assert status["port"] == handle.port
    assert status["pid"] == handle.pid
    assert status["returncode"] is None
    assert status["configured_bin"] == "opencode"
    assert status["last_error"] is None


def test_process_manager_describe_reports_resolved_version(tmp_path: Path) -> None:
    def fake_popen(cmd, env):  # type: ignore[no-untyped-def]
        return FakeProcess()

    manager = OpenCodeProcessManager(
        opencode_bin="opencode",
        data_dir=tmp_path,
        port_range="4100",
        username="codeask",
        password="secret",
        popen_factory=fake_popen,
        version_resolver=lambda _bin: "1.14.48",
    )

    manager.ensure_server()

    assert manager.describe()["version"] == "1.14.48"


def test_process_manager_describe_reports_last_health_at(tmp_path: Path) -> None:
    def fake_popen(cmd, env):  # type: ignore[no-untyped-def]
        return FakeProcess()

    manager = OpenCodeProcessManager(
        opencode_bin="opencode",
        data_dir=tmp_path,
        port_range="4100",
        username="codeask",
        password="secret",
        popen_factory=fake_popen,
    )

    manager.ensure_server()
    manager.record_health_ok()

    assert isinstance(manager.describe()["last_health_at"], str)


def test_process_manager_describe_records_start_failure(tmp_path: Path) -> None:
    def fake_popen(cmd, env):  # type: ignore[no-untyped-def]
        raise FileNotFoundError("opencode missing")

    manager = OpenCodeProcessManager(
        opencode_bin="opencode-missing",
        data_dir=tmp_path,
        port_range="4100",
        username="codeask",
        password="secret",
        popen_factory=fake_popen,
    )

    with suppress(OpenCodeProcessError):
        manager.ensure_server()

    status = manager.describe()

    assert status["running"] is False
    assert status["base_url"] is None
    assert status["port"] is None
    assert status["pid"] is None
    assert status["configured_bin"] == "opencode-missing"
    assert status["resolved_bin"] is None
    assert status["last_error"] == "opencode missing"
    assert status["last_error_code"] == "opencode_bin_missing"


def test_process_manager_writes_default_process_output_to_log_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    popen_kwargs = {}

    def fake_popen(cmd, **kwargs):  # type: ignore[no-untyped-def]
        popen_kwargs.update(kwargs)
        return FakeProcess()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    manager = OpenCodeProcessManager(
        opencode_bin="opencode",
        data_dir=tmp_path,
        port_range="4100",
        username="codeask",
        password="secret",
    )

    manager.ensure_server()

    stdout = popen_kwargs["stdout"]
    assert stdout.name.endswith("agent_sessions/opencode/logs/opencode-server.log")
    assert popen_kwargs["stderr"] == subprocess.STDOUT
    assert stdout.closed is False
    manager.shutdown()
    assert stdout.closed is True


def test_process_manager_raises_classified_start_error(tmp_path: Path) -> None:
    def fake_popen(cmd, env):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")

    manager = OpenCodeProcessManager(
        opencode_bin="opencode",
        data_dir=tmp_path,
        port_range="4100",
        username="codeask",
        password="secret",
        popen_factory=fake_popen,
    )

    with pytest.raises(OpenCodeProcessError) as exc_info:
        manager.ensure_server()

    assert exc_info.value.code == "opencode_start_failed"
    assert "boom" in str(exc_info.value)
    assert manager.describe()["last_error_code"] == "opencode_start_failed"
