"""Wiki read tools for the chat runtime."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from codeask.agent.chat_runtime.events import EvidenceRef
from codeask.agent.chat_runtime.tool_contracts import (
    ToolContext,
    ToolErrorType,
    ToolResult,
    ToolSpec,
)
from codeask.agent.chat_runtime.tool_registry import ToolRegistry
from codeask.db.models import WikiDocument, WikiDocumentVersion, WikiNode, WikiSpace
from codeask.wiki.native_search import NativeWikiSearchService


class SearchWikiInput(BaseModel):
    query: str = Field(
        ...,
        description=(
            "必填。用于搜索 Wiki 的自然语言关键词或用户问题。"
            "如果只有标题/路径但没有 node_id，也先用这里搜索。"
        ),
    )
    feature_ids: list[int] = Field(
        default_factory=list,
        description="可选。模型判断相关的特性 ID 列表；不确定时留空做全局搜索。",
    )
    node_ids: list[int] = Field(
        default_factory=list,
        description="可选。只搜索这些已知 Wiki node_id；不要填标题、路径或目录名。",
    )
    limit: int = Field(default=5, description="可选。返回候选数量，默认 5。")
    offset: int = Field(default=0, description="可选。分页偏移，默认 0。")


class ReadWikiNodeInput(BaseModel):
    node_id: int = Field(
        ...,
        description=(
            "必填。只能使用 RAG 候选上下文或 search_wiki 返回的明确 node_id。"
            "不要猜测，不要把标题、路径、document_id 或目录名填到这里。"
        ),
    )
    heading: str | None = Field(
        default=None,
        description="可选。只读取指定 Markdown 标题下的内容；不确定时留空。",
    )
    max_chars: int = Field(
        default=12_000,
        description="可选。最大读取字符数，默认 12000。",
    )


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


def register_wiki_tools(
    registry: ToolRegistry,
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    fake_search_results: list[dict[str, Any]] | None = None,
    fake_nodes: dict[int, dict[str, Any]] | None = None,
) -> None:
    search_results = fake_search_results or []
    nodes = fake_nodes or {}
    native_search = NativeWikiSearchService()

    async def search_wiki(args: SearchWikiInput, ctx: ToolContext) -> ToolResult:
        if session_factory is not None:
            return await _search_real_wiki(
                session_factory,
                native_search,
                args,
            )

        items = search_results[args.offset : args.offset + args.limit]
        evidence_refs = [
            EvidenceRef(
                type="wiki",
                title=str(item.get("title")) if item.get("title") is not None else None,
                path=str(item.get("path")) if item.get("path") is not None else None,
                node_id=int(item["node_id"]) if item.get("node_id") is not None else None,
            )
            for item in items
        ]
        return ToolResult.ok(
            tool="search_wiki",
            summary=f"命中 {len(items)} 篇 Wiki",
            items=items,
            evidence_refs=evidence_refs,
            truncated=len(search_results) > args.offset + args.limit,
        )

    async def read_wiki_node(args: ReadWikiNodeInput, ctx: ToolContext) -> ToolResult:
        if session_factory is not None:
            return await _read_real_wiki_node(session_factory, args)

        node = nodes.get(args.node_id)
        if node is None:
            return ToolResult.error(
                tool="read_wiki_node",
                error_type=ToolErrorType.NOT_FOUND,
                message=f"wiki node not found: {args.node_id}",
            )
        content = str(node.get("content", ""))
        truncated = len(content) > args.max_chars
        item = {
            **node,
            "node_id": args.node_id,
            "content": content[: args.max_chars],
        }
        return ToolResult.ok(
            tool="read_wiki_node",
            summary=f"读取 Wiki：{node.get('title', args.node_id)}",
            items=[item],
            evidence_refs=[
                EvidenceRef(
                    type="wiki",
                    title=str(node.get("title")) if node.get("title") is not None else None,
                    path=str(node.get("path")) if node.get("path") is not None else None,
                    node_id=args.node_id,
                )
            ],
            truncated=truncated,
            warnings=["Wiki 内容过长，已按 max_chars 截断。"] if truncated else [],
        )

    registry.register(
        ToolSpec(
            name="search_wiki",
            description="搜索 Wiki 文档标题和内容片段，只返回候选证据。",
            input_model=SearchWikiInput,
            read_only=True,
            concurrency_safe=True,
            requires_confirmation=False,
            max_result_size_chars=8_000,
        ),
        search_wiki,
    )
    registry.register(
        ToolSpec(
            name="read_wiki_node",
            description="读取指定 Wiki 文档或 heading 的内容。",
            input_model=ReadWikiNodeInput,
            read_only=True,
            concurrency_safe=True,
            requires_confirmation=False,
            max_result_size_chars=14_000,
        ),
        read_wiki_node,
    )


async def _search_real_wiki(
    session_factory: async_sessionmaker[AsyncSession],
    native_search: NativeWikiSearchService,
    args: SearchWikiInput,
) -> ToolResult:
    feature_ids = _ordered_unique(args.feature_ids)
    async with session_factory() as session:
        if args.node_ids:
            items = await _search_nodes_by_id(session, args.node_ids)
        elif feature_ids:
            hits = []
            for feature_id in feature_ids:
                hits.extend(
                    await _search_wiki_hits_with_fallback(
                        session,
                        native_search,
                        args.query,
                        feature_id=feature_id,
                        current_feature_id=feature_ids[0],
                        limit=args.offset + args.limit,
                    )
                )
            items = [_hit_item(hit) for hit in _dedupe_hits(hits) if hit.kind != "report_ref"]
        else:
            hits = await _search_wiki_hits_with_fallback(
                session,
                native_search,
                args.query,
                feature_id=None,
                current_feature_id=None,
                limit=args.offset + args.limit,
            )
            items = [_hit_item(hit) for hit in _dedupe_hits(hits) if hit.kind != "report_ref"]

    paged_items = items[args.offset : args.offset + args.limit]
    return ToolResult.ok(
        tool="search_wiki",
        summary=f"命中 {len(paged_items)} 篇 Wiki",
        items=paged_items,
        evidence_refs=[
            EvidenceRef(
                type="wiki",
                title=str(item.get("title")) if item.get("title") is not None else None,
                path=str(item.get("path")) if item.get("path") is not None else None,
                node_id=int(item["node_id"]) if item.get("node_id") is not None else None,
                metadata={
                    "feature_id": item.get("feature_id"),
                    "heading_path": item.get("heading_path"),
                },
            )
            for item in paged_items
        ],
        truncated=len(items) > args.offset + args.limit,
    )


async def _search_wiki_hits_with_fallback(
    session: AsyncSession,
    native_search: NativeWikiSearchService,
    query: str,
    *,
    feature_id: int | None,
    current_feature_id: int | None,
    limit: int,
) -> list[Any]:
    hits = await native_search.search(
        session,
        query,
        feature_id=feature_id,
        current_feature_id=current_feature_id,
        limit=limit,
    )
    if hits:
        return hits

    fallback_terms = _fallback_search_terms(query)
    if len(fallback_terms) <= 1:
        return hits

    fallback_hits: list[Any] = []
    seen: set[tuple[str, int | None, int | None, int]] = set()
    for term in fallback_terms[:6]:
        if len(term) < 2:
            continue
        for hit in await native_search.search(
            session,
            term,
            feature_id=feature_id,
            current_feature_id=current_feature_id,
            limit=limit,
        ):
            key = (hit.kind, hit.document_id, hit.report_id, hit.node_id)
            if key in seen:
                continue
            seen.add(key)
            fallback_hits.append(hit)
    fallback_hits.sort(key=lambda item: item.score, reverse=True)
    return fallback_hits[:limit]


async def _search_nodes_by_id(
    session: AsyncSession,
    node_ids: list[int],
) -> list[dict[str, Any]]:
    result = await session.execute(
        select(WikiNode, WikiDocument, WikiSpace.feature_id)
        .join(WikiDocument, WikiDocument.node_id == WikiNode.id)
        .join(WikiSpace, WikiSpace.id == WikiNode.space_id)
        .where(WikiNode.id.in_(node_ids), WikiNode.deleted_at.is_(None))
        .order_by(WikiNode.id.asc())
    )
    return [
        {
            "kind": "document",
            "node_id": int(node.id),
            "document_id": int(document.id),
            "title": document.title,
            "path": node.path,
            "feature_id": feature_id,
            "summary": document.summary,
            "heading_path": None,
        }
        for node, document, feature_id in result.all()
    ]


async def _read_real_wiki_node(
    session_factory: async_sessionmaker[AsyncSession],
    args: ReadWikiNodeInput,
) -> ToolResult:
    async with session_factory() as session:
        row = (
            await session.execute(
                select(
                    WikiNode,
                    WikiDocument,
                    WikiDocumentVersion,
                    WikiSpace.feature_id,
                )
                .join(WikiDocument, WikiDocument.node_id == WikiNode.id)
                .join(
                    WikiDocumentVersion,
                    WikiDocumentVersion.id == WikiDocument.current_version_id,
                )
                .join(WikiSpace, WikiSpace.id == WikiNode.space_id)
                .where(
                    WikiNode.id == args.node_id,
                    WikiNode.deleted_at.is_(None),
                    WikiNode.type == "document",
                )
            )
        ).one_or_none()

    if row is None:
        return ToolResult.error(
            tool="read_wiki_node",
            error_type=ToolErrorType.NOT_FOUND,
            message=f"wiki node not found: {args.node_id}",
        )

    node, document, version, feature_id = row
    body = version.body_markdown
    excerpt = _extract_heading_excerpt(body, args.heading) if args.heading else body
    truncated = len(excerpt) > args.max_chars
    content = excerpt[: args.max_chars]
    item = {
        "node_id": int(node.id),
        "document_id": int(document.id),
        "feature_id": feature_id,
        "title": document.title,
        "path": node.path,
        "heading_path": args.heading,
        "content": content,
    }
    return ToolResult.ok(
        tool="read_wiki_node",
        summary=f"读取 Wiki：{document.title}",
        items=[item],
        evidence_refs=[
            EvidenceRef(
                type="wiki",
                title=document.title,
                path=node.path,
                node_id=int(node.id),
                metadata={"feature_id": feature_id, "heading_path": args.heading},
            )
        ],
        truncated=truncated,
        warnings=["Wiki 内容过长，已按 max_chars 截断。"] if truncated else [],
    )


def _hit_item(hit: Any) -> dict[str, Any]:
    return {
        "kind": hit.kind,
        "node_id": hit.node_id,
        "document_id": hit.document_id,
        "title": hit.title,
        "path": hit.path,
        "feature_id": hit.feature_id,
        "summary": hit.snippet,
        "score": hit.score,
        "heading_path": hit.heading_path,
    }


def _dedupe_hits(hits: list[Any]) -> list[Any]:
    seen: set[tuple[Any, ...]] = set()
    deduped: list[Any] = []
    for hit in hits:
        key = (hit.kind, hit.document_id, hit.report_id, hit.node_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(hit)
    deduped.sort(key=lambda item: item.score, reverse=True)
    return deduped


def _ordered_unique(values: list[int]) -> list[int]:
    seen: set[int] = set()
    ordered: list[int] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _fallback_search_terms(query: str) -> list[str]:
    parts = [
        part.strip("，。？！?!.、：:；;（）()[]【】\"'")
        for part in re.split(r"\s+", query.strip())
    ]
    terms = [part for part in parts if len(part) >= 2]
    compact_cjk = "".join(re.findall(r"[\u4e00-\u9fff]+", query))
    if len(compact_cjk) >= 2 and compact_cjk not in terms:
        terms.append(compact_cjk)
    return _dedupe_terms(terms)


def _dedupe_terms(terms: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for term in terms:
        normalized = term.strip()
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
    return deduped


def _extract_heading_excerpt(body_markdown: str, heading: str | None) -> str:
    if not body_markdown or not heading:
        return body_markdown
    target = heading.split("/")[-1].split(">")[-1].strip().lower()
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
