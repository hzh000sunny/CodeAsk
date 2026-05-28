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
from codeask.wiki.chunker import DocumentChunker
from codeask.wiki.search_grouping import group_for_search_hit


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
    heading_path: str | None = None
    document_id: int | None = None
    report_id: int | None = None


class NativeWikiSearchService:
    def __init__(self) -> None:
        self._chunker = DocumentChunker()

    async def search(
        self,
        session: AsyncSession,
        query: str,
        *,
        feature_id: int | None = None,
        current_feature_id: int | None = None,
        limit: int = 20,
    ) -> list[NativeWikiSearchHit]:
        needle = query.strip()
        if not needle:
            return []

        grouping_feature_id = current_feature_id if current_feature_id is not None else feature_id
        lowered = needle.lower()
        pattern = f"%{needle}%"
        hits: list[NativeWikiSearchHit] = []

        document_filters = [
            WikiNode.deleted_at.is_(None),
            or_(
                WikiDocument.title.ilike(pattern),
                WikiDocumentVersion.body_markdown.ilike(pattern),
            ),
        ]
        if feature_id is not None:
            document_filters.append(WikiSpace.feature_id == feature_id)
        document_rows = (
            await session.execute(
                select(
                    WikiNode,
                    WikiDocument,
                    WikiDocumentVersion,
                    WikiSpace.feature_id,
                    WikiSpace.scope,
                    WikiSpace.status,
                )
                .join(WikiDocument, WikiDocument.node_id == WikiNode.id)
                .join(
                    WikiDocumentVersion,
                    WikiDocumentVersion.id == WikiDocument.current_version_id,
                )
                .join(WikiSpace, WikiSpace.id == WikiNode.space_id)
                .where(*document_filters)
                .order_by(WikiNode.updated_at.desc(), WikiNode.id.desc())
            )
        ).all()
        for (
            node,
            document,
            version,
            document_feature_id,
            space_scope,
            space_status,
        ) in document_rows:
            group_key, group_label = group_for_search_hit(
                kind="document",
                hit_feature_id=document_feature_id,
                grouping_feature_id=grouping_feature_id,
                space_scope=space_scope,
                space_status=space_status,
            )
            hits.append(
                NativeWikiSearchHit(
                    kind="document",
                    node_id=int(node.id),
                    title=document.title,
                    path=node.path,
                    feature_id=document_feature_id,
                    group_key=group_key,
                    group_label=group_label,
                    snippet=_snippet(version.body_markdown, lowered),
                    score=_score(document.title, version.body_markdown, lowered),
                    heading_path=_best_heading_path(
                        self._chunker,
                        title=document.title,
                        body=version.body_markdown,
                        lowered_query=lowered,
                    ),
                    document_id=int(document.id),
                )
            )

        report_filters = [
            WikiNode.deleted_at.is_(None),
            or_(Report.title.ilike(pattern), Report.body_markdown.ilike(pattern)),
        ]
        if feature_id is not None:
            report_filters.append(WikiSpace.feature_id == feature_id)
        report_rows = (
            await session.execute(
                select(
                    WikiNode,
                    WikiReportRef,
                    Report,
                    WikiSpace.feature_id,
                    WikiSpace.scope,
                    WikiSpace.status,
                )
                .join(WikiReportRef, WikiReportRef.node_id == WikiNode.id)
                .join(Report, Report.id == WikiReportRef.report_id)
                .join(WikiSpace, WikiSpace.id == WikiNode.space_id)
                .where(*report_filters)
                .order_by(Report.updated_at.desc(), Report.id.desc())
            )
        ).all()
        for node, report_ref, report, report_feature_id, space_scope, space_status in report_rows:
            group_key, group_label = group_for_search_hit(
                kind="report_ref",
                hit_feature_id=report_feature_id,
                grouping_feature_id=grouping_feature_id,
                space_scope=space_scope,
                space_status=space_status,
            )
            hits.append(
                NativeWikiSearchHit(
                    kind="report_ref",
                    node_id=int(node.id),
                    title=report.title,
                    path=node.path,
                    feature_id=report_feature_id,
                    group_key=group_key,
                    group_label=group_label,
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


def _best_heading_path(
    chunker: DocumentChunker,
    *,
    title: str,
    body: str,
    lowered_query: str,
) -> str | None:
    if not body:
        return None
    try:
        chunks = chunker.chunk_markdown(body)
    except Exception:
        return None
    if not chunks:
        return title.strip() or None

    for chunk in chunks:
        if not chunk.heading_path:
            continue
        haystack = f"{chunk.heading_path}\n{chunk.raw_text}".lower()
        if lowered_query in haystack:
            return chunk.heading_path

    for chunk in chunks:
        if chunk.heading_path:
            return chunk.heading_path
    return title.strip() or None
