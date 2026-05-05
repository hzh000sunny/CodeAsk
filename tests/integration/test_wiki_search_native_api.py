import pytest
from httpx import AsyncClient
from sqlalchemy import select

from codeask.db.models import WikiDocument, WikiDocumentVersion, WikiNode, WikiSpace


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
    assert document_hit["heading_path"] == "Native Search"
    assert report_hit["report_id"] == report_id
    assert report_hit["group_key"] == "current_feature_reports"


@pytest.mark.asyncio
async def test_wiki_search_groups_global_results_by_context_and_is_case_insensitive(
    client: AsyncClient,
    app,
) -> None:  # type: ignore[no-untyped-def]
    current_feature = await client.post(
        "/api/features",
        json={"name": "Current Search", "slug": "current-search"},
        headers={"X-Subject-Id": "owner@test"},
    )
    assert current_feature.status_code == 201, current_feature.text
    current_feature_id = current_feature.json()["id"]

    current_tree = await client.get(f"/api/wiki/tree?feature_id={current_feature_id}")
    assert current_tree.status_code == 200, current_tree.text
    current_tree_body = current_tree.json()
    current_knowledge_root = next(
        node for node in current_tree_body["nodes"] if node["system_role"] == "knowledge_base"
    )

    current_doc = await client.post(
        "/api/wiki/nodes",
        json={
            "space_id": current_tree_body["space"]["id"],
            "parent_id": current_knowledge_root["id"],
            "type": "document",
            "name": "Current Doc",
        },
        headers={"X-Subject-Id": "owner@test"},
    )
    assert current_doc.status_code == 201, current_doc.text
    current_doc_id = current_doc.json()["id"]

    publish_current = await client.post(
        f"/api/wiki/documents/{current_doc_id}/publish",
        json={"body_markdown": "# Current\n\nContains MIXED_CASE_WIKI_MARKER."},
        headers={"X-Subject-Id": "owner@test"},
    )
    assert publish_current.status_code == 200, publish_current.text

    current_report = await client.post(
        "/api/reports",
        json={
            "feature_id": current_feature_id,
            "title": "Current report",
            "body_markdown": "MIXED_CASE_WIKI_MARKER appears in the current report.",
            "metadata": _good_meta(),
        },
        headers={"X-Subject-Id": "owner@test"},
    )
    assert current_report.status_code == 201, current_report.text
    current_report_id = current_report.json()["id"]
    verify_current = await client.post(
        f"/api/reports/{current_report_id}/verify",
        headers={"X-Subject-Id": "owner@test"},
    )
    assert verify_current.status_code == 200, verify_current.text

    other_feature = await client.post(
        "/api/features",
        json={"name": "Other Search", "slug": "other-search"},
        headers={"X-Subject-Id": "owner@test"},
    )
    assert other_feature.status_code == 201, other_feature.text
    other_feature_id = other_feature.json()["id"]

    other_tree = await client.get(f"/api/wiki/tree?feature_id={other_feature_id}")
    assert other_tree.status_code == 200, other_tree.text
    other_tree_body = other_tree.json()
    other_knowledge_root = next(
        node for node in other_tree_body["nodes"] if node["system_role"] == "knowledge_base"
    )

    other_doc = await client.post(
        "/api/wiki/nodes",
        json={
            "space_id": other_tree_body["space"]["id"],
            "parent_id": other_knowledge_root["id"],
            "type": "document",
            "name": "Other Current Doc",
        },
        headers={"X-Subject-Id": "owner@test"},
    )
    assert other_doc.status_code == 201, other_doc.text
    publish_other = await client.post(
        f"/api/wiki/documents/{other_doc.json()['id']}/publish",
        json={"body_markdown": "# Other\n\nContains MIXED_CASE_WIKI_MARKER in another active feature."},
        headers={"X-Subject-Id": "owner@test"},
    )
    assert publish_other.status_code == 200, publish_other.text

    history_feature = await client.post(
        "/api/features",
        json={"name": "History Search", "slug": "history-search"},
        headers={"X-Subject-Id": "owner@test"},
    )
    assert history_feature.status_code == 201, history_feature.text
    history_feature_id = history_feature.json()["id"]

    async with app.state.session_factory() as session:
        history_space = WikiSpace(
            feature_id=history_feature_id,
            scope="history",
            display_name="history-search",
            slug="history-search-history",
            status="archived",
        )
        session.add(history_space)
        await session.flush()

        history_node = WikiNode(
            space_id=history_space.id,
            parent_id=None,
            type="document",
            name="History Doc",
            path="history-doc",
            system_role=None,
            sort_order=0,
        )
        session.add(history_node)
        await session.flush()

        history_document = WikiDocument(
            node_id=history_node.id,
            title="History Doc",
            current_version_id=None,
            index_status="ready",
            broken_refs_json={"links": [], "assets": []},
            provenance_json={"source": "manual_create"},
        )
        session.add(history_document)
        await session.flush()

        history_version = WikiDocumentVersion(
            document_id=history_document.id,
            version_no=1,
            body_markdown="# History\n\nContains MIXED_CASE_WIKI_MARKER in archived knowledge.",
            created_by_subject_id="owner@test",
        )
        session.add(history_version)
        await session.flush()

        history_document.current_version_id = history_version.id
        await session.commit()

    response = await client.get(
        f"/api/wiki/search?q=mixed_case_wiki_marker&current_feature_id={current_feature_id}"
    )
    assert response.status_code == 200, response.text
    body = response.json()

    group_keys = [item["group_key"] for item in body["items"]]
    assert "current_feature" in group_keys
    assert "current_feature_reports" in group_keys
    assert "other_current_features" in group_keys
    assert "history_features" in group_keys
