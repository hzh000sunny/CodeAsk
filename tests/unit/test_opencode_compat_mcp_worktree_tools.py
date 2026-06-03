from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from codeask.agent.opencode_compat.mcp.server import MCPRequestContext, MCPTool
from codeask.agent.opencode_compat.mcp.tools.worktrees import prepare_worktree_tool
from codeask.agent.opencode_compat.worktrees import OpenCodeWorktreeManager
from codeask.db import session_factory
from codeask.db.base import Base
from codeask.db.models import ExternalAgentSession, Repo, Session

_CTX = MCPRequestContext(session_id="sess_worktree")


async def _call_tool_dict(tool: MCPTool, arguments: dict[str, object]) -> dict[str, Any]:
    result = await tool.handler(arguments, _CTX)
    assert isinstance(result, dict)
    return result


class FakeWorktreeManager:
    def __init__(self, target: Path) -> None:
        self.target = target
        self.calls: list[tuple[str, str, str | None]] = []
        self.error: Exception | None = None

    def ensure_worktree(self, repo_id: str, session_id: str, ref: str | None) -> Path:
        self.calls.append((repo_id, session_id, ref))
        if self.error is not None:
            raise self.error
        self.target.mkdir(parents=True, exist_ok=True)
        return self.target

    def destroy_worktree(self, repo_id: str, session_id: str) -> None:
        raise NotImplementedError


@pytest.fixture()
async def db_factory(tmp_path: Path):  # type: ignore[no-untyped-def]
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'worktree-tool.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = session_factory(engine)
    workspace = tmp_path / "session" / "workspace"
    workspace.mkdir(parents=True)
    async with factory() as session:
        session.add(
            Session(
                id="sess_worktree",
                title="代码会话",
                created_by_subject_id="admin",
                status="active",
            )
        )
        session.add(
            ExternalAgentSession(
                id="ext_1",
                session_id="sess_worktree",
                backend_type="opencode",
                external_session_key="ses_open",
                session_dir=str(tmp_path / "session"),
                workspace_dir=str(workspace),
                server_url="http://127.0.0.1:4100",
                port=4100,
                pid=123,
                status="active",
                config_hash="hash",
                config_json={},
            )
        )
        session.add(
            Repo(
                id="repo_1",
                name="anything-llm",
                source="local_dir",
                local_path="/tmp/anything",
                bare_path="/tmp/bare/anything",
                status=Repo.STATUS_READY,
            )
        )
        session.add(
            Repo(
                id="repo_2",
                name="anything-llm-fork",
                source="git",
                url="https://example.test/anything-llm.git",
                bare_path="/tmp/bare/anything-fork",
                status=Repo.STATUS_READY,
            )
        )
        session.add(
            Repo(
                id="repo_failed",
                name="broken-repo",
                source="git",
                url="https://example.test/broken.git",
                bare_path="/tmp/bare/broken",
                status=Repo.STATUS_FAILED,
                error_message="clone failed",
            )
        )
        await session.commit()
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_prepare_worktree_tool_exposes_repo_path(db_factory, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    fake = FakeWorktreeManager(tmp_path / "real-worktree")
    opencode_worktrees = OpenCodeWorktreeManager(worktree_manager=fake)

    result = await _call_tool_dict(
        prepare_worktree_tool(db_factory, opencode_worktrees),
        {"repo_id": "repo_1", "ref": "HEAD"},
    )

    assert fake.calls == [("repo_1", "sess_worktree", "HEAD")]
    assert result["repository"]["repo_id"] == "repo_1"
    assert result["workspace_relative_path"] == "repos/anything-llm"
    assert result["model_hint"] == "Use ./repos/anything-llm when reading this repository."


@pytest.mark.asyncio
async def test_prepare_worktree_tool_accepts_unique_repo_name(db_factory, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    fake = FakeWorktreeManager(tmp_path / "real-worktree")
    opencode_worktrees = OpenCodeWorktreeManager(worktree_manager=fake)

    result = await _call_tool_dict(
        prepare_worktree_tool(db_factory, opencode_worktrees),
        {"repo_name": "anything-llm-fork", "reason": "用户要求查看源码实现"},
    )

    assert fake.calls == [("repo_2", "sess_worktree", None)]
    assert result["repository"]["repo_id"] == "repo_2"
    assert result["audit"]["reason"] == "用户要求查看源码实现"


@pytest.mark.asyncio
async def test_prepare_worktree_tool_returns_candidates_for_ambiguous_name(
    db_factory,
    tmp_path: Path,
) -> None:  # type: ignore[no-untyped-def]
    fake = FakeWorktreeManager(tmp_path / "real-worktree")
    opencode_worktrees = OpenCodeWorktreeManager(worktree_manager=fake)

    result = await _call_tool_dict(
        prepare_worktree_tool(db_factory, opencode_worktrees),
        {"repo_name": "anything"},
    )

    assert result["error"] == "ambiguous_repo"
    assert [candidate["repo_id"] for candidate in result["candidates"]] == ["repo_1", "repo_2"]
    assert fake.calls == []


@pytest.mark.asyncio
async def test_prepare_worktree_tool_rejects_unavailable_repo(db_factory, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    fake = FakeWorktreeManager(tmp_path / "real-worktree")
    opencode_worktrees = OpenCodeWorktreeManager(worktree_manager=fake)

    result = await _call_tool_dict(
        prepare_worktree_tool(db_factory, opencode_worktrees),
        {"repo_id": "missing"},
    )

    assert result["error"] == "repo_not_ready"
    assert result["repository"]["status"] == "missing"
    assert fake.calls == []


@pytest.mark.asyncio
async def test_prepare_worktree_tool_maps_worktree_errors(db_factory, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from codeask.code_index.worktree import InvalidRefError, WorktreeError

    fake = FakeWorktreeManager(tmp_path / "real-worktree")
    fake.error = InvalidRefError("ref 'bad' does not resolve")
    opencode_worktrees = OpenCodeWorktreeManager(worktree_manager=fake)

    invalid = await _call_tool_dict(
        prepare_worktree_tool(db_factory, opencode_worktrees),
        {"repo_id": "repo_1", "ref": "bad"},
    )
    assert invalid["error"] == "invalid_ref"

    fake.error = WorktreeError("bare repo missing: /tmp/bare/anything")
    missing_bare = await _call_tool_dict(
        prepare_worktree_tool(db_factory, opencode_worktrees),
        {"repo_id": "repo_1"},
    )
    assert missing_bare["error"] == "bare_repo_missing"


def test_prepare_worktree_schema_supports_name_ref_and_reason(db_factory, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    tool = prepare_worktree_tool(
        db_factory,
        OpenCodeWorktreeManager(worktree_manager=FakeWorktreeManager(tmp_path / "real")),
    )

    assert set(tool.input_schema["properties"]) == {"repo_id", "repo_name", "ref", "reason"}
    assert "required" not in tool.input_schema
