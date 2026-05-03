"""REST and SSE router for agent sessions."""

from __future__ import annotations

from pathlib import Path
from secrets import token_hex
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from codeask.api.schemas.session import (
    AgentTraceResponse,
    AttachmentResponse,
    AttachmentUpdate,
    MessageCreate,
    SessionBulkDelete,
    SessionBulkDeleteResponse,
    SessionCreate,
    SessionReportCreate,
    SessionResponse,
    SessionTurnResponse,
    SessionUpdate,
)
from codeask.api.schemas.wiki import ReportRead
from codeask.db.models import (
    AgentTrace,
    Feature,
    Report,
    Session,
    SessionAttachment,
    SessionTurn,
)
from codeask.sessions.attachments import (
    append_attachment_alias,
    attachment_description,
    attachment_display_name,
    collect_session_storage_dirs,
    remove_session_storage_dirs,
    write_session_manifest,
)
from codeask.sessions.messages import create_user_turn_and_bindings, stream_agent_response
from codeask.sessions.reports import (
    has_completed_question_answer,
    report_body_from_turns,
    report_metadata_from_turns,
)
from codeask.sessions.traces import is_visible_trace, trace_event_priority
from codeask.wiki.reports import ReportService

router = APIRouter()

_ALLOWED_KINDS = {"log", "image", "doc", "other"}
_ALLOWED_EXTENSIONS = {".log", ".txt", ".md", ".png", ".jpg", ".jpeg"}
_MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024


@router.post("/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(payload: SessionCreate, request: Request) -> SessionResponse:
    factory = request.app.state.session_factory
    session_id = f"sess_{token_hex(8)}"
    row = Session(
        id=session_id,
        title=payload.title,
        created_by_subject_id=request.state.subject_id,
        status="active",
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
    return [AgentTraceResponse.model_validate(row) for row in visible_rows]


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
        if "pinned" in fields and payload.pinned is not None:
            row.pinned = payload.pinned
        await session.commit()
        await session.refresh(row)
        return SessionResponse.model_validate(row)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: str, request: Request) -> None:
    factory = request.app.state.session_factory
    storage_dirs: list[Path]
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
        storage_dirs = await collect_session_storage_dirs(
            session,
            request.app.state.settings.data_dir,
            [session_id],
        )
        await session.delete(row)
        await session.commit()

    remove_session_storage_dirs(storage_dirs)


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
    return SessionBulkDeleteResponse(deleted_ids=deleted_ids)


@router.post("/sessions/{session_id}/messages")
async def post_message(
    session_id: str,
    payload: MessageCreate,
    request: Request,
) -> StreamingResponse:
    await _load_session(request, session_id)
    turn_id = f"turn_{token_hex(8)}"
    await create_user_turn_and_bindings(request, session_id, turn_id, payload)
    return StreamingResponse(
        stream_agent_response(
            request,
            session_id,
            turn_id,
            payload.content,
            force_code_investigation=payload.force_code_investigation,
        ),
        media_type="text/event-stream",
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
        feature = await session.get(Feature, payload.feature_id)
        if feature is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="feature not found")
        turns = (
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
        if not has_completed_question_answer(list(turns)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="至少完成一次问答后才能生成问题定位报告",
            )
        report_id = await ReportService().create_draft(
            session,
            feature_id=payload.feature_id,
            title=payload.title,
            body_markdown=report_body_from_turns(payload.title, list(turns)),
            metadata=report_metadata_from_turns(session_id, list(turns)),
            subject_id=request.state.subject_id,
        )
        await session.commit()
        report = (await session.execute(select(Report).where(Report.id == report_id))).scalar_one()
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
