"""Worktree MCP tools for opencode."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from codeask.agent.opencode_compat.mcp.server import MCPRequestContext, MCPTool
from codeask.agent.opencode_compat.worktrees import OpenCodeWorktreeManager
from codeask.code_index.worktree import InvalidRefError, WorktreeError
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
        repo_id = _optional_text(arguments.get("repo_id"))
        repo_name = _optional_text(arguments.get("repo_name"))
        ref = arguments.get("ref")
        ref_value = ref.strip() if isinstance(ref, str) and ref.strip() else None
        reason = _optional_text(arguments.get("reason"))

        async with session_factory() as session:
            repo, candidates = await _resolve_repo(session, repo_id=repo_id, repo_name=repo_name)
            if candidates:
                return _ambiguous_repo_result(candidates)
            if repo is None or repo.status != Repo.STATUS_READY:
                return _repo_unavailable_result(repo, requested_repo=repo_id or repo_name)
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

        try:
            worktree = worktree_manager.prepare_worktree(
                repo_id=repo.id,
                session_id=ctx.session_id,
                workspace_dir=workspace_dir,
                ref=ref_value,
                display_name=repo.name,
            )
        except InvalidRefError as exc:
            return {
                "summary": f"invalid repository ref: {ref_value}",
                "error": "invalid_ref",
                "repository": _repo_payload(repo),
                "ref": ref_value,
                "detail": str(exc),
                "recovery_hint": (
                    "Choose another branch, tag, or commit and call prepare_worktree again."
                ),
            }
        except WorktreeError as exc:
            return _worktree_error_result(repo, exc)

        return {
            "summary": f"已准备仓库工作区：{repo.name}",
            "repository": {**_repo_payload(repo), "ref": ref_value},
            "workspace_relative_path": worktree.relative_path,
            "model_hint": f"Use ./{worktree.relative_path} when reading this repository.",
            "audit": {"reason": reason},
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
                "repo_name": {
                    "type": "string",
                    "description": "Repository name when repo_id is unknown.",
                },
                "ref": {
                    "type": "string",
                    "description": (
                        "Optional branch, tag, or commit. Defaults to repository default."
                    ),
                },
                "reason": {
                    "type": "string",
                    "description": "Short audit reason for why code access is needed.",
                },
            },
            "additionalProperties": False,
        },
        handler=handler,
    )


async def _resolve_repo(
    session: AsyncSession,
    *,
    repo_id: str | None,
    repo_name: str | None,
) -> tuple[Repo | None, list[dict[str, Any]]]:
    if repo_id is not None:
        return await session.get(Repo, repo_id), []
    if repo_name is None:
        return None, []

    pattern = f"%{repo_name.lower()}%"
    rows = (
        await session.execute(
            select(Repo)
            .where(or_(Repo.name == repo_name, func.lower(Repo.name).like(pattern)))
            .order_by(Repo.name.asc(), Repo.id.asc())
            .limit(10)
        )
    ).scalars()
    matches = list(rows)
    exact = [repo for repo in matches if repo.name == repo_name]
    if len(exact) == 1:
        return exact[0], []
    if len(matches) == 1:
        return matches[0], []
    return None, [_repo_payload(repo) for repo in matches]


def _ambiguous_repo_result(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "summary": f"repository is ambiguous: {len(candidates)} candidates",
        "error": "ambiguous_repo",
        "candidates": candidates,
        "recovery_hint": "Call prepare_worktree again with one candidate repo_id.",
    }


def _repo_unavailable_result(repo: Repo | None, *, requested_repo: str | None) -> dict[str, Any]:
    if repo is None:
        return {
            "summary": f"repo not ready or not found: {requested_repo or 'missing'}",
            "error": "repo_not_ready",
            "repository": {
                "repo_id": requested_repo,
                "status": "missing",
                "error_message": None,
            },
            "recovery_hint": "Call list_feature_repos and choose a ready repository.",
        }

    error = "repo_clone_failed" if repo.status == Repo.STATUS_FAILED else "repo_not_ready"
    return {
        "summary": f"repo is not ready: {repo.name}",
        "error": error,
        "repository": _repo_payload(repo),
        "recovery_hint": (
            "Repository sync failed; inspect its status and error before retrying."
            if error == "repo_clone_failed"
            else "Wait until the repository becomes ready or choose another ready repository."
        ),
    }


def _worktree_error_result(repo: Repo, exc: WorktreeError) -> dict[str, Any]:
    detail = str(exc)
    error = "bare_repo_missing" if "bare repo missing" in detail else "worktree_prepare_failed"
    return {
        "summary": f"failed to prepare repository worktree: {repo.name}",
        "error": error,
        "repository": _repo_payload(repo),
        "detail": detail,
        "recovery_hint": (
            "Repository storage is missing; refresh or resync the repository before retrying."
            if error == "bare_repo_missing"
            else "Inspect the repository state and retry with a valid ready repository."
        ),
    }


def _repo_payload(repo: Repo) -> dict[str, Any]:
    return {
        "repo_id": repo.id,
        "name": repo.name,
        "status": repo.status,
        "source": repo.source,
        "error_message": repo.error_message,
        "last_synced_at": repo.last_synced_at.isoformat() if repo.last_synced_at else None,
    }


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None
