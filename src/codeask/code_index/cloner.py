"""Background git clone worker for the global repo pool."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from codeask.db.models import Repo

log = structlog.get_logger("codeask.code_index.cloner")


class CloneError(Exception):
    """Base class for clone failures."""


class CloneFailedError(CloneError):
    """Raised when git clone exits with a non-zero status."""


class CloneTimeoutError(CloneError):
    """Raised when git clone exceeds the configured timeout."""


class RepoCloner:
    """Run ``git clone --bare`` and update the repo status row."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        clone_timeout_seconds: int = 1800,
    ) -> None:
        self._session_factory = session_factory
        self._timeout = clone_timeout_seconds

    def run_clone(self, repo_id: str) -> None:
        """Clone a registered repo into its bare path.

        This method is intentionally synchronous so APScheduler can run it in a
        thread pool without tying it to the FastAPI event loop.
        """
        repo = self._load_repo_sync(repo_id)
        if repo is None:
            log.warning("clone_skipped_missing_repo", repo_id=repo_id)
            return
        if repo.status == Repo.STATUS_READY:
            log.info("clone_skipped_already_ready", repo_id=repo_id)
            return

        bare_path = Path(repo.bare_path)
        self._set_status(repo_id, Repo.STATUS_CLONING, error=None)

        try:
            argv = self._build_clone_argv(repo, bare_path)
            self._exec_clone(argv, bare_path)
        except CloneError as exc:
            self._set_status(repo_id, Repo.STATUS_FAILED, error=str(exc))
            raise

        self._set_status(repo_id, Repo.STATUS_READY, error=None, mark_synced=True)
        log.info("clone_succeeded", repo_id=repo_id, bare_path=str(bare_path))

    def _build_clone_argv(self, repo: Repo, bare_path: Path) -> list[str]:
        if repo.source == Repo.SOURCE_GIT:
            if not repo.url:
                raise CloneFailedError("git source requires non-empty url")
            return ["git", "clone", "--bare", repo.url, str(bare_path)]

        if repo.source == Repo.SOURCE_LOCAL_DIR:
            if not repo.local_path:
                raise CloneFailedError("local_dir source requires non-empty local_path")
            return [
                "git",
                "clone",
                "--bare",
                "--local",
                repo.local_path,
                str(bare_path),
            ]

        raise CloneFailedError(f"unknown source {repo.source!r}")

    def _exec_clone(self, argv: list[str], bare_path: Path) -> None:
        if bare_path.exists():
            shutil.rmtree(bare_path, ignore_errors=True)
        bare_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            proc = subprocess.run(
                argv,
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise CloneTimeoutError(f"git clone exceeded {self._timeout}s") from exc

        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip()[:4000]
            raise CloneFailedError(f"git clone exited {proc.returncode}: {stderr or 'no stderr'}")

    def _load_repo_sync(self, repo_id: str) -> Repo | None:
        async def _load() -> Repo | None:
            async with self._session_factory() as session:
                result = await session.execute(select(Repo).where(Repo.id == repo_id))
                return result.scalar_one_or_none()

        return asyncio.run(_load())

    def _set_status(
        self,
        repo_id: str,
        status: str,
        error: str | None,
        mark_synced: bool = False,
    ) -> None:
        async def _update() -> None:
            values: dict[str, object] = {
                "status": status,
                "error_message": error,
            }
            if mark_synced:
                values["last_synced_at"] = datetime.now(UTC)

            async with self._session_factory() as session:
                await session.execute(update(Repo).where(Repo.id == repo_id).values(**values))
                await session.commit()

        asyncio.run(_update())
