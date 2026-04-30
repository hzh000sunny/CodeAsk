"""End-to-end /api/reports tests."""

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
        "error_signatures": ["ERR_ORDER_CONTEXT_EMPTY"],
        "tags": ["order"],
    }


@pytest.mark.asyncio
async def test_create_then_verify_then_unverify(client: AsyncClient) -> None:
    response = await client.post(
        "/api/features",
        json={"name": "Order", "slug": "order"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    feature_id = response.json()["id"]

    response = await client.post(
        "/api/reports",
        json={
            "feature_id": feature_id,
            "title": "Order context empty",
            "body_markdown": "see metadata",
            "metadata": _good_meta(),
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert response.status_code == 201
    report_id = response.json()["id"]
    assert response.json()["status"] == "draft"
    assert response.json()["verified"] is False

    response = await client.post(
        f"/api/reports/{report_id}/verify",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["verified"] is True
    assert body["status"] == "verified"
    assert body["verified_by"] == "alice@dev-1"
    assert body["verified_at"] is not None

    response = await client.get("/api/reports/search?q=ERR_ORDER_CONTEXT_EMPTY")
    assert response.status_code == 200
    hits = response.json()
    assert any(hit["report_id"] == report_id for hit in hits)
    found = next(hit for hit in hits if hit["report_id"] == report_id)
    assert found["verified_by"] == "alice@dev-1"
    assert found["commit_sha"] == "abc1234"

    response = await client.post(
        f"/api/reports/{report_id}/unverify",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert response.status_code == 200
    assert response.json()["verified"] is False
    assert response.json()["status"] == "draft"

    response = await client.get("/api/reports/search?q=ERR_ORDER_CONTEXT_EMPTY")
    hits = response.json()
    assert all(hit["report_id"] != report_id for hit in hits)


@pytest.mark.asyncio
async def test_verify_gate_rejects_missing_log_evidence(client: AsyncClient) -> None:
    bad = _good_meta()
    bad["evidence"] = [item for item in bad["evidence"] if item["type"] != "log"]
    response = await client.post(
        "/api/reports",
        json={"title": "t", "body_markdown": "b", "metadata": bad},
        headers={"X-Subject-Id": "x@y"},
    )
    report_id = response.json()["id"]
    response = await client.post(
        f"/api/reports/{report_id}/verify",
        headers={"X-Subject-Id": "x@y"},
    )
    assert response.status_code == 422
    assert "log" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_draft_then_verify(client: AsyncClient) -> None:
    bad = _good_meta()
    bad["applicability"] = ""
    response = await client.post(
        "/api/reports",
        json={"title": "t", "body_markdown": "b", "metadata": bad},
        headers={"X-Subject-Id": "x@y"},
    )
    report_id = response.json()["id"]
    fixed = _good_meta()
    response = await client.put(
        f"/api/reports/{report_id}",
        json={"metadata": fixed},
        headers={"X-Subject-Id": "x@y"},
    )
    assert response.status_code == 200
    response = await client.post(
        f"/api/reports/{report_id}/verify",
        headers={"X-Subject-Id": "x@y"},
    )
    assert response.status_code == 200
