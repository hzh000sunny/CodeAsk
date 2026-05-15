"""Shared opencode server process management."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Protocol


class ProcessLike(Protocol):
    pid: int

    def poll(self) -> int | None: ...
    def terminate(self) -> None: ...
    def wait(self, timeout: float | None = None) -> int: ...


PopenFactory = Callable[[Sequence[str], dict[str, str]], ProcessLike]


@dataclass(frozen=True)
class OpenCodeServerHandle:
    base_url: str
    port: int
    pid: int


class OpenCodeProcessManager:
    """Manage one shared `opencode serve` process."""

    def __init__(
        self,
        *,
        opencode_bin: str,
        data_dir: Path,
        port_range: str,
        username: str,
        password: str,
        hostname: str = "127.0.0.1",
        log_level: str = "ERROR",
        popen_factory: PopenFactory | None = None,
    ) -> None:
        self._opencode_bin = opencode_bin
        self._data_dir = data_dir
        self._ports = _parse_port_range(port_range)
        self._username = username
        self._password = password
        self._hostname = hostname
        self._log_level = log_level
        self._popen_factory = popen_factory or _default_popen
        self._process: ProcessLike | None = None
        self._handle: OpenCodeServerHandle | None = None
        self._next_port_index = 0
        self._lock = Lock()
        self._last_error: str | None = None

    def ensure_server(self) -> OpenCodeServerHandle:
        with self._lock:
            if (
                self._process is not None
                and self._process.poll() is None
                and self._handle is not None
            ):
                self._last_error = None
                return self._handle

            port = self._next_port()
            env = self._build_env()
            cmd = [
                self._opencode_bin,
                "serve",
                "--hostname",
                self._hostname,
                "--port",
                str(port),
                "--pure",
                "--log-level",
                self._log_level,
            ]
            try:
                proc = self._popen_factory(cmd, env)
            except Exception as exc:
                self._last_error = str(exc).strip() or exc.__class__.__name__
                raise
            handle = OpenCodeServerHandle(
                base_url=f"http://{self._hostname}:{port}",
                port=port,
                pid=proc.pid,
            )
            self._process = proc
            self._handle = handle
            self._last_error = None
            return handle

    def shutdown(self) -> None:
        with self._lock:
            if self._process is None or self._process.poll() is not None:
                return
            self._process.terminate()
            self._process.wait(timeout=5)

    def describe(self) -> dict[str, object]:
        with self._lock:
            returncode = self._process.poll() if self._process is not None else None
            running = self._process is not None and returncode is None
            last_error = self._last_error
            if self._process is not None and returncode is not None:
                last_error = last_error or f"opencode process exited with code {returncode}"
            return {
                "running": running,
                "base_url": self._handle.base_url if self._handle is not None else None,
                "port": self._handle.port if self._handle is not None else None,
                "pid": self._handle.pid if self._handle is not None else None,
                "returncode": returncode,
                "configured_bin": self._opencode_bin,
                "resolved_bin": shutil.which(self._opencode_bin),
                "last_error": last_error,
            }

    def _next_port(self) -> int:
        if not self._ports:
            raise ValueError("opencode port range is empty")
        port = self._ports[self._next_port_index % len(self._ports)]
        self._next_port_index += 1
        return port

    def _build_env(self) -> dict[str, str]:
        server_home = self._data_dir / "agent_sessions" / "opencode" / "server_home"
        data_home = self._data_dir / "agent_sessions" / "opencode" / "server_data"
        config_home = self._data_dir / "agent_sessions" / "opencode" / "server_config"
        cache_home = self._data_dir / "agent_sessions" / "opencode" / "server_cache"
        for path in [server_home, data_home, config_home, cache_home]:
            path.mkdir(parents=True, exist_ok=True)

        env = dict(os.environ)
        env.update(
            {
                "HOME": str(server_home),
                "XDG_DATA_HOME": str(data_home),
                "XDG_CONFIG_HOME": str(config_home),
                "XDG_CACHE_HOME": str(cache_home),
                "OPENCODE_SERVER_USERNAME": self._username,
                "OPENCODE_SERVER_PASSWORD": self._password,
            }
        )
        return env


def _default_popen(cmd: Sequence[str], env: dict[str, str]) -> ProcessLike:
    return subprocess.Popen(  # noqa: S603
        list(cmd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _parse_port_range(value: str) -> list[int]:
    cleaned = value.strip()
    if "-" in cleaned:
        start_text, end_text = cleaned.split("-", 1)
        start = int(start_text)
        end = int(end_text)
        if end < start:
            raise ValueError(f"invalid opencode port range: {value}")
        return list(range(start, end + 1))
    return [int(cleaned)]
