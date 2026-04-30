"""REST and SSE router for agent sessions."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from secrets import token_hex
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from codeask.agent.sse import SSEMultiplexer
from codeask.api.schemas.session import (
    AttachmentResponse,
    MessageCreate,
    SessionCreate,
    SessionResponse,
)
from codeask.db.models import Session, SessionAttachment, SessionFeature, SessionTurn

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
                .order_by(Session.created_at.desc())
            )
        ).scalars()
        return [SessionResponse.model_validate(row) for row in rows]


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str, request: Request) -> SessionResponse:
    row = await _load_session(request, session_id)
    return SessionResponse.model_validate(row)


@router.post("/sessions/{session_id}/messages")
async def post_message(
    session_id: str,
    payload: MessageCreate,
    request: Request,
) -> StreamingResponse:
    await _load_session(request, session_id)
    factory = request.app.state.session_factory
    turn_id = f"turn_{token_hex(8)}"
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
        await session.commit()

    orchestrator = request.app.state.agent_orchestrator
    multiplexer = SSEMultiplexer()

    async def stream() -> AsyncIterator[bytes]:
        async for event in orchestrator.run(
            session_id,
            turn_id,
            payload.content,
            force_code_investigation=payload.force_code_investigation,
        ):
            yield multiplexer.format(event)

    return StreamingResponse(stream(), media_type="text/event-stream")


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
) -> AttachmentResponse:
    await _load_session(request, session_id)
    if kind not in _ALLOWED_KINDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="invalid kind"
        )
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="file must have a name")
    filename = Path(file.filename).name
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
        file_path=str(target),
        mime_type=file.content_type or "application/octet-stream",
    )
    factory = request.app.state.session_factory
    async with factory() as session:
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return AttachmentResponse.model_validate(row)


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
