from pathlib import Path

import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker

from codeask.agent.chat_runtime.retrieval import DatabaseRetrievalService
from codeask.db.models import (
    Feature,
    FeatureRepo,
    Repo,
    Report,
    WikiDocument,
    WikiDocumentVersion,
    WikiNode,
    WikiReportRef,
    WikiSpace,
)
from codeask.wiki.native_search import NativeWikiSearchHit


@pytest.mark.asyncio
async def test_database_retrieval_returns_feature_rag_pack(
    app: FastAPI,
    tmp_path: Path,
) -> None:
    session_factory: async_sessionmaker = app.state.session_factory
    async with session_factory() as session:
        feature = Feature(
            name="Claude Code",
            slug="claude-code",
            description="Claude Code 源码学习与 TUI buddy 电子宠物分析",
            owner_subject_id="admin",
        )
        session.add(feature)
        await session.flush()

        repo = Repo(
            id="repo_claude_code",
            name="claude-code-source",
            source=Repo.SOURCE_LOCAL_DIR,
            local_path=str(tmp_path),
            bare_path=str(tmp_path / "bare"),
            status=Repo.STATUS_READY,
        )
        session.add(repo)
        await session.flush()
        session.add(FeatureRepo(feature_id=feature.id, repo_id=repo.id))

        space = WikiSpace(
            feature_id=feature.id,
            scope="current",
            display_name="Claude Code",
            slug="claude-code",
            status="active",
        )
        session.add(space)
        await session.flush()
        doc_node = WikiNode(
            space_id=space.id,
            parent_id=None,
            type="document",
            name="buddy.md",
            path="knowledge-base/buddy",
        )
        report_node = WikiNode(
            space_id=space.id,
            parent_id=None,
            type="report_ref",
            name="buddy-report",
            path="reports/verified/buddy-report",
        )
        session.add_all([doc_node, report_node])
        await session.flush()
        doc = WikiDocument(node_id=doc_node.id, title="Buddy 电子宠物实现")
        session.add(doc)
        await session.flush()
        version = WikiDocumentVersion(
            document_id=doc.id,
            version_no=1,
            body_markdown="CompanionSprite 渲染 buddy 电子宠物动画。",
            created_by_subject_id="admin",
        )
        session.add(version)
        await session.flush()
        doc.current_version_id = version.id

        report = Report(
            feature_id=feature.id,
            title="Buddy 电子宠物结论",
            body_markdown="claude code 的 buddy 目录包含电子宠物实现。",
            metadata_json={},
            status="verified",
            verified=True,
            created_by_subject_id="admin",
        )
        session.add(report)
        await session.flush()
        session.add(WikiReportRef(node_id=report_node.id, report_id=report.id))
        await session.commit()

    service = DatabaseRetrievalService(session_factory)
    result = await service.retrieve(
        user_message="claude code 里面有 buddy 电子宠物吗",
        session_summary=None,
        attachments=[],
    )

    assert result["feature_candidates"][0]["feature_id"] == feature.id
    assert result["feature_candidates"][0]["linked_repos"] == [
        {"repo_id": "repo_claude_code", "name": "claude-code-source"}
    ]
    assert result["wiki_hits"][0]["title"] == "Buddy 电子宠物实现"
    assert result["wiki_hits"][0]["feature_id"] == feature.id
    assert result["report_hits"][0]["title"] == "Buddy 电子宠物结论"
    assert result["report_hits"][0]["feature_id"] == feature.id


