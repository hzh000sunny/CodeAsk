"""Report read tools for the chat runtime."""

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


class SearchReportsInput(BaseModel):
    query: str
    feature_ids: list[int] = Field(default_factory=list)
    limit: int = 3
    offset: int = 0


class ReadReportInput(BaseModel):
    report_id: int
    max_chars: int = 12_000


def register_report_tools(
    registry: ToolRegistry,
    *,
    fake_reports: list[dict[str, Any]] | None = None,
) -> None:
    reports = fake_reports or []

    async def search_reports(args: SearchReportsInput, ctx: ToolContext) -> ToolResult:
        sorted_reports = sorted(
            reports,
            key=lambda report: 0 if report.get("status") == "verified" else 1,
        )
        items = sorted_reports[args.offset : args.offset + args.limit]
        return ToolResult.ok(
            tool="search_reports",
            summary=f"命中 {len(items)} 个问题报告",
            items=items,
            evidence_refs=[
                EvidenceRef(
                    type="report",
                    title=str(item.get("title")) if item.get("title") is not None else None,
                    path=str(item.get("path")) if item.get("path") is not None else None,
                    report_id=int(item["report_id"]) if item.get("report_id") is not None else None,
                )
                for item in items
            ],
            truncated=len(sorted_reports) > args.offset + args.limit,
        )

    async def read_report(args: ReadReportInput, ctx: ToolContext) -> ToolResult:
        report = next(
            (item for item in reports if item.get("report_id") == args.report_id),
            None,
        )
        if report is None:
            return ToolResult.error(
                tool="read_report",
                error_type=ToolErrorType.NOT_FOUND,
                message=f"report not found: {args.report_id}",
            )
        body = str(report.get("body", report.get("content", "")))
        truncated = len(body) > args.max_chars
        return ToolResult.ok(
            tool="read_report",
            summary=f"读取问题报告：{report.get('title', args.report_id)}",
            items=[{**report, "body": body[: args.max_chars]}],
            evidence_refs=[
                EvidenceRef(
                    type="report",
                    title=str(report.get("title")) if report.get("title") is not None else None,
                    path=str(report.get("path")) if report.get("path") is not None else None,
                    report_id=args.report_id,
                )
            ],
            truncated=truncated,
            warnings=["报告内容过长，已按 max_chars 截断。"] if truncated else [],
        )

    registry.register(
        ToolSpec(
            name="search_reports",
            description="搜索已验证和历史问题定位报告，只返回候选证据。",
            input_model=SearchReportsInput,
            read_only=True,
            concurrency_safe=True,
            requires_confirmation=False,
        ),
        search_reports,
    )
    registry.register(
        ToolSpec(
            name="read_report",
            description="读取指定问题定位报告。",
            input_model=ReadReportInput,
            read_only=True,
            concurrency_safe=True,
            requires_confirmation=False,
        ),
        read_report,
    )
