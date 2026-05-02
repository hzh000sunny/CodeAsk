"""REST and SSE router for agent sessions."""

from __future__ import annotations

import json
import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from secrets import token_hex
from typing import Annotated, Any, cast

import structlog
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.agent.sse import SSEMultiplexer
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
from codeask.code_index.worktree import InvalidRefError, WorktreeError
from codeask.db.models import (
    AgentTrace,
    Feature,
    Repo,
    Report,
    Session,
    SessionAttachment,
    SessionFeature,
    SessionRepoBinding,
    SessionTurn,
)
from codeask.wiki.reports import ReportService

router = APIRouter()
log = structlog.get_logger("codeask.api.sessions")

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
    visible_rows = [row for row in rows if _is_visible_trace(row)]
    visible_rows.sort(key=lambda row: (row.created_at, _trace_event_priority(row), row.id))
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
        storage_dirs = await _collect_session_storage_dirs(
            session,
            request.app.state.settings.data_dir,
            [session_id],
        )
        await session.delete(row)
        await session.commit()

    _remove_session_storage_dirs(storage_dirs)


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
        storage_dirs = await _collect_session_storage_dirs(
            session,
            request.app.state.settings.data_dir,
            list(owned_ids),
        )
        for row in rows:
            await session.delete(row)
        await session.commit()

    deleted_ids = [session_id for session_id in requested if session_id in owned_ids]
    _remove_session_storage_dirs(storage_dirs)
    return SessionBulkDeleteResponse(deleted_ids=deleted_ids)


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

    orchestrator = request.app.state.agent_orchestrator
    multiplexer = SSEMultiplexer()

    async def stream() -> AsyncIterator[bytes]:
        assistant_chunks: list[str] = []
        completed = False
        async for event in orchestrator.run(
            session_id,
            turn_id,
            payload.content,
            force_code_investigation=payload.force_code_investigation,
        ):
            if event.type == "text_delta":
                delta = event.data.get("delta") or event.data.get("text")
                if isinstance(delta, str):
                    assistant_chunks.append(delta)
            if event.type == "done":
                completed = True
            yield multiplexer.format(event)
        if completed:
            content = "".join(assistant_chunks).strip()
            if content:
                await _persist_agent_turn(request, session_id, content)

    return StreamingResponse(stream(), media_type="text/event-stream")


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
        if not _has_completed_question_answer(list(turns)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="至少完成一次问答后才能生成问题定位报告",
            )
        report_id = await ReportService().create_draft(
            session,
            feature_id=payload.feature_id,
            title=payload.title,
            body_markdown=_report_body_from_turns(payload.title, list(turns)),
            metadata={"source": "session", "session_id": session_id},
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
    filename = _attachment_display_name(file.filename)
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
        description=_attachment_description(description),
        file_path=str(target),
        mime_type=file.content_type or "application/octet-stream",
        size_bytes=len(content),
    )
    factory = request.app.state.session_factory
    async with factory() as session:
        session.add(row)
        await session.commit()
        await session.refresh(row)
    await _write_session_manifest(request, session_id)
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
            display_name = _attachment_display_name(payload.display_name)
            if not display_name:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="display name must not be empty",
                )
            row.display_name = display_name
            row.aliases_json = _append_attachment_alias(row.aliases_json, display_name)
        if "description" in fields:
            row.description = _attachment_description(payload.description)
        await session.commit()
        await session.refresh(row)
    await _write_session_manifest(request, session_id)
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

    await _write_session_manifest(request, session_id)
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


def _attachment_display_name(value: str) -> str:
    return Path(value.strip()).name.strip()


def _is_visible_trace(row: AgentTrace) -> bool:
    if row.event_type != "llm_event":
        return True
    payload = _agent_trace_payload(row)
    return payload.get("type") in {"message_start", "tool_call_done", "error"}


