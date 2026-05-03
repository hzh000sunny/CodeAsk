"""Preflight checks for native wiki directory-style imports."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Literal

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.db.models import Feature, WikiNode, WikiSpace
from codeask.wiki.actor import WikiActor
from codeask.wiki.documents.markdown_refs import parse_markdown_references, resolve_reference_path
from codeask.wiki.paths import normalize_asset_name, normalize_node_name
from codeask.wiki.permissions import can_write_feature


IssueSeverity = Literal["error", "warning"]
ImportItemKind = Literal["document", "asset"]


@dataclass(slots=True)
class PreflightIssue:
    severity: IssueSeverity
    code: str
    message: str
    target: str | None = None
    resolved_path: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "target": self.target,
            "resolved_path": self.resolved_path,
        }


@dataclass(slots=True)
class PreflightItem:
    relative_path: str
    kind: ImportItemKind
    target_path: str
    issues: list[PreflightIssue] = field(default_factory=list)
    markdown_body: str | None = None

    @property
    def status(self) -> str:
        return "conflict" if any(issue.severity == "error" for issue in self.issues) else "ready"

    def as_dict(self) -> dict[str, object]:
        return {
            "relative_path": self.relative_path,
            "kind": self.kind,
            "target_path": self.target_path,
            "status": self.status,
            "issues": [issue.as_dict() for issue in self.issues],
        }


class WikiImportPreflightService:
    async def run_preflight(
        self,
        session: AsyncSession,
        *,
        actor: WikiActor,
        space: WikiSpace,
        parent: WikiNode | None,
        files: list[UploadFile],
    ) -> dict[str, object]:
        items, summary, ready = await self.analyze_import(
            session,
            actor=actor,
            space=space,
            parent=parent,
            files=files,
        )
        return {
            "ready": ready,
            "summary": summary,
            "items": [item.as_dict() for item in items],
        }

    async def analyze_import(
        self,
        session: AsyncSession,
        *,
        actor: WikiActor,
        space: WikiSpace,
        parent: WikiNode | None,
        files: list[UploadFile],
    ) -> tuple[list[PreflightItem], dict[str, int], bool]:
        feature = await self._load_feature_for_space(session, space_id=space.id)
        self._require_write(actor, feature)
        self._validate_parent(space=space, parent=parent)
        if not files:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="import preflight requires at least one file",
            )

        items: list[PreflightItem] = []
        for file in files:
            relative_path = self._normalize_relative_path(file.filename)
            kind = self._classify_kind(relative_path)
            target_path = self._target_path(
                base_path=parent.path if parent is not None else None,
                relative_path=relative_path,
                kind=kind,
            )
            body = None
            if kind == "document":
                body = (await file.read()).decode("utf-8", errors="replace")
                await file.seek(0)
            items.append(
                PreflightItem(
                    relative_path=relative_path,
                    kind=kind,
                    target_path=target_path,
                    markdown_body=body,
                )
            )

        existing_nodes = await self._load_existing_nodes(session, space_id=space.id)
        folder_claims = self._folder_claims(items)
        self._apply_internal_conflicts(items, folder_claims)
        self._apply_existing_conflicts(items, existing_nodes)
        self._apply_reference_warnings(items, existing_nodes)

        error_count = sum(
            1 for item in items for issue in item.issues if issue.severity == "error"
        )
        warning_count = sum(
            1 for item in items for issue in item.issues if issue.severity == "warning"
        )
        summary = {
            "total_files": len(items),
            "document_count": sum(1 for item in items if item.kind == "document"),
            "asset_count": sum(1 for item in items if item.kind == "asset"),
            "conflict_count": error_count,
            "warning_count": warning_count,
        }
        return items, summary, error_count == 0

    async def _load_feature_for_space(self, session: AsyncSession, *, space_id: int) -> Feature:
        feature = (
            await session.execute(
                select(Feature)
                .join(WikiSpace, WikiSpace.feature_id == Feature.id)
                .where(WikiSpace.id == space_id)
            )
        ).scalar_one_or_none()
        if feature is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="feature not found")
        return feature

    async def _load_existing_nodes(
        self,
        session: AsyncSession,
        *,
        space_id: int,
    ) -> dict[str, WikiNode]:
        rows = (
            await session.execute(
                select(WikiNode).where(
                    WikiNode.space_id == space_id,
                    WikiNode.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        return {row.path: row for row in rows}

    def _validate_parent(self, *, space: WikiSpace, parent: WikiNode | None) -> None:
        if parent is None:
            return
        if parent.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="wiki node not found")
        if parent.space_id != space.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="parent node belongs to a different wiki space",
            )
        if parent.type != "folder":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="import target parent must be a folder",
            )

    def _require_write(self, actor: WikiActor, feature: Feature) -> None:
        if not can_write_feature(actor, feature):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="write access denied for this wiki feature",
            )

    def _normalize_relative_path(self, value: str | None) -> str:
        if not value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="import file is missing a relative path",
            )
        normalized = value.replace("\\", "/").strip().lstrip("/")
        parts = [part for part in PurePosixPath(normalized).parts if part not in {"", "."}]
        if not parts or any(part == ".." for part in parts):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"invalid import relative path: {value}",
            )
        return "/".join(parts)

    def _classify_kind(self, relative_path: str) -> ImportItemKind:
        suffix = PurePosixPath(relative_path).suffix.lower()
        if suffix in {".md", ".markdown"}:
            return "document"
        return "asset"

    def _target_path(
        self,
        *,
        base_path: str | None,
        relative_path: str,
        kind: ImportItemKind,
    ) -> str:
        source = PurePosixPath(relative_path)
        parents = [normalize_node_name(part) for part in source.parts[:-1]]
        if kind == "document":
            leaf = normalize_node_name(source.stem)
        else:
            leaf = normalize_asset_name(source.name)
        parts = [part for part in [base_path, *parents, leaf] if part]
        return "/".join(parts)

    def _folder_claims(self, items: list[PreflightItem]) -> Counter[str]:
        counter: Counter[str] = Counter()
        for item in items:
            for folder_path in self._ancestor_paths(item.target_path):
                counter[folder_path] += 1
        return counter

    def _apply_internal_conflicts(self, items: list[PreflightItem], folder_claims: Counter[str]) -> None:
        target_counts = Counter(item.target_path for item in items)
        for item in items:
            if target_counts[item.target_path] > 1:
                item.issues.append(
                    PreflightIssue(
                        severity="error",
                        code="path_conflict",
                        message=f"import target path conflicts with another uploaded item: {item.target_path}",
                    )
                )
            if folder_claims[item.target_path] > 0:
                item.issues.append(
                    PreflightIssue(
                        severity="error",
                        code="path_conflict",
                        message=f"import target path conflicts with an uploaded folder path: {item.target_path}",
                    )
                )

    def _apply_existing_conflicts(
        self,
        items: list[PreflightItem],
        existing_nodes: dict[str, WikiNode],
    ) -> None:
        for item in items:
            existing = existing_nodes.get(item.target_path)
            if existing is not None:
                item.issues.append(
                    PreflightIssue(
                        severity="error",
                        code="path_conflict",
                        message=f"wiki node path conflict: {item.target_path}",
                    )
                )
            for ancestor_path in self._ancestor_paths(item.target_path):
                ancestor = existing_nodes.get(ancestor_path)
                if ancestor is not None and ancestor.type != "folder":
                    item.issues.append(
                        PreflightIssue(
                            severity="error",
                            code="path_conflict",
                            message=(
                                f"import path requires folder ancestor {ancestor_path}, "
                                f"but an existing {ancestor.type} already occupies that path"
                            ),
                        )
                    )
                    break

    def _apply_reference_warnings(
        self,
        items: list[PreflightItem],
        existing_nodes: dict[str, WikiNode],
    ) -> None:
        staged_documents = {item.target_path for item in items if item.kind == "document"}
        staged_assets = {item.target_path for item in items if item.kind == "asset"}
        for item in items:
            if item.kind != "document" or item.markdown_body is None:
                continue
            references = parse_markdown_references(item.markdown_body)
            for ref in references:
                resolved_path = self._normalize_reference_target(
                    resolve_reference_path(item.target_path, ref.target),
                    kind=ref.kind,
                )
                if ref.kind == "link":
                    if resolved_path in staged_documents:
                        continue
                    existing = existing_nodes.get(resolved_path)
                    if existing is not None and existing.type == "document":
                        continue
                    item.issues.append(
                        PreflightIssue(
                            severity="warning",
                            code="broken_link",
                            message=f"markdown link target is missing: {ref.target}",
                            target=ref.target,
                            resolved_path=resolved_path,
                        )
                    )
                    continue
                if resolved_path in staged_assets:
                    continue
                existing = existing_nodes.get(resolved_path)
                if existing is not None and existing.type == "asset":
                    continue
                item.issues.append(
                    PreflightIssue(
                        severity="warning",
                        code="broken_asset",
                        message=f"markdown image target is missing: {ref.target}",
                        target=ref.target,
                        resolved_path=resolved_path,
                    )
                    )

    def _ancestor_paths(self, path: str) -> list[str]:
        parts = path.split("/")
        return ["/".join(parts[:index]) for index in range(1, len(parts))]

    def _normalize_reference_target(self, resolved_path: str, *, kind: str) -> str:
        source = PurePosixPath(resolved_path)
        parents = [normalize_node_name(part) for part in source.parts[:-1]]
        leaf = (
            normalize_node_name(source.name)
            if kind == "link"
            else normalize_asset_name(source.name)
        )
        return "/".join([*parents, leaf]).strip("/")
