"""Native wiki-backed search and read tools for the agent runtime."""

from __future__ import annotations

from dataclasses import asdict
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from codeask.agent.tool_models import ToolContext, ToolResult
from codeask.db.models import Feature, WikiDocument, WikiNode, WikiReportRef, WikiSpace
from codeask.wiki.actor import WikiActor
from codeask.wiki.documents.service import WikiDocumentService
from codeask.wiki.path_resolver import WikiPathResolver
from codeask.wiki.native_search import NativeWikiSearchService
from codeask.wiki.report_projection import WikiReportProjectionService

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


class AgentWikiToolService:
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory
        self._native_search = NativeWikiSearchService()
        self._document_service = WikiDocumentService()
        self._path_resolver = WikiPathResolver()
        self._report_projection = WikiReportProjectionService()

    async def describe_scope(
        self,
        query: str,
        feature_ids: list[int],
    ) -> dict[str, object] | None:
        selected_feature_ids = _ordered_unique_feature_ids(feature_ids)
        if not selected_feature_ids:
            return None

        default_payload: list[dict[str, object]] = []
        match_payload: list[dict[str, object]] = []
        async with self._factory() as session:
            for feature_id in selected_feature_ids:
                space = (
                    await session.execute(
                        select(WikiSpace).where(
                            WikiSpace.feature_id == feature_id,
                            WikiSpace.scope == "current",
                        )
                    )
                ).scalar_one_or_none()
                if space is None:
                    continue

                default_nodes = (
                    await session.execute(
                        select(WikiNode)
                        .where(
                            WikiNode.space_id == space.id,
                            WikiNode.deleted_at.is_(None),
                            WikiNode.system_role.in_(("knowledge_base", "reports")),
                        )
                        .order_by(WikiNode.sort_order.asc(), WikiNode.path.asc(), WikiNode.id.asc())
                    )
                ).scalars().all()
                matches = await self._path_resolver.resolve_path(
                    session,
                    query,
                    feature_id=feature_id,
                    limit=5,
                )

                default_payload.extend(
                    {
                        "feature_id": feature_id,
                        "node_id": int(node.id),
                        "path": node.path,
                        "label": node.name,
                        "system_role": node.system_role,
                    }
                    for node in default_nodes
                )
                default_node_ids = {int(node.id) for node in default_nodes}
                match_payload.extend(
                    {
                        "feature_id": feature_id,
                        "node_id": hit.node_id,
                        "path": hit.path,
                        "label": hit.name,
                        "match_reason": hit.match_reason,
                        "matched_phrase": hit.matched_phrase,
                    }
                    for hit in matches
                    if hit.node_id not in default_node_ids
                )

        if not default_payload and not match_payload:
            return None
        return {
            "feature_id": selected_feature_ids[0],
            "feature_ids": selected_feature_ids,
            "query": query,
            "defaults": default_payload,
            "matches": match_payload,
        }

    async def search(
        self,
        query: str,
        feature_ids: list[int],
        top_k: int = 8,
    ) -> list[dict[str, object]]:
        selected_feature_ids = _ordered_unique_feature_ids(feature_ids)
        current_feature_id = selected_feature_ids[0] if selected_feature_ids else None
        async with self._factory() as session:
            if not selected_feature_ids:
                hits = await self._native_search.search(
                    session,
                    query,
                    feature_id=None,
                    current_feature_id=None,
                    limit=top_k,
                )
            else:
                hits = await self._search_selected_features(
                    session,
                    query=query,
                    feature_ids=selected_feature_ids,
                    current_feature_id=current_feature_id,
                    limit=top_k,
                )
                if not hits:
                    fallback_queries = await self._feature_fallback_queries(
                        session,
                        feature_ids=selected_feature_ids,
                    )
                    for fallback_query in fallback_queries:
                        hits = await self._search_selected_features(
                            session,
                            query=fallback_query,
                            feature_ids=selected_feature_ids,
                            current_feature_id=current_feature_id,
                            limit=top_k,
                        )
                        if hits:
                            break

        deduped_hits = list(_dedupe_hits(hits))
        deduped_hits.sort(key=lambda item: item.score, reverse=True)
        items: list[dict[str, object]] = []
        for hit in deduped_hits[:top_k]:
            payload = {
                "source": "report" if hit.kind == "report_ref" else "doc",
                "title": hit.title,
                "summary": hit.snippet,
                "score": hit.score,
                "node_id": hit.node_id,
                "path": hit.path,
                "feature_id": hit.feature_id,
                "heading_path": hit.heading_path,
            }
            if hit.document_id is not None:
                payload["document_id"] = hit.document_id
            if hit.report_id is not None:
                payload["report_id"] = hit.report_id
            items.append(payload)
        return items

    async def _search_selected_features(
        self,
        session: AsyncSession,
        *,
        query: str,
        feature_ids: list[int],
        current_feature_id: int | None,
        limit: int,
    ) -> list[object]:
        hits: list[object] = []
        for feature_id in feature_ids:
            hits.extend(
                await self._native_search.search(
                    session,
                    query,
                    feature_id=feature_id,
                    current_feature_id=current_feature_id,
                    limit=limit,
                )
            )
        return hits

    async def _feature_fallback_queries(
        self,
        session: AsyncSession,
        *,
        feature_ids: list[int],
    ) -> list[str]:
        rows = (
            await session.execute(
                select(Feature.id, Feature.name, WikiSpace.display_name)
                .join(
                    WikiSpace,
                    (WikiSpace.feature_id == Feature.id) & (WikiSpace.scope == "current"),
                    isouter=True,
                )
                .where(Feature.id.in_(feature_ids))
            )
        ).all()
        variants: list[str] = []
        for _feature_id, feature_name, space_display_name in rows:
            for value in (feature_name, space_display_name):
                if not isinstance(value, str):
                    continue
                normalized = value.strip()
                if normalized and normalized not in variants:
                    variants.append(normalized)
        return variants

    async def search_wiki(self, args: dict[str, object], ctx: ToolContext) -> ToolResult:
        query = str(args["query"])
        top_k = int(args.get("top_k") or 8)
        items = await self.search(query, ctx.feature_ids, top_k)
        documents = [item for item in items if item.get("source") == "doc"]
        return ToolResult(
            ok=True,
            summary=f"找到 {len(documents)} 条 Wiki 文档候选",
            data={"items": documents},
        )

    async def search_reports(self, args: dict[str, object], ctx: ToolContext) -> ToolResult:
        query = str(args["query"])
        top_k = int(args.get("top_k") or 8)
        items = await self.search(query, ctx.feature_ids, top_k)
        reports = [item for item in items if item.get("source") == "report"]
        return ToolResult(
            ok=True,
            summary=f"找到 {len(reports)} 条问题报告候选",
            data={"items": reports},
        )

    async def read_wiki_doc(self, args: dict[str, object], ctx: ToolContext) -> ToolResult:
        document_id = int(args["document_id"])
        async with self._factory() as session:
            document = (
                await session.execute(select(WikiDocument).where(WikiDocument.id == document_id))
            ).scalar_one_or_none()
            if document is None:
                return ToolResult(
                    ok=False,
                    error_code="WIKI_DOC_NOT_FOUND",
                    message=f"wiki document {document_id} not found",
                )
            return await self._read_document_node(
                session,
                node_id=int(document.node_id),
                ctx=ctx,
                heading_path=args.get("heading_path"),
                document_id=document_id,
            )

    async def read_wiki_node(self, args: dict[str, object], ctx: ToolContext) -> ToolResult:
        async with self._factory() as session:
            return await self._read_document_node(
                session,
                node_id=int(args["node_id"]),
                ctx=ctx,
                heading_path=args.get("heading_path"),
                document_id=None,
            )

    async def read_report(self, args: dict[str, object], ctx: ToolContext) -> ToolResult:
        report_id = int(args["report_id"])
        del ctx
        async with self._factory() as session:
            report_ref = (
                await session.execute(select(WikiReportRef).where(WikiReportRef.report_id == report_id))
            ).scalar_one_or_none()
            if report_ref is None:
                return ToolResult(
                    ok=False,
                    error_code="WIKI_REPORT_NOT_FOUND",
                    message=f"wiki report {report_id} not found",
                )
            detail = await self._report_projection.get_report_by_node(
                session,
                node_id=int(report_ref.node_id),
            )
        payload = asdict(detail)
        return ToolResult(
            ok=True,
            summary=f"已读取问题报告《{detail.title}》",
            data=payload,
        )

    async def _read_document_node(
        self,
        session: AsyncSession,
        *,
        node_id: int,
        ctx: ToolContext,
        heading_path: object,
        document_id: int | None,
    ) -> ToolResult:
        heading = str(heading_path) if isinstance(heading_path, str) and heading_path.strip() else None
        try:
            node, document = await self._document_service.load_document_by_node(session, node_id=node_id)
        except Exception:
            return ToolResult(
                ok=False,
                error_code="WIKI_DOC_NOT_FOUND",
                message=f"wiki node {node_id} not found or is not a document",
            )
        detail = await self._document_service.get_document_detail(
            session,
            node_id=int(node.id),
            actor=WikiActor(subject_id=ctx.subject_id, role="member"),
        )
        body_markdown = str(detail.get("current_body_markdown") or "")
        excerpt_markdown = _extract_heading_excerpt(body_markdown, heading) if heading else body_markdown
        return ToolResult(
            ok=True,
            summary=f"已读取 Wiki 文档《{detail['title']}》",
            data={
                "document_id": document_id or int(document.id),
                "node_id": detail["node_id"],
                "title": detail["title"],
                "path": node.path,
                "heading_path": heading,
                "body_markdown": body_markdown,
                "excerpt_markdown": excerpt_markdown,
                "resolved_refs_json": detail.get("resolved_refs_json"),
                "broken_refs_json": detail.get("broken_refs_json"),
            },
        )


