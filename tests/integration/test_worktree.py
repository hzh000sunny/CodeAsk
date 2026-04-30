"""WorktreeManager tests against a real bare git repo."""

import subprocess
from pathlib import Path

import pytest

from codeask.code_index.worktree import InvalidRefError, WorktreeError, WorktreeManager


def _bootstrap_bare(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    subprocess.run(
        ["git", "init", "--initial-branch=main", str(src)],
        check=True,
        capture_output=True,
    )
    (src / "f.py").write_text("print('hi')\n")
    subprocess.run(["git", "-C", str(src), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(src), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(src), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(src), "commit", "-m", "init"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(src), "tag", "v1"],
        check=True,
        capture_output=True,
    )
    bare = tmp_path / "pool" / "r" / "bare"
    bare.parent.mkdir(parents=True)
    subprocess.run(
        ["git", "clone", "--bare", "--local", str(src), str(bare)],
        check=True,
        capture_output=True,
    )
    return bare


def test_resolve_default_ref(tmp_path: Path) -> None:
    _bootstrap_bare(tmp_path)
    mgr = WorktreeManager(repo_root=tmp_path / "pool")
    sha = mgr.resolve_ref("r", None)
    assert len(sha) == 40


def test_resolve_branch_and_tag(tmp_path: Path) -> None:
    _bootstrap_bare(tmp_path)
    mgr = WorktreeManager(repo_root=tmp_path / "pool")
    sha_main = mgr.resolve_ref("r", "main")
    sha_tag = mgr.resolve_ref("r", "v1")
    assert sha_main == sha_tag
    assert mgr.resolve_ref("r", sha_main) == sha_main


def test_resolve_invalid_ref_raises(tmp_path: Path) -> None:
    _bootstrap_bare(tmp_path)
    mgr = WorktreeManager(repo_root=tmp_path / "pool")
    with pytest.raises(InvalidRefError):
        mgr.resolve_ref("r", "no-such-branch")


def test_ensure_and_destroy_worktree(tmp_path: Path) -> None:
    _bootstrap_bare(tmp_path)
    mgr = WorktreeManager(repo_root=tmp_path / "pool")

    path = mgr.ensure_worktree("r", "sess-1", "main")
    assert path.is_dir()
    assert (path / "f.py").is_file()

    path2 = mgr.ensure_worktree("r", "sess-1", "main")
    assert path2 == path

    paths = mgr.list_worktrees("r")
    assert path.resolve() in {p.resolve() for p in paths}

    mgr.destroy_worktree("r", "sess-1")
    assert not path.exists()


def test_ensure_worktree_rejects_unsafe_session_id(tmp_path: Path) -> None:
    _bootstrap_bare(tmp_path)
    mgr = WorktreeManager(repo_root=tmp_path / "pool")
    with pytest.raises(WorktreeError):
        mgr.ensure_worktree("r", "../escape", "main")
