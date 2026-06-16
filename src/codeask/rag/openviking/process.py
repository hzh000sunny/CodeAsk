"""OpenViking server process manager."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
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
PidResolver = Callable[[str, int], int | None]
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
        pid_resolver: PidResolver | None = None,
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
        self._pid_resolver = pid_resolver or _default_pid_resolver
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
        # Sticky reason for the most recent abnormal exit: survives the keepalive
        # relaunch loop so the actual failure (e.g. model download error) stays
        # observable instead of being masked by the next "starting up" probe.
        self._last_failure_log: str | None = None
        self._consecutive_failures = 0
        self._version: str | None = None
        self._installed_version: str | None = None
        self._installed_version_resolved = False
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
                exit_code = self._process.poll()
                self._available = False
                self._consecutive_failures += 1
                self._last_failure_log = self._read_log_tail()
                self._last_error = f"OpenViking process exited with code {exit_code}"
                self._last_error_code = "openviking_process_exited"
                self._process = None
                self._handle = None
                self._started_at = None
            if self._process is None and adopt_existing:
                external_handle = OpenVikingServerHandle(
                    base_url=base_url,
                    port=self._port,
                    pid=self._resolve_listening_pid(),
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
            self._version = self._resolve_installed_version()
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
            handle_pid = self._handle.pid if self._handle else None
            if handle_pid is None and self._handle is not None and self._available:
                resolved_pid = self._resolve_listening_pid()
                if resolved_pid is not None:
                    self._handle = OpenVikingServerHandle(
                        base_url=self._handle.base_url,
                        port=self._handle.port,
                        pid=resolved_pid,
                    )
                    handle_pid = resolved_pid
            installed_version = self._resolve_installed_version()
            available = running and self._available
            last_error, last_error_code = self._effective_error(available)
            # The log tail is the single source of truth for *why* a start failed
            # (model download, port conflict, bad config, OOM …). Expose it whenever
            # the server is not healthy so callers don't have to grep the log file.
            log_tail = None if available else (self._last_failure_log or self._read_log_tail())
            return {
                "running": running,
                "available": available,
                "base_url": self._handle.base_url if self._handle else None,
                "port": self._port,
                "pid": handle_pid,
                "returncode": returncode,
                "version": self._version,
                "installed_version": installed_version,
                "verified_version": installed_version,
                "supported_version_range": ">=0.3.22,<0.4",
                "configured_bin": self._openviking_bin,
                "resolved_bin": shutil.which(self._openviking_bin),
                "last_error": last_error,
                "last_error_code": last_error_code,
                "consecutive_failures": self._consecutive_failures,
                "log_tail": log_tail,
                "config_file": str(self._runtime_config.config_path),
                "workspace_path": str(self._runtime_config.workspace_dir),
                "log_file": str(self._server_log_path()),
            }

    def _effective_error(self, available: bool) -> tuple[str | None, str | None]:
        if available:
            return None, None
        # A process that keeps exiting gets relaunched within the same locked call,
        # so the live last_error flaps to "starting up". Prefer the sticky crash-loop
        # signal so the real failure stays visible across restarts.
        if self._consecutive_failures >= 2 and self._last_failure_log:
            return (
                f"OpenViking 反复启动失败（连续 {self._consecutive_failures} 次），"
                "请查看下方日志定位原因。",
                "openviking_crash_loop",
            )
        return self._last_error, self._last_error_code

    def _server_log_path(self) -> Path:
        return self._runtime_config.log_dir / "openviking-server.log"

    def _read_log_tail(self, *, max_bytes: int = 16384, max_lines: int = 40) -> str | None:
        path = self._server_log_path()
        try:
            size = path.stat().st_size
            with path.open("rb") as handle:
                if size > max_bytes:
                    handle.seek(size - max_bytes)
                raw = handle.read()
        except OSError:
            return None
        text = raw.decode("utf-8", errors="replace").strip()
        if not text:
            return None
        lines = text.splitlines()
        return "\n".join(lines[-max_lines:])

    def _refresh_health(self, handle: OpenVikingServerHandle) -> None:
        health = self._health_probe(handle.base_url, self._health_timeout_seconds)
        if health.healthy:
            self._available = True
            self._last_error = None
            self._last_error_code = None
            self._last_failure_log = None
            self._consecutive_failures = 0
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

    def _resolve_installed_version(self) -> str | None:
        if self._installed_version_resolved:
            return self._installed_version
        self._installed_version = (
            self._version_resolver() if self._version_resolver else _default_version_resolver()
        )
        self._installed_version_resolved = True
        return self._installed_version

    def _resolve_listening_pid(self) -> int | None:
        try:
            return self._pid_resolver(self._host, self._port)
        except Exception:
            return None

    def _terminate_current(self) -> None:
        if self._process is None or self._process.poll() is not None:
            return
        self._process.terminate()
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            kill = getattr(self._process, "kill", None)
            if callable(kill):
                with suppress(Exception):
                    kill()
            with suppress(Exception):
                self._process.wait(timeout=5)
        except Exception:
            return

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


def _default_version_resolver() -> str | None:
    try:
        return package_version("openviking")
    except (PackageNotFoundError, Exception):
        return None


def _default_pid_resolver(_host: str, port: int) -> int | None:
    inodes = _listening_socket_inodes(port)
    if not inodes:
        return None
    return _pid_for_socket_inodes(inodes)


def _listening_socket_inodes(port: int) -> set[str]:
    inodes: set[str] = set()
    for proc_net_path in (Path("/proc/net/tcp"), Path("/proc/net/tcp6")):
        try:
            lines = proc_net_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines[1:]:
            parts = line.split()
            if len(parts) < 10:
                continue
            local_address = parts[1]
            state = parts[3]
            inode = parts[9]
            if state != "0A" or ":" not in local_address:
                continue
            _address_hex, port_hex = local_address.rsplit(":", 1)
            try:
                local_port = int(port_hex, 16)
            except ValueError:
                continue
            if local_port == port:
                inodes.add(inode)
    return inodes


def _pid_for_socket_inodes(inodes: set[str]) -> int | None:
    proc_root = Path("/proc")
    try:
        pid_dirs = [
            entry for entry in proc_root.iterdir() if entry.name.isdigit() and entry.is_dir()
        ]
    except OSError:
        return None
    for pid_dir in sorted(pid_dirs, key=lambda entry: int(entry.name)):
        fd_dir = pid_dir / "fd"
        try:
            fd_entries = list(fd_dir.iterdir())
        except OSError:
            continue
        for fd_entry in fd_entries:
            try:
                target = os.readlink(fd_entry)
            except OSError:
                continue
            if not target.startswith("socket:[") or not target.endswith("]"):
                continue
            inode = target.removeprefix("socket:[").removesuffix("]")
            if inode in inodes:
                return int(pid_dir.name)
    return None


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
