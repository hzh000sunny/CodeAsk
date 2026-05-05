"""End-to-end native wiki asset API tests."""

from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from codeask.db.models import WikiAsset, WikiSource


PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89"
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00"
    b"\x18\xdd\x8d\xb1"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


async def _create_space_and_folder(client: AsyncClient, slug: str = "wiki-assets") -> tuple[int, int]:
    feature = await client.post(
        "/api/features",
        json={"name": "Wiki Assets", "slug": slug},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert feature.status_code == 201, feature.text
    feature_id = int(feature.json()["id"])

    tree = await client.get("/api/wiki/tree", params={"feature_id": feature_id})
    assert tree.status_code == 200, tree.text
    space_id = int(tree.json()["space"]["id"])

    folder = await client.post(
        "/api/wiki/nodes",
        json={"space_id": space_id, "parent_id": None, "type": "folder", "name": "Docs"},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert folder.status_code == 201, folder.text
    return space_id, int(folder.json()["id"])


@pytest.mark.asyncio
async def test_upload_asset_and_stream_content(client: AsyncClient, app, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    space_id, parent_id = await _create_space_and_folder(client)
    file_path = tmp_path / "diagram.png"
    file_path.write_bytes(PNG_BYTES)

    with file_path.open("rb") as file:
        response = await client.post(
            "/api/wiki/assets",
            data={"space_id": str(space_id), "parent_id": str(parent_id)},
            files={"file": ("diagram.png", file, "image/png")},
            headers={"X-Subject-Id": "owner@dev-1"},
        )
    assert response.status_code == 201, response.text
    body = response.json()
    node_id = int(body["node_id"])
    assert body["path"] == "docs/diagram.png"
    assert body["mime_type"] == "image/png"

    response = await client.get(
        f"/api/wiki/assets/{node_id}/content",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/png"
    assert response.content == PNG_BYTES

    async with app.state.session_factory() as session:
        asset = (
            await session.execute(select(WikiAsset).where(WikiAsset.node_id == node_id))
        ).scalar_one_or_none()
        source = await session.get(WikiSource, asset.provenance_json["source_id"]) if asset else None
    assert asset is not None
    assert asset.provenance_json["source"] == "manual_upload"
    assert asset.provenance_json["source_id"] is not None
    assert source is not None
    assert source.kind == "manual_upload"


@pytest.mark.asyncio
async def test_published_markdown_resolves_uploaded_asset(client: AsyncClient, tmp_path: Path) -> None:
    space_id, parent_id = await _create_space_and_folder(client, slug="wiki-assets-resolve")
    file_path = tmp_path / "diagram.png"
    file_path.write_bytes(PNG_BYTES)

    with file_path.open("rb") as file:
        response = await client.post(
            "/api/wiki/assets",
            data={"space_id": str(space_id), "parent_id": str(parent_id)},
            files={"file": ("diagram.png", file, "image/png")},
            headers={"X-Subject-Id": "owner@dev-1"},
        )
    assert response.status_code == 201, response.text
    asset_node_id = int(response.json()["node_id"])

    document = await client.post(
        "/api/wiki/nodes",
        json={
            "space_id": space_id,
            "parent_id": parent_id,
            "type": "document",
            "name": "Runbook",
        },
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert document.status_code == 201, document.text
    node_id = int(document.json()["id"])

    response = await client.post(
        f"/api/wiki/documents/{node_id}/publish",
        json={"body_markdown": "# Doc\n\n![Diagram](./diagram.png)"},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert response.status_code == 200, response.text
    refs = {item["target"]: item for item in response.json()["resolved_refs_json"]}
    assert refs["./diagram.png"]["resolved_node_id"] == asset_node_id
    assert refs["./diagram.png"]["broken"] is False
    assert response.json()["broken_refs_json"]["assets"] == []


@pytest.mark.asyncio
async def test_non_owner_can_upload_asset_in_v1_0_1(client: AsyncClient, tmp_path: Path) -> None:
    space_id, parent_id = await _create_space_and_folder(client, slug="wiki-assets-denied")
    file_path = tmp_path / "diagram.png"
    file_path.write_bytes(PNG_BYTES)

    with file_path.open("rb") as file:
        response = await client.post(
            "/api/wiki/assets",
            data={"space_id": str(space_id), "parent_id": str(parent_id)},
            files={"file": ("diagram.png", file, "image/png")},
            headers={"X-Subject-Id": "viewer@dev-9"},
        )
    assert response.status_code == 201, response.text
    assert response.json()["original_name"] == "diagram.png"