def _trace_event_priority(row: AgentTrace) -> int:
    priorities = {
        "stage_enter": 0,
        "llm_input": 1,
        "scope_decision": 2,
        "sufficiency_decision": 2,
        "tool_call": 3,
        "tool_result": 4,
        "stage_exit": 9,
    }
    if row.event_type == "llm_event":
        payload = _agent_trace_payload(row)
        llm_type = payload.get("type")
        if llm_type == "message_start":
            return 1
        if llm_type == "tool_call_done":
            return 3
        if llm_type == "error":
            return 8
    return priorities.get(row.event_type, 5)


def _agent_trace_payload(row: AgentTrace) -> dict[str, Any]:
    payload: Any = row.payload
    if isinstance(payload, dict):
        return cast(dict[str, Any], payload)
    return {}


async def _collect_session_storage_dirs(
    session: AsyncSession,
    data_dir: Path,
    session_ids: list[str],
) -> list[Path]:
    unique_session_ids = list(dict.fromkeys(session_ids))
    dirs: dict[str, Path] = {}
    for session_id in unique_session_ids:
        storage_dir = data_dir / "sessions" / session_id
        dirs[str(storage_dir)] = storage_dir

    if not unique_session_ids:
        return list(dirs.values())

    rows = (
        await session.execute(
            select(SessionAttachment.session_id, SessionAttachment.file_path).where(
                SessionAttachment.session_id.in_(unique_session_ids)
            )
        )
    ).all()
    for row in rows:
        attachment_storage_dir = _session_storage_dir_from_attachment_path(
            row.file_path,
            row.session_id,
        )
        if attachment_storage_dir is not None:
            dirs[str(attachment_storage_dir)] = attachment_storage_dir
    return list(dirs.values())


def _session_storage_dir_from_attachment_path(file_path: str, session_id: str) -> Path | None:
    path = Path(file_path)
    for candidate in path.parents:
        if candidate.name == session_id and candidate.parent.name == "sessions":
            return candidate
    return None


def _remove_session_storage_dirs(storage_dirs: list[Path]) -> None:
    for storage_dir in storage_dirs:
        try:
            shutil.rmtree(storage_dir)
        except FileNotFoundError:
            continue
        except OSError as exc:
            log.warning(
                "session_storage_cleanup_failed",
                path=str(storage_dir),
                error=str(exc),
            )


def _attachment_description(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    return cleaned or None


def _append_attachment_alias(current: list[str] | None, value: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in [*(current or []), value]:
        cleaned = str(item or "").strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


async def _write_session_manifest(request: Request, session_id: str) -> None:
    storage_dir = request.app.state.settings.data_dir / "sessions" / session_id
    storage_dir.mkdir(parents=True, exist_ok=True)
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
    manifest = {
        "session_id": session_id,
        "storage_dir": str(storage_dir),
        "attachments": [_attachment_manifest_entry(row) for row in rows],
    }
    manifest_path = storage_dir / "manifest.json"
    temp_path = storage_dir / "manifest.json.tmp"
    temp_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(manifest_path)


def _attachment_manifest_entry(row: SessionAttachment) -> dict[str, Any]:
    return {
        "id": row.id,
        "kind": row.kind,
        "display_name": row.display_name,
        "original_filename": row.original_filename,
        "aliases": row.aliases,
        "reference_names": row.reference_names,
        "description": row.description,
        "stored_filename": Path(row.file_path).name,
        "file_path": row.file_path,
        "mime_type": row.mime_type,
        "size_bytes": row.size_bytes,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


async def _persist_agent_turn(request: Request, session_id: str, content: str) -> None:
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


def _has_completed_question_answer(turns: list[SessionTurn]) -> bool:
    has_user_question = False
    for turn in turns:
        if turn.role == "user" and turn.content.strip():
            has_user_question = True
        if turn.role == "agent" and turn.content.strip() and has_user_question:
            return True
    return False


def _report_body_from_turns(title: str, turns: list[SessionTurn]) -> str:
    if not turns:
        return f"# {title}\n\n本报告由会话生成，当前会话尚无可汇总的消息。"
    lines = [f"# {title}", "", "## 会话摘要"]
    for turn in turns[-10:]:
        label = "用户" if turn.role == "user" else "助手"
        lines.append(f"- {label}: {turn.content}")
    return "\n".join(lines)
