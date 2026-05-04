"""Read-only API tests for native wiki spaces and tree."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from codeask.db.models import Document, Feature, Report, WikiDocument, WikiReportRef, WikiSpace


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
