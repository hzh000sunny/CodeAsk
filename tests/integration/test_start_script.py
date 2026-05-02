"""Regression tests for the local start.sh bootstrap script."""

import stat
import subprocess
from pathlib import Path

from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[2]


def _copy_start_script(tmp_path: Path) -> Path:
    script = tmp_path / "start.sh"
    script.write_text((ROOT / "start.sh").read_text(encoding="utf-8"), encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


def _write_fake_command(bin_dir: Path, name: str, log: Path) -> None:
    command = bin_dir / name
    command.write_text(
        f'#!/bin/bash\necho "{name} $*" >> {log}\nexit 0\n',
        encoding="utf-8",
    )
    command.chmod(command.stat().st_mode | stat.S_IXUSR)


def _write_env_logging_command(bin_dir: Path, name: str, log: Path) -> None:
    command = bin_dir / name
    litellm_env = "LITELLM_LOCAL_MODEL_COST_MAP=${LITELLM_LOCAL_MODEL_COST_MAP:-}"
    command.write_text(
        (
            "#!/bin/bash\n"
            f'echo "{name} $* {litellm_env}" >> {log}\n'
            "exit 0\n"
        ),
        encoding="utf-8",
    )
    command.chmod(command.stat().st_mode | stat.S_IXUSR)


def _write_passthrough_command(bin_dir: Path, name: str, target: str) -> None:
    command = bin_dir / name
    command.write_text(
        f'#!/bin/bash\nexec {target} "$@"\n',
        encoding="utf-8",
    )
    command.chmod(command.stat().st_mode | stat.S_IXUSR)


def test_start_script_fails_fast_without_data_key(tmp_path: Path) -> None:
    script = _copy_start_script(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_passthrough_command(bin_dir, "dirname", "/usr/bin/dirname")
    _write_passthrough_command(bin_dir, "cat", "/bin/cat")
    env = {
        "PATH": str(bin_dir),
        "HOME": str(tmp_path),
    }

    result = subprocess.run(
        ["/bin/bash", str(script)],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "CODEASK_DATA_KEY is not set" in result.stderr


def test_start_script_builds_frontend_dist_when_tools_are_available(tmp_path: Path) -> None:
    script = _copy_start_script(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "commands.log"
    _write_passthrough_command(bin_dir, "dirname", "/usr/bin/dirname")
    _write_passthrough_command(bin_dir, "cat", "/bin/cat")
    _write_fake_command(bin_dir, "uv", log)
    _write_fake_command(bin_dir, "corepack", log)
    _write_fake_command(bin_dir, "pnpm", log)
    (tmp_path / "frontend").mkdir()

    env = {
        "PATH": str(bin_dir),
        "HOME": str(tmp_path),
        "CODEASK_DATA_KEY": Fernet.generate_key().decode(),
        "LITELLM_LOCAL_MODEL_COST_MAP": "False",
    }
    result = subprocess.run(
        ["/bin/bash", str(script)],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "frontend/dist not found" in result.stdout
    commands = log.read_text(encoding="utf-8")
    assert "uv sync --frozen" in commands
    assert "corepack pnpm --dir frontend install --frozen-lockfile" in commands
    assert "corepack pnpm --dir frontend build" in commands
    assert "uv run codeask" in commands


def test_start_script_warns_when_frontend_dist_missing_and_tools_unavailable(
    tmp_path: Path,
) -> None:
    script = _copy_start_script(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "commands.log"
    _write_passthrough_command(bin_dir, "dirname", "/usr/bin/dirname")
    _write_passthrough_command(bin_dir, "cat", "/bin/cat")
    _write_fake_command(bin_dir, "uv", log)
    (tmp_path / "frontend").mkdir()

    env = {
        "PATH": str(bin_dir),
        "HOME": str(tmp_path),
        "CODEASK_DATA_KEY": Fernet.generate_key().decode(),
    }
    result = subprocess.run(
        ["/bin/bash", str(script)],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "WARNING: frontend/dist/index.html not found." in result.stderr
    commands = log.read_text(encoding="utf-8")
    assert "uv sync --frozen" in commands
    assert "uv run codeask" in commands


def test_start_script_exports_litellm_local_model_cost_map_by_default(
    tmp_path: Path,
) -> None:
    script = _copy_start_script(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "commands.log"
    _write_passthrough_command(bin_dir, "dirname", "/usr/bin/dirname")
    _write_env_logging_command(bin_dir, "uv", log)
    dist = tmp_path / "frontend" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")

    env = {
        "PATH": str(bin_dir),
        "HOME": str(tmp_path),
        "CODEASK_DATA_KEY": Fernet.generate_key().decode(),
    }
    result = subprocess.run(
        ["/bin/bash", str(script)],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    commands = log.read_text(encoding="utf-8")
    assert "uv sync --frozen LITELLM_LOCAL_MODEL_COST_MAP=True" in commands
    assert "uv run codeask LITELLM_LOCAL_MODEL_COST_MAP=True" in commands
