import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from codeask.agent.state import AgentState
from codeask.agent.tool_models import ToolContext


def _tool_ctx(feature_id: int) -> ToolContext:
    return ToolContext(
        session_id="sess_wiki_tools",
        turn_id="turn_wiki_tools",
        feature_ids=[feature_id],
        repo_bindings=[],
        subject_id="owner@test",
        phase=AgentState.KnowledgeRetrieval,
        limits={},
    )


@pytest.mark.asyncio
async def test_wiki_agent_tools_search_and_read_native_wiki_content(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/features",
        json={"name": "Wiki Tools", "slug": "wiki-tools"},
        headers={"X-Subject-Id": "owner@test"},
    )
    assert response.status_code == 201, response.text
    feature_id = response.json()["id"]

    response = await client.get(f"/api/wiki/tree?feature_id={feature_id}")
    assert response.status_code == 200, response.text
    tree = response.json()
    knowledge_root = next(node for node in tree["nodes"] if node["system_role"] == "knowledge_base")

    response = await client.post(
        "/api/wiki/nodes",
        json={
            "space_id": tree["space"]["id"],
            "parent_id": knowledge_root["id"],
            "type": "document",
            "name": "回调 Runbook",
        },
        headers={"X-Subject-Id": "owner@test"},
    )
    assert response.status_code == 201, response.text
    node_id = response.json()["id"]

    response = await client.post(
        f"/api/wiki/documents/{node_id}/publish",
        json={
            "body_markdown": "# 回调 Runbook\n\n## 排查步骤\n\n先检查 webhook 回调是否超时。\n\n## 结论\n\n处理完成。",
        },
        headers={"X-Subject-Id": "owner@test"},
    )
    assert response.status_code == 200, response.text
    document_id = response.json()["document_id"]

    response = await client.post(
        "/api/reports",
        json={
            "feature_id": feature_id,
            "title": "回调超时报错",
            "body_markdown": "webhook 回调超时导致告警。",
            "metadata": {
                "evidence": [{"type": "log", "summary": "timeout"}],
                "applicability": "callback pipeline",
                "recommended_fix": "increase timeout guard",
            },
        },
        headers={"X-Subject-Id": "owner@test"},
    )
    assert response.status_code == 201, response.text
    report_id = response.json()["id"]
    response = await client.post(
        f"/api/reports/{report_id}/verify",
        headers={"X-Subject-Id": "owner@test"},
    )
    assert response.status_code == 200, response.text

    registry = app.state.tool_registry
    ctx = _tool_ctx(feature_id)

    search_docs = await registry.call("search_wiki", {"query": "webhook 回调"}, ctx)
    assert search_docs.ok is True
    doc_items = search_docs.data["items"]
    assert isinstance(doc_items, list)
    assert doc_items[0]["document_id"] == document_id
    assert doc_items[0]["heading_path"] == "回调 Runbook > 排查步骤"

    read_doc = await registry.call(
        "read_wiki_doc",
        {"document_id": document_id, "heading_path": "排查步骤"},
        ctx,
    )
    assert read_doc.ok is True
    assert read_doc.data["title"] == "回调 Runbook"
    assert "先检查 webhook 回调是否超时。" in read_doc.data["excerpt_markdown"]
    assert "## 结论" not in read_doc.data["excerpt_markdown"]

    read_node = await registry.call(
        "read_wiki_node",
        {"node_id": node_id, "heading_path": "排查步骤"},
        ctx,
    )
    assert read_node.ok is True
    assert read_node.data["document_id"] == document_id
    assert read_node.data["node_id"] == node_id
    assert "先检查 webhook 回调是否超时。" in read_node.data["excerpt_markdown"]

    search_reports = await registry.call("search_reports", {"query": "回调超时"}, ctx)
    assert search_reports.ok is True
    report_items = search_reports.data["items"]
    assert isinstance(report_items, list)
    assert report_items[0]["report_id"] == report_id

    read_report = await registry.call("read_report", {"report_id": report_id}, ctx)
    assert read_report.ok is True
    assert read_report.data["title"] == "回调超时报错"
    assert "webhook 回调超时导致告警。" in read_report.data["body_markdown"]


@pytest.mark.asyncio
async def test_wiki_agent_tools_search_across_multiple_features(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    first = await client.post(
        "/api/features",
        json={"name": "Orders", "slug": "orders"},
        headers={"X-Subject-Id": "owner@test"},
    )
    assert first.status_code == 201, first.text
    first_feature_id = first.json()["id"]

    second = await client.post(
        "/api/features",
        json={"name": "Payments", "slug": "payments"},
        headers={"X-Subject-Id": "owner@test"},
    )
    assert second.status_code == 201, second.text
    second_feature_id = second.json()["id"]

    first_tree = await client.get(f"/api/wiki/tree?feature_id={first_feature_id}")
    assert first_tree.status_code == 200, first_tree.text
    first_knowledge_root = next(
        node for node in first_tree.json()["nodes"] if node["system_role"] == "knowledge_base"
    )
    second_tree = await client.get(f"/api/wiki/tree?feature_id={second_feature_id}")
    assert second_tree.status_code == 200, second_tree.text
    second_knowledge_root = next(
        node for node in second_tree.json()["nodes"] if node["system_role"] == "knowledge_base"
    )

    first_doc = await client.post(
        "/api/wiki/nodes",
        json={
            "space_id": first_tree.json()["space"]["id"],
            "parent_id": first_knowledge_root["id"],
            "type": "document",
            "name": "Orders Runbook",
        },
        headers={"X-Subject-Id": "owner@test"},
    )
    assert first_doc.status_code == 201, first_doc.text
    first_node_id = first_doc.json()["id"]
    publish_first = await client.post(
        f"/api/wiki/documents/{first_node_id}/publish",
        json={"body_markdown": "# Orders\n\nContains CROSS_FEATURE_MARKER in orders."},
        headers={"X-Subject-Id": "owner@test"},
    )
    assert publish_first.status_code == 200, publish_first.text

    second_doc = await client.post(
        "/api/wiki/nodes",
        json={
            "space_id": second_tree.json()["space"]["id"],
            "parent_id": second_knowledge_root["id"],
            "type": "document",
            "name": "Payments Runbook",
        },
        headers={"X-Subject-Id": "owner@test"},
    )
    assert second_doc.status_code == 201, second_doc.text
    second_node_id = second_doc.json()["id"]
    publish_second = await client.post(
        f"/api/wiki/documents/{second_node_id}/publish",
        json={"body_markdown": "# Payments\n\nContains CROSS_FEATURE_MARKER in payments."},
        headers={"X-Subject-Id": "owner@test"},
    )
    assert publish_second.status_code == 200, publish_second.text

    registry = app.state.tool_registry
    ctx = ToolContext(
        session_id="sess_multi_feature",
        turn_id="turn_multi_feature",
        feature_ids=[first_feature_id, second_feature_id],
        repo_bindings=[],
        subject_id="owner@test",
        phase=AgentState.KnowledgeRetrieval,
        limits={},
    )

    search_docs = await registry.call(
        "search_wiki",
        {"query": "CROSS_FEATURE_MARKER"},
        ctx,
    )
    assert search_docs.ok is True
    items = search_docs.data["items"]
    assert isinstance(items, list)
    assert {item["feature_id"] for item in items} == {first_feature_id, second_feature_id}
