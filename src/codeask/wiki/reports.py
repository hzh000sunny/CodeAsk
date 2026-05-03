"""Report lifecycle service."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.db.models import Report, SessionTurn
from codeask.metrics.audit import record_audit_log
from codeask.sessions.reports import merge_session_report_metadata
from codeask.wiki.audit import AuditWriter
from codeask.wiki.indexer import WikiIndexer


class ReportVerificationError(Exception):
    """Raised when a report does not satisfy verification gates."""


def _non_empty_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _as_mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, dict):
        return cast(Mapping[str, object], value)
    return {}


def _as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return cast(list[object], value)
    return []


def _is_verifiable_evidence(item: object) -> bool:
    evidence = _as_mapping(item)
    return evidence.get("type") in {"log", "code"}


def _check_gate(metadata: Mapping[str, object]) -> None:
    evidence = _as_list(metadata.get("evidence"))
    if not any(_is_verifiable_evidence(item) for item in evidence):
        raise ReportVerificationError(
            "report must include at least one log or code evidence before verification"
        )

    for item in evidence:
        evidence_item = _as_mapping(item)
        if evidence_item.get("type") == "code":
            source = _as_mapping(evidence_item.get("source"))
            commit_sha = source.get("commit_sha")
            if not _non_empty_text(commit_sha):
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


async def _metadata_with_session_fallback(
    session: AsyncSession,
    metadata: Mapping[str, object],
) -> Mapping[str, object]:
    if metadata.get("source") != "session":
        return metadata
    session_id = metadata.get("session_id")
    if not _non_empty_text(session_id):
        return metadata
    turns = (
        (
            await session.execute(
                select(SessionTurn)
                .where(SessionTurn.session_id == session_id)
                .order_by(SessionTurn.turn_index, SessionTurn.created_at)
            )
        )
        .scalars()
        .all()
    )
    if not turns:
        return metadata
    return merge_session_report_metadata(metadata, str(session_id), list(turns))


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
        if report.status not in {"draft", "rejected"}:
            raise ReportVerificationError("only draft or rejected reports can be edited")
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
        metadata = await _metadata_with_session_fallback(
            session,
            _as_mapping(cast(object, report.metadata_json)),
        )
        report.metadata_json = dict(metadata)
        _check_gate(metadata)

        report.verified = True
        report.status = "verified"
        report.verified_by = subject_id
        report.verified_at = datetime.now(UTC)
        await session.flush()
        await self._indexer.unindex_report(session, report_id=int(report.id))
        await self._indexer.index_report(session, report)
        await record_audit_log(
            session,
            entity_type="report",
            entity_id=str(report.id),
            action="verify",
            from_status="draft",
            to_status="verified",
            subject_id=subject_id,
        )
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
        await record_audit_log(
            session,
            entity_type="report",
            entity_id=str(report.id),
            action="unverify",
            from_status="verified",
            to_status="draft",
            subject_id=subject_id,
        )
        self._audit.write(
            "report.unverified",
            {"report_id": int(report.id), "feature_id": report.feature_id},
            subject_id=subject_id,
        )

    async def reject(
        self,
        session: AsyncSession,
        *,
        report_id: int,
        subject_id: str,
    ) -> None:
        report = (await session.execute(select(Report).where(Report.id == report_id))).scalar_one()
        from_status = report.status
        report.verified = False
        report.status = "rejected"
        report.verified_by = None
        report.verified_at = None
        await session.flush()
        await self._indexer.unindex_report(session, report_id=int(report.id))
        await record_audit_log(
            session,
            entity_type="report",
            entity_id=str(report.id),
            action="reject",
            from_status=from_status,
            to_status="rejected",
            subject_id=subject_id,
        )
        self._audit.write(
            "report.rejected",
            {"report_id": int(report.id), "feature_id": report.feature_id},
            subject_id=subject_id,
        )
