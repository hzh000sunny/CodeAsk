"""Message persistence and streaming helpers for session routes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from secrets import token_hex

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select

from codeask.agent.sse import SSEMultiplexer
from codeask.api.schemas.session import MessageCreate
from codeask.code_index.worktree import InvalidRefError, WorktreeError
from codeask.db.models import Repo, SessionFeature, SessionRepoBinding, SessionTurn


async def create_user_turn_and_bindings(
    request: Request,
    session_id: str,
    turn_id: str,
    payload: MessageCreate,
) -> None:
    factory = request.app.state.session_factory
    async with factory() as session:
        max_index = (
            await session.execute(
                select(func.max(SessionTurn.turn_index)).where(SessionTurn.session_id == session_id)
            )
        ).scalar_one()
        turn = SessionTurn(
            id=turn_id,
            session_id=session_id,
            turn_index=(int(max_index) + 1) if max_index is not None else 0,
            role="user",
            content=payload.content,
            evidence=None,
        )
        session.add(turn)
        for feature_id in payload.feature_ids:
            session.add(
                SessionFeature(
                    session_id=session_id,
                    feature_id=feature_id,
                    source="manual",
                )
            )
        for binding in payload.repo_bindings:
            repo = await session.get(Repo, binding.repo_id)
            if repo is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"repo {binding.repo_id!r} not found",
                )
            if repo.status != Repo.STATUS_READY:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"repo {binding.repo_id!r} status is {repo.status}",
                )
            worktree_manager = request.app.state.worktree_manager
            try:
                commit_sha = worktree_manager.resolve_ref(binding.repo_id, binding.ref)
                worktree_path = worktree_manager.ensure_worktree(
                    binding.repo_id,
                    session_id,
                    commit_sha,
                )
            except InvalidRefError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(exc),
                ) from exc
            except WorktreeError as exc:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=str(exc),
                ) from exc
            existing = await session.get(
                SessionRepoBinding,
                {
                    "session_id": session_id,
                    "repo_id": binding.repo_id,
                    "commit_sha": commit_sha,
                },
            )
            if existing is None:
                session.add(
                    SessionRepoBinding(
                        session_id=session_id,
                        repo_id=binding.repo_id,
                        commit_sha=commit_sha,
                        worktree_path=str(worktree_path),
                    )
                )
            else:
                existing.worktree_path = str(worktree_path)
        await session.commit()


async def stream_agent_response(
    request: Request,
    session_id: str,
    turn_id: str,
    content: str,
    *,
    force_code_investigation: bool,
) -> AsyncIterator[bytes]:
    orchestrator = request.app.state.agent_orchestrator
    multiplexer = SSEMultiplexer()
    assistant_chunks: list[str] = []
    completed = False
    async for event in orchestrator.run(
        session_id,
        turn_id,
        content,
        force_code_investigation=force_code_investigation,
    ):
        if event.type == "text_delta":
            delta = event.data.get("delta") or event.data.get("text")
            if isinstance(delta, str):
                assistant_chunks.append(delta)
        if event.type == "done":
            completed = True
        yield multiplexer.format(event)
    if completed:
        assistant_content = "".join(assistant_chunks).strip()
        if assistant_content:
            await persist_agent_turn(request, session_id, assistant_content)


async def persist_agent_turn(request: Request, session_id: str, content: str) -> None:
    factory = request.app.state.session_factory
    async with factory() as session:
        max_index = (
            await session.execute(
                select(func.max(SessionTurn.turn_index)).where(SessionTurn.session_id == session_id)
            )
        ).scalar_one()
        session.add(
            SessionTurn(
                id=f"turn_{token_hex(8)}",
                session_id=session_id,
                turn_index=(int(max_index) + 1) if max_index is not None else 0,
                role="agent",
                content=content,
                evidence=None,
            )
        )
        await session.commit()
