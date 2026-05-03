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
