"""Wiki read tools for the chat runtime."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from codeask.agent.chat_runtime.events import EvidenceRef
from codeask.agent.chat_runtime.tool_contracts import (
    ToolContext,
    ToolErrorType,
    ToolResult,
    ToolSpec,
)
from codeask.agent.chat_runtime.tool_registry import ToolRegistry


class SearchWikiInput(BaseModel):
    query: str
    feature_ids: list[int] = Field(default_factory=list)
    node_ids: list[int] = Field(default_factory=list)
    limit: int = 5
    offset: int = 0


class ReadWikiNodeInput(BaseModel):
    node_id: int
    heading: str | None = None
    max_chars: int = 12_000


def register_wiki_tools(
    registry: ToolRegistry,
    *,
    fake_search_results: list[dict[str, Any]] | None = None,
    fake_nodes: dict[int, dict[str, Any]] | None = None,
) -> None:
    search_results = fake_search_results or []
    nodes = fake_nodes or {}

    async def search_wiki(args: SearchWikiInput, ctx: ToolContext) -> ToolResult:
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
        ),
        read_wiki_node,
    )
