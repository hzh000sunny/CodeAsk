"""Git worktree lifecycle for session-scoped code access."""

from __future__ import annotations

import re
import shutil
import subprocess
from contextlib import suppress
from pathlib import Path

import structlog

log = structlog.get_logger("codeask.code_index.worktree")

_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_SHA_RE = re.compile(r"[0-9a-f]{40}")
_GIT_TIMEOUT = 60


class WorktreeError(Exception):
    """Base class for worktree errors."""


class InvalidRefError(WorktreeError):
    """Raised when a ref, branch, tag, or sha does not resolve to a commit."""


class WorktreeManager:
    """Manage session worktrees under ``<repo_root>/<repo_id>/worktrees``."""

    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root

    def _bare(self, repo_id: str) -> Path:
        if not _SAFE_ID.fullmatch(repo_id):
            raise WorktreeError(f"unsafe repo_id: {repo_id!r}")
        return self._repo_root / repo_id / "bare"

    def worktree_path(self, repo_id: str, session_id: str) -> Path:
        if not _SAFE_ID.fullmatch(repo_id):
            raise WorktreeError(f"unsafe repo_id: {repo_id!r}")
        if not _SAFE_ID.fullmatch(session_id):
            raise WorktreeError(f"unsafe session_id: {session_id!r}")
        return self._repo_root / repo_id / "worktrees" / session_id

    def resolve_ref(self, repo_id: str, ref: str | None) -> str:
        bare = self._bare(repo_id)
        if not bare.is_dir():
            raise WorktreeError(f"bare repo missing: {bare}")

        target = ref if ref else "HEAD"
        try:
            proc = subprocess.run(
                [
                    "git",
                    "--git-dir",
                    str(bare),
                    "rev-parse",
                    "--verify",
                    f"{target}^{{commit}}",
                ],
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                timeout=_GIT_TIMEOUT,
            )
        except subprocess.TimeoutExpired as exc:
            raise WorktreeError("git rev-parse timed out") from exc

        if proc.returncode != 0:
            raise InvalidRefError(
                f"ref {target!r} does not resolve in {repo_id}: {proc.stderr.strip()}"
            )

        sha = proc.stdout.strip()
        if not _SHA_RE.fullmatch(sha):
            raise InvalidRefError(f"unexpected rev-parse output: {sha!r}")
        return sha

    def ensure_worktree(self, repo_id: str, session_id: str, ref: str | None) -> Path:
        bare = self._bare(repo_id)
        sha = self.resolve_ref(repo_id, ref)
        path = self.worktree_path(repo_id, session_id)

        if path.is_dir():
            head = self._read_worktree_head(path)
            if head == sha:
                return path
            self.destroy_worktree(repo_id, session_id)

        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            proc = subprocess.run(
                [
                    "git",
                    "--git-dir",
                    str(bare),
                    "worktree",
                    "add",
                    "--detach",
                    str(path),
                    sha,
                ],
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                timeout=_GIT_TIMEOUT,
            )
        except subprocess.TimeoutExpired as exc:
            raise WorktreeError("git worktree add timed out") from exc

        if proc.returncode != 0:
            raise WorktreeError(f"git worktree add failed: {proc.stderr.strip()}")

        log.info("worktree_created", repo_id=repo_id, session_id=session_id, sha=sha)
        return path

    def destroy_worktree(self, repo_id: str, session_id: str) -> None:
        bare = self._bare(repo_id)
        path = self.worktree_path(repo_id, session_id)
        if not path.exists():
            return

        with suppress(subprocess.TimeoutExpired):
            subprocess.run(
                [
                    "git",
                    "--git-dir",
                    str(bare),
                    "worktree",
                    "remove",
                    "--force",
                    str(path),
                ],
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                timeout=_GIT_TIMEOUT,
            )

        subprocess.run(
            ["git", "--git-dir", str(bare), "worktree", "prune"],
            shell=False,
            check=False,
            capture_output=True,
            timeout=_GIT_TIMEOUT,
        )
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
        log.info("worktree_destroyed", repo_id=repo_id, session_id=session_id)

    def list_worktrees(self, repo_id: str) -> list[Path]:
        bare = self._bare(repo_id)
        if not bare.is_dir():
            return []

        try:
            proc = subprocess.run(
                ["git", "--git-dir", str(bare), "worktree", "list", "--porcelain"],
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                timeout=_GIT_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return []

        if proc.returncode != 0:
            return []

        paths: list[Path] = []
        for line in proc.stdout.splitlines():
            if line.startswith("worktree "):
                paths.append(Path(line.removeprefix("worktree ")))
        return [path for path in paths if path.resolve() != bare.resolve()]

    def _read_worktree_head(self, path: Path) -> str | None:
        try:
            proc = subprocess.run(
                ["git", "-C", str(path), "rev-parse", "HEAD"],
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                timeout=_GIT_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return None

        sha = proc.stdout.strip()
        if proc.returncode == 0 and _SHA_RE.fullmatch(sha):
            return sha
        return None
