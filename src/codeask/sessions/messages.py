"""Message persistence and streaming helpers for session routes."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from secrets import token_hex
from typing import Any

from fastapi import HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import delete, func, select

from codeask.agent.chat_runtime.context import SessionMessage
from codeask.agent.sse import SSEMultiplexer
from codeask.api.schemas.session import MessageCreate
from codeask.code_index.worktree import InvalidRefError, WorktreeError
from codeask.db.models import (
    AgentTrace,
    Repo,
    SessionAttachment,
    SessionConversationSummary,
    SessionFeature,
    SessionRepoBinding,
    SessionTurn,
)
from codeask.sessions.title_generation import maybe_generate_session_title


def _event_data_dict(data: object) -> dict[str, object]:
    if isinstance(data, BaseModel):
        return data.model_dump(mode="json")
    if isinstance(data, dict):
        return data
    return {}


async def create_user_turn_and_bindings(
    request: Request,
    session_id: str,
    turn_id: str,
    payload: MessageCreate,
) -> None:
    factory = request.app.state.session_factory
    async with factory() as session:
        existing_turn = await session.get(SessionTurn, turn_id)
        if existing_turn is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"turn {turn_id!r} already exists",
            )
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
    runtime = request.app.state.chat_runtime
    multiplexer = SSEMultiplexer()
    assistant_chunks: list[str] = []
    completed = False
    (
        history,
        tool_action_summary,
        attachments,
        conversation_summary,
    ) = await load_chat_runtime_context(
        request,
        session_id,
        current_turn_id=turn_id,
    )
    try:
        async for event in runtime.run(
            session_id,
            turn_id,
            content,
            subject_id=request.state.subject_id,
            history=history,
            attachments=attachments,
            conversation_summary=conversation_summary,
            tool_action_summary=tool_action_summary,
        ):
            await persist_runtime_audit_payload(
                request,
                session_id,
                turn_id,
                event.type,
                event.data,
            )
            event_data = _event_data_dict(event.data)
            await persist_runtime_event_trace(request, session_id, turn_id, event.type, event_data)
            if event.type == "text_delta":
                delta = event_data.get("delta") or event_data.get("text")
                if isinstance(delta, str):
                    assistant_chunks.append(delta)
            if event.type == "done":
                completed = True
            yield multiplexer.format(
                event.model_copy(update={"data": {**event_data, "turn_id": turn_id}})
            )
    except asyncio.CancelledError:
        await rollback_session_turn(request.app.state.session_factory, session_id, turn_id)
        raise
    if completed:
        assistant_content = "".join(assistant_chunks).strip()
        if assistant_content:
            await persist_agent_turn(
                request,
                session_id,
                assistant_content,
                parent_turn_id=turn_id,
            )
            asyncio.create_task(
                maybe_generate_session_title(
                    request.app.state.session_factory,
                    request.app.state.llm_gateway,
                    session_id=session_id,
                    subject_id=request.state.subject_id,
                    user_content=content,
                    assistant_content=assistant_content,
                )
            )


async def persist_runtime_audit_payload(
    request: Request,
    session_id: str,
    turn_id: str,
    event_type: str,
    data: object,
) -> None:
    if event_type != "tool_result":
        return
    raw_payload = getattr(data, "audit_raw_result", None)
    if not isinstance(raw_payload, dict):
        return
    if not await session_turn_exists(request.app.state.session_factory, session_id, turn_id):
        return
    trace_logger = request.app.state.trace_logger
    await trace_logger.log(
        session_id,
        turn_id,
        "chat_runtime",
        "tool_result_raw",
        raw_payload,
    )


async def rollback_session_turn(
    session_factory: Any,
    session_id: str,
    turn_id: str,
) -> None:
    async with session_factory() as session:
        await session.execute(
            delete(AgentTrace).where(
                AgentTrace.session_id == session_id,
                AgentTrace.turn_id == turn_id,
            )
        )
        await session.execute(
            delete(SessionTurn).where(
                SessionTurn.session_id == session_id,
                SessionTurn.id == turn_id,
            )
        )
        await session.commit()


async def load_chat_runtime_context(
    request: Request,
    session_id: str,
    *,
    current_turn_id: str,
    max_history_messages: int = 12,
    max_tool_events: int = 12,
) -> tuple[list[SessionMessage], str | None, list[dict[str, Any]], str | None]:
    factory = request.app.state.session_factory
    async with factory() as session:
        summary_row = await _ensure_conversation_summary(
            session,
            session_id=session_id,
            current_turn_id=current_turn_id,
            keep_recent_messages=max_history_messages,
        )
        turn_query = (
            select(SessionTurn)
            .where(
                SessionTurn.session_id == session_id,
                SessionTurn.id != current_turn_id,
            )
        )
        if summary_row is not None:
            turn_query = turn_query.where(
                SessionTurn.turn_index > summary_row.covered_turn_index
            )
        turn_rows = (
            (
                await session.execute(
                    turn_query
                    .order_by(SessionTurn.turn_index.desc(), SessionTurn.created_at.desc())
                    .limit(max_history_messages)
                )
            )
            .scalars()
            .all()
        )
        trace_rows = (
            (
                await session.execute(
                    select(AgentTrace)
                    .where(
                        AgentTrace.session_id == session_id,
                        AgentTrace.turn_id != current_turn_id,
                        AgentTrace.event_type.in_(["tool_call", "tool_result"]),
                    )
                    .order_by(AgentTrace.created_at.desc(), AgentTrace.id.desc())
                    .limit(max_tool_events)
                )
            )
            .scalars()
            .all()
        )
        attachment_rows = (
            (
                await session.execute(
                    select(SessionAttachment)
                    .where(SessionAttachment.session_id == session_id)
                    .order_by(SessionAttachment.created_at.asc(), SessionAttachment.id.asc())
                )
            )
            .scalars()
            .all()
        )
    history = [
        SessionMessage(
            role="assistant" if row.role == "agent" else "user",
            content=row.content,
        )
        for row in reversed(turn_rows)
    ]
    tool_action_summary = summarize_tool_actions(list(reversed(trace_rows)))
    attachments = [_attachment_context(row) for row in attachment_rows]
    conversation_summary = summary_row.summary if summary_row is not None else None
    return history, tool_action_summary, attachments, conversation_summary


async def _ensure_conversation_summary(
    session: Any,
    *,
    session_id: str,
    current_turn_id: str,
    keep_recent_messages: int,
) -> SessionConversationSummary | None:
    turn_rows = (
        (
            await session.execute(
                select(SessionTurn)
                .where(
                    SessionTurn.session_id == session_id,
                    SessionTurn.id != current_turn_id,
                )
                .order_by(SessionTurn.turn_index.asc(), SessionTurn.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    if len(turn_rows) <= keep_recent_messages:
        return await session.get(SessionConversationSummary, session_id)

    covered_rows = list(turn_rows[: -keep_recent_messages])
    if not covered_rows:
        return await session.get(SessionConversationSummary, session_id)
    covered_turn_index = max(row.turn_index for row in covered_rows)

    summary_row = await session.get(SessionConversationSummary, session_id)
    if (
        summary_row is not None
        and summary_row.consecutive_failures >= 3
        and summary_row.covered_turn_index >= 0
    ):
        return summary_row
    if (
        summary_row is not None
        and summary_row.covered_turn_index >= covered_turn_index
    ):
        return summary_row

    trace_rows = await _load_summary_trace_rows(
        session,
        session_id=session_id,
        covered_turn_ids=[row.id for row in covered_rows],
    )
    try:
        summary_text = _build_extractive_conversation_summary(
            previous_summary=summary_row.summary if summary_row is not None else None,
            covered_rows=covered_rows,
            trace_rows=trace_rows,
            covered_turn_index=covered_turn_index,
        )
    except Exception:
        if summary_row is not None:
            summary_row.consecutive_failures = min(
                summary_row.consecutive_failures + 1,
                3,
            )
            await session.commit()
            return summary_row
        return None
    if summary_row is None:
        summary_row = SessionConversationSummary(
            session_id=session_id,
            summary=summary_text,
            covered_turn_index=covered_turn_index,
            covered_turn_count=len(covered_rows),
            covered_trace_count=len(trace_rows),
            consecutive_failures=0,
        )
        session.add(summary_row)
    else:
        summary_row.summary = summary_text
        summary_row.covered_turn_index = covered_turn_index
        summary_row.covered_turn_count = len(covered_rows)
        summary_row.covered_trace_count = len(trace_rows)
        summary_row.consecutive_failures = 0
    await session.commit()
    return summary_row


async def _load_summary_trace_rows(
    session: Any,
    *,
    session_id: str,
    covered_turn_ids: list[str],
    limit: int = 30,
) -> list[AgentTrace]:
    if not covered_turn_ids:
        return []
    rows = (
        (
            await session.execute(
                select(AgentTrace)
                .where(
                    AgentTrace.session_id == session_id,
                    AgentTrace.turn_id.in_(covered_turn_ids),
                    AgentTrace.event_type.in_(["tool_call", "tool_result"]),
                )
                .order_by(AgentTrace.created_at.asc(), AgentTrace.id.asc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


def _build_extractive_conversation_summary(
    *,
    previous_summary: str | None,
    covered_rows: list[SessionTurn],
    trace_rows: list[AgentTrace],
    covered_turn_index: int,
) -> str:
    lines = [
        f"覆盖 turn_index <= {covered_turn_index}。",
        "摘要类型：extractive；事实来自历史会话 turn 和工具行动摘要。",
    ]
    if previous_summary:
        lines.extend(["", "上一版摘要：", _truncate_summary(previous_summary, 1800)])
    if covered_rows:
        lines.extend(["", "较早对话要点："])
        for row in covered_rows[-8:]:
            label = "用户" if row.role == "user" else "CodeAsk"
            lines.append(
                f"- turn_index={row.turn_index} {label}: "
                f"{_truncate_summary(row.content, 360)}"
            )
    tool_summary = summarize_tool_actions(trace_rows)
    if tool_summary:
        lines.extend(["", "较早工具行动事实：", _truncate_summary(tool_summary, 1800)])
    lines.extend(
        [
            "",
            "使用要求：继续对话时必须把这段摘要视为历史上下文；",
            "如果用户追问刚刚、上一轮、是否查过代码或用了什么证据，",
            "需要结合本摘要和最近 turns 回答，不能回答成第一次交流。",
        ]
    )
    return "\n".join(lines)


def _truncate_summary(text: str, limit: int) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 15)] + "...[truncated]"


def _attachment_context(row: SessionAttachment) -> dict[str, Any]:
    return {
        "id": row.id,
        "attachment_id": row.id,
        "display_name": row.display_name,
        "original_filename": row.original_filename,
        "aliases": row.aliases,
        "reference_names": row.reference_names,
        "description": row.description,
        "kind": row.kind,
        "mime_type": row.mime_type,
        "size_bytes": row.size_bytes,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def summarize_tool_actions(rows: list[AgentTrace]) -> str | None:
    if not rows:
        return None
    calls: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in rows:
        payload = row.payload if isinstance(row.payload, dict) else {}
        call_id = _trace_call_id(payload)
        if not call_id:
            continue
        if call_id not in calls:
            calls[call_id] = {}
            order.append(call_id)
        if row.event_type == "tool_call":
            calls[call_id]["call"] = payload
        elif row.event_type == "tool_result":
            calls[call_id]["result"] = payload

    lines: list[str] = []
    for call_id in order:
        item = calls[call_id]
        call = item.get("call") or {}
        result = item.get("result") or {}
        tool_name = _text(call.get("tool_name") or result.get("tool_name"))
        if not tool_name:
            continue
        arguments = call.get("arguments_summary")
        summary = _text(result.get("summary"))
        ok = result.get("ok")
        status = "成功" if ok is True else "失败" if ok is False else "已调用"
        line = f"- {tool_name}：{status}"
        if isinstance(arguments, dict) and arguments:
            line += f"，参数 {arguments}"
        if summary:
            line += f"，结果：{summary}"
        line += f"，源码读取：{_code_read_label(tool_name)}"
        lines.append(line)
    return "\n".join(lines) if lines else None


def _trace_call_id(payload: dict[str, Any]) -> str | None:
    value = payload.get("tool_call_id") or payload.get("id")
    return value if isinstance(value, str) and value.strip() else None


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _code_read_label(tool_name: str) -> str:
    if tool_name == "read_code_file":
        return "是"
    if tool_name in {"list_code_repos", "search_code", "inspect_repo_tree", "list_code_paths"}:
        return "否"
    return "不适用"


async def persist_runtime_event_trace(
    request: Request,
    session_id: str,
    turn_id: str,
    event_type: str,
    data: object,
) -> None:
    if event_type in {"text_delta", "done"}:
        return
    event_data = _event_data_dict(data)
    if event_type == "runtime_state" and event_data.get("update_reason") == "assistant_delta":
        return
    if not await session_turn_exists(request.app.state.session_factory, session_id, turn_id):
        return
    trace_logger = request.app.state.trace_logger
    await trace_logger.log(
        session_id,
        turn_id,
        "chat_runtime",
        event_type,
        event_data,
    )


async def stream_legacy_orchestrator_response(
    request: Request,
    session_id: str,
    turn_id: str,
    content: str,
    *,
    force_code_investigation: bool,
) -> AsyncIterator[bytes]:
    orchestrator = request.app.state.agent_orchestrator
    multiplexer = SSEMultiplexer()
    async for event in orchestrator.run(
        session_id,
        turn_id,
        content,
        force_code_investigation=force_code_investigation,
    ):
        yield multiplexer.format(event)


async def persist_agent_turn(
    request: Request,
    session_id: str,
    content: str,
    *,
    parent_turn_id: str | None = None,
) -> None:
    factory = request.app.state.session_factory
    async with factory() as session:
        if parent_turn_id is not None:
            parent_turn = await session.get(SessionTurn, parent_turn_id)
            if parent_turn is None or parent_turn.session_id != session_id:
                return
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


async def session_turn_exists(
    session_factory: Any,
    session_id: str,
    turn_id: str,
) -> bool:
    async with session_factory() as session:
        row = await session.get(SessionTurn, turn_id)
        return row is not None and row.session_id == session_id
