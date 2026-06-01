"""OpenViking server process manager."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, BinaryIO, Protocol, cast

import httpx

from codeask.rag.openviking.config import OpenVikingRuntimeConfig, write_ov_conf
from codeask.rag.openviking.health import OpenVikingHealthStatus


class ProcessLike(Protocol):
    pid: int

    def poll(self) -> int | None: ...
    def terminate(self) -> None: ...
    def wait(self, timeout: float | None = None) -> int: ...


PopenFactory = Callable[[Sequence[str], dict[str, str]], ProcessLike]
VersionResolver = Callable[[], str | None]
HealthProbe = Callable[[str, float], OpenVikingHealthStatus]
Clock = Callable[[], float]


@dataclass(frozen=True)
class OpenVikingServerHandle:
    base_url: str
    port: int
    pid: int | None


class OpenVikingProcessError(RuntimeError):
    """Classified OpenViking process lifecycle error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class OpenVikingProcessManager:
    def __init__(
        self,
        *,
        data_dir: Path,
        port: int,
        host: str = "127.0.0.1",
        openviking_bin: str = "openviking-server",
        popen_factory: PopenFactory | None = None,
        version_resolver: VersionResolver | None = None,
        health_probe: HealthProbe | None = None,
        startup_grace_seconds: float = 30.0,
        health_timeout_seconds: float = 2.0,
        clock: Clock | None = None,
    ) -> None:
        self._runtime_config = OpenVikingRuntimeConfig(data_dir=data_dir, host=host, port=port)
        self._host = host
        self._port = port
        self._openviking_bin = openviking_bin
        self._popen_factory = popen_factory
        self._version_resolver = version_resolver
        self._health_probe = health_probe or _default_health_probe
        self._startup_grace_seconds = startup_grace_seconds
        self._health_timeout_seconds = health_timeout_seconds
        self._clock = clock or time.monotonic
        self._process: ProcessLike | None = None
        self._handle: OpenVikingServerHandle | None = None
        self._log_file: BinaryIO | None = None
        self._lock = RLock()
        self._last_error: str | None = None
        self._last_error_code: str | None = None
        self._version: str | None = None
        self._available = False
        self._started_at: float | None = None

    def ensure_server(self) -> OpenVikingServerHandle:
        return self._ensure_server(adopt_existing=True)

    def _ensure_server(self, *, adopt_existing: bool) -> OpenVikingServerHandle:
        with self._lock:
            base_url = f"http://{self._host}:{self._port}"
            if (
                self._process is not None
                and self._process.poll() is None
                and self._handle is not None
            ):
                self._refresh_health(self._handle)
                if self._available or self._within_startup_grace():
                    return self._handle
                self._terminate_current()
                self._process = None
                self._handle = None
                self._available = False
                self._last_error_code = "openviking_health_failed"
            if self._process is not None and self._process.poll() is not None:
                self._available = False
                self._last_error = f"OpenViking process exited with code {self._process.poll()}"
                self._last_error_code = "openviking_process_exited"
                self._process = None
                self._handle = None
                self._started_at = None
            if self._process is None and adopt_existing:
                external_handle = OpenVikingServerHandle(
                    base_url=base_url,
                    port=self._port,
                    pid=None,
                )
                self._refresh_health(external_handle)
                if self._available:
                    self._handle = external_handle
                    self._started_at = None
                    return external_handle
            write_ov_conf(self._runtime_config)
            cmd = [
                self._openviking_bin,
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
                error = _classify_start_error(
                    exc,
                    resolved_bin=shutil.which(self._openviking_bin),
                )
                self._last_error = str(error).strip() or error.__class__.__name__
                self._last_error_code = error.code
                raise error from exc
            self._process = proc
            self._handle = OpenVikingServerHandle(
                base_url=base_url,
                port=self._port,
                pid=proc.pid,
            )
            self._started_at = self._clock()
            self._available = False
            self._refresh_health(self._handle)
            return self._handle

    def shutdown(self) -> None:
        with self._lock:
            self._terminate_current()
            self._available = False
            self._started_at = None
            self._close_log_file()

    def regenerate_ov_conf(self, runtime_config: OpenVikingRuntimeConfig | None = None) -> Path:
        with self._lock:
            if runtime_config is not None:
                self._runtime_config = runtime_config
                self._host = runtime_config.host
                self._port = runtime_config.port
            return write_ov_conf(self._runtime_config)

    def restart_openviking(
        self,
        runtime_config: OpenVikingRuntimeConfig | None = None,
    ) -> OpenVikingServerHandle:
        with self._lock:
            if runtime_config is not None:
                self._runtime_config = runtime_config
                self._host = runtime_config.host
                self._port = runtime_config.port
            self.shutdown()
            self._process = None
            self._handle = None
            return self._ensure_server(adopt_existing=False)

    def describe(self) -> dict[str, object]:
        with self._lock:
            returncode = self._process.poll() if self._process is not None else None
            running = (self._process is not None and returncode is None) or (
                self._process is None and self._handle is not None and self._available
            )
            return {
                "running": running,
                "available": running and self._available,
                "base_url": self._handle.base_url if self._handle else None,
                "port": self._port,
                "pid": self._handle.pid if self._handle else None,
                "returncode": returncode,
                "version": self._version,
                "verified_version": "0.3.17",
                "configured_bin": self._openviking_bin,
                "resolved_bin": shutil.which(self._openviking_bin),
                "last_error": self._last_error,
                "last_error_code": self._last_error_code,
                "config_file": str(self._runtime_config.config_path),
                "workspace_path": str(self._runtime_config.workspace_dir),
                "log_file": str(self._server_log_path()),
            }

    def _server_log_path(self) -> Path:
        return self._runtime_config.log_dir / "openviking-server.log"

    def _refresh_health(self, handle: OpenVikingServerHandle) -> None:
        health = self._health_probe(handle.base_url, self._health_timeout_seconds)
        if health.healthy:
            self._available = True
            self._last_error = None
            self._last_error_code = None
            if health.version:
                self._version = health.version
            return
        self._available = False
        self._last_error = health.error or "OpenViking health check failed"
        self._last_error_code = (
            "openviking_health_pending"
            if self._within_startup_grace()
            else "openviking_health_failed"
        )

    def _within_startup_grace(self) -> bool:
        if self._started_at is None:
            return False
        return (self._clock() - self._started_at) < self._startup_grace_seconds

    def _terminate_current(self) -> None:
        if self._process is None or self._process.poll() is not None:
            return
        self._process.terminate()
        with suppress(Exception):
            self._process.wait(timeout=5)

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


def _classify_start_error(exc: Exception, *, resolved_bin: str | None) -> OpenVikingProcessError:
    if isinstance(exc, FileNotFoundError) or resolved_bin is None:
        return OpenVikingProcessError(
            "openviking_bin_not_found",
            (
                "未找到 openviking-server，请先执行 `uv sync`，"
                "或通过 CODEASK_OPENVIKING_BIN 配置可执行文件路径。"
            ),
        )
    message = str(exc).strip() or exc.__class__.__name__
    return OpenVikingProcessError("openviking_start_failed", message)


def _default_health_probe(base_url: str, timeout: float) -> OpenVikingHealthStatus:
    try:
        with httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            trust_env=False,
        ) as client:
            response = client.get("/health")
            response.raise_for_status()
            response_data = response.json()
    except Exception as exc:
        return OpenVikingHealthStatus(healthy=False, version=None, error=str(exc))
    data = cast(dict[str, Any], response_data) if isinstance(response_data, dict) else {}
    version = data.get("version")
    return OpenVikingHealthStatus(
        healthy=bool(data.get("healthy", data.get("status") == "ok")),
        version=version if isinstance(version, str) else None,
        error=None,
    )
