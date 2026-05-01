"""End-to-end /api/documents tests."""

from pathlib import Path

import pytest
from httpx import AsyncClient

MARKDOWN = """# Submit Order

## Overview

Call /api/order/submit to submit the order. NullPointerException means user is absent.
"""


async def _create_feature(client: AsyncClient, slug: str = "order") -> int:
    response = await client.post(
        "/api/features",
        json={"name": "Order", "slug": slug},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    return int(response.json()["id"])


@pytest.mark.asyncio
async def test_upload_then_list_then_search(client: AsyncClient, tmp_path: Path) -> None:
    feature_id = await _create_feature(client)
    markdown_path = tmp_path / "submit.md"
    markdown_path.write_text(MARKDOWN, encoding="utf-8")

    with markdown_path.open("rb") as file:
        response = await client.post(
            "/api/documents",
            data={
                "feature_id": str(feature_id),
                "title": "Submit Order Spec",
                "tags": "order,spec",
            },
            files={"file": ("submit.md", file, "text/markdown")},
            headers={"X-Subject-Id": "alice@dev-1"},
        )
    assert response.status_code == 201, response.text
    document_id = response.json()["id"]

    response = await client.get(f"/api/documents?feature_id={feature_id}")
    assert response.status_code == 200
    assert any(document["id"] == document_id for document in response.json())

    response = await client.get("/api/documents/search?q=submit+order")
    assert response.status_code == 200
    hits = response.json()
    assert any(hit["document_id"] == document_id for hit in hits)


@pytest.mark.asyncio
async def test_soft_delete_document_removes_from_search(
    client: AsyncClient,
    tmp_path: Path,
) -> None:
    feature_id = await _create_feature(client)
    markdown_path = tmp_path / "x.md"
    markdown_path.write_text(MARKDOWN, encoding="utf-8")
    with markdown_path.open("rb") as file:
        response = await client.post(
            "/api/documents",
            data={"feature_id": str(feature_id)},
            files={"file": ("x.md", file, "text/markdown")},
            headers={"X-Subject-Id": "u@1"},
        )
    document_id = response.json()["id"]

    response = await client.delete(f"/api/documents/{document_id}")
    assert response.status_code == 204

    response = await client.get("/api/documents/search?q=submit+order")
    hits = response.json()
    assert all(hit["document_id"] != document_id for hit in hits)


@pytest.mark.asyncio
async def test_unsupported_extension_rejected(client: AsyncClient, tmp_path: Path) -> None:
    feature_id = await _create_feature(client)
    binary_path = tmp_path / "x.bin"
    binary_path.write_bytes(b"\x00\x01")
    with binary_path.open("rb") as file:
        response = await client.post(
            "/api/documents",
            data={"feature_id": str(feature_id)},
            files={"file": ("x.bin", file, "application/octet-stream")},
            headers={"X-Subject-Id": "u@1"},
        )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_pdf_spoofed_executable_rejected_before_parsing(
    client: AsyncClient,
    tmp_path: Path,
) -> None:
    feature_id = await _create_feature(client, slug="order-spoofed-pdf")
    binary_path = tmp_path / "evil.pdf"
    binary_path.write_bytes(b"MZ\x90\x00\x03\x00" + b"\x00" * 1024)

    with binary_path.open("rb") as file:
        response = await client.post(
            "/api/documents",
            data={"feature_id": str(feature_id)},
            files={"file": ("evil.pdf", file, "application/pdf")},
            headers={"X-Subject-Id": "u@1"},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "unsupported file content: executable payload"
