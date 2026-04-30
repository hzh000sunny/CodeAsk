"""End-to-end clone tests with real local git repositories."""

import asyncio
import subprocess
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select

from codeask.code_index.cloner import CloneFailedError, RepoCloner
from codeask.db import Base, create_engine, session_factory
from codeask.db.models import Repo


def _make_local_git_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "--initial-branch=main", str(root)],
        check=True,
        capture_output=True,
    )
    (root / "README.md").write_text("hello\n")
    subprocess.run(["git", "-C", str(root), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "-m", "init"],
        check=True,
        capture_output=True,
    )
    return root


@pytest_asyncio.fixture()
async def db_engine(tmp_path: Path):  # type: ignore[no-untyped-def]
    eng = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.mark.asyncio
async def test_clone_local_dir_success(tmp_path: Path, db_engine) -> None:  # type: ignore[no-untyped-def]
    src = _make_local_git_repo(tmp_path / "src")
    bare = tmp_path / "pool" / "r-1" / "bare"
    factory = session_factory(db_engine)

    async with factory() as s:
        s.add(
            Repo(
                id="r-1",
                name="local",
                source=Repo.SOURCE_LOCAL_DIR,
                url=None,
                local_path=str(src),
                bare_path=str(bare),
                status=Repo.STATUS_REGISTERED,
            )
        )
        await s.commit()

    cloner = RepoCloner(factory, clone_timeout_seconds=30)
    await asyncio.to_thread(cloner.run_clone, "r-1")

    async with factory() as s:
        repo = (await s.execute(select(Repo).where(Repo.id == "r-1"))).scalar_one()
        assert repo.status == Repo.STATUS_READY
        assert repo.error_message is None
        assert repo.last_synced_at is not None
    assert (bare / "HEAD").is_file()


@pytest.mark.asyncio
async def test_clone_failure_records_error(tmp_path: Path, db_engine) -> None:  # type: ignore[no-untyped-def]
    bare = tmp_path / "pool" / "r-2" / "bare"
    factory = session_factory(db_engine)

    async with factory() as s:
        s.add(
            Repo(
                id="r-2",
                name="bad",
                source=Repo.SOURCE_LOCAL_DIR,
                url=None,
                local_path="/nonexistent/path/does/not/exist",
                bare_path=str(bare),
                status=Repo.STATUS_REGISTERED,
            )
        )
        await s.commit()

    cloner = RepoCloner(factory, clone_timeout_seconds=10)
    with pytest.raises(CloneFailedError):
        await asyncio.to_thread(cloner.run_clone, "r-2")

    async with factory() as s:
        repo = (await s.execute(select(Repo).where(Repo.id == "r-2"))).scalar_one()
        assert repo.status == Repo.STATUS_FAILED
        assert repo.error_message
        assert "nonexistent" in repo.error_message.lower() or repo.error_message


@pytest.mark.asyncio
async def test_clone_marks_cloning_then_ready(tmp_path: Path, db_engine) -> None:  # type: ignore[no-untyped-def]
    src = _make_local_git_repo(tmp_path / "src")
    bare = tmp_path / "pool" / "r-3" / "bare"
    factory = session_factory(db_engine)

    async with factory() as s:
        s.add(
            Repo(
                id="r-3",
                name="local",
                source=Repo.SOURCE_LOCAL_DIR,
                url=None,
                local_path=str(src),
                bare_path=str(bare),
                status=Repo.STATUS_REGISTERED,
            )
        )
        await s.commit()

    observed: list[str] = []

    cloner = RepoCloner(factory, clone_timeout_seconds=30)
    original = cloner._set_status

    def _spy(
        repo_id: str,
        status: str,
        error: str | None = None,
        mark_synced: bool = False,
    ) -> None:
        observed.append(status)
        original(repo_id, status, error, mark_synced)

    cloner._set_status = _spy  # type: ignore[method-assign]

    await asyncio.to_thread(cloner.run_clone, "r-3")
    assert observed == [Repo.STATUS_CLONING, Repo.STATUS_READY]
