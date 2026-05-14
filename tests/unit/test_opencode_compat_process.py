from __future__ import annotations

from pathlib import Path

from codeask.agent.opencode_compat.process import OpenCodeProcessManager


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
