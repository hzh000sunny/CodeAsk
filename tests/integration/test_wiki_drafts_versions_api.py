"""Compatibility tests for native draft/version endpoints."""

from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from codeask.db.models import WikiDocument

MARKDOWN = """# Legacy

## Overview

Legacy markdown body.
"""


async def _create_legacy_markdown_document(client: AsyncClient, tmp_path: Path) -> int:
    feature = await client.post(
        "/api/features",
        json={"name": "Legacy Sync", "slug": "legacy-sync"},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert feature.status_code == 201, feature.text
    feature_id = int(feature.json()["id"])

    markdown_path = tmp_path / "legacy.md"
    markdown_path.write_text(MARKDOWN, encoding="utf-8")
    with markdown_path.open("rb") as file:
        response = await client.post(
            "/api/documents",
            data={"feature_id": str(feature_id), "title": "Legacy Runbook"},
            files={"file": ("legacy.md", file, "text/markdown")},
            headers={"X-Subject-Id": "owner@dev-1"},
        )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


@pytest.mark.asyncio
async def test_legacy_markdown_sync_exposes_current_native_body(
    client: AsyncClient,
    app,
    tmp_path: Path,
) -> None:  # type: ignore[no-untyped-def]
    legacy_document_id = await _create_legacy_markdown_document(client, tmp_path)

    async with app.state.session_factory() as session:
        wiki_document = (
            await session.execute(
                select(WikiDocument).where(WikiDocument.legacy_document_id == legacy_document_id)
            )
        ).scalar_one()
        node_id = wiki_document.node_id

    response = await client.get(
        f"/api/wiki/documents/{node_id}",
        headers={"X-Subject-Id": "owner@dev-1"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["current_body_markdown"] == MARKDOWN


@pytest.mark.asyncio
async def test_versions_diff_and_rollback(client: AsyncClient) -> None:
    feature = await client.post(
        "/api/features",
        json={"name": "Diff Rollback", "slug": "diff-rollback"},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert feature.status_code == 201, feature.text
    feature_id = int(feature.json()["id"])

    tree = await client.get("/api/wiki/tree", params={"feature_id": feature_id})
    assert tree.status_code == 200, tree.text
    space_id = int(tree.json()["space"]["id"])

    document = await client.post(
        "/api/wiki/nodes",
        json={"space_id": space_id, "parent_id": None, "type": "document", "name": "Runbook"},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert document.status_code == 201, document.text
    node_id = int(document.json()["id"])

    publish = await client.post(
        f"/api/wiki/documents/{node_id}/publish",
        json={"body_markdown": "# V1\n\nalpha"},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert publish.status_code == 200, publish.text

    publish = await client.post(
        f"/api/wiki/documents/{node_id}/publish",
        json={"body_markdown": "# V2\n\nbeta"},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert publish.status_code == 200, publish.text

    versions = await client.get(
        f"/api/wiki/documents/{node_id}/versions",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert versions.status_code == 200, versions.text
    version_list = versions.json()["versions"]
    v2_id = int(version_list[0]["id"])
    v1_id = int(version_list[1]["id"])

    diff = await client.get(
        f"/api/wiki/documents/{node_id}/diff",
        params={"from_version_id": v1_id, "to_version_id": v2_id},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert diff.status_code == 200, diff.text
    patch = diff.json()["patch"]
    assert "-# V1" in patch
    assert "+# V2" in patch
    assert "-alpha" in patch
    assert "+beta" in patch

    rollback = await client.post(
        f"/api/wiki/documents/{node_id}/versions/{v1_id}/rollback",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert rollback.status_code == 200, rollback.text
    assert rollback.json()["current_body_markdown"] == "# V1\n\nalpha"

    versions = await client.get(
        f"/api/wiki/documents/{node_id}/versions",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert versions.status_code == 200, versions.text
    version_list = versions.json()["versions"]
    assert [item["version_no"] for item in version_list] == [3, 2, 1]
    assert version_list[0]["body_markdown"] == "# V1\n\nalpha"