def _extract_heading_excerpt(body_markdown: str, heading_path: str | None) -> str:
    if not body_markdown or not heading_path:
        return body_markdown
    target = heading_path.split("/")[-1].split(">")[-1].strip().lower()
    if not target:
        return body_markdown

    matches = list(_HEADING_RE.finditer(body_markdown))
    for index, match in enumerate(matches):
        heading_text = match.group(2).strip().lower()
        if heading_text != target:
            continue
        level = len(match.group(1))
        start = match.start()
        end = len(body_markdown)
        for next_match in matches[index + 1 :]:
            if len(next_match.group(1)) <= level:
                end = next_match.start()
                break
        return body_markdown[start:end].strip()
    return body_markdown


def _ordered_unique_feature_ids(feature_ids: list[int]) -> list[int]:
    seen: set[int] = set()
    ordered: list[int] = []
    for feature_id in feature_ids:
        if feature_id in seen:
            continue
        seen.add(feature_id)
        ordered.append(feature_id)
    return ordered


def _dedupe_hits(hits: list[object]) -> list[object]:
    seen: set[tuple[object, ...]] = set()
    deduped: list[object] = []
    for hit in hits:
        key = (
            getattr(hit, "kind", None),
            getattr(hit, "document_id", None),
            getattr(hit, "report_id", None),
            getattr(hit, "node_id", None),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(hit)
    return deduped
