"""Worktree MCP tools for opencode."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from codeask.agent.opencode_compat.mcp.server import MCPRequestContext, MCPTool
from codeask.agent.opencode_compat.worktrees import OpenCodeWorktreeManager
from codeask.db.models import ExternalAgentSession, Repo

SessionFactory = async_sessionmaker[AsyncSession]


def build_worktree_tools(
    session_factory: SessionFactory,
    worktree_manager: OpenCodeWorktreeManager,
) -> list[MCPTool]:
    return [prepare_worktree_tool(session_factory, worktree_manager)]


def prepare_worktree_tool(
    session_factory: SessionFactory,
    worktree_manager: OpenCodeWorktreeManager,
) -> MCPTool:
    async def handler(arguments: dict[str, Any], ctx: MCPRequestContext) -> dict[str, Any]:
        repo_id = arguments.get("repo_id")
        if not isinstance(repo_id, str) or not repo_id.strip():
            raise ValueError("repo_id must be a non-empty string")
        ref = arguments.get("ref")
        ref_value = ref.strip() if isinstance(ref, str) and ref.strip() else None

        async with session_factory() as session:
            repo = await session.get(Repo, repo_id)
            if repo is None or repo.status != Repo.STATUS_READY:
                return {
                    "summary": f"repo not ready or not found: {repo_id}",
                    "error": "repo_not_ready_or_not_found",
                    "repo_id": repo_id,
                    "recovery_hint": (
                        "Call list_feature_repos or ask the user to choose a ready repository."
                    ),
                }
            external = (
                await session.execute(
                    select(ExternalAgentSession).where(
                        ExternalAgentSession.session_id == ctx.session_id,
                        ExternalAgentSession.backend_type == "opencode",
                    )
                )
            ).scalar_one_or_none()
            if external is None:
                return {
                    "summary": f"opencode session binding not found: {ctx.session_id}",
                    "error": "opencode_session_not_found",
                    "session_id": ctx.session_id,
                }
            workspace_dir = Path(external.workspace_dir)

        worktree = worktree_manager.prepare_worktree(
            repo_id=repo.id,
            session_id=ctx.session_id,
            workspace_dir=workspace_dir,
            ref=ref_value,
            display_name=repo.name,
        )
        return {
            "summary": f"已准备仓库工作区：{repo.name}",
            "repository": {
                "repo_id": repo.id,
                "name": repo.name,
                "status": repo.status,
                "source": repo.source,
                "ref": ref_value,
            },
            "workspace_relative_path": worktree.relative_path,
            "model_hint": f"Use ./{worktree.relative_path} when reading this repository.",
        }

    return MCPTool(
        name="prepare_worktree",
        description=(
            "Prepare a ready repository as a read path inside the current opencode workspace. "
            "Call this only after the model decides code reading is needed. Do not use it "
            "for ordinary conceptual/product questions when wiki or report evidence can "
            "answer the user; answer first and offer source-code verification instead."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "repo_id": {"type": "string", "description": "Repository id."},
                "ref": {
                    "type": "string",
                    "description": (
                        "Optional branch, tag, or commit. Defaults to repository default."
                    ),
                },
            },
            "required": ["repo_id"],
            "additionalProperties": False,
        },
        handler=handler,
    )
