"""Search the native wiki document/report surfaces used by the workbench."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.db.models import (
    Report,
    WikiDocument,
    WikiDocumentVersion,
    WikiNode,
    WikiReportRef,
    WikiSpace,
)


@dataclass(slots=True)
class NativeWikiSearchHit:
    kind: str
    node_id: int
    title: str
    path: str
    feature_id: int | None
    group_key: str
    group_label: str
    snippet: str
    score: float
    document_id: int | None = None
    report_id: int | None = None


class NativeWikiSearchService:
    async def search(
        self,
        session: AsyncSession,
        query: str,
        *,
        feature_id: int | None = None,
        limit: int = 20,
    ) -> list[NativeWikiSearchHit]:
        needle = query.strip()
        if not needle:
            return []

        lowered = needle.lower()
        pattern = f"%{needle}%"
        casefold_pattern = f"%{lowered}%"
        hits: list[NativeWikiSearchHit] = []

        document_rows = (
            await session.execute(
                select(WikiNode, WikiDocument, WikiDocumentVersion, WikiSpace.feature_id)
                .join(WikiDocument, WikiDocument.node_id == WikiNode.id)
                .join(
                    WikiDocumentVersion,
                    WikiDocumentVersion.id == WikiDocument.current_version_id,
                )
                .join(WikiSpace, WikiSpace.id == WikiNode.space_id)
                .where(
                    WikiNode.deleted_at.is_(None),
                    WikiSpace.feature_id == feature_id if feature_id is not None else True,
                    or_(
                        WikiDocument.title.ilike(pattern),
                        WikiDocumentVersion.body_markdown.ilike(pattern),
                    ),
                )
                .order_by(WikiNode.updated_at.desc(), WikiNode.id.desc())
            )
        ).all()
        for node, document, version, document_feature_id in document_rows:
            hits.append(
                NativeWikiSearchHit(
                    kind="document",
                    node_id=int(node.id),
                    title=document.title,
                    path=node.path,
                    feature_id=document_feature_id,
                    group_key="current_feature" if feature_id is not None else "all_documents",
                    group_label="当前特性" if feature_id is not None else "全部文档",
                    snippet=_snippet(version.body_markdown, lowered),
                    score=_score(document.title, version.body_markdown, lowered),
                    document_id=int(document.id),
                )
            )

        report_rows = (
            await session.execute(
                select(WikiNode, WikiReportRef, Report)
                .join(WikiReportRef, WikiReportRef.node_id == WikiNode.id)
                .join(Report, Report.id == WikiReportRef.report_id)
                .where(
                    WikiNode.deleted_at.is_(None),
                    or_(Report.title.ilike(pattern), Report.body_markdown.ilike(pattern)),
                )
                .order_by(Report.updated_at.desc(), Report.id.desc())
            )
        ).all()
        for node, report_ref, report in report_rows:
            if feature_id is not None and report.feature_id != feature_id:
                continue
            hits.append(
                NativeWikiSearchHit(
                    kind="report_ref",
                    node_id=int(node.id),
                    title=report.title,
                    path=node.path,
                    feature_id=report.feature_id,
                    group_key="current_feature_reports"
                    if feature_id is not None and report.feature_id == feature_id
                    else "reports",
                    group_label="问题定位报告"
                    if feature_id is not None and report.feature_id == feature_id
                    else "报告",
                    snippet=_snippet(report.body_markdown, lowered),
                    score=_score(report.title, report.body_markdown, lowered),
                    report_id=int(report_ref.report_id),
                )
            )

        hits.sort(key=lambda item: item.score, reverse=True)
        return hits[:limit]


def _score(title: str, body: str, lowered_query: str) -> float:
    score = 1.0
    if lowered_query in title.lower():
        score += 3.0
    if lowered_query in body.lower():
        score += 1.0
    return score


def _snippet(body: str, lowered_query: str, *, radius: int = 64) -> str:
    lowered_body = body.lower()
    index = lowered_body.find(lowered_query)
    if index < 0:
        return body[: radius * 2].strip()
    start = max(index - radius, 0)
    end = min(index + len(lowered_query) + radius, len(body))
    return body[start:end].strip()
