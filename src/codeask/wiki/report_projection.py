"""Projection helpers for exposing reports inside the native wiki workbench."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.db.models import Report, WikiNode, WikiReportRef


@dataclass(slots=True)
class WikiReportProjection:
    node_id: int
    report_id: int
    feature_id: int | None
    title: str
    status: str
    status_group: str
    verified: bool
    verified_by: str | None
    verified_at: object | None
    updated_at: object


@dataclass(slots=True)
class WikiReportDetail:
    node_id: int
    report_id: int
    feature_id: int | None
    title: str
    body_markdown: str
    metadata_json: dict
    status: str
    verified: bool
    verified_by: str | None
    verified_at: object | None
    created_by_subject_id: str
    created_at: object
    updated_at: object


class WikiReportProjectionService:
    async def list_projections(
        self,
        session: AsyncSession,
        *,
        feature_id: int,
    ) -> list[WikiReportProjection]:
        rows = (
            await session.execute(
                select(WikiNode, WikiReportRef, Report)
                .join(WikiReportRef, WikiReportRef.node_id == WikiNode.id)
                .join(Report, Report.id == WikiReportRef.report_id)
                .where(
                    Report.feature_id == feature_id,
                    WikiNode.deleted_at.is_(None),
                )
                .order_by(Report.updated_at.desc(), Report.id.desc())
            )
        ).all()

        projections: list[WikiReportProjection] = []
        for node, report_ref, report in rows:
            projections.append(
                WikiReportProjection(
                    node_id=int(node.id),
                    report_id=int(report_ref.report_id),
                    feature_id=report.feature_id,
                    title=report.title,
                    status=report.status,
                    status_group=_status_group(report.status, report.verified),
                    verified=report.verified,
                    verified_by=report.verified_by,
                    verified_at=report.verified_at,
                    updated_at=report.updated_at,
                )
            )
        return projections

    async def get_report_by_node(
        self,
        session: AsyncSession,
        *,
        node_id: int,
    ) -> WikiReportDetail:
        row = (
            await session.execute(
                select(WikiNode, WikiReportRef, Report)
                .join(WikiReportRef, WikiReportRef.node_id == WikiNode.id)
                .join(Report, Report.id == WikiReportRef.report_id)
                .where(
                    WikiNode.id == node_id,
                    WikiNode.deleted_at.is_(None),
                )
            )
        ).one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="wiki report projection not found",
            )

        node, report_ref, report = row
        metadata_json = report.metadata_json if isinstance(report.metadata_json, dict) else {}
        return WikiReportDetail(
            node_id=int(node.id),
            report_id=int(report_ref.report_id),
            feature_id=report.feature_id,
            title=report.title,
            body_markdown=report.body_markdown,
            metadata_json=metadata_json,
            status=report.status,
            verified=report.verified,
            verified_by=report.verified_by,
            verified_at=report.verified_at,
            created_by_subject_id=report.created_by_subject_id,
            created_at=report.created_at,
            updated_at=report.updated_at,
        )


def _status_group(status: str, verified: bool) -> str:
    if verified or status == "verified":
        return "verified"
    if status == "rejected":
        return "rejected"
    return "draft"
