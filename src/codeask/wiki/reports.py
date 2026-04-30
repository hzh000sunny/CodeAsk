"""Report lifecycle service."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.db.models import Report
from codeask.wiki.audit import AuditWriter
from codeask.wiki.indexer import WikiIndexer


class ReportVerificationError(Exception):
    """Raised when a report does not satisfy verification gates."""


def _non_empty_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _check_gate(metadata: dict[str, Any]) -> None:
    evidence = metadata.get("evidence") or []
    if not isinstance(evidence, list) or not any(
        isinstance(item, dict) and item.get("type") == "log" for item in evidence
    ):
        raise ReportVerificationError(
            "report must include at least one log evidence before verification"
        )

    for item in evidence:
        if isinstance(item, dict) and item.get("type") == "code":
            source = item.get("source") if isinstance(item.get("source"), dict) else {}
            if not source.get("commit_sha"):
                raise ReportVerificationError(
                    "all code evidence must bind a commit_sha before verification"
                )

    if not _non_empty_text(metadata.get("applicability")):
        raise ReportVerificationError("report must have a non-empty applicability section")

    if not _non_empty_text(metadata.get("recommended_fix")) and not _non_empty_text(
        metadata.get("verification_steps")
    ):
        raise ReportVerificationError(
            "report must include either recommended_fix or verification_steps"
        )


class ReportService:
    def __init__(
        self,
        indexer: WikiIndexer | None = None,
        audit: AuditWriter | None = None,
    ) -> None:
        self._indexer = indexer or WikiIndexer()
        self._audit = audit or AuditWriter()

    async def create_draft(
        self,
        session: AsyncSession,
        *,
        feature_id: int | None,
        title: str,
        body_markdown: str,
        metadata: dict[str, Any],
        subject_id: str,
    ) -> int:
        report = Report(
            feature_id=feature_id,
            title=title,
            body_markdown=body_markdown,
            metadata_json=metadata,
            status="draft",
            verified=False,
            created_by_subject_id=subject_id,
        )
        session.add(report)
        await session.flush()
        return int(report.id)

    async def update_draft(
        self,
        session: AsyncSession,
        *,
        report_id: int,
        title: str | None = None,
        body_markdown: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        report = (await session.execute(select(Report).where(Report.id == report_id))).scalar_one()
        if report.status != "draft":
            raise ReportVerificationError("only draft reports can be edited")
        if title is not None:
            report.title = title
        if body_markdown is not None:
            report.body_markdown = body_markdown
        if metadata is not None:
            report.metadata_json = metadata

    async def verify(
        self,
        session: AsyncSession,
        *,
        report_id: int,
        subject_id: str,
    ) -> None:
        report = (await session.execute(select(Report).where(Report.id == report_id))).scalar_one()
        metadata = report.metadata_json if isinstance(report.metadata_json, dict) else {}
        _check_gate(metadata)

        report.verified = True
        report.status = "verified"
        report.verified_by = subject_id
        report.verified_at = datetime.now(UTC)
        await session.flush()
        await self._indexer.unindex_report(session, report_id=int(report.id))
        await self._indexer.index_report(session, report)
        self._audit.write(
            "report.verified",
            {"report_id": int(report.id), "feature_id": report.feature_id},
            subject_id=subject_id,
        )

    async def unverify(
        self,
        session: AsyncSession,
        *,
        report_id: int,
        subject_id: str,
    ) -> None:
        report = (await session.execute(select(Report).where(Report.id == report_id))).scalar_one()
        report.verified = False
        report.status = "draft"
        await session.flush()
        await self._indexer.unindex_report(session, report_id=int(report.id))
        self._audit.write(
            "report.unverified",
            {"report_id": int(report.id), "feature_id": report.feature_id},
            subject_id=subject_id,
        )