@pytest.mark.asyncio
async def test_database_retrieval_returns_ready_repo_candidates_for_model_choice(
    app: FastAPI,
    tmp_path: Path,
) -> None:
    session_factory: async_sessionmaker = app.state.session_factory
    async with session_factory() as session:
        repo = Repo(
            id="repo_claude_code",
            name="E2E claude-code 1778123017269",
            source=Repo.SOURCE_LOCAL_DIR,
            local_path=str(tmp_path),
            bare_path=str(tmp_path / "bare"),
            status=Repo.STATUS_READY,
        )
        ignored = Repo(
            id="repo_not_ready",
            name="claude-code indexing",
            source=Repo.SOURCE_LOCAL_DIR,
            local_path=str(tmp_path),
            bare_path=str(tmp_path / "ignored"),
            status=Repo.STATUS_CLONING,
        )
        session.add_all([repo, ignored])
        await session.commit()

    service = DatabaseRetrievalService(session_factory)
    result = await service.retrieve(
        user_message="claude code中，是如何调用工具进行grep的",
        session_summary=None,
        attachments=[],
    )

    assert result["repo_candidates"] == [
        {
            "repo_id": "repo_claude_code",
            "name": "E2E claude-code 1778123017269",
            "source": Repo.SOURCE_LOCAL_DIR,
            "status": Repo.STATUS_READY,
            "linked_feature_ids": [],
        }
    ]


@pytest.mark.asyncio
async def test_database_retrieval_matches_feature_name_embedded_in_chinese_sentence(
    app: FastAPI,
) -> None:
    session_factory: async_sessionmaker = app.state.session_factory
    async with session_factory() as session:
        feature = Feature(
            name="小米",
            slug="xiaomi",
            description="小米病历和病情变化记录",
            owner_subject_id="admin",
        )
        session.add(feature)
        await session.flush()

        other_feature = Feature(
            name="Claude Code",
            slug="claude-code",
            description="Claude Code 源码分析",
            owner_subject_id="admin",
        )
        archived_feature = Feature(
            name="历史小米",
            slug="history-xiaomi",
            description="已归档特性",
            owner_subject_id="admin",
            status="archived",
        )
        session.add_all([other_feature, archived_feature])
        await session.flush()

        unrelated_repo = Repo(
            id="repo_codeask",
            name="CodeAsk local 20260502-194633",
            source=Repo.SOURCE_LOCAL_DIR,
            local_path="/tmp/codeask",
            bare_path="/tmp/codeask/bare",
            status=Repo.STATUS_READY,
        )
        session.add(unrelated_repo)
        await session.commit()

    service = DatabaseRetrievalService(session_factory)
    result = await service.retrieve(
        user_message="我想知道小米的病情变化",
        session_summary=None,
        attachments=[],
    )

    assert [item["feature_id"] for item in result["feature_catalog"]] == [
        feature.id,
        other_feature.id,
    ]
    assert result["feature_catalog"][0]["name"] == "小米"
    assert result["repo_candidates"] == []


@pytest.mark.asyncio
async def test_database_retrieval_ranks_matched_feature_before_older_catalog_items(
    app: FastAPI,
) -> None:
    session_factory: async_sessionmaker = app.state.session_factory
    async with session_factory() as session:
        older = Feature(
            name="通用资料",
            slug="general-docs",
            description="无关的较早特性",
            owner_subject_id="admin",
        )
        matched = Feature(
            name="小米",
            slug="xiaomi",
            description="小米病历和病情变化记录",
            owner_subject_id="admin",
        )
        session.add_all([older, matched])
        await session.commit()

    service = DatabaseRetrievalService(session_factory)
    result = await service.retrieve(
        user_message="小米什么时候得的肿瘤",
        session_summary=None,
        attachments=[],
    )

    assert result["feature_candidates"][0]["feature_id"] == matched.id
    assert result["feature_catalog"][0]["feature_id"] == matched.id
    assert result["feature_catalog"][1]["feature_id"] == older.id


