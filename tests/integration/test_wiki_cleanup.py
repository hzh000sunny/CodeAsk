"""Integration tests for wiki soft-delete cleanup."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from codeask.db.models import (
    Feature,
    WikiAsset,
    WikiDocument,
    WikiDocumentVersion,
    WikiNode,
    WikiSpace,
)
from codeask.wiki.cleanup import purge_expired_soft_deleted_nodes


async def _create_feature_tree(client: AsyncClient, slug: str) -> tuple[int, int]:
    feature = await client.post(
        "/api/features",
        json={"name": slug, "slug": slug},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert feature.status_code == 201, feature.text
    feature_id = int(feature.json()["id"])

    tree = await client.get("/api/wiki/tree", params={"feature_id": feature_id})
    assert tree.status_code == 200, tree.text
    return feature_id, int(tree.json()["space"]["id"])


@pytest.mark.asyncio
async def test_cleanup_purges_expired_soft_deleted_nodes_and_asset_files(
    client: AsyncClient,
    app,
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    _feature_id, space_id = await _create_feature_tree(client, "wiki-cleanup")

    document = await client.post(
        "/api/wiki/nodes",
        json={"space_id": space_id, "parent_id": None, "type": "document", "name": "Runbook"},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert document.status_code == 201, document.text
    document_node_id = int(document.json()["id"])

    published = await client.post(
        f"/api/wiki/documents/{document_node_id}/publish",
        json={"body_markdown": "# Runbook"},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert published.status_code == 200, published.text

    asset_file = tmp_path / "diagram.png"
    asset_file.write_bytes(b"fake-image")

    async with app.state.session_factory() as session:
        asset_node = WikiNode(
            space_id=space_id,
            parent_id=None,
            type="asset",
            name="diagram.png",
            path="diagram.png",
            system_role=None,
            sort_order=0,
        )
        session.add(asset_node)
        await session.flush()
        session.add(
            WikiAsset(
                node_id=asset_node.id,
                original_name="diagram.png",
                file_name="diagram.png",
                storage_path=str(asset_file),
                mime_type="image/png",
                size_bytes=asset_file.stat().st_size,
                provenance_json={"source": "directory_import"},
            )
        )
        await session.commit()
        asset_node_id = asset_node.id

    deleted_document = await client.delete(
        f"/api/wiki/nodes/{document_node_id}",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert deleted_document.status_code == 204, deleted_document.text

    deleted_asset = await client.delete(
        f"/api/wiki/nodes/{asset_node_id}",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert deleted_asset.status_code == 204, deleted_asset.text

    expired_at = datetime.now(UTC) - timedelta(days=31)
    async with app.state.session_factory() as session:
        nodes = (
            await session.execute(
                select(WikiNode).where(WikiNode.id.in_([document_node_id, asset_node_id]))
            )
        ).scalars().all()
        for node in nodes:
            node.deleted_at = expired_at
        await session.commit()

    result = await purge_expired_soft_deleted_nodes(app.state.session_factory, retention_days=30)

    assert result["removed_nodes"] == 2
    assert result["removed_assets"] == 1
    assert not asset_file.exists()

    async with app.state.session_factory() as session:
        assert await session.get(WikiNode, document_node_id) is None
        assert await session.get(WikiNode, asset_node_id) is None
        wiki_document = (
            await session.execute(select(WikiDocument).where(WikiDocument.node_id == document_node_id))
        ).scalar_one_or_none()
        versions = (
            await session.execute(
                select(WikiDocumentVersion).join(WikiDocument).where(WikiDocument.node_id == document_node_id)
            )
        ).scalars().all()
        asset = (
            await session.execute(select(WikiAsset).where(WikiAsset.node_id == asset_node_id))
        ).scalar_one_or_none()
    assert wiki_document is None
    assert versions == []
    assert asset is None


@pytest.mark.asyncio
async def test_cleanup_keeps_archived_feature_and_history_space(client: AsyncClient, app) -> None:  # type: ignore[no-untyped-def]
    feature_id, _space_id = await _create_feature_tree(client, "wiki-archive-keep")

    archived = await client.delete(
        f"/api/features/{feature_id}",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert archived.status_code == 204, archived.text

    result = await purge_expired_soft_deleted_nodes(app.state.session_factory, retention_days=30)
    assert result["removed_nodes"] == 0

    async with app.state.session_factory() as session:
        feature = await session.get(Feature, feature_id)
        history_space = (
            await session.execute(
                select(WikiSpace).where(
                    WikiSpace.feature_id == feature_id,
                    WikiSpace.scope == "history",
                )
            )
        ).scalar_one_or_none()
    assert feature is not None
    assert feature.status == "archived"
    assert history_space is not None
    assert history_space.scope == "history"
