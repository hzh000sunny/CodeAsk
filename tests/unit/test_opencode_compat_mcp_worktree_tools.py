from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from codeask.agent.opencode_compat.mcp.server import MCPRequestContext
from codeask.agent.opencode_compat.mcp.tools.worktrees import prepare_worktree_tool
from codeask.agent.opencode_compat.worktrees import OpenCodeWorktreeManager
from codeask.db import session_factory
from codeask.db.base import Base
from codeask.db.models import ExternalAgentSession, Repo, Session

_CTX = MCPRequestContext(session_id="sess_worktree")


class FakeWorktreeManager:
    def __init__(self, target: Path) -> None:
        self.target = target
        self.calls: list[tuple[str, str, str | None]] = []

    def ensure_worktree(self, repo_id: str, session_id: str, ref: str | None) -> Path:
        self.calls.append((repo_id, session_id, ref))
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
        await session.commit()
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_prepare_worktree_tool_exposes_repo_path(db_factory, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    fake = FakeWorktreeManager(tmp_path / "real-worktree")
    opencode_worktrees = OpenCodeWorktreeManager(worktree_manager=fake)

    result = await prepare_worktree_tool(db_factory, opencode_worktrees).handler(
        {"repo_id": "repo_1", "ref": "HEAD"},
        _CTX,
    )

    assert fake.calls == [("repo_1", "sess_worktree", "HEAD")]
    assert result["repository"]["repo_id"] == "repo_1"
    assert result["workspace_relative_path"] == "repos/anything-llm"
    assert result["model_hint"] == "Use ./repos/anything-llm when reading this repository."


@pytest.mark.asyncio
async def test_prepare_worktree_tool_rejects_unavailable_repo(db_factory, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    fake = FakeWorktreeManager(tmp_path / "real-worktree")
    opencode_worktrees = OpenCodeWorktreeManager(worktree_manager=fake)

    result = await prepare_worktree_tool(db_factory, opencode_worktrees).handler(
        {"repo_id": "missing"},
        _CTX,
    )

    assert result["error"] == "repo_not_ready_or_not_found"
    assert fake.calls == []