@pytest.mark.asyncio
async def test_database_retrieval_surfaces_wiki_index_when_feature_name_does_not_match(
    app: FastAPI,
) -> None:
    session_factory: async_sessionmaker = app.state.session_factory
    async with session_factory() as session:
        feature = Feature(
            name="宠物健康",
            slug="pet-health",
            description="治疗记录和健康档案",
            owner_subject_id="admin",
        )
        session.add(feature)
        await session.flush()

        space = WikiSpace(
            feature_id=feature.id,
            scope="current",
            display_name="宠物健康",
            slug="pet-health",
            status="active",
        )
        session.add(space)
        await session.flush()

        doc_node = WikiNode(
            space_id=space.id,
            parent_id=None,
            type="document",
            name="小米病历.md",
            path="knowledge-base/小米病历",
        )
        session.add(doc_node)
        await session.flush()
        doc = WikiDocument(node_id=doc_node.id, title="小米病历")
        session.add(doc)
        await session.flush()
        version = WikiDocumentVersion(
            document_id=doc.id,
            version_no=1,
            body_markdown=(
                "## 基本情况\n"
                "姓名：小米\n"
                "体重：2.5kg（现2.2kg）\n"
                "治疗历史：右脚脚掌肥大细胞瘤，胰腺炎、胆囊炎。\n"
            ),
            created_by_subject_id="admin",
        )
        session.add(version)
        await session.flush()
        doc.current_version_id = version.id
        await session.commit()

    service = DatabaseRetrievalService(session_factory)
    result = await service.retrieve(
        user_message="我想知道小米的病情变化",
        session_summary=None,
        attachments=[],
    )

    assert result["feature_catalog"][0]["feature_id"] == feature.id
    assert result["feature_catalog"][0]["name"] == "宠物健康"
    assert result["wiki_hits"][0]["feature_id"] == feature.id
    assert result["wiki_hits"][0]["title"] == "小米病历"
    knowledge_index = result["feature_knowledge_index"][0]
    assert knowledge_index["feature_id"] == feature.id
    assert "小米病历" in knowledge_index["wiki_titles"]
    assert "knowledge-base/小米病历" in knowledge_index["wiki_paths"]
    assert "小米" in knowledge_index["keywords"]


@pytest.mark.asyncio
async def test_database_retrieval_deduplicates_native_hits_by_source_identity(
    app: FastAPI,
) -> None:
    session_factory: async_sessionmaker = app.state.session_factory
    service = DatabaseRetrievalService(session_factory)
    service._native_search = _DuplicateNativeSearch()  # type: ignore[attr-defined]
    result = await service.retrieve(
        user_message="小米病情趋势",
        session_summary=None,
        attachments=[],
    )

    assert [item["document_id"] for item in result["wiki_hits"]] == [10]
    assert [item["report_id"] for item in result["report_hits"]] == [20]


class _DuplicateNativeSearch:
    async def search(self, *args: object, **kwargs: object) -> list[NativeWikiSearchHit]:
        return [
            NativeWikiSearchHit(
                kind="document",
                node_id=1,
                title="小米病历",
                path="knowledge-base/小米病历",
                feature_id=3,
                group_key="current_feature",
                group_label="当前特性",
                snippet="小米病情趋势",
                score=5.0,
                document_id=10,
            ),
            NativeWikiSearchHit(
                kind="document",
                node_id=2,
                title="小米病历",
                path="knowledge-base/小米病历#基本情况",
                feature_id=3,
                group_key="current_feature",
                group_label="当前特性",
                snippet="小米病情趋势重复片段",
                score=4.5,
                document_id=10,
            ),
            NativeWikiSearchHit(
                kind="report_ref",
                node_id=3,
                title="小米病情趋势报告",
                path="reports/verified/小米病情趋势报告",
                feature_id=3,
                group_key="current_feature_reports",
                group_label="问题定位报告",
                snippet="小米病情趋势报告",
                score=4.0,
                report_id=20,
            ),
            NativeWikiSearchHit(
                kind="report_ref",
                node_id=4,
                title="小米病情趋势报告",
                path="reports/verified/小米病情趋势报告#摘要",
                feature_id=3,
                group_key="current_feature_reports",
                group_label="问题定位报告",
                snippet="小米病情趋势报告重复片段",
                score=3.5,
                report_id=20,
            ),
        ]
