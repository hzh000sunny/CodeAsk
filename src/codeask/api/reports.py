"""REST router for report lifecycle."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from dataclasses import asdict

from codeask.api.schemas.wiki import ReportCreate, ReportRead, ReportUpdate
from codeask.api.schemas.wiki import ReportSearchHit as ReportSearchHitSchema
from codeask.api.wiki.deps import SessionDep
from codeask.db.models import Report
from codeask.wiki.reports import ReportService, ReportVerificationError
from codeask.wiki.search import WikiSearchService
from codeask.wiki.sync import LegacyWikiSyncService

router = APIRouter(prefix="/reports")


@router.get("", response_model=list[ReportRead])
async def list_reports(session: SessionDep, feature_id: int | None = None) -> list[ReportRead]:
    stmt = select(Report)
    if feature_id is not None:
        stmt = stmt.where(Report.feature_id == feature_id)
    rows = (await session.execute(stmt.order_by(Report.id))).scalars().all()
    return [ReportRead.model_validate(row) for row in rows]


@router.post("", response_model=ReportRead, status_code=status.HTTP_201_CREATED)
async def create_report(
    payload: ReportCreate,
    request: Request,
    session: SessionDep,
) -> ReportRead:
    sync_service = LegacyWikiSyncService()
    report_id = await ReportService().create_draft(
        session,
        feature_id=payload.feature_id,
        title=payload.title,
        body_markdown=payload.body_markdown,
        metadata=payload.metadata,
        subject_id=request.state.subject_id,
    )
    await sync_service.sync_report_ref(
        session,
        report_id=report_id,
        feature_id=payload.feature_id,
        title=payload.title,
    )
    await session.commit()
    report = (await session.execute(select(Report).where(Report.id == report_id))).scalar_one()
    return ReportRead.model_validate(report)


@router.get("/search", response_model=list[ReportSearchHitSchema])
async def search_reports(
    session: SessionDep,
    q: str,
    feature_id: int | None = None,
    limit: int = 20,
) -> list[ReportSearchHitSchema]:
    hits = await WikiSearchService().search_reports(session, q, feature_id=feature_id, limit=limit)
    return [ReportSearchHitSchema(**asdict(hit)) for hit in hits]


@router.get("/{report_id}", response_model=ReportRead)
async def get_report(report_id: int, session: SessionDep) -> ReportRead:
    report = (
        await session.execute(select(Report).where(Report.id == report_id))
    ).scalar_one_or_none()
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="report not found")
    return ReportRead.model_validate(report)


@router.put("/{report_id}", response_model=ReportRead)
async def update_report(
    report_id: int,
    payload: ReportUpdate,
    session: SessionDep,
) -> ReportRead:
    sync_service = LegacyWikiSyncService()
    try:
        await ReportService().update_draft(
            session,
            report_id=report_id,
            title=payload.title,
            body_markdown=payload.body_markdown,
            metadata=payload.metadata,
        )
    except ReportVerificationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    report = (await session.execute(select(Report).where(Report.id == report_id))).scalar_one()
    await sync_service.sync_report_ref(
        session,
        report_id=report_id,
        feature_id=report.feature_id,
        title=report.title,
    )
    await session.commit()
    return ReportRead.model_validate(report)


@router.post("/{report_id}/verify", response_model=ReportRead)
async def verify_report(
    report_id: int,
    request: Request,
    session: SessionDep,
) -> ReportRead:
    try:
        await ReportService().verify(
            session, report_id=report_id, subject_id=request.state.subject_id
        )
    except ReportVerificationError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    await session.commit()
    report = (await session.execute(select(Report).where(Report.id == report_id))).scalar_one()
    return ReportRead.model_validate(report)


@router.post("/{report_id}/unverify", response_model=ReportRead)
async def unverify_report(
    report_id: int,
    request: Request,
    session: SessionDep,
) -> ReportRead:
    await ReportService().unverify(
        session, report_id=report_id, subject_id=request.state.subject_id
    )
    await session.commit()
    report = (await session.execute(select(Report).where(Report.id == report_id))).scalar_one()
    return ReportRead.model_validate(report)


@router.post("/{report_id}/reject", response_model=ReportRead)
async def reject_report(
    report_id: int,
    request: Request,
    session: SessionDep,
) -> ReportRead:
    await ReportService().reject(
        session, report_id=report_id, subject_id=request.state.subject_id
    )
    await session.commit()
    report = (await session.execute(select(Report).where(Report.id == report_id))).scalar_one()
    return ReportRead.model_validate(report)


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(report_id: int, request: Request, session: SessionDep) -> None:
    report = (
        await session.execute(select(Report).where(Report.id == report_id))
    ).scalar_one_or_none()
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="report not found")
    from_status = report.status
    from codeask.metrics.audit import record_audit_log
    from codeask.wiki.indexer import WikiIndexer

    await WikiIndexer().unindex_report(session, report_id=report_id)
    await record_audit_log(
        session,
        entity_type="report",
        entity_id=str(report_id),
        action="delete",
        from_status=from_status,
        to_status="deleted",
        subject_id=request.state.subject_id,
    )
    await LegacyWikiSyncService().delete_report_ref(session, report_id=report_id)
    await session.delete(report)
    await session.commit()
