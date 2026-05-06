"""Read-only API tests for native wiki spaces and tree."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from codeask.db.models import Document, Feature, Report, WikiDocument, WikiReportRef, WikiSpace


PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89"
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00"
    b"\x18\xdd\x8d\xb1"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


async def _create_feature(client: AsyncClient) -> int:
    response = await client.post(
        "/api/features",
        json={"name": "Knowledge", "slug": "knowledge"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


@pytest.mark.asyncio
async def test_get_wiki_space_by_feature(client: AsyncClient) -> None:
    feature_id = await _create_feature(client)

    response = await client.get(f"/api/wiki/spaces/by-feature/{feature_id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["feature_id"] == feature_id
    assert body["scope"] == "current"
    assert body["slug"] == "knowledge"


@pytest.mark.asyncio
async def test_get_wiki_tree_for_feature(client: AsyncClient) -> None:
    feature_id = await _create_feature(client)

    response = await client.get("/api/wiki/tree", params={"feature_id": feature_id})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["space"]["feature_id"] == feature_id
    assert [node["name"] for node in body["nodes"]] == ["知识库", "问题定位报告"]


@pytest.mark.asyncio
async def test_get_wiki_tree_returns_global_virtual_roots(client: AsyncClient) -> None:
    first_feature_id = await _create_feature(client)
    second = await client.post(
        "/api/features",
        json={"name": "Billing", "slug": "billing"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert second.status_code == 201, second.text
    second_feature_id = int(second.json()["id"])

    response = await client.get("/api/wiki/tree")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["space"] is None

    current_root = next(
        node for node in body["nodes"] if node["system_role"] == "feature_group_current"
    )
    history_root = next(
        node for node in body["nodes"] if node["system_role"] == "feature_group_history"
    )
    assert current_root["name"] == "当前特性"
    assert history_root["name"] == "历史特性"
    assert current_root["parent_id"] is None
    assert history_root["parent_id"] is None

    current_feature_nodes = [
        node
        for node in body["nodes"]
        if node["parent_id"] == current_root["id"]
        and node["system_role"] == "feature_space_current"
    ]
    assert [node["name"] for node in current_feature_nodes] == ["Knowledge", "Billing"]

    first_feature_root = next(
        node for node in current_feature_nodes if node["feature_id"] == first_feature_id
    )
    second_feature_root = next(
        node for node in current_feature_nodes if node["feature_id"] == second_feature_id
    )

    first_children = [
        node["name"] for node in body["nodes"] if node["parent_id"] == first_feature_root["id"]
    ]
    second_children = [
        node["name"] for node in body["nodes"] if node["parent_id"] == second_feature_root["id"]
    ]
    assert first_children == ["知识库", "问题定位报告"]
    assert second_children == ["知识库", "问题定位报告"]


@pytest.mark.asyncio
async def test_get_wiki_tree_returns_full_active_node_set(client: AsyncClient) -> None:
    feature_id = await _create_feature(client)

    tree = await client.get("/api/wiki/tree", params={"feature_id": feature_id})
    assert tree.status_code == 200, tree.text
    space_id = int(tree.json()["space"]["id"])
    knowledge_root = next(
        node for node in tree.json()["nodes"] if node["name"] == "知识库"
    )

    folder = await client.post(
        "/api/wiki/nodes",
        json={
            "space_id": space_id,
            "parent_id": int(knowledge_root["id"]),
            "type": "folder",
            "name": "Runbooks",
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert folder.status_code == 201, folder.text

    document = await client.post(
        "/api/wiki/nodes",
        json={
            "space_id": space_id,
            "parent_id": int(folder.json()["id"]),
            "type": "document",
            "name": "Payment Callback",
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert document.status_code == 201, document.text

    response = await client.get("/api/wiki/tree", params={"feature_id": feature_id})

    assert response.status_code == 200, response.text
    body = response.json()
    paths = [node["path"] for node in body["nodes"]]
    root_path = str(knowledge_root["path"])
    assert root_path in paths
    assert f"{root_path}/runbooks" in paths
    assert f"{root_path}/runbooks/payment-callback" in paths


@pytest.mark.asyncio
async def test_rename_wiki_document_updates_document_title(client: AsyncClient, app) -> None:  # type: ignore[no-untyped-def]
    feature_id = await _create_feature(client)

    tree = await client.get("/api/wiki/tree", params={"feature_id": feature_id})
    assert tree.status_code == 200, tree.text
    body = tree.json()
    knowledge_root = next(node for node in body["nodes"] if node["system_role"] == "knowledge_base")

    created = await client.post(
        "/api/wiki/nodes",
        json={
            "space_id": body["space"]["id"],
            "parent_id": knowledge_root["id"],
            "type": "document",
            "name": "旧标题",
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert created.status_code == 201, created.text
    node_id = int(created.json()["id"])

    renamed = await client.put(
        f"/api/wiki/nodes/{node_id}",
        json={"name": "新标题"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert renamed.status_code == 200, renamed.text

    async with app.state.session_factory() as session:
        document = (
            await session.execute(select(WikiDocument).where(WikiDocument.node_id == node_id))
        ).scalar_one()

    assert document.title == "新标题"


@pytest.mark.asyncio
async def test_renaming_target_document_refreshes_linking_document_reference_state(
    client: AsyncClient,
) -> None:
    feature_id = await _create_feature(client)

    tree = await client.get("/api/wiki/tree", params={"feature_id": feature_id})
    assert tree.status_code == 200, tree.text
    body = tree.json()
    knowledge_root = next(node for node in body["nodes"] if node["system_role"] == "knowledge_base")

    runbook = await client.post(
        "/api/wiki/nodes",
        json={
            "space_id": body["space"]["id"],
            "parent_id": knowledge_root["id"],
            "type": "document",
            "name": "Runbook",
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert runbook.status_code == 201, runbook.text
    runbook_id = int(runbook.json()["id"])

    guide = await client.post(
        "/api/wiki/nodes",
        json={
            "space_id": body["space"]["id"],
            "parent_id": knowledge_root["id"],
            "type": "document",
            "name": "Guide",
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert guide.status_code == 201, guide.text
    guide_id = int(guide.json()["id"])

    publish_runbook = await client.post(
        f"/api/wiki/documents/{runbook_id}/publish",
        json={"body_markdown": "# Runbook\n\nSee [Guide](./Guide.md)"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert publish_runbook.status_code == 200, publish_runbook.text

    publish_guide = await client.post(
        f"/api/wiki/documents/{guide_id}/publish",
        json={"body_markdown": "# Guide\n\nStable target."},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert publish_guide.status_code == 200, publish_guide.text

    detail_before = await client.get(
        f"/api/wiki/documents/{runbook_id}",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert detail_before.status_code == 200, detail_before.text
    assert detail_before.json()["broken_refs_json"] == {"links": [], "assets": []}

    renamed = await client.put(
        f"/api/wiki/nodes/{guide_id}",
        json={"name": "Guide v2"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert renamed.status_code == 200, renamed.text

    detail_after = await client.get(
        f"/api/wiki/documents/{runbook_id}",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert detail_after.status_code == 200, detail_after.text
    assert detail_after.json()["broken_refs_json"]["links"][0]["target"] == "./Guide.md"


@pytest.mark.asyncio
async def test_moving_document_out_and_back_restores_relative_asset_references(
    client: AsyncClient,
    tmp_path,
) -> None:
    feature_id = await _create_feature(client)

    tree = await client.get("/api/wiki/tree", params={"feature_id": feature_id})
    assert tree.status_code == 200, tree.text
    body = tree.json()
    space_id = int(body["space"]["id"])
    knowledge_root = next(node for node in body["nodes"] if node["system_role"] == "knowledge_base")

    asset_folder = await client.post(
        "/api/wiki/nodes",
        json={
            "space_id": space_id,
            "parent_id": int(knowledge_root["id"]),
            "type": "folder",
            "name": "Untitled.assets",
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert asset_folder.status_code == 201, asset_folder.text

    image_path = tmp_path / "image.png"
    image_path.write_bytes(PNG_BYTES)
    with image_path.open("rb") as image_file:
        asset = await client.post(
            "/api/wiki/assets",
            data={"space_id": str(space_id), "parent_id": str(asset_folder.json()["id"])},
            files={"file": ("image.png", image_file, "image/png")},
            headers={"X-Subject-Id": "alice@dev-1"},
        )
    assert asset.status_code == 201, asset.text
    asset_node_id = int(asset.json()["node_id"])

    nested_folder = await client.post(
        "/api/wiki/nodes",
        json={
            "space_id": space_id,
            "parent_id": int(knowledge_root["id"]),
            "type": "folder",
            "name": "test",
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert nested_folder.status_code == 201, nested_folder.text

    document = await client.post(
        "/api/wiki/nodes",
        json={
            "space_id": space_id,
            "parent_id": int(knowledge_root["id"]),
            "type": "document",
            "name": "Xiaomi",
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert document.status_code == 201, document.text
    document_node_id = int(document.json()["id"])

    publish = await client.post(
        f"/api/wiki/documents/{document_node_id}/publish",
        json={
            "body_markdown": (
                '<img src="Untitled.assets/image.png" alt="image" style="zoom:50%;" />'
            )
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert publish.status_code == 200, publish.text
    refs_before = {item["target"]: item for item in publish.json()["resolved_refs_json"]}
    assert refs_before["Untitled.assets/image.png"]["broken"] is False
    assert refs_before["Untitled.assets/image.png"]["resolved_node_id"] == asset_node_id

    moved_into_folder = await client.post(
        f"/api/wiki/nodes/{document_node_id}/move",
        json={"target_parent_id": int(nested_folder.json()["id"]), "target_index": 0},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert moved_into_folder.status_code == 200, moved_into_folder.text

    detail_inside = await client.get(
        f"/api/wiki/documents/{document_node_id}",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert detail_inside.status_code == 200, detail_inside.text
    assert detail_inside.json()["broken_refs_json"]["assets"][0]["target"] == "Untitled.assets/image.png"

    moved_back = await client.post(
        f"/api/wiki/nodes/{document_node_id}/move",
        json={"target_parent_id": int(knowledge_root["id"]), "target_index": 0},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert moved_back.status_code == 200, moved_back.text

    detail_after = await client.get(
        f"/api/wiki/documents/{document_node_id}",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert detail_after.status_code == 200, detail_after.text
    refs_after = {item["target"]: item for item in detail_after.json()["resolved_refs_json"]}
    assert detail_after.json()["broken_refs_json"]["assets"] == []
    assert refs_after["Untitled.assets/image.png"]["broken"] is False
    assert refs_after["Untitled.assets/image.png"]["resolved_node_id"] == asset_node_id


@pytest.mark.asyncio
async def test_get_wiki_space_bootstraps_legacy_feature_without_space(
    client: AsyncClient,
    app,
) -> None:  # type: ignore[no-untyped-def]
    async with app.state.session_factory() as session:
        feature = Feature(
            name="Legacy",
            slug="legacy",
            description="legacy feature",
            owner_subject_id="legacy@dev-1",
        )
        session.add(feature)
        await session.commit()
        feature_id = feature.id

    response = await client.get(f"/api/wiki/spaces/by-feature/{feature_id}")

    assert response.status_code == 200, response.text
    async with app.state.session_factory() as session:
        space = (
            await session.execute(
                select(WikiSpace).where(WikiSpace.feature_id == feature_id, WikiSpace.scope == "current")
            )
        ).scalar_one_or_none()
    assert space is not None
    assert space.slug == "legacy"


@pytest.mark.asyncio
async def test_get_wiki_tree_backfills_legacy_docs_and_reports(
    client: AsyncClient,
    app,
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    markdown_path = tmp_path / "legacy.md"
    markdown_path.write_text("# Legacy Doc\n\nBody", encoding="utf-8")

    async with app.state.session_factory() as session:
        feature = Feature(
            name="Legacy Data",
            slug="legacy-data",
            description="legacy data",
            owner_subject_id="legacy@dev-2",
        )
        session.add(feature)
        await session.flush()
        session.add(
            Document(
                feature_id=feature.id,
                kind="markdown",
                title="Legacy Doc",
                path="legacy.md",
                tags_json=None,
                raw_file_path=str(markdown_path),
                summary=None,
                is_deleted=False,
                uploaded_by_subject_id="legacy@dev-2",
            )
        )
        session.add(
            Report(
                feature_id=feature.id,
                title="Legacy Report",
                body_markdown="legacy report body",
                metadata_json={"evidence": [], "applicability": "", "recommended_fix": ""},
                status="draft",
                verified=False,
                created_by_subject_id="legacy@dev-2",
            )
        )
        await session.commit()
        feature_id = feature.id

    response = await client.get("/api/wiki/tree", params={"feature_id": feature_id})

    assert response.status_code == 200, response.text
    async with app.state.session_factory() as session:
        wiki_doc = (await session.execute(select(WikiDocument))).scalar_one_or_none()
        wiki_report = (await session.execute(select(WikiReportRef))).scalar_one_or_none()

    assert wiki_doc is not None
    assert wiki_doc.legacy_document_id is not None
    assert wiki_report is not None


@pytest.mark.asyncio
async def test_archived_feature_moves_from_current_root_to_history_root(
    client: AsyncClient,
) -> None:
    active_feature_id = await _create_feature(client)
    archived_feature = await client.post(
        "/api/features",
        json={"name": "Legacy Billing", "slug": "legacy-billing"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert archived_feature.status_code == 201, archived_feature.text
    archived_feature_id = int(archived_feature.json()["id"])

    archived_tree = await client.get("/api/wiki/tree", params={"feature_id": archived_feature_id})
    assert archived_tree.status_code == 200, archived_tree.text
    archived_knowledge_root = next(
        node for node in archived_tree.json()["nodes"] if node["system_role"] == "knowledge_base"
    )
    archived_document = await client.post(
        "/api/wiki/nodes",
        json={
            "space_id": archived_tree.json()["space"]["id"],
            "parent_id": archived_knowledge_root["id"],
            "type": "document",
            "name": "Archived Runbook",
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert archived_document.status_code == 201, archived_document.text

    archived_delete = await client.delete(
        f"/api/features/{archived_feature_id}",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert archived_delete.status_code == 204, archived_delete.text

    global_tree = await client.get("/api/wiki/tree")
    assert global_tree.status_code == 200, global_tree.text
    body = global_tree.json()

    current_root = next(
        node for node in body["nodes"] if node["system_role"] == "feature_group_current"
    )
    history_root = next(
        node for node in body["nodes"] if node["system_role"] == "feature_group_history"
    )

    current_feature_nodes = [
        node
        for node in body["nodes"]
        if node["parent_id"] == current_root["id"]
        and node["system_role"] == "feature_space_current"
    ]
    history_feature_nodes = [
        node
        for node in body["nodes"]
        if node["parent_id"] == history_root["id"]
        and node["system_role"] == "feature_space_history"
    ]

    assert [node["feature_id"] for node in current_feature_nodes] == [active_feature_id]
    assert [node["feature_id"] for node in history_feature_nodes] == [archived_feature_id]

    archived_history_root = next(
        node for node in history_feature_nodes if node["feature_id"] == archived_feature_id
    )
    archived_history_children = [
        node["name"] for node in body["nodes"] if node["parent_id"] == archived_history_root["id"]
    ]
    assert archived_history_children == ["知识库", "问题定位报告"]

    archived_doc_node = next(
        node for node in body["nodes"] if node["id"] == archived_document.json()["id"]
    )
    assert archived_doc_node["name"] == "Archived Runbook"


@pytest.mark.asyncio
async def test_archived_feature_tree_and_space_remain_accessible_by_feature_id(
    client: AsyncClient,
) -> None:
    feature_id = await _create_feature(client)

    tree = await client.get("/api/wiki/tree", params={"feature_id": feature_id})
    assert tree.status_code == 200, tree.text
    body = tree.json()
    knowledge_root = next(node for node in body["nodes"] if node["system_role"] == "knowledge_base")

    created = await client.post(
        "/api/wiki/nodes",
        json={
            "space_id": body["space"]["id"],
            "parent_id": knowledge_root["id"],
            "type": "document",
            "name": "History Runbook",
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert created.status_code == 201, created.text

    archived = await client.delete(
        f"/api/features/{feature_id}",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert archived.status_code == 204, archived.text

    space_response = await client.get(f"/api/wiki/spaces/by-feature/{feature_id}")
    assert space_response.status_code == 200, space_response.text
    assert space_response.json()["scope"] == "history"
    assert space_response.json()["status"] == "archived"

    archived_tree = await client.get("/api/wiki/tree", params={"feature_id": feature_id})
    assert archived_tree.status_code == 200, archived_tree.text
    archived_body = archived_tree.json()
    assert archived_body["space"]["scope"] == "history"
    assert archived_body["space"]["status"] == "archived"
    archived_names = [node["name"] for node in archived_body["nodes"]]
    assert "知识库" in archived_names
    assert "问题定位报告" in archived_names
    assert "History Runbook" in archived_names


@pytest.mark.asyncio
async def test_admin_can_restore_archived_feature_space(client: AsyncClient) -> None:
    feature_id = await _create_feature(client)

    archived = await client.delete(
        f"/api/features/{feature_id}",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert archived.status_code == 204, archived.text

    history_space = await client.get(f"/api/wiki/spaces/by-feature/{feature_id}")
    assert history_space.status_code == 200, history_space.text
    assert history_space.json()["scope"] == "history"

    login = await client.post(
        "/api/auth/admin/login",
        json={"username": "admin", "password": "admin"},
    )
    assert login.status_code == 200, login.text

    restored = await client.post(f"/api/wiki/spaces/{history_space.json()['id']}/restore")
    assert restored.status_code == 200, restored.text
    assert restored.json()["feature_id"] == feature_id
    assert restored.json()["scope"] == "current"
    assert restored.json()["status"] == "active"

    features = await client.get("/api/features")
    assert features.status_code == 200, features.text
    assert any(item["id"] == feature_id for item in features.json())

    global_tree = await client.get("/api/wiki/tree")
    assert global_tree.status_code == 200, global_tree.text
    current_feature_nodes = [
        node
        for node in global_tree.json()["nodes"]
        if node["system_role"] == "feature_space_current"
    ]
    assert any(node["feature_id"] == feature_id for node in current_feature_nodes)
