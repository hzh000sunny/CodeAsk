"""Shared opencode server process management."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from io import TextIOWrapper
from pathlib import Path
from threading import Lock
from typing import Protocol


class ProcessLike(Protocol):
    pid: int

    def poll(self) -> int | None: ...
    def terminate(self) -> None: ...
    def wait(self, timeout: float | None = None) -> int: ...


PopenFactory = Callable[[Sequence[str], dict[str, str]], ProcessLike]
VersionResolver = Callable[[str], str | None]


@dataclass(frozen=True)
class OpenCodeServerHandle:
    base_url: str
    port: int
    pid: int


class OpenCodeProcessError(RuntimeError):
    """Classified opencode process lifecycle error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


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
        version_resolver: VersionResolver | None = None,
    ) -> None:
        self._opencode_bin = opencode_bin
        self._data_dir = data_dir
        self._ports = _parse_port_range(port_range)
        self._username = username
        self._password = password
        self._hostname = hostname
        self._log_level = log_level
        self._popen_factory = popen_factory
        self._version_resolver = version_resolver
        self._process: ProcessLike | None = None
        self._handle: OpenCodeServerHandle | None = None
        self._log_file: TextIOWrapper | None = None
        self._next_port_index = 0
        self._lock = Lock()
        self._last_error: str | None = None
        self._last_error_code: str | None = None
        self._version: str | None = None
        self._last_health_at: str | None = None

    def ensure_server(self) -> OpenCodeServerHandle:
        with self._lock:
            if (
                self._process is not None
                and self._process.poll() is None
                and self._handle is not None
            ):
                self._last_error = None
                self._last_error_code = None
                return self._handle

            port = self._next_port()
            env = self._build_env()
            self._version = self._resolve_version()
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
                if self._popen_factory is not None:
                    proc = self._popen_factory(cmd, env)
                else:
                    proc, log_file = _default_popen(cmd, env, self._server_log_path())
                    self._replace_log_file(log_file)
            except Exception as exc:
                error = _classify_start_error(exc, resolved_bin=shutil.which(self._opencode_bin))
                self._last_error = str(error).strip() or error.__class__.__name__
                self._last_error_code = error.code
                raise error from exc
            handle = OpenCodeServerHandle(
                base_url=f"http://{self._hostname}:{port}",
                port=port,
                pid=proc.pid,
            )
            self._process = proc
            self._handle = handle
            self._last_error = None
            self._last_error_code = None
            return handle

    def shutdown(self) -> None:
        with self._lock:
            if self._process is None or self._process.poll() is not None:
                self._close_log_file()
                return
            self._process.terminate()
            self._process.wait(timeout=5)
            self._close_log_file()

    def record_health_ok(self) -> None:
        with self._lock:
            self._last_health_at = datetime.now(UTC).isoformat()
            self._last_error = None
            self._last_error_code = None

    def describe(self) -> dict[str, object]:
        with self._lock:
            returncode = self._process.poll() if self._process is not None else None
            running = self._process is not None and returncode is None
            last_error = self._last_error
            last_error_code = self._last_error_code
            if self._process is not None and returncode is not None:
                last_error = last_error or f"opencode process exited with code {returncode}"
                last_error_code = last_error_code or "opencode_process_exited"
            return {
                "running": running,
                "base_url": self._handle.base_url if self._handle is not None else None,
                "port": self._handle.port if self._handle is not None else None,
                "pid": self._handle.pid if self._handle is not None else None,
                "returncode": returncode,
                "configured_bin": self._opencode_bin,
                "resolved_bin": shutil.which(self._opencode_bin),
                "last_error": last_error,
                "last_error_code": last_error_code,
                "last_health_at": self._last_health_at,
                "log_file": str(self._server_log_path()),
                "version": self._version,
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

    def _server_log_path(self) -> Path:
        return self._data_dir / "agent_sessions" / "opencode" / "logs" / "opencode-server.log"

    def _replace_log_file(self, log_file: TextIOWrapper) -> None:
        self._close_log_file()
        self._log_file = log_file

    def _close_log_file(self) -> None:
        if self._log_file is None:
            return
        with suppress(Exception):
            self._log_file.close()
        self._log_file = None

    def _resolve_version(self) -> str | None:
        resolver = self._version_resolver
        if resolver is not None:
            return resolver(self._opencode_bin)
        if self._popen_factory is not None:
            return None
        return _default_version_resolver(self._opencode_bin)


def _default_popen(
    cmd: Sequence[str],
    env: dict[str, str],
    output_path: Path,
) -> tuple[ProcessLike, TextIOWrapper]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = output_path.open("a", encoding="utf-8")
    process = subprocess.Popen(  # noqa: S603
        list(cmd),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return process, log_file


def _classify_start_error(exc: Exception, *, resolved_bin: str | None) -> OpenCodeProcessError:
    message = str(exc).strip() or exc.__class__.__name__
    if isinstance(exc, FileNotFoundError) or resolved_bin is None:
        return OpenCodeProcessError("opencode_bin_missing", message)
    return OpenCodeProcessError("opencode_start_failed", message)


def _default_version_resolver(opencode_bin: str) -> str | None:
    try:
        completed = subprocess.run(  # noqa: S603
            [opencode_bin, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return None
    output = (completed.stdout or completed.stderr or "").strip()
    return output.splitlines()[0].strip() if output else None


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
