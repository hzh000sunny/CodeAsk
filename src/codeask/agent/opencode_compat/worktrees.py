"""Expose CodeAsk-managed git worktrees inside opencode workspaces."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class WorktreeManagerLike(Protocol):
    def ensure_worktree(self, repo_id: str, session_id: str, ref: str | None) -> Path: ...
    def destroy_worktree(self, repo_id: str, session_id: str) -> None: ...


@dataclass(frozen=True)
class OpenCodeWorktree:
    repo_id: str
    absolute_path: Path
    workspace_path: Path
    relative_path: str


class OpenCodeWorktreeManager:
    """Bridge existing CodeAsk WorktreeManager to opencode workspace paths."""

    def __init__(self, *, worktree_manager: WorktreeManagerLike) -> None:
        self._worktree_manager = worktree_manager

    def prepare_worktree(
        self,
        *,
        repo_id: str,
        session_id: str,
        workspace_dir: Path,
        ref: str | None,
        display_name: str | None = None,
    ) -> OpenCodeWorktree:
        absolute_path = self._worktree_manager.ensure_worktree(repo_id, session_id, ref)
        repos_dir = workspace_dir / "repos"
        repos_dir.mkdir(parents=True, exist_ok=True)
        link_name = _safe_link_name(display_name or repo_id)
        workspace_path = repos_dir / link_name

        if workspace_path.is_symlink():
            if workspace_path.resolve() != absolute_path.resolve():
                workspace_path.unlink()
        elif workspace_path.exists():
            raise ValueError(f"workspace repo path exists and is not a symlink: {workspace_path}")

        if not workspace_path.exists():
            os.symlink(absolute_path.resolve(), workspace_path)

        return OpenCodeWorktree(
            repo_id=repo_id,
            absolute_path=absolute_path,
            workspace_path=workspace_path,
            relative_path=workspace_path.relative_to(workspace_dir).as_posix(),
        )

    def cleanup_worktree(self, *, repo_id: str, session_id: str) -> None:
        self._worktree_manager.destroy_worktree(repo_id, session_id)


def _safe_link_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()).strip("._-")
    return cleaned or "repo"
