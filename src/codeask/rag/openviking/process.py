"""OpenViking server process manager."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import BinaryIO, Protocol

from codeask.rag.openviking.config import OpenVikingRuntimeConfig, write_ov_conf


class ProcessLike(Protocol):
    pid: int

    def poll(self) -> int | None: ...
    def terminate(self) -> None: ...
    def wait(self, timeout: float | None = None) -> int: ...


PopenFactory = Callable[[Sequence[str], dict[str, str]], ProcessLike]
VersionResolver = Callable[[], str | None]


@dataclass(frozen=True)
class OpenVikingServerHandle:
    base_url: str
    port: int
    pid: int


class OpenVikingProcessManager:
    def __init__(
        self,
        *,
        data_dir: Path,
        port: int,
        host: str = "127.0.0.1",
        package: str = "openviking==0.3.17",
        popen_factory: PopenFactory | None = None,
        version_resolver: VersionResolver | None = None,
    ) -> None:
        self._runtime_config = OpenVikingRuntimeConfig(data_dir=data_dir, host=host, port=port)
        self._host = host
        self._port = port
        self._package = package
        self._popen_factory = popen_factory
        self._version_resolver = version_resolver
        self._process: ProcessLike | None = None
        self._handle: OpenVikingServerHandle | None = None
        self._log_file: BinaryIO | None = None
        self._lock = Lock()
        self._last_error: str | None = None
        self._last_error_code: str | None = None
        self._version: str | None = None

    def ensure_server(self) -> OpenVikingServerHandle:
        with self._lock:
            if (
                self._process is not None
                and self._process.poll() is None
                and self._handle is not None
            ):
                return self._handle
            write_ov_conf(self._runtime_config)
            cmd = [
                "uvx",
                "--from",
                self._package,
                "--with",
                "socksio",
                "openviking-server",
                "--config",
                str(self._runtime_config.config_path),
            ]
            env = dict(os.environ)
            self._version = self._version_resolver() if self._version_resolver else None
            try:
                if self._popen_factory:
                    proc = self._popen_factory(cmd, env)
                else:
                    proc, log_file = _default_popen(cmd, env, self._server_log_path())
                    self._replace_log_file(log_file)
            except Exception as exc:
                self._last_error = str(exc)
                self._last_error_code = "openviking_start_failed"
                raise
            self._process = proc
            self._handle = OpenVikingServerHandle(
                base_url=f"http://{self._host}:{self._port}",
                port=self._port,
                pid=proc.pid,
            )
            self._last_error = None
            self._last_error_code = None
            return self._handle

    def shutdown(self) -> None:
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                self._process.terminate()
                with suppress(Exception):
                    self._process.wait(timeout=5)
            self._close_log_file()

    def describe(self) -> dict[str, object]:
        with self._lock:
            returncode = self._process.poll() if self._process is not None else None
            running = self._process is not None and returncode is None
            return {
                "running": running,
                "available": running,
                "base_url": self._handle.base_url if self._handle else None,
                "port": self._port,
                "pid": self._handle.pid if self._handle else None,
                "returncode": returncode,
                "version": self._version,
                "verified_version": "0.3.17",
                "last_error": self._last_error,
                "last_error_code": self._last_error_code,
                "config_file": str(self._runtime_config.config_path),
                "workspace_path": str(self._runtime_config.workspace_dir),
                "log_file": str(self._server_log_path()),
            }

    def _server_log_path(self) -> Path:
        return self._runtime_config.log_dir / "openviking-server.log"

    def _replace_log_file(self, log_file: BinaryIO) -> None:
        self._close_log_file()
        self._log_file = log_file

    def _close_log_file(self) -> None:
        if self._log_file is None:
            return
        with suppress(Exception):
            self._log_file.close()
        self._log_file = None


def _default_popen(
    cmd: Sequence[str],
    env: dict[str, str],
    output_path: Path,
) -> tuple[subprocess.Popen[bytes], BinaryIO]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = output_path.open("ab")
    proc = subprocess.Popen(  # noqa: S603
        list(cmd),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    return proc, log_file
