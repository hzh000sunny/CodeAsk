from __future__ import annotations

import json
from pathlib import Path

import pytest

from codeask.agent.opencode_compat.wiki_workspace import (
    WikiWorkspaceExporter,
    WikiWorkspaceProjector,
)
from codeask.db.models import (
    Feature,
    Report,
    WikiDocument,
    WikiDocumentVersion,
    WikiNode,
    WikiReportRef,
    WikiSpace,
)


@pytest.mark.asyncio
async def test_wiki_workspace_exporter_materializes_current_wiki_and_reports(
    app,
    tmp_path: Path,
) -> None:
    async with app.state.session_factory() as session:
        feature = Feature(
            name="小米",
            slug="xiaomi",
            description="病例知识库",
            owner_subject_id="admin",
            status="active",
            summary_text="主知识库摘要",
        )
        session.add(feature)
        await session.flush()
        space = WikiSpace(
            feature_id=feature.id,
            scope="current",
            display_name="小米",
            slug="xiaomi",
            status="active",
        )
        session.add(space)
        await session.flush()
        doc_node = WikiNode(
            space_id=space.id,
            parent_id=None,
            type="document",
            name="小米病历",
            path="knowledge-base/小米病历",
            system_role="knowledge_base",
            sort_order=1,
        )
        report_node = WikiNode(
            space_id=space.id,
            parent_id=None,
            type="report_ref",
            name="肿瘤定位",
            path="problem-location-reports/肿瘤定位",
            system_role="reports",
            sort_order=2,
        )
        session.add_all([doc_node, report_node])
        await session.flush()
        document = WikiDocument(node_id=doc_node.id, title="小米病历")
        session.add(document)
        await session.flush()
        version = WikiDocumentVersion(
            document_id=document.id,
            version_no=1,
            body_markdown="## 基本情况\n右脚脚掌肥大细胞瘤已切除。",
            created_by_subject_id="admin",
        )
        session.add(version)
        await session.flush()
        document.current_version_id = version.id
        report = Report(
            feature_id=feature.id,
            session_id=None,
            title="2026-05-13 小米肿瘤定位",
            body_markdown="## 问题根因\n病历显示肿瘤发生在右脚脚掌。",
            metadata_json={},
            status="verified",
            verified=True,
            verified_by="admin",
            created_by_subject_id="admin",
        )
        session.add(report)
        await session.flush()
        session.add(WikiReportRef(node_id=report_node.id, report_id=report.id))
        await session.commit()

    exporter = WikiWorkspaceExporter(
        session_factory=app.state.session_factory,
        workspace_root=tmp_path / "wiki_workspace" / "current",
    )

    result = await exporter.export_current()

    assert result.feature_count == 1
    assert result.document_count == 1
    assert result.report_count == 1
    manifest = json.loads((result.root / "_manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["view_mode"] == "live"
    assert manifest["exported_at"]
    assert manifest["feature_count"] == 1
    assert manifest["document_count"] == 1
    assert manifest["report_count"] == 1
    assert manifest["features"] == [
        {
            "feature_id": feature.id,
            "name": "小米",
            "slug": "xiaomi",
            "path": "./xiaomi",
            "document_count": 1,
            "report_count": 1,
        }
    ]
    feature_dir = result.root / "xiaomi"
    assert (feature_dir / "README.md").read_text(encoding="utf-8").startswith("# 小米")
    doc_text = (feature_dir / "knowledge-base" / "小米病历.md").read_text(encoding="utf-8")
    assert "node_id:" in doc_text
    assert "右脚脚掌肥大细胞瘤已切除" in doc_text
    report_text = (feature_dir / "problem-reports" / "verified" / "肿瘤定位.md").read_text(
        encoding="utf-8"
    )
    assert "problem_report" in report_text
    assert "病历显示肿瘤发生在右脚脚掌" in report_text


@pytest.mark.asyncio
async def test_projector_rebuild_feature_replaces_files_without_removing_feature_dir(
    app,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with app.state.session_factory() as session:
        feature = Feature(
            name="Atomic Rebuild",
            slug="atomic-rebuild",
            owner_subject_id="admin",
            status="active",
        )
        session.add(feature)
        await session.flush()
        space = WikiSpace(
            feature_id=feature.id,
            scope="current",
            display_name="Atomic Rebuild",
            slug="atomic-rebuild",
            status="active",
        )
        session.add(space)
        await session.flush()
        node = WikiNode(
            space_id=space.id,
            parent_id=None,
            type="document",
            name="Fresh",
            path="knowledge-base/fresh",
            sort_order=1,
        )
        session.add(node)
        await session.flush()
        document = WikiDocument(node_id=node.id, title="Fresh")
        session.add(document)
        await session.flush()
        version = WikiDocumentVersion(
            document_id=document.id,
            version_no=1,
            body_markdown="fresh body",
            created_by_subject_id="admin",
        )
        session.add(version)
        await session.flush()
        document.current_version_id = version.id
        await session.commit()

    workspace_root = tmp_path / "wiki_workspace" / "current"
    feature_dir = workspace_root / "atomic-rebuild"
    stale = feature_dir / "knowledge-base" / "stale.md"
    stale.parent.mkdir(parents=True)
    stale.write_text("stale body", encoding="utf-8")
    observed_feature_dir_exists: list[bool] = []
    original_copy2 = __import__("shutil").copy2

    def copy2_probe(src: Path, dst: Path):
        observed_feature_dir_exists.append(feature_dir.exists())
        return original_copy2(src, dst)

    monkeypatch.setattr("codeask.agent.opencode_compat.wiki_workspace.shutil.copy2", copy2_probe)
    projector = WikiWorkspaceProjector(
        session_factory=app.state.session_factory,
        workspace_root=workspace_root,
    )

    await projector.rebuild_feature("atomic-rebuild")

    assert observed_feature_dir_exists
    assert all(observed_feature_dir_exists)
    assert not stale.exists()
    assert (feature_dir / "knowledge-base" / "fresh.md").read_text(encoding="utf-8").endswith(
        "fresh body"
    )
