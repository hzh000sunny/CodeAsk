"""REST and SSE router for agent sessions."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from contextlib import suppress
from datetime import date
from pathlib import Path
from secrets import token_hex
from time import perf_counter
from typing import Annotated, TypedDict, cast

import structlog
from fastapi import (
    APIRouter,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.agent.chat_runtime.events import ChatRuntimeEvent
from codeask.agent.sse import AgentEvent, SSEMultiplexer
from codeask.api.schemas.session import (
    AgentTraceResponse,
    AttachmentResponse,
    AttachmentUpdate,
    MessageCreate,
    SessionBulkDelete,
    SessionBulkDeleteResponse,
    SessionCreate,
    SessionReportCreate,
    SessionReportPrepared,
    SessionReportPrepareRequest,
    SessionReportPrepareStatus,
    SessionResponse,
    SessionTurnResponse,
    SessionUpdate,
)
from codeask.api.schemas.wiki import ReportRead
from codeask.audit import write_audit
from codeask.db.models import (
    AgentTrace,
    Feature,
    Session,
    SessionAttachment,
    SessionFeature,
    SessionTurn,
    SystemSetting,
)
from codeask.sessions.attachments import (
    append_attachment_alias,
    attachment_description,
    attachment_display_name,
    collect_session_storage_dirs,
    remove_session_storage_dirs,
    write_session_manifest,
)
from codeask.sessions.messages import (
    AgentTurnTiming,
    create_user_turn_and_bindings,
    stream_agent_response,
)
from codeask.sessions.report_generation import prepare_session_report_draft
from codeask.sessions.reports import (
    has_completed_question_answer,
    merge_session_report_metadata,
)
from codeask.sessions.title_generation import generate_session_title_from_history
from codeask.sessions.trace_redaction import redact_trace_payload_for_frontend
from codeask.sessions.traces import is_visible_trace, trace_event_priority
from codeask.wiki.reports import ReportService
from codeask.wiki.sync import LegacyWikiSyncService

router = APIRouter()
log = structlog.get_logger("codeask.api.sessions")

_REPORT_PREPARE_CACHE_LIMIT = 128
_FEATURE_INFERENCE_SESSION_BINDING_WEIGHT = 1000
_FEATURE_INFERENCE_SCOPE_DECISION_WEIGHT = 120
_FEATURE_INFERENCE_TOOL_EVIDENCE_WEIGHT = 110
_FEATURE_INFERENCE_WIKI_HIT_WEIGHT = 90
_FEATURE_INFERENCE_REPORT_HIT_WEIGHT = 90
_FEATURE_INFERENCE_WIKI_SCOPE_MATCH_WEIGHT = 80
_FEATURE_INFERENCE_VERSION_INFO_WEIGHT = 60
_FEATURE_INFERENCE_CANDIDATE_WEIGHT = 30

_ALLOWED_KINDS = {"log", "image", "doc", "other"}
_ALLOWED_EXTENSIONS = {".log", ".txt", ".md", ".png", ".jpg", ".jpeg"}
_MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
_DEFAULT_SESSION_TITLE = "新的研发会话"
_SESSION_ATTACHMENTS_ENABLED_KEY = "session_attachments_enabled"


class _ReasoningTraceBucket(TypedDict):
    fields: set[str]
    length: int
    chunks: int
    redacted: bool


def _dict_payload(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return cast(dict[str, object], value)
    return {}


def _list_payload(value: object) -> list[object]:
    if isinstance(value, list):
        return cast(list[object], value)
    return []


def _format_runtime_event(multiplexer: SSEMultiplexer, event: ChatRuntimeEvent) -> bytes:
    return multiplexer.format(cast(AgentEvent, event))


def _compact_reasoning_trace_responses(rows: list[AgentTrace]) -> list[AgentTraceResponse]:
    responses: list[AgentTraceResponse] = []
    reasoning_by_turn: dict[str, _ReasoningTraceBucket] = {}
    reasoning_order: dict[str, int] = {}
    for row in rows:
        if row.event_type != "reasoning_observed":
            responses.append(AgentTraceResponse.model_validate(row))
            continue

        payload = _dict_payload(row.payload)
        bucket = reasoning_by_turn.get(row.turn_id)
        if bucket is None:
            bucket = _ReasoningTraceBucket(
                fields=set[str](),
                length=0,
                chunks=0,
                redacted=False,
            )
            reasoning_by_turn[row.turn_id] = bucket
            reasoning_order[row.turn_id] = len(responses)
            responses.append(
                AgentTraceResponse(
                    id=f"{row.id}_summary",
                    session_id=row.session_id,
                    turn_id=row.turn_id,
                    stage=row.stage,
                    event_type=row.event_type,
                    payload={},
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
            )

        field = payload.get("field")
        if isinstance(field, str) and field:
            bucket["fields"].update(part.strip() for part in field.split(",") if part.strip())
        length = payload.get("length")
        if isinstance(length, int):
            bucket["length"] += length
        chunks = payload.get("chunks")
        bucket["chunks"] += chunks if isinstance(chunks, int) else 1
        if payload.get("redacted") is True:
            bucket["redacted"] = True

    for turn_id, bucket in reasoning_by_turn.items():
        index = reasoning_order[turn_id]
        fields = bucket["fields"]
        responses[index].payload = {
            "field": ", ".join(sorted(fields)) if fields else "unknown",
            "length": bucket["length"],
            "chunks": bucket["chunks"],
            "redacted": bucket["redacted"],
            "raw_reasoning_used": False,
        }
    return responses


def _redact_trace_responses_for_frontend(
    responses: list[AgentTraceResponse],
    *,
    session_id: str,
) -> list[AgentTraceResponse]:
    return [
        response.model_copy(
            update={
                "payload": redact_trace_payload_for_frontend(
                    response.payload,
                    session_id=session_id,
                )
            }
        )
        for response in responses
    ]


@router.post("/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(payload: SessionCreate, request: Request) -> SessionResponse:
    factory = request.app.state.session_factory
    session_id = f"sess_{token_hex(8)}"
    title = payload.title.strip() or _DEFAULT_SESSION_TITLE
    row = Session(
        id=session_id,
        title=title,
        created_by_subject_id=request.state.subject_id,
        status="active",
        title_source="default" if title == _DEFAULT_SESSION_TITLE else "manual",
    )
    async with factory() as session:
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return SessionResponse.model_validate(row)


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(request: Request) -> list[SessionResponse]:
    factory = request.app.state.session_factory
    async with factory() as session:
        rows = (
            await session.execute(
                select(Session)
                .where(Session.created_by_subject_id == request.state.subject_id)
                .order_by(
                    Session.pinned.desc(),
                    Session.updated_at.desc(),
                    Session.created_at.desc(),
                )
            )
        ).scalars()
        return [SessionResponse.model_validate(row) for row in rows]


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str, request: Request) -> SessionResponse:
    row = await _load_session(request, session_id)
    return SessionResponse.model_validate(row)


@router.get("/sessions/{session_id}/turns", response_model=list[SessionTurnResponse])
async def list_session_turns(session_id: str, request: Request) -> list[SessionTurnResponse]:
    await _load_session(request, session_id)
    factory = request.app.state.session_factory
    async with factory() as session:
        rows = (
            (
                await session.execute(
                    select(SessionTurn)
                    .where(SessionTurn.session_id == session_id)
                    .order_by(SessionTurn.turn_index, SessionTurn.created_at)
                )
            )
            .scalars()
            .all()
        )
    return [SessionTurnResponse.model_validate(row) for row in rows]


@router.get("/sessions/{session_id}/traces", response_model=list[AgentTraceResponse])
async def list_session_traces(session_id: str, request: Request) -> list[AgentTraceResponse]:
    await _load_session(request, session_id)
    factory = request.app.state.session_factory
    async with factory() as session:
        rows = (
            (
                await session.execute(
                    select(AgentTrace)
                    .where(AgentTrace.session_id == session_id)
                    .order_by(AgentTrace.created_at, AgentTrace.id)
                )
            )
            .scalars()
            .all()
        )
    visible_rows = [row for row in rows if is_visible_trace(row)]
    visible_rows.sort(key=lambda row: (row.created_at, trace_event_priority(row), row.id))
    return _redact_trace_responses_for_frontend(
        _compact_reasoning_trace_responses(visible_rows),
        session_id=session_id,
    )


@router.patch("/sessions/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: str,
    payload: SessionUpdate,
    request: Request,
) -> SessionResponse:
    factory = request.app.state.session_factory
    fields = payload.model_fields_set
    async with factory() as session:
        row = (
            await session.execute(
                select(Session).where(
                    Session.id == session_id,
                    Session.created_by_subject_id == request.state.subject_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
        if "title" in fields and payload.title is not None:
            row.title = payload.title
            row.title_source = "manual"
            row.title_generated_at = None
        if "pinned" in fields and payload.pinned is not None:
            row.pinned = payload.pinned
        await session.commit()
        await session.refresh(row)
        return SessionResponse.model_validate(row)


@router.post("/sessions/{session_id}/title/generate", response_model=SessionResponse)
async def generate_session_title(session_id: str, request: Request) -> SessionResponse:
    await _load_session(request, session_id)
    await generate_session_title_from_history(
        request.app.state.session_factory,
        request.app.state.llm_gateway,
        session_id=session_id,
        subject_id=request.state.subject_id,
    )
    row = await _load_session(request, session_id)
    return SessionResponse.model_validate(row)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: str, request: Request) -> None:
    factory = request.app.state.session_factory
    storage_dirs: list[Path]
    async with factory() as session:
        row = (
            await session.execute(select(Session).where(Session.id == session_id))
        ).scalar_one_or_none()
        if row is None:
            return
        if row.created_by_subject_id != request.state.subject_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
        storage_dirs = await collect_session_storage_dirs(
            session,
            request.app.state.settings.data_dir,
            [session_id],
        )
        await session.delete(row)
        await session.commit()

    remove_session_storage_dirs(storage_dirs)
    await _cleanup_opencode_session_resources(request, [session_id])


@router.post("/sessions/bulk-delete", response_model=SessionBulkDeleteResponse)
async def bulk_delete_sessions(
    payload: SessionBulkDelete,
    request: Request,
) -> SessionBulkDeleteResponse:
    factory = request.app.state.session_factory
    requested = list(dict.fromkeys(payload.session_ids))
    storage_dirs: list[Path] = []
    async with factory() as session:
        rows = (
            (
                await session.execute(
                    select(Session).where(
                        Session.id.in_(requested),
                        Session.created_by_subject_id == request.state.subject_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        owned_ids = {row.id for row in rows}
        storage_dirs = await collect_session_storage_dirs(
            session,
            request.app.state.settings.data_dir,
            list(owned_ids),
        )
        for row in rows:
            await session.delete(row)
        await session.commit()

    deleted_ids = [session_id for session_id in requested if session_id in owned_ids]
    remove_session_storage_dirs(storage_dirs)
    await _cleanup_opencode_session_resources(request, deleted_ids)
    return SessionBulkDeleteResponse(deleted_ids=deleted_ids)


@router.post("/sessions/{session_id}/messages")
async def post_message(
    session_id: str,
    payload: MessageCreate,
    request: Request,
) -> StreamingResponse:
    turn_id = payload.client_turn_id or f"turn_{token_hex(8)}"
    return StreamingResponse(
        _stream_post_message_response(
            request,
            session_id,
            turn_id,
            payload,
        ),
        media_type="text/event-stream",
        headers={"X-CodeAsk-Turn-Id": turn_id},
    )


async def _stream_post_message_response(
    request: Request,
    session_id: str,
    turn_id: str,
    payload: MessageCreate,
):
    started_at = perf_counter()
    multiplexer = SSEMultiplexer()
    timing = AgentTurnTiming()
    log.info(
        "session_message_stream_received",
        session_id=session_id,
        turn_id=turn_id,
        subject_id=getattr(request.state, "subject_id", None),
    )
    received_event = ChatRuntimeEvent(
        type="assistant_action",
        data={
            "action": "agent_request_received",
            "summary": "后端已收到会话请求，正在准备运行环境",
            "turn_id": turn_id,
        },
    )
    received_data = timing.annotate(received_event.type, _dict_payload(received_event.data))
    yield _format_runtime_event(
        multiplexer,
        received_event.model_copy(update={"data": received_data}),
    )
    try:
        _record_opencode_server_status_if_configured(request)
        log.info("session_message_preflight_start", session_id=session_id, turn_id=turn_id)
        await _load_session(request, session_id)
        log.info(
            "session_message_preflight_done",
            session_id=session_id,
            turn_id=turn_id,
            elapsed_ms=round((perf_counter() - started_at) * 1000, 2),
        )
        log.info("session_message_user_turn_start", session_id=session_id, turn_id=turn_id)
        await create_user_turn_and_bindings(request, session_id, turn_id, payload)
        log.info(
            "session_message_user_turn_done",
            session_id=session_id,
            turn_id=turn_id,
            elapsed_ms=round((perf_counter() - started_at) * 1000, 2),
        )
        async for chunk in stream_agent_response(
            request,
            session_id,
            turn_id,
            payload.content,
            runtime_llm_config=(
                payload.guest_llm_config.model_dump()
                if payload.guest_llm_config is not None
                and not bool(getattr(request.state, "authenticated", False))
                else None
            ),
            timing=timing,
        ):
            yield chunk
        log.info(
            "session_message_stream_done",
            session_id=session_id,
            turn_id=turn_id,
            elapsed_ms=round((perf_counter() - started_at) * 1000, 2),
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        log.exception(
            "session_message_stream_failed",
            session_id=session_id,
            turn_id=turn_id,
            elapsed_ms=round((perf_counter() - started_at) * 1000, 2),
        )
        error_event = ChatRuntimeEvent(
            type="error",
            data={
                "turn_id": turn_id,
                "backend": "codeask",
                "error": _stream_error_message(exc),
            },
        )
        error_data = timing.annotate(error_event.type, _dict_payload(error_event.data))
        yield _format_runtime_event(
            multiplexer,
            error_event.model_copy(
                update={
                    "data": redact_trace_payload_for_frontend(
                        error_data,
                        session_id=session_id,
                    )
                }
            ),
        )


def _record_opencode_server_status_if_configured(request: Request) -> None:
    process_manager = getattr(request.app.state, "opencode_process_manager", None)
    describe = getattr(process_manager, "describe", None)
    if not callable(describe):
        return
    raw_status = describe()
    status_payload = (
        dict(cast(Mapping[str, object], raw_status)) if isinstance(raw_status, Mapping) else {}
    )
    log.info(
        "opencode_server_status_before_request",
        running=status_payload.get("running"),
        port=status_payload.get("port"),
        pid=status_payload.get("pid"),
        last_error_code=status_payload.get("last_error_code"),
    )


def _stream_error_message(exc: Exception) -> str:
    detail = getattr(exc, "detail", None)
    if detail is not None:
        return str(detail)
    message = str(exc).strip()
    return message or exc.__class__.__name__


async def _cleanup_opencode_session_resources(
    request: Request,
    session_ids: list[str],
) -> None:
    compat = getattr(request.app.state, "opencode_compat", None)
    cleanup = getattr(compat, "cleanup_session", None)
    if cleanup is None:
        return
    for session_id in session_ids:
        try:
            await cleanup(session_id)
        except Exception as exc:  # pragma: no cover - defensive cleanup logging
            log.warning(
                "opencode_session_cleanup_failed",
                session_id=session_id,
                error=str(exc),
            )


@router.post("/sessions/{session_id}/turns/{turn_id}/abort", status_code=status.HTTP_204_NO_CONTENT)
async def abort_session_turn(session_id: str, turn_id: str, request: Request) -> None:
    await _load_session(request, session_id)

    with suppress(Exception):
        await request.app.state.opencode_compat.abort_turn(session_id)


@router.post(
    "/sessions/{session_id}/reports/prepare",
    response_model=SessionReportPrepareStatus,
)
async def prepare_session_report(
    session_id: str,
    payload: SessionReportPrepareRequest,
    request: Request,
    response: Response,
) -> SessionReportPrepareStatus:
    await _load_session(request, session_id)
    request_id = (request.headers.get("X-CodeAsk-Request-Id") or "").strip() or (
        f"report_prepare_{token_hex(8)}"
    )
    response.headers["X-CodeAsk-Request-Id"] = request_id
    cache_key = _report_prepare_cache_key(session_id, request_id)
    cached = _report_prepare_cache(request).get(cache_key)
    if cached is not None:
        return cached

    factory = request.app.state.session_factory
    async with factory() as session:
        turns = await _load_session_turns(session, session_id)
        if not has_completed_question_answer(list(turns)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="至少完成一次问答后才能生成问题定位报告",
            )
        report_service = ReportService()
        existing_report = await report_service.get_session_bound_report(
            session,
            session_id=session_id,
        )
        inferred_feature_ids = await _load_inferred_feature_ids(session, session_id=session_id)
        selected_feature_id = _select_report_feature_id(
            explicit_feature_id=payload.feature_id,
            existing_feature_id=existing_report.feature_id if existing_report is not None else None,
            inferred_feature_ids=inferred_feature_ids,
        )
        await _load_optional_feature(session, selected_feature_id)

    running = SessionReportPrepareStatus(request_id=request_id, status="running")
    _store_report_prepare_status(request, session_id, request_id, running)
    task = asyncio.create_task(
        _run_session_report_prepare_task(
            request.app,
            session_id=session_id,
            request_id=request_id,
            subject_id=request.state.subject_id,
            feature_id=selected_feature_id,
        )
    )
    _report_prepare_tasks(request.app)[cache_key] = task
    return running


@router.get(
    "/sessions/{session_id}/reports/prepare/{request_id}",
    response_model=SessionReportPrepareStatus,
)
async def get_session_report_prepare_status(
    session_id: str,
    request_id: str,
    request: Request,
    response: Response,
) -> SessionReportPrepareStatus:
    await _load_session(request, session_id)
    response.headers["X-CodeAsk-Request-Id"] = request_id
    cached = _report_prepare_cache(request).get(_report_prepare_cache_key(session_id, request_id))
    if cached is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="report prepare request not found",
        )
    return cached


async def _run_session_report_prepare_task(
    app: FastAPI,
    *,
    session_id: str,
    request_id: str,
    subject_id: str,
    feature_id: int | None,
) -> None:
    started_at = perf_counter()
    factory = app.state.session_factory
    async with factory() as session:
        turns = await _load_session_turns(session, session_id)
        existing_report = await ReportService().get_session_bound_report(
            session,
            session_id=session_id,
        )
        inferred_feature_ids = await _load_inferred_feature_ids(session, session_id=session_id)
        selected_feature = await _load_optional_feature(session, feature_id)
        traces = await _load_session_traces(session, session_id)

    log.info(
        "session_report_prepare_started",
        session_id=session_id,
        request_id=request_id,
        subject_id=subject_id,
        feature_id=feature_id,
        turn_count=len(turns),
    )
    try:
        prepared = await prepare_session_report_draft(
            app.state.llm_gateway,
            subject_id=subject_id,
            session_id=session_id,
            turns=list(turns),
            tool_action_summary=traces,
            selected_feature=selected_feature,
            existing_report=existing_report,
            today=date.today(),
        )
    except Exception as exc:
        duration_ms = int((perf_counter() - started_at) * 1000)
        log.exception(
            "session_report_prepare_failed",
            session_id=session_id,
            request_id=request_id,
            subject_id=subject_id,
            feature_id=feature_id,
            duration_ms=duration_ms,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        _store_report_prepare_status_for_app(
            app,
            session_id,
            request_id,
            SessionReportPrepareStatus(
                request_id=request_id,
                status="failed",
                error=f"报告草稿生成失败：{type(exc).__name__}: {exc}",
            ),
        )
        return
    duration_ms = int((perf_counter() - started_at) * 1000)
    log.info(
        "session_report_prepare_succeeded",
        session_id=session_id,
        request_id=request_id,
        subject_id=subject_id,
        feature_id=feature_id,
        duration_ms=duration_ms,
        title=prepared.title,
    )
    draft = SessionReportPrepared(
        existing_report_id=int(existing_report.id) if existing_report is not None else None,
        feature_id=feature_id,
        inferred_feature_ids=inferred_feature_ids,
        title=prepared.title,
        body_markdown=prepared.body_markdown,
    )
    _store_report_prepare_status_for_app(
        app,
        session_id,
        request_id,
        SessionReportPrepareStatus(
            request_id=request_id,
            status="succeeded",
            draft=draft,
        ),
    )


@router.post(
    "/sessions/{session_id}/reports",
    response_model=ReportRead,
    status_code=status.HTTP_201_CREATED,
)
async def generate_session_report(
    session_id: str,
    payload: SessionReportCreate,
    request: Request,
) -> ReportRead:
    await _load_session(request, session_id)
    factory = request.app.state.session_factory
    async with factory() as session:
        feature = await _load_optional_feature(session, payload.feature_id)
        turns = await _load_session_turns(session, session_id)
        if not has_completed_question_answer(list(turns)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="至少完成一次问答后才能生成问题定位报告",
            )
        report_service = ReportService()
        existing_report = await report_service.get_session_bound_report(
            session,
            session_id=session_id,
        )
        existing_metadata = (
            _dict_payload(existing_report.metadata_json) if existing_report is not None else {}
        )
        report = await report_service.upsert_session_draft(
            session,
            feature_id=payload.feature_id,
            session_id=session_id,
            title=payload.title,
            body_markdown=payload.body_markdown,
            metadata=merge_session_report_metadata(existing_metadata, session_id, list(turns)),
            subject_id=request.state.subject_id,
        )
        await write_audit(
            session,
            entity_type="report",
            entity_id=str(report.id),
            action="session_report.upsert",
            subject_id=request.state.subject_id,
            result="draft",
        )
        sync_service = LegacyWikiSyncService()
        duplicate_reports = await report_service.list_session_report_duplicates(
            session,
            session_id=session_id,
            keep_report_id=int(report.id),
        )
        for duplicate_report in duplicate_reports:
            await sync_service.delete_report_ref(session, report_id=int(duplicate_report.id))
            await session.delete(duplicate_report)
        if feature is None:
            await sync_service.delete_report_ref(session, report_id=int(report.id))
        else:
            await sync_service.sync_report_ref(
                session,
                report_id=int(report.id),
                feature_id=feature.id,
                title=report.title,
            )
        await session.commit()
        return ReportRead.model_validate(report)


@router.get("/sessions/{session_id}/attachments", response_model=list[AttachmentResponse])
async def list_attachments(session_id: str, request: Request) -> list[AttachmentResponse]:
    await _load_session(request, session_id)
    factory = request.app.state.session_factory
    async with factory() as session:
        rows = (
            (
                await session.execute(
                    select(SessionAttachment)
                    .where(SessionAttachment.session_id == session_id)
                    .order_by(SessionAttachment.created_at, SessionAttachment.id)
                )
            )
            .scalars()
            .all()
        )
    return [AttachmentResponse.model_validate(row) for row in rows]


@router.post(
    "/sessions/{session_id}/attachments",
    response_model=AttachmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachment(
    session_id: str,
    request: Request,
    file: Annotated[UploadFile, File()],
    kind: Annotated[str, Form()] = "log",
    description: Annotated[str | None, Form()] = None,
) -> AttachmentResponse:
    await _load_session(request, session_id)
    if not await _session_attachments_enabled(request):
        async with request.app.state.session_factory() as audit_session:
            await write_audit(
                audit_session,
                entity_type="session",
                entity_id=session_id,
                action="session_attachment.upload_denied",
                subject_id=request.state.subject_id,
                result="denied",
                reason="disabled",
            )
            await audit_session.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="该功能已被禁用",
        )
    if kind not in _ALLOWED_KINDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="invalid kind"
        )
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="file must have a name")
    filename = attachment_display_name(file.filename)
    if not filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="file must have a name")
    extension = Path(filename).suffix.lower()
    if extension not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unsupported attachment extension: {extension}",
        )
    content = await file.read()
    if len(content) > _MAX_ATTACHMENT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="file too large"
        )

    attachment_id = f"att_{token_hex(8)}"
    storage_dir = request.app.state.settings.data_dir / "sessions" / session_id
    storage_dir.mkdir(parents=True, exist_ok=True)
    target = storage_dir / f"{attachment_id}{extension}"
    target.write_bytes(content)

    row = SessionAttachment(
        id=attachment_id,
        session_id=session_id,
        kind=kind,
        display_name=filename,
        original_filename=filename,
        aliases_json=[filename],
        description=attachment_description(description),
        file_path=str(target),
        mime_type=file.content_type or "application/octet-stream",
        size_bytes=len(content),
    )
    factory = request.app.state.session_factory
    async with factory() as session:
        session.add(row)
        await session.commit()
        await session.refresh(row)
    await write_session_manifest(request, session_id)
    return AttachmentResponse.model_validate(row)


@router.patch(
    "/sessions/{session_id}/attachments/{attachment_id}",
    response_model=AttachmentResponse,
)
async def update_attachment(
    session_id: str,
    attachment_id: str,
    payload: AttachmentUpdate,
    request: Request,
) -> AttachmentResponse:
    await _load_session(request, session_id)
    factory = request.app.state.session_factory
    async with factory() as session:
        row = (
            await session.execute(
                select(SessionAttachment).where(
                    SessionAttachment.id == attachment_id,
                    SessionAttachment.session_id == session_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="attachment not found",
            )
        fields = payload.model_fields_set
        if "display_name" in fields and payload.display_name is not None:
            display_name = attachment_display_name(payload.display_name)
            if not display_name:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="display name must not be empty",
                )
            row.display_name = display_name
            row.aliases_json = append_attachment_alias(row.aliases_json, display_name)
        if "description" in fields:
            row.description = attachment_description(payload.description)
        await session.commit()
        await session.refresh(row)
    await write_session_manifest(request, session_id)
    return AttachmentResponse.model_validate(row)


@router.delete(
    "/sessions/{session_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_attachment(session_id: str, attachment_id: str, request: Request) -> None:
    await _load_session(request, session_id)
    factory = request.app.state.session_factory
    file_path: str | None = None
    async with factory() as session:
        row = (
            await session.execute(
                select(SessionAttachment).where(
                    SessionAttachment.id == attachment_id,
                    SessionAttachment.session_id == session_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="attachment not found",
            )
        file_path = row.file_path
        await session.delete(row)
        await session.commit()

    await write_session_manifest(request, session_id)
    if file_path:
        Path(file_path).unlink(missing_ok=True)


async def _load_session(request: Request, session_id: str) -> Session:
    factory = request.app.state.session_factory
    async with factory() as session:
        row = (
            await session.execute(
                select(Session).where(
                    Session.id == session_id,
                    Session.created_by_subject_id == request.state.subject_id,
                )
            )
        ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
    return row


async def _session_attachments_enabled(request: Request) -> bool:
    factory = request.app.state.session_factory
    async with factory() as session:
        row = await session.get(SystemSetting, _SESSION_ATTACHMENTS_ENABLED_KEY)
    if row is None:
        return True
    return bool(row.value)


def _report_prepare_cache_for_app(app: FastAPI) -> dict[str, SessionReportPrepareStatus]:
    cache = getattr(app.state, "report_prepare_results", None)
    if not isinstance(cache, dict):
        cache = {}
        app.state.report_prepare_results = cache
    return cast(dict[str, SessionReportPrepareStatus], cache)


def _report_prepare_cache(request: Request) -> dict[str, SessionReportPrepareStatus]:
    return _report_prepare_cache_for_app(request.app)


def _report_prepare_tasks(app: FastAPI) -> dict[str, asyncio.Task[None]]:
    tasks = getattr(app.state, "report_prepare_tasks", None)
    if not isinstance(tasks, dict):
        tasks = {}
        app.state.report_prepare_tasks = tasks
    return cast(dict[str, asyncio.Task[None]], tasks)


def _report_prepare_cache_key(session_id: str, request_id: str) -> str:
    return f"{session_id}:{request_id}"


def _store_report_prepare_status_for_app(
    app: FastAPI,
    session_id: str,
    request_id: str,
    value: SessionReportPrepareStatus,
) -> None:
    cache = _report_prepare_cache_for_app(app)
    cache_key = _report_prepare_cache_key(session_id, request_id)
    cache[cache_key] = value
    while len(cache) > _REPORT_PREPARE_CACHE_LIMIT:
        oldest_key = next(iter(cache))
        cache.pop(oldest_key, None)
        _report_prepare_tasks(app).pop(oldest_key, None)


def _store_report_prepare_status(
    request: Request,
    session_id: str,
    request_id: str,
    value: SessionReportPrepareStatus,
) -> None:
    _store_report_prepare_status_for_app(request.app, session_id, request_id, value)


async def _load_session_turns(session: AsyncSession, session_id: str) -> list[SessionTurn]:
    rows = (
        (
            await session.execute(
                select(SessionTurn)
                .where(SessionTurn.session_id == session_id)
                .order_by(SessionTurn.turn_index, SessionTurn.created_at)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def _load_session_traces(session: AsyncSession, session_id: str) -> str | None:
    rows = (
        (
            await session.execute(
                select(AgentTrace)
                .where(AgentTrace.session_id == session_id)
                .order_by(AgentTrace.created_at.asc(), AgentTrace.id.asc())
            )
        )
        .scalars()
        .all()
    )
    from codeask.sessions.messages import summarize_tool_actions

    return summarize_tool_actions(list(rows))


async def _load_inferred_feature_ids(session: AsyncSession, *, session_id: str) -> list[int]:
    session_feature_rows = list(
        (
            await session.execute(
                select(SessionFeature.feature_id).where(SessionFeature.session_id == session_id)
            )
        )
        .scalars()
        .all()
    )
    trace_rows = list(
        (
            await session.execute(
                select(AgentTrace.event_type, AgentTrace.payload)
                .where(AgentTrace.session_id == session_id)
                .order_by(AgentTrace.created_at.asc(), AgentTrace.id.asc())
            )
        ).all()
    )
    scores: dict[int, int] = {}
    latest_order: dict[int, int] = {}
    order = 0

    def add_observation(feature_id: int, weight: int) -> None:
        nonlocal order
        scores[feature_id] = scores.get(feature_id, 0) + weight
        latest_order[feature_id] = order
        order += 1

    for value in session_feature_rows:
        add_observation(value, _FEATURE_INFERENCE_SESSION_BINDING_WEIGHT)

    for row in trace_rows:
        event_type = row[0]
        payload = row[1]
        if not isinstance(event_type, str):
            continue
        for feature_id, weight in _feature_observations_from_trace_payload(event_type, payload):
            add_observation(feature_id, weight)

    return sorted(
        scores,
        key=lambda feature_id: (
            scores[feature_id],
            latest_order.get(feature_id, -1),
        ),
        reverse=True,
    )


def _feature_observations_from_trace_payload(
    event_type: str,
    payload: object,
) -> list[tuple[int, int]]:
    feature_ids: list[int] = []

    def append_id(value: object) -> None:
        if isinstance(value, int):
            feature_ids.append(value)

    def append_ids(values: object) -> None:
        for item in _list_payload(values):
            append_id(item)

    data = _dict_payload(payload)
    if event_type == "scope_decision":
        output = data.get("output")
        output_data = _dict_payload(output)
        if output_data:
            append_ids(output_data.get("feature_ids"))
        return [
            (feature_id, _FEATURE_INFERENCE_SCOPE_DECISION_WEIGHT) for feature_id in feature_ids
        ]

    if event_type == "retrieval_context":
        observations: list[tuple[int, int]] = []
        for key, weight in (
            ("feature_candidates", _FEATURE_INFERENCE_CANDIDATE_WEIGHT),
            ("wiki_hits", _FEATURE_INFERENCE_WIKI_HIT_WEIGHT),
            ("report_hits", _FEATURE_INFERENCE_REPORT_HIT_WEIGHT),
        ):
            for item in _list_payload(data.get(key)):
                item_data = _dict_payload(item)
                if item_data:
                    value = item_data.get("feature_id")
                    if isinstance(value, int):
                        observations.append((value, weight))
        return observations

    if event_type == "wiki_scope_resolution":
        observations: list[tuple[int, int]] = []
        for item in _list_payload(data.get("feature_ids")):
            if isinstance(item, int):
                observations.append((item, _FEATURE_INFERENCE_WIKI_SCOPE_MATCH_WEIGHT))
        for key in ("defaults", "matches"):
            for item in _list_payload(data.get(key)):
                item_data = _dict_payload(item)
                if item_data:
                    value = item_data.get("feature_id")
                    if isinstance(value, int):
                        observations.append((value, _FEATURE_INFERENCE_WIKI_SCOPE_MATCH_WEIGHT))
        return observations

    if event_type == "tool_result":
        observations: list[tuple[int, int]] = []
        evidence_refs = data.get("evidence_refs")
        for ref in _list_payload(evidence_refs):
            ref_data = _dict_payload(ref)
            if not ref_data:
                continue
            metadata = _dict_payload(ref_data.get("metadata"))
            if metadata:
                value = metadata.get("feature_id")
                if isinstance(value, int):
                    observations.append((value, _FEATURE_INFERENCE_TOOL_EVIDENCE_WEIGHT))
        version_info = _dict_payload(data.get("version_info"))
        if version_info:
            for item in _list_payload(version_info.get("feature_ids")):
                if isinstance(item, int):
                    observations.append((item, _FEATURE_INFERENCE_VERSION_INFO_WEIGHT))
        return observations

    return []


def _select_report_feature_id(
    *,
    explicit_feature_id: int | None,
    existing_feature_id: int | None,
    inferred_feature_ids: list[int],
) -> int | None:
    if explicit_feature_id is not None:
        return explicit_feature_id
    if inferred_feature_ids:
        return inferred_feature_ids[0]
    return existing_feature_id


async def _load_optional_feature(session: AsyncSession, feature_id: int | None) -> Feature | None:
    if feature_id is None:
        return None
    feature = await session.get(Feature, feature_id)
    if feature is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="feature not found")
    return feature
