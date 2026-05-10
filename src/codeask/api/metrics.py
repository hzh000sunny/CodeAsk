"""Metrics REST API: feedback, frontend events, and audit-log reads."""

from datetime import UTC
from secrets import token_hex

import structlog
from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.elements import ColumnElement

from codeask.api.schemas.metrics import (
    AuditLogEntry,
    AuditLogResponse,
    FeedbackAck,
    FeedbackCreate,
    FrontendEventAck,
    FrontendEventCreate,
)
from codeask.db.models import AuditLog, Feedback, FrontendEvent
from codeask.identity import require_admin

router = APIRouter()
log = structlog.get_logger("codeask.api.metrics")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{token_hex(12)}"


@router.post("/feedback", response_model=FeedbackAck, status_code=status.HTTP_201_CREATED)
async def post_feedback(payload: FeedbackCreate, request: Request) -> FeedbackAck:
    factory = request.app.state.session_factory
    async with factory() as session:
        session.add(
            Feedback(
                id=_new_id("fb"),
                session_turn_id=payload.session_turn_id,
                feedback=payload.feedback,
                note=payload.note,
                subject_id=request.state.subject_id,
            )
        )
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="session turn not found",
            ) from exc

    log.info(
        "feedback_recorded",
        session_turn_id=payload.session_turn_id,
        feedback=payload.feedback,
    )
    return FeedbackAck()


@router.post("/events", response_model=FrontendEventAck, status_code=status.HTTP_201_CREATED)
async def post_event(payload: FrontendEventCreate, request: Request) -> FrontendEventAck:
    factory = request.app.state.session_factory
    event_id = _new_id("ev")
    async with factory() as session:
        session.add(
            FrontendEvent(
                id=event_id,
                event_type=payload.event_type,
                session_id=payload.session_id,
                subject_id=request.state.subject_id,
                payload=payload.payload,
            )
        )
        await session.commit()

    log.info(
        "frontend_event_recorded",
        event_type=payload.event_type,
        session_id=payload.session_id,
    )
    return FrontendEventAck(id=event_id)


@router.get("/audit-log", response_model=AuditLogResponse)
async def list_audit_log(
    request: Request,
    entity_type: str | None = Query(default=None, min_length=1, max_length=64),
    entity_id: str | None = Query(default=None, min_length=1, max_length=64),
    action: str | None = Query(default=None, min_length=1, max_length=64),
    subject: str | None = Query(default=None, min_length=1, max_length=128),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> AuditLogResponse:
    require_admin(request)
    factory = request.app.state.session_factory
    conditions: list[ColumnElement[bool]] = []
    if entity_type is not None:
        conditions.append(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        conditions.append(AuditLog.entity_id == entity_id)
    if action is not None:
        conditions.append(AuditLog.action == action)
    if subject is not None:
        conditions.append(AuditLog.subject_id == subject)

    stmt = select(AuditLog)
    if conditions:
        stmt = stmt.where(*conditions)
    stmt = stmt.order_by(AuditLog.at.desc()).offset(offset).limit(limit)
    async with factory() as session:
        rows = (await session.execute(stmt)).scalars().all()
    entries: list[AuditLogEntry] = []
    for row in rows:
        at = row.at if row.at.tzinfo else row.at.replace(tzinfo=UTC)
        entries.append(
            AuditLogEntry(
                id=row.id,
                entity_type=row.entity_type,
                entity_id=row.entity_id,
                action=row.action,
                from_status=row.from_status,
                to_status=row.to_status,
                subject_id=row.subject_id,
                at=at,
            )
        )
    return AuditLogResponse(entries=entries)
