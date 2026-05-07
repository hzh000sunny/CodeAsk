import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from codeask.agent.chat_runtime.tool_contracts import ToolContext, ToolErrorType
from codeask.agent.chat_runtime.tool_executor import ToolExecutor


@pytest.mark.asyncio
async def test_chat_runtime_registers_real_wiki_tools(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    feature = await client.post(
        "/api/features",
        json={"name": "Runtime Wiki", "slug": "runtime-wiki"},
        headers={"X-Subject-Id": "owner@test"},
    )
    assert feature.status_code == 201, feature.text
    feature_id = int(feature.json()["id"])

    tree_response = await client.get(f"/api/wiki/tree?feature_id={feature_id}")
    assert tree_response.status_code == 200, tree_response.text
    tree = tree_response.json()
    knowledge_root = next(node for node in tree["nodes"] if node["system_role"] == "knowledge_base")

    node_response = await client.post(
        "/api/wiki/nodes",
        json={
            "space_id": tree["space"]["id"],
            "parent_id": knowledge_root["id"],
            "type": "document",
            "name": "回调 Runbook",
        },
        headers={"X-Subject-Id": "owner@test"},
    )
    assert node_response.status_code == 201, node_response.text
    node_id = int(node_response.json()["id"])

    publish = await client.post(
        f"/api/wiki/documents/{node_id}/publish",
        json={
            "body_markdown": (
                "# 回调 Runbook\n\n"
                "## 排查步骤\n\n"
                "先检查 webhook 回调是否超时。\n\n"
                "## 结论\n\n"
                "处理完成。"
            ),
        },
        headers={"X-Subject-Id": "owner@test"},
    )
    assert publish.status_code == 200, publish.text

    registry = app.state.chat_runtime._tool_registry
    tool_names = {tool.name for tool in registry.available_tools()}
    assert {"search_wiki", "read_wiki_node"} <= tool_names

    executor = ToolExecutor(registry)
    search = await executor.execute(
        "search_wiki",
        {"query": "webhook 回调", "feature_ids": [feature_id], "limit": 5},
        ToolContext(session_id="sess_wiki", turn_id="turn_search", subject_id="owner@test"),
    )
    assert search.ok is True
    assert search.items[0]["node_id"] == node_id
    assert search.items[0]["feature_id"] == feature_id
    assert search.items[0]["heading_path"] == "回调 Runbook > 排查步骤"
    assert search.evidence_refs[0].node_id == node_id

    read = await executor.execute(
        "read_wiki_node",
        {"node_id": node_id, "heading": "排查步骤"},
        ToolContext(session_id="sess_wiki", turn_id="turn_read", subject_id="owner@test"),
    )
    assert read.ok is True
    assert read.items[0]["node_id"] == node_id
    assert "先检查 webhook 回调是否超时。" in read.items[0]["content"]
    assert "## 结论" not in read.items[0]["content"]

    missing = await executor.execute(
        "read_wiki_node",
        {"node_id": 999999},
        ToolContext(session_id="sess_wiki", turn_id="turn_missing", subject_id="owner@test"),
    )
    assert missing.ok is False
    assert missing.error_type == ToolErrorType.NOT_FOUND


@pytest.mark.asyncio
async def test_search_wiki_falls_back_to_terms_for_long_mixed_query(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    feature = await client.post(
        "/api/features",
        json={"name": "AnythingLLM Reference", "slug": "anythingllm-reference"},
        headers={"X-Subject-Id": "owner@test"},
    )
    assert feature.status_code == 201, feature.text
    feature_id = int(feature.json()["id"])

    tree_response = await client.get(f"/api/wiki/tree?feature_id={feature_id}")
    assert tree_response.status_code == 200, tree_response.text
    tree = tree_response.json()
    knowledge_root = next(node for node in tree["nodes"] if node["system_role"] == "knowledge_base")

    node_response = await client.post(
        "/api/wiki/nodes",
        json={
            "space_id": tree["space"]["id"],
            "parent_id": knowledge_root["id"],
            "type": "document",
            "name": "Ingestion And Document Lifecycle",
        },
        headers={"X-Subject-Id": "owner@test"},
    )
    assert node_response.status_code == 201, node_response.text
    node_id = int(node_response.json()["id"])

    publish = await client.post(
        f"/api/wiki/documents/{node_id}/publish",
        json={
            "body_markdown": (
                "# Ingestion And Document Lifecycle\n\n"
                "AnythingLLM uses workspace retrieval with document chunks and embeddings."
            ),
        },
        headers={"X-Subject-Id": "owner@test"},
    )
    assert publish.status_code == 200, publish.text

    executor = ToolExecutor(app.state.chat_runtime._tool_registry)
    search = await executor.execute(
        "search_wiki",
        {
            "query": "AnythingLLM 召回 retrieval embedding search",
            "feature_ids": [feature_id],
            "limit": 5,
        },
        ToolContext(session_id="sess_wiki", turn_id="turn_search", subject_id="owner@test"),
    )

    assert search.ok is True
    assert search.items
    assert search.items[0]["node_id"] == node_id
    assert search.evidence_refs[0].node_id == node_id
