"""APScheduler idle worktree cleanup job."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

import structlog

from codeask.code_index.worktree import WorktreeManager

log = structlog.get_logger("codeask.code_index.cleanup")

_DEFAULT_IDLE_SECONDS = 24 * 3600


def find_idle_worktrees(
    repo_root: Path,
    idle_threshold_seconds: int = _DEFAULT_IDLE_SECONDS,
) -> list[tuple[str, str, Path]]:
    """Return ``(repo_id, session_id, path)`` for idle worktree directories."""
    if not repo_root.is_dir():
        return []

    cutoff = time.time() - idle_threshold_seconds
    idle: list[tuple[str, str, Path]] = []
    for repo_dir in repo_root.iterdir():
        if not repo_dir.is_dir():
            continue
        worktrees_root = repo_dir / "worktrees"
        if not worktrees_root.is_dir():
            continue
        for session_dir in worktrees_root.iterdir():
            if not session_dir.is_dir():
                continue
            try:
                mtime = session_dir.stat().st_mtime
            except OSError:
                continue
            if mtime < cutoff:
                idle.append((repo_dir.name, session_dir.name, session_dir))
    return idle


def build_cleanup_job(
    worktree_manager: WorktreeManager,
    repo_root: Path,
    idle_threshold_seconds: int = _DEFAULT_IDLE_SECONDS,
) -> Callable[[], None]:
    """Return a synchronous callable suitable for ``scheduler.add_job``."""

    def _run() -> None:
        for repo_id, session_id, _path in find_idle_worktrees(
            repo_root,
            idle_threshold_seconds,
        ):
            try:
                worktree_manager.destroy_worktree(repo_id, session_id)
                log.info(
                    "worktree_cleanup_removed",
                    repo_id=repo_id,
                    session_id=session_id,
                )
            except Exception as exc:  # pragma: no cover - defensive job boundary
                log.warning(
                    "worktree_cleanup_failed",
                    repo_id=repo_id,
                    session_id=session_id,
                    error=str(exc),
                )

    return _run
