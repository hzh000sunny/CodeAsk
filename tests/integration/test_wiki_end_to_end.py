"""Spec-level wiki flow across features, documents, and reports."""

from pathlib import Path

import pytest
from httpx import AsyncClient

MARKDOWN = """# Order ctx

## Overview

call /api/order/submit; null user raises NullPointerException with code ERR_ORDER_CONTEXT_EMPTY.
"""


@pytest.mark.asyncio
async def test_full_wiki_flow(client: AsyncClient, tmp_path: Path) -> None:
    response = await client.post(
        "/api/features",
        json={"name": "Order", "slug": "order"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert response.status_code == 201
    feature_id = response.json()["id"]

    markdown_path = tmp_path / "spec.md"
    markdown_path.write_text(MARKDOWN, encoding="utf-8")
    with markdown_path.open("rb") as file:
        response = await client.post(
            "/api/documents",
            data={"feature_id": str(feature_id), "title": "Order Spec"},
            files={"file": ("spec.md", file, "text/markdown")},
            headers={"X-Subject-Id": "alice@dev-1"},
        )
    assert response.status_code == 201
    document_id = response.json()["id"]

    response = await client.get("/api/documents/search?q=ERR_ORDER_CONTEXT_EMPTY")
    hits = response.json()
    assert any(hit["document_id"] == document_id for hit in hits)

    response = await client.post(
        "/api/reports",
        json={
            "feature_id": feature_id,
            "title": "ERR_ORDER_CONTEXT_EMPTY triage",
            "body_markdown": "see evidence",
            "metadata": {
                "evidence": [
                    {"type": "log", "summary": "stack trace shows ERR_ORDER_CONTEXT_EMPTY"},
                    {
                        "type": "code",
                        "source": {
                            "repo_id": "repo_order",
                            "commit_sha": "abc1234",
                            "path": "src/x.py",
                        },
                        "summary": "no null guard",
                    },
                ],
                "applicability": "v2.4.x",
                "recommended_fix": "guard user",
                "repo_commits": [{"repo_id": "repo_order", "commit_sha": "abc1234"}],
                "error_signatures": ["ERR_ORDER_CONTEXT_EMPTY"],
                "tags": ["order"],
            },
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    report_id = response.json()["id"]

    response = await client.get("/api/reports/search?q=ERR_ORDER_CONTEXT_EMPTY")
    assert all(hit["report_id"] != report_id for hit in response.json())

    response = await client.post(
        f"/api/reports/{report_id}/verify",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert response.status_code == 200

    response = await client.get("/api/reports/search?q=ERR_ORDER_CONTEXT_EMPTY")
    hits = response.json()
    found = next(hit for hit in hits if hit["report_id"] == report_id)
    assert found["verified_by"] == "alice@dev-1"
    assert found["verified_at"] is not None
    assert found["commit_sha"] == "abc1234"

    response = await client.post(
        f"/api/reports/{report_id}/unverify",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert response.status_code == 200
    response = await client.get("/api/reports/search?q=ERR_ORDER_CONTEXT_EMPTY")
    assert all(hit["report_id"] != report_id for hit in response.json())
