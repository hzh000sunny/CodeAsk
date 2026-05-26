"""Report read tools for the chat runtime."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, cast

from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from codeask.agent.chat_runtime.events import EvidenceRef
from codeask.agent.native_backend.chat_runtime.tool_contracts import (
    ToolContext,
    ToolErrorType,
    ToolResult,
    ToolSpec,
)
from codeask.agent.native_backend.chat_runtime.tool_registry import ToolRegistry
from codeask.db.models import Report, WikiNode, WikiReportRef


@dataclass(slots=True)
class ReportSearchHit:
    report_id: int
    title: str
    feature_id: int | None
    verified_by: str | None
    verified_at: datetime | None
    commit_sha: str | None
    snippet: str
    score: float


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
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    fake_reports: list[dict[str, Any]] | None = None,
) -> None:
    reports = fake_reports or []

    async def search_reports(args: SearchReportsInput, ctx: ToolContext) -> ToolResult:
        if session_factory is not None:
            return await _search_real_reports(session_factory, args)

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
        if session_factory is not None:
            return await _read_real_report(session_factory, args)

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
            max_result_size_chars=8_000,
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
            max_result_size_chars=14_000,
        ),
        read_report,
    )


async def _search_real_reports(
    session_factory: async_sessionmaker[AsyncSession],
    args: SearchReportsInput,
) -> ToolResult:
    feature_ids = _ordered_unique(args.feature_ids)
    async with session_factory() as session:
        if feature_ids:
            hits: list[ReportSearchHit] = []
            for feature_id in feature_ids:
                hits.extend(
                    await _search_report_hits(
                        session,
                        args.query,
                        feature_id=feature_id,
                        limit=args.offset + args.limit,
                    )
                )
        else:
            hits = await _search_report_hits(
                session,
                args.query,
                feature_id=None,
                limit=args.offset + args.limit,
            )
        hits = _dedupe_hits(hits)
        report_nodes = await _load_report_nodes(session, [hit.report_id for hit in hits])

    items = [
        {
            **asdict(hit),
            "summary": hit.snippet,
            "status": "verified",
            "node_id": report_nodes.get(hit.report_id, {}).get("node_id"),
            "path": report_nodes.get(hit.report_id, {}).get("path"),
        }
        for hit in hits
    ]
    paged_items = items[args.offset : args.offset + args.limit]
    return ToolResult.ok(
        tool="search_reports",
        summary=f"命中 {len(paged_items)} 个问题报告",
        items=paged_items,
        evidence_refs=[
            EvidenceRef(
                type="report",
                title=str(item.get("title")) if item.get("title") is not None else None,
                path=str(item.get("path")) if item.get("path") is not None else None,
                report_id=int(item["report_id"]) if item.get("report_id") is not None else None,
                node_id=int(item["node_id"]) if item.get("node_id") is not None else None,
                metadata={
                    "feature_id": item.get("feature_id"),
                    "status": item.get("status"),
                    "commit_sha": item.get("commit_sha"),
                },
            )
            for item in paged_items
        ],
        truncated=len(items) > args.offset + args.limit,
    )


async def _read_real_report(
    session_factory: async_sessionmaker[AsyncSession],
    args: ReadReportInput,
) -> ToolResult:
    async with session_factory() as session:
        report = await session.get(Report, args.report_id)
        if report is None:
            return ToolResult.error(
                tool="read_report",
                error_type=ToolErrorType.NOT_FOUND,
                message=f"report not found: {args.report_id}",
            )
        node_info = (await _load_report_nodes(session, [args.report_id])).get(args.report_id, {})

    body = report.body_markdown
    truncated = len(body) > args.max_chars
    item = {
        "report_id": int(report.id),
        "feature_id": report.feature_id,
        "node_id": node_info.get("node_id"),
        "path": node_info.get("path"),
        "title": report.title,
        "body_markdown": body[: args.max_chars],
        "metadata": report.metadata_json if isinstance(report.metadata_json, dict) else {},
        "status": report.status,
        "verified": report.verified,
        "verified_by": report.verified_by,
        "verified_at": report.verified_at.isoformat() if report.verified_at else None,
    }
    return ToolResult.ok(
        tool="read_report",
        summary=f"读取问题报告：{report.title}",
        items=[item],
        evidence_refs=[
            EvidenceRef(
                type="report",
                title=report.title,
                path=str(node_info.get("path")) if node_info.get("path") is not None else None,
                report_id=args.report_id,
                node_id=(
                    int(node_info["node_id"]) if node_info.get("node_id") is not None else None
                ),
                metadata={"feature_id": report.feature_id, "status": report.status},
            )
        ],
        truncated=truncated,
        warnings=["报告内容过长，已按 max_chars 截断。"] if truncated else [],
    )


async def _load_report_nodes(
    session: AsyncSession,
    report_ids: list[int],
) -> dict[int, dict[str, Any]]:
    if not report_ids:
        return {}
    rows = (
        await session.execute(
            select(WikiReportRef.report_id, WikiNode.id, WikiNode.path)
            .join(WikiNode, WikiNode.id == WikiReportRef.node_id)
            .where(
                WikiReportRef.report_id.in_(report_ids),
                WikiNode.deleted_at.is_(None),
            )
        )
    ).all()
    return {
        int(report_id): {"node_id": int(node_id), "path": str(path)}
        for report_id, node_id, path in rows
    }


async def _search_report_hits(
    session: AsyncSession,
    query: str,
    *,
    feature_id: int | None = None,
    limit: int = 20,
) -> list[ReportSearchHit]:
    needle = query.strip()
    if not needle:
        return []

    lowered = needle.lower()
    pattern = f"%{needle}%"
    rows = (
        await session.execute(
            select(Report)
            .where(
                Report.verified.is_(True),
                Report.feature_id == feature_id if feature_id is not None else True,
                or_(Report.title.ilike(pattern), Report.body_markdown.ilike(pattern)),
            )
            .order_by(Report.updated_at.desc(), Report.id.desc())
            .limit(max(limit * 4, limit))
        )
    ).scalars()

    hits: list[ReportSearchHit] = []
    for report in rows:
        metadata = _metadata(report.metadata_json)
        hits.append(
            ReportSearchHit(
                report_id=int(report.id),
                title=report.title,
                feature_id=report.feature_id,
                verified_by=report.verified_by,
                verified_at=_parse_datetime(report.verified_at),
                commit_sha=_first_commit_sha(metadata),
                snippet=_snippet(report.body_markdown, lowered),
                score=_score(report.title, report.body_markdown, lowered),
            )
        )

    hits.sort(key=lambda hit: hit.score, reverse=True)
    return hits[:limit]


def _dedupe_hits(hits: list[ReportSearchHit]) -> list[ReportSearchHit]:
    deduped: list[ReportSearchHit] = []
    seen: set[int] = set()
    for hit in sorted(hits, key=lambda item: item.score, reverse=True):
        if hit.report_id in seen:
            continue
        seen.add(hit.report_id)
        deduped.append(hit)
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


def _metadata(value: object) -> Mapping[str, object]:
    if isinstance(value, dict):
        return cast(Mapping[str, object], value)
    if isinstance(value, str) and value:
        try:
            parsed: object = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return cast(Mapping[str, object], parsed) if isinstance(parsed, dict) else {}
    return {}


def _first_commit_sha(metadata: Mapping[str, object]) -> str | None:
    raw_repo_commits = metadata.get("repo_commits")
    if not isinstance(raw_repo_commits, list):
        return None
    repo_commits = cast(list[object], raw_repo_commits)
    if repo_commits and isinstance(repo_commits[0], dict):
        first_commit = cast(Mapping[str, object], repo_commits[0])
        commit = first_commit.get("commit_sha")
        return str(commit) if commit else None
    return None


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


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
