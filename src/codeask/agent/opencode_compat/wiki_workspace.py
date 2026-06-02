"""Export CodeAsk Wiki data into an opencode-readable workspace tree."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
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
        self._export_lock = asyncio.Lock()

    async def export_current(self) -> WikiWorkspaceExportResult:
        async with self._export_lock:
            return await self._export_current_locked()

    async def _export_current_locked(self) -> WikiWorkspaceExportResult:
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
            manifest_features: list[dict[str, Any]] = []
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
                manifest_features.append(
                    {
                        "feature_id": int(feature.id),
                        "name": feature.name,
                        "slug": feature.slug,
                        "path": f"./{_safe_segment(feature.slug)}",
                        "document_count": feature_document_count,
                        "report_count": feature_report_count,
                    }
                )
                self._write_feature_index(
                    feature_dir,
                    feature=feature,
                    space=space,
                    document_count=feature_document_count,
                    report_count=feature_report_count,
                )
            self._write_manifest(
                tmp_root,
                feature_count=feature_count,
                document_count=document_count,
                report_count=report_count,
                features=manifest_features,
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
                    WikiDocument.current_version_id.is_not(None),
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
            target = feature_dir / "problem-reports" / report_bucket / _report_relpath(node.path)
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

    def _write_manifest(
        self,
        root: Path,
        *,
        feature_count: int,
        document_count: int,
        report_count: int,
        features: list[dict[str, Any]],
    ) -> None:
        manifest = {
            "schema_version": 1,
            "view_mode": "live",
            "exported_at": datetime.now(UTC).isoformat(),
            "feature_count": feature_count,
            "document_count": document_count,
            "report_count": report_count,
            "features": features,
        }
        (root / "_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def _document_relpath(value: str) -> Path:
    parts = [_safe_segment(part) for part in value.split("/") if part.strip()]
    if parts and parts[0] == "knowledge-base":
        parts = parts[1:]
    if not parts:
        parts = ["index"]
    path = Path("knowledge-base", *parts)
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
    path = Path(*[_safe_segment(part) for part in parts])
    if path.suffix.lower() not in {".md", ".markdown"}:
        path = path.with_name(f"{path.name}.md")
    return path


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


class WikiWorkspaceProjector:
    """Incrementally maintain the current wiki workspace projection."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        workspace_root: Path,
    ) -> None:
        self._session_factory = session_factory
        self._workspace_root = workspace_root
        self._lock = asyncio.Lock()

    async def bootstrap(self) -> WikiWorkspaceExportResult:
        exporter = WikiWorkspaceExporter(
            session_factory=self._session_factory,
            workspace_root=self._workspace_root,
        )
        async with self._lock:
            # Reuse the legacy full exporter as the cold-start repair path.
            return await exporter._export_current_locked()  # pyright: ignore[reportPrivateUsage]

    async def project_document(self, document_id: int) -> None:
        async with self._lock, self._session_factory() as session:
            row = (
                await session.execute(
                    select(Feature, WikiSpace, WikiNode, WikiDocument, WikiDocumentVersion)
                    .join(WikiSpace, WikiSpace.feature_id == Feature.id)
                    .join(WikiNode, WikiNode.space_id == WikiSpace.id)
                    .join(WikiDocument, WikiDocument.node_id == WikiNode.id)
                    .join(
                        WikiDocumentVersion,
                        WikiDocumentVersion.id == WikiDocument.current_version_id,
                        isouter=True,
                    )
                    .where(WikiDocument.id == document_id)
                )
            ).one_or_none()
            if row is None:
                return
            feature, space, node, document, version = row
            if feature.status != "active" or space.scope != "current" or space.status != "active":
                self._delete_feature_tree(feature.slug)
                await self._refresh_manifest(session)
                return
            if node.deleted_at is not None or version is None:
                self._delete_document_path(feature.slug, node.path)
                await self._refresh_feature_indexes(session, feature_slug=feature.slug)
                return
            self._write_document_file(
                feature_slug=feature.slug,
                node=node,
                document=document,
                version=version,
            )
            await self._refresh_feature_indexes(session, feature_slug=feature.slug)

    async def delete_document_path(self, *, feature_slug: str, node_path: str) -> None:
        async with self._lock, self._session_factory() as session:
            self._delete_document_path(feature_slug, node_path)
            await self._refresh_feature_indexes(session, feature_slug=feature_slug)

    async def delete_document_paths_by_node_ids(
        self,
        *,
        feature_slug: str,
        node_ids: tuple[int, ...],
    ) -> None:
        if not node_ids:
            await self.refresh_feature_indexes(feature_slug)
            return
        async with self._lock, self._session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(WikiNode.path)
                        .where(WikiNode.id.in_(node_ids), WikiNode.type == "document")
                        .order_by(WikiNode.path.asc(), WikiNode.id.asc())
                    )
                )
                .scalars()
                .all()
            )
            for node_path in rows:
                self._delete_document_path(feature_slug, str(node_path))
            await self._refresh_feature_indexes(session, feature_slug=feature_slug)

    async def move_document_path(
        self,
        *,
        feature_slug: str,
        old_path: str,
        new_path: str,
    ) -> None:
        async with self._lock:
            old_file = self._feature_dir(feature_slug) / _document_relpath(old_path)
            new_file = self._feature_dir(feature_slug) / _document_relpath(new_path)
            if old_file.exists():
                new_file.parent.mkdir(parents=True, exist_ok=True)
                os.replace(old_file, new_file)
                self._cleanup_empty_parents(
                    old_file.parent,
                    stop_at=self._knowledge_base_dir(feature_slug),
                )
            async with self._session_factory() as session:
                await self._refresh_feature_indexes(session, feature_slug=feature_slug)

    async def move_document_subtree(
        self,
        *,
        feature_slug: str,
        old_path: str,
        new_path: str,
        affected_node_ids: tuple[int, ...],
    ) -> None:
        async with self._lock:
            old_target = self._feature_dir(feature_slug) / _document_relpath(old_path)
            new_target = self._feature_dir(feature_slug) / _document_relpath(new_path)
            old_root = old_target.with_suffix("") if old_target.suffix else old_target
            new_root = new_target.with_suffix("") if new_target.suffix else new_target
            if old_root.exists():
                new_root.parent.mkdir(parents=True, exist_ok=True)
                if new_root.exists():
                    shutil.rmtree(new_root)
                os.replace(old_root, new_root)
                self._cleanup_empty_parents(
                    old_root.parent,
                    stop_at=self._knowledge_base_dir(feature_slug),
                )
        await self.project_documents_by_node_ids(node_ids=affected_node_ids)

    async def project_documents_by_node_ids(
        self,
        *,
        node_ids: tuple[int, ...],
    ) -> None:
        if not node_ids:
            return
        async with self._lock, self._session_factory() as session:
            rows = (
                await session.execute(
                    select(Feature, WikiSpace, WikiNode, WikiDocument, WikiDocumentVersion)
                    .join(WikiSpace, WikiSpace.feature_id == Feature.id)
                    .join(WikiNode, WikiNode.space_id == WikiSpace.id)
                    .join(WikiDocument, WikiDocument.node_id == WikiNode.id)
                    .join(
                        WikiDocumentVersion,
                        WikiDocumentVersion.id == WikiDocument.current_version_id,
                        isouter=True,
                    )
                    .where(WikiNode.id.in_(node_ids), WikiNode.type == "document")
                    .order_by(WikiNode.path.asc(), WikiNode.id.asc())
                )
            ).all()
            touched_features: set[str] = set()
            for feature, space, node, document, version in rows:
                if (
                    feature.status != "active"
                    or space.scope != "current"
                    or space.status != "active"
                ):
                    self._delete_feature_tree(feature.slug)
                    touched_features.add(feature.slug)
                    continue
                if node.deleted_at is not None or version is None:
                    self._delete_document_path(feature.slug, node.path)
                else:
                    self._write_document_file(
                        feature_slug=feature.slug,
                        node=node,
                        document=document,
                        version=version,
                    )
                touched_features.add(feature.slug)
            for feature_slug in touched_features:
                await self._refresh_feature_indexes(session, feature_slug=feature_slug)

    async def project_reports(self, *, feature_slug: str) -> None:
        async with self._lock, self._session_factory() as session:
            row = (
                await session.execute(
                    select(Feature, WikiSpace)
                    .join(WikiSpace, WikiSpace.feature_id == Feature.id)
                    .where(
                        Feature.slug == feature_slug,
                        Feature.status == "active",
                        WikiSpace.scope == "current",
                        WikiSpace.status == "active",
                    )
                )
            ).one_or_none()
            if row is None:
                self._delete_feature_tree(feature_slug)
                await self._refresh_manifest(session)
                return
            _feature, space = row
            feature_dir = self._feature_dir(feature_slug)
            reports_dir = feature_dir / "problem-reports"
            shutil.rmtree(reports_dir, ignore_errors=True)
            exporter = WikiWorkspaceExporter(
                session_factory=self._session_factory,
                workspace_root=self._workspace_root,
            )
            await exporter._export_reports(  # pyright: ignore[reportPrivateUsage]
                session, space.id, feature_dir
            )
            await self._refresh_feature_indexes(session, feature_slug=feature_slug)

    async def rebuild_feature(self, feature_slug: str) -> None:
        async with self._lock, self._session_factory() as session:
            row = (
                await session.execute(
                    select(Feature, WikiSpace)
                    .join(WikiSpace, WikiSpace.feature_id == Feature.id)
                    .where(
                        Feature.slug == feature_slug,
                        Feature.status == "active",
                        WikiSpace.scope == "current",
                        WikiSpace.status == "active",
                    )
                )
            ).one_or_none()
            if row is None:
                self._delete_feature_tree(feature_slug)
                await self._refresh_manifest(session)
                return
            feature, space = row
            safe_slug = _safe_segment(feature.slug)
            tmp_feature_dir = self._workspace_root / f".{safe_slug}.tmp.{os.getpid()}"
            if tmp_feature_dir.exists():
                shutil.rmtree(tmp_feature_dir)
            tmp_feature_dir.mkdir(parents=True, exist_ok=True)
            exporter = WikiWorkspaceExporter(
                session_factory=self._session_factory,
                workspace_root=self._workspace_root,
            )
            await exporter._export_documents(  # pyright: ignore[reportPrivateUsage]
                session, space.id, tmp_feature_dir
            )
            await exporter._export_reports(  # pyright: ignore[reportPrivateUsage]
                session, space.id, tmp_feature_dir
            )
            document_count = await self._document_count(session, space_id=space.id)
            report_count = await self._report_count(session, space_id=space.id)
            exporter._write_feature_index(  # pyright: ignore[reportPrivateUsage]
                tmp_feature_dir,
                feature=feature,
                space=space,
                document_count=document_count,
                report_count=report_count,
            )
            try:
                self._sync_feature_tree_from_temp(
                    feature_slug=feature.slug,
                    tmp_feature_dir=tmp_feature_dir,
                )
            finally:
                shutil.rmtree(tmp_feature_dir, ignore_errors=True)
            await self._refresh_manifest(session)

    async def prune_feature(self, feature_slug: str) -> None:
        async with self._lock:
            self._delete_feature_tree(feature_slug)
            async with self._session_factory() as session:
                await self._refresh_manifest(session)

    async def refresh_feature_indexes(self, feature_slug: str) -> None:
        async with self._lock, self._session_factory() as session:
            await self._refresh_feature_indexes(session, feature_slug=feature_slug)

    def _write_document_file(
        self,
        *,
        feature_slug: str,
        node: WikiNode,
        document: WikiDocument,
        version: WikiDocumentVersion,
    ) -> None:
        target = self._feature_dir(feature_slug) / _document_relpath(node.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        text = (
            _front_matter(
                {
                    "type": "wiki_document",
                    "node_id": node.id,
                    "path": node.path,
                    "title": document.title,
                }
            )
            + version.body_markdown
        )
        _atomic_write_text(target, text)

    def _delete_document_path(self, feature_slug: str, node_path: str) -> None:
        target = self._feature_dir(feature_slug) / _document_relpath(node_path)
        target.unlink(missing_ok=True)
        self._cleanup_empty_parents(target.parent, stop_at=self._knowledge_base_dir(feature_slug))

    def _delete_feature_tree(self, feature_slug: str) -> None:
        shutil.rmtree(self._feature_dir(feature_slug), ignore_errors=True)

    def _sync_feature_tree_from_temp(self, *, feature_slug: str, tmp_feature_dir: Path) -> None:
        feature_dir = self._feature_dir(feature_slug)
        feature_dir.mkdir(parents=True, exist_ok=True)
        expected: set[Path] = set()
        for source in tmp_feature_dir.rglob("*"):
            relative = source.relative_to(tmp_feature_dir)
            target = feature_dir / relative
            expected.add(target)
            if source.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp_target = target.with_name(f".{target.name}.tmp")
            shutil.copy2(source, tmp_target)
            os.replace(tmp_target, target)

        stale_targets = sorted(
            feature_dir.rglob("*"),
            key=lambda item: len(item.parts),
            reverse=True,
        )
        for target in stale_targets:
            if target in expected:
                continue
            if target.is_dir():
                with contextlib.suppress(OSError):
                    target.rmdir()
            else:
                target.unlink(missing_ok=True)

    async def _refresh_feature_indexes(self, session: AsyncSession, *, feature_slug: str) -> None:
        row = (
            await session.execute(
                select(Feature, WikiSpace)
                .join(WikiSpace, WikiSpace.feature_id == Feature.id)
                .where(
                    Feature.slug == feature_slug,
                    Feature.status == "active",
                    WikiSpace.scope == "current",
                    WikiSpace.status == "active",
                )
            )
        ).one_or_none()
        if row is None:
            await self._refresh_manifest(session)
            return
        feature, space = row
        document_count = await self._document_count(session, space_id=space.id)
        report_count = await self._report_count(session, space_id=space.id)
        feature_dir = self._feature_dir(feature.slug)
        feature_dir.mkdir(parents=True, exist_ok=True)
        exporter = WikiWorkspaceExporter(
            session_factory=self._session_factory,
            workspace_root=self._workspace_root,
        )
        exporter._write_feature_index(  # pyright: ignore[reportPrivateUsage]
            feature_dir,
            feature=feature,
            space=space,
            document_count=document_count,
            report_count=report_count,
        )
        await self._refresh_manifest(session)

    async def _refresh_manifest(self, session: AsyncSession) -> None:
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
        features: list[dict[str, Any]] = []
        total_documents = 0
        total_reports = 0
        for feature, space in rows:
            document_count = await self._document_count(session, space_id=space.id)
            report_count = await self._report_count(session, space_id=space.id)
            total_documents += document_count
            total_reports += report_count
            features.append(
                {
                    "feature_id": int(feature.id),
                    "name": feature.name,
                    "slug": feature.slug,
                    "path": f"./{_safe_segment(feature.slug)}",
                    "document_count": document_count,
                    "report_count": report_count,
                }
            )
        self._workspace_root.mkdir(parents=True, exist_ok=True)
        exporter = WikiWorkspaceExporter(
            session_factory=self._session_factory,
            workspace_root=self._workspace_root,
        )
        exporter._write_manifest(  # pyright: ignore[reportPrivateUsage]
            self._workspace_root,
            feature_count=len(features),
            document_count=total_documents,
            report_count=total_reports,
            features=features,
        )

    async def _document_count(self, session: AsyncSession, *, space_id: int) -> int:
        rows = (
            await session.execute(
                select(WikiNode.id)
                .join(WikiDocument, WikiDocument.node_id == WikiNode.id)
                .where(
                    WikiNode.space_id == space_id,
                    WikiNode.deleted_at.is_(None),
                    WikiNode.type == "document",
                    WikiDocument.current_version_id.is_not(None),
                )
            )
        ).all()
        return len(rows)

    async def _report_count(self, session: AsyncSession, *, space_id: int) -> int:
        rows = (
            await session.execute(
                select(WikiNode.id)
                .join(WikiReportRef, WikiReportRef.node_id == WikiNode.id)
                .where(
                    WikiNode.space_id == space_id,
                    WikiNode.deleted_at.is_(None),
                    WikiNode.type == "report_ref",
                )
            )
        ).all()
        return len(rows)

    def _feature_dir(self, feature_slug: str) -> Path:
        return self._workspace_root / _safe_segment(feature_slug)

    def _knowledge_base_dir(self, feature_slug: str) -> Path:
        return self._feature_dir(feature_slug) / "knowledge-base"

    def _cleanup_empty_parents(self, path: Path, *, stop_at: Path) -> None:
        current = path
        stop = stop_at.resolve()
        while current.exists():
            try:
                if current.resolve() == stop:
                    return
                current.rmdir()
            except OSError:
                return
            current = current.parent


def _atomic_write_text(target: Path, text: str) -> None:
    tmp = target.with_name(f".{target.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, target)
