"""Export CodeAsk Wiki data into an opencode-readable workspace tree."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from codeask.db.models import (
    Feature,
    Report,
    WikiDocument,
    WikiDocumentVersion,
    WikiNode,
    WikiReportRef,
    WikiSpace,
)

_UNSAFE_SEGMENT_CHARS = re.compile(r"[\x00-\x1f\x7f/\\]+")


@dataclass(frozen=True)
class WikiWorkspaceExportResult:
    root: Path
    feature_count: int
    document_count: int
    report_count: int


class WikiWorkspaceExporter:
    """Materialize a read-only-ish file view of current Wiki content.

    The exported tree is a projection for opencode grep/read. It intentionally
    does not implement ranking, RAG, or business decisions.
    """

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        workspace_root: Path,
    ) -> None:
        self._session_factory = session_factory
        self._workspace_root = workspace_root

    async def export_current(self) -> WikiWorkspaceExportResult:
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(Feature, WikiSpace)
                    .join(WikiSpace, WikiSpace.feature_id == Feature.id)
                    .where(
                        Feature.status == "active",
                        WikiSpace.scope == "current",
                        WikiSpace.status == "active",
                    )
                    .order_by(Feature.slug.asc(), Feature.id.asc())
                )
            ).all()

            tmp_root = self._workspace_root.with_name(f"{self._workspace_root.name}.tmp")
            if tmp_root.exists():
                shutil.rmtree(tmp_root)
            tmp_root.mkdir(parents=True, exist_ok=True)

            feature_count = 0
            document_count = 0
            report_count = 0
            for feature, space in rows:
                feature_count += 1
                feature_dir = tmp_root / _safe_segment(feature.slug)
                feature_dir.mkdir(parents=True, exist_ok=True)
                feature_document_count = await self._export_documents(
                    session,
                    space.id,
                    feature_dir,
                )
                feature_report_count = await self._export_reports(session, space.id, feature_dir)
                document_count += feature_document_count
                report_count += feature_report_count
                self._write_feature_index(
                    feature_dir,
                    feature=feature,
                    space=space,
                    document_count=feature_document_count,
                    report_count=feature_report_count,
                )

        if self._workspace_root.exists():
            shutil.rmtree(self._workspace_root)
        tmp_root.rename(self._workspace_root)
        return WikiWorkspaceExportResult(
            root=self._workspace_root,
            feature_count=feature_count,
            document_count=document_count,
            report_count=report_count,
        )

    async def _export_documents(
        self,
        session: AsyncSession,
        space_id: int,
        feature_dir: Path,
    ) -> int:
        rows = (
            await session.execute(
                select(WikiNode, WikiDocument, WikiDocumentVersion)
                .join(WikiDocument, WikiDocument.node_id == WikiNode.id)
                .join(
                    WikiDocumentVersion,
                    WikiDocumentVersion.id == WikiDocument.current_version_id,
                    isouter=True,
                )
                .where(
                    WikiNode.space_id == space_id,
                    WikiNode.deleted_at.is_(None),
                    WikiNode.type == "document",
                )
                .order_by(WikiNode.path.asc(), WikiNode.id.asc())
            )
        ).all()
        count = 0
        for node, document, version in rows:
            target = feature_dir / _document_relpath(node.path)
            target.parent.mkdir(parents=True, exist_ok=True)
            body = version.body_markdown if version is not None else ""
            target.write_text(
                _front_matter(
                    {
                        "type": "wiki_document",
                        "node_id": node.id,
                        "path": node.path,
                        "title": document.title,
                    }
                )
                + body,
                encoding="utf-8",
            )
            count += 1
        return count

    async def _export_reports(
        self,
        session: AsyncSession,
        space_id: int,
        feature_dir: Path,
    ) -> int:
        rows = (
            await session.execute(
                select(WikiNode, WikiReportRef, Report)
                .join(WikiReportRef, WikiReportRef.node_id == WikiNode.id)
                .join(Report, Report.id == WikiReportRef.report_id)
                .where(
                    WikiNode.space_id == space_id,
                    WikiNode.deleted_at.is_(None),
                    WikiNode.type == "report_ref",
                )
                .order_by(WikiNode.path.asc(), WikiNode.id.asc())
            )
        ).all()
        count = 0
        for node, report_ref, report in rows:
            report_bucket = "verified" if report.verified else "drafts"
            target = (
                feature_dir
                / "problem-reports"
                / report_bucket
                / _report_relpath(node.path)
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                _front_matter(
                    {
                        "type": "problem_report",
                        "node_id": node.id,
                        "report_ref_id": report_ref.id,
                        "report_id": report.id,
                        "path": node.path,
                        "title": report.title,
                        "status": report.status,
                        "verified": bool(report.verified),
                    }
                )
                + report.body_markdown,
                encoding="utf-8",
            )
            count += 1
        return count

    def _write_feature_index(
        self,
        feature_dir: Path,
        *,
        feature: Feature,
        space: WikiSpace,
        document_count: int,
        report_count: int,
    ) -> None:
        lines = [
            f"# {feature.name}",
            "",
            f"- feature_id: {feature.id}",
            f"- feature_slug: {feature.slug}",
            f"- wiki_space_id: {space.id}",
            f"- wiki_space_slug: {space.slug}",
            f"- exported_documents: {document_count}",
            f"- exported_reports: {report_count}",
            "",
            "## Directory Guide",
            "",
            "- `knowledge-base/`: primary Wiki knowledge. Prefer this directory first.",
            "- `problem-reports/verified/`: verified issue reports. Use as reference "
            "evidence only; treat a report as the same issue only when the error, "
            "scene, and root cause match exactly.",
            "- `problem-reports/drafts/`: draft issue reports. Use only as weak "
            "background, not as a confirmed conclusion.",
        ]
        if feature.description:
            lines.extend(["", "## Description", "", feature.description])
        if feature.summary_text:
            lines.extend(["", "## Summary", "", feature.summary_text])
        (feature_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _document_relpath(value: str) -> Path:
    parts = [_safe_segment(part) for part in value.split("/") if part.strip()]
    if not parts:
        parts = ["index"]
    path = Path(*parts)
    if path.suffix.lower() not in {".md", ".markdown"}:
        path = path.with_name(f"{path.name}.md")
    return path


def _report_relpath(value: str) -> Path:
    parts = [part for part in value.split("/") if part.strip()]
    while parts and _safe_segment(parts[0]).lower() in {
        "reports",
        "problem-reports",
        "problem-location-reports",
    }:
        parts.pop(0)
    if not parts:
        parts = ["index"]
    return _document_relpath("/".join(parts))


def _safe_segment(value: object) -> str:
    cleaned = _UNSAFE_SEGMENT_CHARS.sub("_", str(value or "").strip())
    cleaned = cleaned.strip(". ")
    if not cleaned or cleaned in {".", ".."}:
        return "_"
    return cleaned[:180]


def _front_matter(values: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in values.items():
        text = str(value).replace("\n", " ").strip()
        lines.append(f"{key}: {text}")
    lines.extend(["---", ""])
    return "\n".join(lines)
