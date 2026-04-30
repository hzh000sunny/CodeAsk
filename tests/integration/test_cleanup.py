"""Idle worktree cleanup tests."""

import os
import subprocess
import time
from pathlib import Path

from codeask.code_index.cleanup import build_cleanup_job, find_idle_worktrees
from codeask.code_index.worktree import WorktreeManager


def _bootstrap(tmp_path: Path) -> tuple[Path, Path]:
    src = tmp_path / "src"
    src.mkdir()
    subprocess.run(
        ["git", "init", "--initial-branch=main", str(src)],
        check=True,
        capture_output=True,
    )
    (src / "f.py").write_text("x=1\n")
    subprocess.run(["git", "-C", str(src), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(src), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(src), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(src), "commit", "-m", "init"],
        check=True,
        capture_output=True,
    )
    pool = tmp_path / "pool"
    bare = pool / "r" / "bare"
    bare.parent.mkdir(parents=True)
    subprocess.run(
        ["git", "clone", "--bare", "--local", str(src), str(bare)],
        check=True,
        capture_output=True,
    )
    return pool, bare


def test_find_idle_worktrees_threshold(tmp_path: Path) -> None:
    pool, _ = _bootstrap(tmp_path)
    manager = WorktreeManager(repo_root=pool)

    manager.ensure_worktree("r", "fresh-sess", "main")
    stale = manager.ensure_worktree("r", "stale-sess", "main")

    old = time.time() - 48 * 3600
    os.utime(stale, (old, old))

    idle = find_idle_worktrees(pool, idle_threshold_seconds=24 * 3600)
    idle_session_ids = {session_id for (_repo, session_id, _path) in idle}
    assert "stale-sess" in idle_session_ids
    assert "fresh-sess" not in idle_session_ids


def test_cleanup_job_destroys_idle(tmp_path: Path) -> None:
    pool, _ = _bootstrap(tmp_path)
    manager = WorktreeManager(repo_root=pool)

    fresh = manager.ensure_worktree("r", "fresh", "main")
    stale = manager.ensure_worktree("r", "stale", "main")
    old = time.time() - 48 * 3600
    os.utime(stale, (old, old))

    job = build_cleanup_job(manager, pool, idle_threshold_seconds=24 * 3600)
    job()

    assert fresh.exists()
    assert not stale.exists()


def test_cleanup_job_no_op_when_pool_missing(tmp_path: Path) -> None:
    manager = WorktreeManager(repo_root=tmp_path / "no-pool")
    job = build_cleanup_job(manager, tmp_path / "no-pool", idle_threshold_seconds=1)
    job()
