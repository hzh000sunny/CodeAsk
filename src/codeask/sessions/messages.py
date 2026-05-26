"""Message persistence and streaming helpers for session routes."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from secrets import token_hex
from typing import Any

import structlog
from fastapi import HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import delete, func, select

from codeask.agent.chat_runtime.context import SessionMessage
from codeask.agent.chat_runtime.events import ChatRuntimeEvent
from codeask.agent.opencode_compat.process import OpenCodeProcessError
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
from codeask.llm.gateway import LLMConfigSelection
from codeask.llm.types import LLMEvent
from codeask.sessions.title_generation import maybe_generate_session_title
from codeask.sessions.trace_redaction import redact_trace_payload_for_frontend

log = structlog.get_logger("codeask.sessions.messages")


def _event_data_dict(data: object) -> dict[str, object]:
    if isinstance(data, BaseModel):
        return data.model_dump(mode="json")
    if isinstance(data, dict):
        return data
    return {}


def _frontend_event(
    event: ChatRuntimeEvent,
    event_data: dict[str, object],
    *,
    session_id: str,
    turn_id: str,
) -> ChatRuntimeEvent:
    frontend_data: dict[str, object]
    if event.type == "text_delta":
        frontend_data = event_data
    else:
        frontend_data = redact_trace_payload_for_frontend(
            event_data,
            session_id=session_id,
        )
    return event.model_copy(
        update={
            "data": {
                **frontend_data,
                "turn_id": turn_id,
            }
        }
    )


class AgentTurnTiming:
    """Attach lightweight timing diagnostics to each agent event."""

    _INTERNAL_OPENCODE_ACTIONS = {
        "opencode_prompt_async_start",
        "opencode_prompt_async_done",
        "opencode_event_stream_open",
    }

    def __init__(self) -> None:
        now = time.perf_counter()
        self._started_at = now
        self._previous_event_at = now
        self._event_index = 0
        self._model_send_started_at: float | None = None
        self._model_send_done_at: float | None = None
        self._event_stream_open_at: float | None = None
        self._first_backend_event_at: float | None = None
        self._first_response_at: float | None = None
        self._response_observed = False

    def annotate(self, event_type: str, data: dict[str, object]) -> dict[str, object]:
        now = time.perf_counter()
        self._event_index += 1
        action = data.get("action")
        action = action if isinstance(action, str) else ""

        if action == "opencode_prompt_async_start" and self._model_send_started_at is None:
            self._model_send_started_at = now
        elif action == "opencode_prompt_async_done" and self._model_send_done_at is None:
            self._model_send_done_at = now
        elif action == "opencode_event_stream_open" and self._event_stream_open_at is None:
            self._event_stream_open_at = now
        elif (
            self._event_stream_open_at is not None
            and self._first_backend_event_at is None
            and action not in self._INTERNAL_OPENCODE_ACTIONS
        ):
            self._first_backend_event_at = now

        if self._is_response_event(event_type, data) and self._first_response_at is None:
            self._first_response_at = now
            self._response_observed = True

        timing: dict[str, object] = {
            "event_index": self._event_index,
            "turn_elapsed_ms": _elapsed_ms(self._started_at, now),
            "since_previous_event_ms": _elapsed_ms(self._previous_event_at, now),
            "response_observed": self._response_observed,
        }
        if self._model_send_started_at is not None:
            timing["model_send_started_elapsed_ms"] = _elapsed_ms(
                self._started_at,
                self._model_send_started_at,
            )
        if self._model_send_done_at is not None:
            timing["model_send_done_elapsed_ms"] = _elapsed_ms(
                self._started_at,
                self._model_send_done_at,
            )
        if self._model_send_started_at is not None and self._model_send_done_at is not None:
            timing["model_send_duration_ms"] = _elapsed_ms(
                self._model_send_started_at,
                self._model_send_done_at,
            )
        if self._event_stream_open_at is not None:
            timing["event_stream_open_elapsed_ms"] = _elapsed_ms(
                self._started_at,
                self._event_stream_open_at,
            )
        if self._event_stream_open_at is not None and self._first_backend_event_at is not None:
            timing["first_backend_event_wait_ms"] = _elapsed_ms(
                self._event_stream_open_at,
                self._first_backend_event_at,
            )
        if self._model_send_done_at is not None and self._first_response_at is not None:
            timing["first_response_wait_ms"] = _elapsed_ms(
                self._model_send_done_at,
                self._first_response_at,
            )
        if event_type in {"done", "error"}:
            timing["total_elapsed_ms"] = _elapsed_ms(self._started_at, now)

        existing = data.get("timing")
        if isinstance(existing, dict):
            timing = {**existing, **timing}
        annotated = {**data, "timing": timing}
        self._previous_event_at = now
        return annotated

    @staticmethod
    def _is_response_event(event_type: str, data: dict[str, object]) -> bool:
        if event_type == "text_delta":
            delta = data.get("delta") or data.get("text")
            return isinstance(delta, str) and bool(delta)
        return event_type in {"tool_call", "tool_result", "reasoning_observed"}


def _elapsed_ms(start: float, end: float) -> float:
    return round(max(0.0, end - start) * 1000, 2)


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
    runtime_llm_config: dict[str, Any] | None = None,
    timing: AgentTurnTiming | None = None,
) -> AsyncIterator[bytes]:
    timing = timing or AgentTurnTiming()
    if getattr(request.app.state.settings, "agent_backend", "opencode") == "opencode":
        async for chunk in stream_opencode_response(
            request,
            session_id,
            turn_id,
            content,
            runtime_llm_config=runtime_llm_config,
            timing=timing,
        ):
            yield chunk
        return

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
            runtime_llm_config=runtime_llm_config,
        ):
            await persist_runtime_audit_payload(
                request,
                session_id,
                turn_id,
                event.type,
                event.data,
            )
            event_data = timing.annotate(event.type, _event_data_dict(event.data))
            await persist_runtime_event_trace(request, session_id, turn_id, event.type, event_data)
            if event.type == "text_delta":
                delta = event_data.get("delta") or event_data.get("text")
                if isinstance(delta, str):
                    assistant_chunks.append(delta)
            if event.type == "done":
                completed = True
            yield multiplexer.format(
                _frontend_event(event, event_data, session_id=session_id, turn_id=turn_id)
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


async def stream_opencode_response(
    request: Request,
    session_id: str,
    turn_id: str,
    content: str,
    *,
    runtime_llm_config: dict[str, Any] | None = None,
    timing: AgentTurnTiming | None = None,
) -> AsyncIterator[bytes]:
    compat = request.app.state.opencode_compat
    multiplexer = SSEMultiplexer()
    assistant_chunks: list[str] = []
    completed = False
    excluded_global_config_ids: set[str] = set()
    last_initial_error: ChatRuntimeEvent | None = None
    pooled_provider_configs: tuple[Any, ...] = ()
    timing = timing or AgentTurnTiming()

    while True:
        selection = await _resolve_opencode_llm_config(
            request,
            session_id,
            runtime_llm_config,
            excluded_global_config_ids=excluded_global_config_ids,
        )
        if isinstance(selection, ChatRuntimeEvent):
            if last_initial_error is not None:
                selection = last_initial_error
            event_data = timing.annotate(selection.type, _event_data_dict(selection.data))
            await persist_runtime_event_trace(
                request,
                session_id,
                turn_id,
                selection.type,
                event_data,
            )
            yield multiplexer.format(
                _frontend_event(selection, event_data, session_id=session_id, turn_id=turn_id)
            )
            return

        llm_config = selection.config
        if selection.pooled_global and not pooled_provider_configs:
            pooled_provider_configs = tuple(
                await request.app.state.llm_config_repo.list_runtime_global_configs()
            )
        initializing_event = ChatRuntimeEvent(
            type="assistant_action",
            data={
                "action": "opencode_busy",
                "summary": "opencode 正在初始化当前会话",
            },
        )
        initializing_data = timing.annotate(
            initializing_event.type,
            _event_data_dict(initializing_event.data),
        )
        await persist_runtime_event_trace(
            request,
            session_id,
            turn_id,
            initializing_event.type,
            initializing_data,
        )
        yield multiplexer.format(
            _frontend_event(
                initializing_event,
                initializing_data,
                session_id=session_id,
                turn_id=turn_id,
            )
        )

        try:
            binding = await compat.initialize_session(
                session_id,
                llm_config,
                provider_config_pool=pooled_provider_configs if selection.pooled_global else (),
                force_new_external_session=selection.pooled_global
                and bool(excluded_global_config_ids),
            )
            context_window = int(
                getattr(request.app.state.settings, "model_context_window_tokens", 200_000)
            )
            runtime_event = _opencode_runtime_state_event(selection, content, context_window)
            runtime_data = timing.annotate(runtime_event.type, _event_data_dict(runtime_event.data))
            await persist_runtime_event_trace(
                request,
                session_id,
                turn_id,
                runtime_event.type,
                runtime_data,
            )
            yield multiplexer.format(
                _frontend_event(
                    runtime_event,
                    runtime_data,
                    session_id=session_id,
                    turn_id=turn_id,
                )
            )
            emitted_text = False
            retrying_with_next_config = False
            async for event in compat.run_turn(
                session_id=session_id,
                user_message=content,
                llm_config=llm_config,
                binding=binding,
                context_window_tokens=context_window,
            ):
                event_data = timing.annotate(event.type, _event_data_dict(event.data))
                if event.type == "error" and not emitted_text:
                    last_initial_error = event
                    if _retry_next_opencode_global_config(
                        request,
                        selection,
                        event_data,
                        session_id=session_id,
                        excluded_global_config_ids=excluded_global_config_ids,
                    ):
                        assistant_chunks.clear()
                        retrying_with_next_config = True
                        break
                elif event.type == "error":
                    log.info(
                        "opencode_global_pool_retry_skipped",
                        session_id=session_id,
                        turn_id=turn_id,
                        config_id=getattr(selection.config, "id", None),
                        pooled_global=selection.pooled_global,
                        emitted_text=emitted_text,
                    )
                    await persist_runtime_event_trace(
                        request,
                        session_id,
                        turn_id,
                        event.type,
                        event_data,
                    )
                    yield multiplexer.format(
                        _frontend_event(
                            event,
                            event_data,
                            session_id=session_id,
                            turn_id=turn_id,
                        )
                    )
                    return

                await persist_runtime_event_trace(
                    request,
                    session_id,
                    turn_id,
                    event.type,
                    event_data,
                )
                if event.type == "text_delta":
                    delta = event_data.get("delta") or event_data.get("text")
                    if isinstance(delta, str):
                        assistant_chunks.append(delta)
                        emitted_text = True
                if event.type == "done":
                    completed = True
                    request.app.state.llm_gateway.record_runtime_config_success(selection)
                yield multiplexer.format(
                    _frontend_event(event, event_data, session_id=session_id, turn_id=turn_id)
                )
                if event.type == "done":
                    break
                if event.type == "error":
                    return
            if completed:
                break
            if retrying_with_next_config:
                continue
            return
        except asyncio.CancelledError:
            await rollback_session_turn(request.app.state.session_factory, session_id, turn_id)
            raise
        except Exception as exc:
            error_code = exc.code if isinstance(exc, OpenCodeProcessError) else None
            error_event = ChatRuntimeEvent(
                type="error",
                data={
                    "backend": "opencode",
                    "error": str(exc) or exc.__class__.__name__,
                    **({"code": error_code} if error_code else {}),
                },
            )
            error_data = timing.annotate(error_event.type, _event_data_dict(error_event.data))
            await persist_runtime_event_trace(
                request,
                session_id,
                turn_id,
                error_event.type,
                error_data,
            )
            yield multiplexer.format(
                _frontend_event(
                    error_event,
                    error_data,
                    session_id=session_id,
                    turn_id=turn_id,
                )
            )
            return

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


async def _resolve_opencode_llm_config(
    request: Request,
    session_id: str,
    runtime_llm_config: dict[str, Any] | None,
    *,
    excluded_global_config_ids: set[str] | None = None,
) -> LLMConfigSelection | ChatRuntimeEvent:
    selection = await request.app.state.llm_gateway.select_runtime_config(
        config_id=None,
        subject_id=getattr(request.state, "subject_id", None),
        session_id=session_id,
        runtime_llm_config=runtime_llm_config,
        excluded_global_config_ids=excluded_global_config_ids,
    )
    if isinstance(selection, LLMEvent):
        return _llm_error_to_chat_error(selection)
    return selection


def _opencode_runtime_state_event(
    selection: LLMConfigSelection,
    current_user_message: str,
    context_window: int = 200_000,
):
    llm_config = selection.config
    context_size = max(0, len(current_user_message))
    context_window = max(1, context_window)
    return ChatRuntimeEvent(
        type="runtime_state",
        data={
            "backend": "opencode",
            "config_id": llm_config.id,
            "model_name": llm_config.model_name,
            "protocol": llm_config.protocol,
            "scope": llm_config.scope,
            "context_size_chars": context_size,
            "context_window_chars": context_window,
            "context_used": context_size,
            "context_window": context_window,
            "context_unit": "chars_estimate",
            "context_metric_source": "initial_estimate",
            "usage_ratio": context_size / context_window,
            "usage_label": f"{context_size // 1000}k / {context_window // 1000}k",
            "is_global_pool": selection.pooled_global,
        },
    )


def _retry_next_opencode_global_config(
    request: Request,
    selection: LLMConfigSelection,
    error_data: dict[str, Any],
    *,
    session_id: str,
    excluded_global_config_ids: set[str],
) -> bool:
    should_count = request.app.state.llm_gateway.runtime_error_counts_for_config_health(error_data)
    log.info(
        "opencode_global_pool_retry_decision",
        session_id=session_id,
        config_id=getattr(selection.config, "id", None),
        pooled_global=selection.pooled_global,
        should_count=should_count,
        excluded_count=len(excluded_global_config_ids),
    )
    if not selection.pooled_global:
        return False
    if not should_count:
        return False
    request.app.state.llm_gateway.record_runtime_config_failure(
        selection,
        error_data,
        session_id=session_id,
        clear_sticky=True,
    )
    excluded_global_config_ids.add(selection.config.id)
    return True


def _llm_error_to_chat_error(event: LLMEvent) -> ChatRuntimeEvent:
    return ChatRuntimeEvent(
        type="error",
        data={
            "backend": "opencode",
            "error": str(event.data.get("message") or "LLM config selection failed"),
            "error_code": event.data.get("error_code"),
            "retryable": event.data.get("retryable"),
        },
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
        turn_query = select(SessionTurn).where(
            SessionTurn.session_id == session_id,
            SessionTurn.id != current_turn_id,
        )
        if summary_row is not None:
            turn_query = turn_query.where(SessionTurn.turn_index > summary_row.covered_turn_index)
        turn_rows = (
            (
                await session.execute(
                    turn_query.order_by(
                        SessionTurn.turn_index.desc(), SessionTurn.created_at.desc()
                    ).limit(max_history_messages)
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

    covered_rows = list(turn_rows[:-keep_recent_messages])
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
    if summary_row is not None and summary_row.covered_turn_index >= covered_turn_index:
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
                f"- turn_index={row.turn_index} {label}: {_truncate_summary(row.content, 360)}"
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
    if event_type == "text_delta":
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
