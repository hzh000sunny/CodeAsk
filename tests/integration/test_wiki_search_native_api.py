import pytest
from httpx import AsyncClient


def _good_meta() -> dict:
    return {
        "evidence": [
            {"type": "log", "summary": "stack trace null user"},
            {
                "type": "code",
                "source": {
                    "repo_id": "repo_order",
                    "commit_sha": "abc1234",
                    "path": "src/x.py",
                },
                "summary": "missing null check",
            },
        ],
        "applicability": "v2.4.x default config",
        "recommended_fix": "guard user before user.id",
        "repo_commits": [{"repo_id": "repo_order", "commit_sha": "abc1234"}],
        "error_signatures": ["ERR_NATIVE_WIKI_SEARCH"],
        "tags": ["order"],
    }


@pytest.mark.asyncio
async def test_wiki_search_returns_native_documents_and_report_refs(client: AsyncClient) -> None:
    response = await client.post(
        "/api/features",
        json={"name": "Native Search", "slug": "native-search"},
        headers={"X-Subject-Id": "owner@test"},
    )
    feature_id = response.json()["id"]

    response = await client.get(f"/api/wiki/tree?feature_id={feature_id}")
    assert response.status_code == 200, response.text
    tree_body = response.json()
    knowledge_root = next(node for node in tree_body["nodes"] if node["system_role"] == "knowledge_base")

    response = await client.post(
        "/api/wiki/nodes",
        json={
            "space_id": tree_body["space"]["id"],
            "parent_id": knowledge_root["id"],
            "type": "document",
            "name": "Native search doc",
        },
        headers={"X-Subject-Id": "owner@test"},
    )
    assert response.status_code == 201, response.text
    document_node_id = response.json()["id"]

    response = await client.post(
        f"/api/wiki/documents/{document_node_id}/publish",
        json={
            "body_markdown": "# Native Search\n\nThis body contains NATIVE_WIKI_SEARCH_MARKER.",
        },
        headers={"X-Subject-Id": "owner@test"},
    )
    assert response.status_code == 200, response.text

    response = await client.post(
        "/api/reports",
        json={
            "feature_id": feature_id,
            "title": "Searchable wiki report",
            "body_markdown": "NATIVE_WIKI_SEARCH_MARKER also appears in the report body.",
            "metadata": _good_meta(),
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

    response = await client.get(
        f"/api/wiki/search?q=NATIVE_WIKI_SEARCH_MARKER&feature_id={feature_id}"
    )
    assert response.status_code == 200, response.text
    body = response.json()

    document_hit = next(item for item in body["items"] if item["kind"] == "document")
    report_hit = next(item for item in body["items"] if item["kind"] == "report_ref")

    assert document_hit["node_id"] == document_node_id
    assert document_hit["group_key"] == "current_feature"
    assert report_hit["report_id"] == report_id
    assert report_hit["group_key"] == "current_feature_reports"
