"""End-to-end /api/reports tests."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from codeask.db.models import WikiNode, WikiReportRef, WikiSpace


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
async def test_verify_gate_rejects_missing_log_and_code_evidence(client: AsyncClient) -> None:
    bad = _good_meta()
    bad["evidence"] = [
        item for item in bad["evidence"] if item["type"] not in {"log", "code"}
    ]
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
    assert "log or code" in response.json()["detail"].lower()


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


@pytest.mark.asyncio
async def test_reject_report_keeps_it_out_of_search_and_allows_edit(client: AsyncClient) -> None:
    response = await client.post(
        "/api/reports",
        json={
            "title": "Rejected report",
            "body_markdown": "ERR_REJECTED_CASE",
            "metadata": _good_meta(),
        },
        headers={"X-Subject-Id": "reviewer"},
    )
    report_id = response.json()["id"]

    response = await client.post(
        f"/api/reports/{report_id}/reject",
        headers={"X-Subject-Id": "reviewer"},
    )

    assert response.status_code == 200
    assert response.json()["verified"] is False
    assert response.json()["status"] == "rejected"
    response = await client.get("/api/reports/search?q=ERR_REJECTED_CASE")
    assert all(hit["report_id"] != report_id for hit in response.json())

    response = await client.put(
        f"/api/reports/{report_id}",
        json={"title": "Edited rejected report"},
        headers={"X-Subject-Id": "reviewer"},
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Edited rejected report"


@pytest.mark.asyncio
async def test_delete_report_removes_verified_report_from_search(client: AsyncClient) -> None:
    response = await client.post(
        "/api/reports",
        json={
            "title": "Delete me",
            "body_markdown": "ERR_DELETE_ME",
            "metadata": _good_meta(),
        },
        headers={"X-Subject-Id": "reviewer"},
    )
    report_id = response.json()["id"]
    response = await client.post(
        f"/api/reports/{report_id}/verify",
        headers={"X-Subject-Id": "reviewer"},
    )
    assert response.status_code == 200
    response = await client.get("/api/reports/search?q=ERR_DELETE_ME")
    assert any(hit["report_id"] == report_id for hit in response.json())

    response = await client.delete(
        f"/api/reports/{report_id}",
        headers={"X-Subject-Id": "reviewer"},
    )

    assert response.status_code == 204
    response = await client.get(f"/api/reports/{report_id}")
    assert response.status_code == 404
    response = await client.get("/api/reports/search?q=ERR_DELETE_ME")
    assert all(hit["report_id"] != report_id for hit in response.json())


@pytest.mark.asyncio
async def test_create_report_creates_native_wiki_report_ref(
    client: AsyncClient,
    app,
) -> None:  # type: ignore[no-untyped-def]
    response = await client.post(
        "/api/features",
        json={"name": "Wiki Reports", "slug": "wiki-reports"},
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
    assert response.status_code == 201, response.text
    report_id = int(response.json()["id"])

    async with app.state.session_factory() as session:
        space = (
            await session.execute(
                select(WikiSpace).where(WikiSpace.feature_id == feature_id, WikiSpace.scope == "current")
            )
        ).scalar_one()
        reports_root = (
            await session.execute(
                select(WikiNode).where(
                    WikiNode.space_id == space.id,
                    WikiNode.system_role == "reports",
                )
            )
        ).scalar_one()
        node = (
            await session.execute(
                select(WikiNode).where(
                    WikiNode.parent_id == reports_root.id,
                    WikiNode.type == "report_ref",
                    WikiNode.name == "Order context empty",
                )
            )
        ).scalar_one_or_none()
        assert node is not None
        report_ref = (
            await session.execute(select(WikiReportRef).where(WikiReportRef.node_id == node.id))
        ).scalar_one_or_none()

    assert report_ref is not None
    assert report_ref.report_id == report_id
