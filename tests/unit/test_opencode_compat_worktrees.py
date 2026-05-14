from __future__ import annotations

from pathlib import Path

from codeask.agent.opencode_compat.worktrees import OpenCodeWorktreeManager


class FakeWorktreeManager:
    def __init__(self, target: Path) -> None:
        self.target = target
        self.ensure_calls: list[tuple[str, str, str | None]] = []
        self.destroy_calls: list[tuple[str, str]] = []

    def ensure_worktree(self, repo_id: str, session_id: str, ref: str | None) -> Path:
        self.ensure_calls.append((repo_id, session_id, ref))
        self.target.mkdir(parents=True, exist_ok=True)
        return self.target

    def destroy_worktree(self, repo_id: str, session_id: str) -> None:
        self.destroy_calls.append((repo_id, session_id))


def test_prepare_worktree_exposes_relative_symlink(tmp_path: Path) -> None:
    fake = FakeWorktreeManager(tmp_path / "real-worktree")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    manager = OpenCodeWorktreeManager(worktree_manager=fake)

    result = manager.prepare_worktree(
        repo_id="repo_1",
        session_id="sess_1",
        workspace_dir=workspace,
        ref="HEAD",
        display_name="Anything LLM",
    )

    assert fake.ensure_calls == [("repo_1", "sess_1", "HEAD")]
    assert result.repo_id == "repo_1"
    assert result.absolute_path == fake.target
    assert result.workspace_path == workspace / "repos" / "Anything_LLM"
    assert result.relative_path == "repos/Anything_LLM"
    assert result.workspace_path.is_symlink()
    assert result.workspace_path.resolve() == fake.target.resolve()


def test_cleanup_worktree_delegates_to_existing_manager(tmp_path: Path) -> None:
    fake = FakeWorktreeManager(tmp_path / "real-worktree")
    manager = OpenCodeWorktreeManager(worktree_manager=fake)

    manager.cleanup_worktree(repo_id="repo_1", session_id="sess_1")

    assert fake.destroy_calls == [("repo_1", "sess_1")]
