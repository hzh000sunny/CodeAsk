import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_wiki_path_resolver_matches_roots_and_named_nodes_within_feature(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/features",
        json={"name": "Resolver Feature", "slug": "resolver-feature"},
        headers={"X-Subject-Id": "owner@test"},
    )
    assert response.status_code == 201, response.text
    feature_id = response.json()["id"]

    response = await client.get(f"/api/wiki/tree?feature_id={feature_id}")
    assert response.status_code == 200, response.text
    tree = response.json()
    space_id = tree["space"]["id"]
    knowledge_root = next(node for node in tree["nodes"] if node["system_role"] == "knowledge_base")
    reports_root = next(node for node in tree["nodes"] if node["system_role"] == "reports")

    response = await client.post(
        "/api/wiki/nodes",
        json={
            "space_id": space_id,
            "parent_id": knowledge_root["id"],
            "type": "folder",
            "name": "支付回调",
        },
        headers={"X-Subject-Id": "owner@test"},
    )
    assert response.status_code == 201, response.text
    callback_folder = response.json()

    response = await client.post(
        "/api/wiki/nodes",
        json={
            "space_id": space_id,
            "parent_id": callback_folder["id"],
            "type": "document",
            "name": "回调 Runbook",
        },
        headers={"X-Subject-Id": "owner@test"},
    )
    assert response.status_code == 201, response.text
    runbook_document = response.json()

    resolve_root = await client.get(
        f"/api/wiki/resolve-path?q=问题报告&feature_id={feature_id}"
    )
    assert resolve_root.status_code == 200, resolve_root.text
    root_body = resolve_root.json()
    assert root_body["items"][0]["node_id"] == reports_root["id"]
    assert root_body["items"][0]["system_role"] == "reports"
    assert root_body["items"][0]["match_reason"] == "alias"

    resolve_folder = await client.get(
        f"/api/wiki/resolve-path?q=知识库/支付回调&feature_id={feature_id}"
    )
    assert resolve_folder.status_code == 200, resolve_folder.text
    folder_body = resolve_folder.json()
    assert folder_body["items"][0]["node_id"] == callback_folder["id"]
    assert folder_body["items"][0]["name"] == "支付回调"

    resolve_document = await client.get(
        f"/api/wiki/resolve-path?q=runbook 回调&feature_id={feature_id}"
    )
    assert resolve_document.status_code == 200, resolve_document.text
    document_body = resolve_document.json()
    assert document_body["items"][0]["node_id"] == runbook_document["id"]
    assert document_body["items"][0]["name"] == "回调 Runbook"

