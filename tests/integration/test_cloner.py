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


def _commit_file(repo: Path, relative_path: str, content: str, message: str) -> str:
    target = repo / relative_path
    target.write_text(content)
    subprocess.run(["git", "-C", str(repo), "add", relative_path], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", message],
        check=True,
        capture_output=True,
    )
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _show_bare_file(bare: Path, ref_path: str) -> str:
    return subprocess.run(
        ["git", "--git-dir", str(bare), "show", ref_path],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


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


@pytest.mark.asyncio
async def test_force_clone_refreshes_ready_repo(tmp_path: Path, db_engine) -> None:  # type: ignore[no-untyped-def]
    src = _make_local_git_repo(tmp_path / "src-force")
    bare = tmp_path / "pool" / "r-4" / "bare"
    factory = session_factory(db_engine)

    async with factory() as s:
        s.add(
            Repo(
                id="r-4",
                name="ready-local",
                source=Repo.SOURCE_LOCAL_DIR,
                url=None,
                local_path=str(src),
                bare_path=str(bare),
                status=Repo.STATUS_READY,
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

    await asyncio.to_thread(cloner.run_clone, "r-4", force=True)

    assert observed == [Repo.STATUS_CLONING, Repo.STATUS_READY]
    assert (bare / "HEAD").is_file()


@pytest.mark.asyncio
async def test_force_refresh_updates_existing_bare_repo_in_place(
    tmp_path: Path,
    db_engine,
) -> None:  # type: ignore[no-untyped-def]
    src = _make_local_git_repo(tmp_path / "src-refresh")
    bare = tmp_path / "pool" / "r-5" / "bare"
    factory = session_factory(db_engine)

    async with factory() as s:
        s.add(
            Repo(
                id="r-5",
                name="ready-local",
                source=Repo.SOURCE_LOCAL_DIR,
                url=None,
                local_path=str(src),
                bare_path=str(bare),
                status=Repo.STATUS_REGISTERED,
            )
        )
        await s.commit()

    cloner = RepoCloner(factory, clone_timeout_seconds=30)
    await asyncio.to_thread(cloner.run_clone, "r-5")
    marker = bare / "codeask-cache-marker"
    marker.write_text("keep existing cache directory\n")

    expected_head = _commit_file(src, "README.md", "hello\nupdated\n", "update readme")

    await asyncio.to_thread(cloner.run_clone, "r-5", force=True)

    assert marker.is_file()
    assert _show_bare_file(bare, "main:README.md") == "hello\nupdated\n"
    bare_head = subprocess.run(
        ["git", "--git-dir", str(bare), "rev-parse", "main"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert bare_head == expected_head


@pytest.mark.asyncio
async def test_refresh_all_updates_every_non_cloning_repo(
    tmp_path: Path,
    db_engine,
) -> None:  # type: ignore[no-untyped-def]
    first_src = _make_local_git_repo(tmp_path / "first")
    second_src = _make_local_git_repo(tmp_path / "second")
    first_bare = tmp_path / "pool" / "r-6" / "bare"
    second_bare = tmp_path / "pool" / "r-7" / "bare"
    factory = session_factory(db_engine)

    async with factory() as s:
        s.add_all(
            [
                Repo(
                    id="r-6",
                    name="first",
                    source=Repo.SOURCE_LOCAL_DIR,
                    url=None,
                    local_path=str(first_src),
                    bare_path=str(first_bare),
                    status=Repo.STATUS_REGISTERED,
                ),
                Repo(
                    id="r-7",
                    name="second",
                    source=Repo.SOURCE_LOCAL_DIR,
                    url=None,
                    local_path=str(second_src),
                    bare_path=str(second_bare),
                    status=Repo.STATUS_REGISTERED,
                ),
            ]
        )
        await s.commit()

    cloner = RepoCloner(factory, clone_timeout_seconds=30)
    await asyncio.to_thread(cloner.run_clone, "r-6")
    await asyncio.to_thread(cloner.run_clone, "r-7")
    _commit_file(first_src, "README.md", "first\nupdated\n", "update first")
    _commit_file(second_src, "README.md", "second\nupdated\n", "update second")

    await asyncio.to_thread(cloner.refresh_all)

    assert _show_bare_file(first_bare, "main:README.md") == "first\nupdated\n"
    assert _show_bare_file(second_bare, "main:README.md") == "second\nupdated\n"
