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
async def test_wiki_report_projections_group_by_report_status(client: AsyncClient) -> None:
    response = await client.post(
        "/api/features",
        json={"name": "Projection Feature", "slug": "projection-feature"},
        headers={"X-Subject-Id": "owner@test"},
    )
    feature_id = response.json()["id"]

    response = await client.post(
        "/api/reports",
        json={
            "feature_id": feature_id,
            "title": "Draft report",
            "body_markdown": "draft body",
            "metadata": _good_meta(),
        },
        headers={"X-Subject-Id": "owner@test"},
    )
    draft_report_id = response.json()["id"]

    response = await client.post(
        "/api/reports",
        json={
            "feature_id": feature_id,
            "title": "Verified report",
            "body_markdown": "verified body",
            "metadata": _good_meta(),
        },
        headers={"X-Subject-Id": "owner@test"},
    )
    verified_report_id = response.json()["id"]
    await client.post(
        f"/api/reports/{verified_report_id}/verify",
        headers={"X-Subject-Id": "owner@test"},
    )

    response = await client.post(
        "/api/reports",
        json={
            "feature_id": feature_id,
            "title": "Rejected report",
            "body_markdown": "rejected body",
            "metadata": _good_meta(),
        },
        headers={"X-Subject-Id": "owner@test"},
    )
    rejected_report_id = response.json()["id"]
    await client.post(
        f"/api/reports/{rejected_report_id}/reject",
        headers={"X-Subject-Id": "owner@test"},
    )

    response = await client.get(f"/api/wiki/reports/projections?feature_id={feature_id}")
    assert response.status_code == 200, response.text
    body = response.json()

    items = {item["report_id"]: item for item in body["items"]}
    assert items[draft_report_id]["status_group"] == "draft"
    assert items[verified_report_id]["status_group"] == "verified"
    assert items[rejected_report_id]["status_group"] == "rejected"


@pytest.mark.asyncio
async def test_get_wiki_report_by_node_reads_markdown_body(client: AsyncClient) -> None:
    response = await client.post(
        "/api/features",
        json={"name": "Projection Detail", "slug": "projection-detail"},
        headers={"X-Subject-Id": "owner@test"},
    )
    feature_id = response.json()["id"]

    response = await client.post(
        "/api/reports",
        json={
            "feature_id": feature_id,
            "title": "Projection detail report",
            "body_markdown": "# Heading\n\nbody from wiki report ref",
            "metadata": _good_meta(),
        },
        headers={"X-Subject-Id": "owner@test"},
    )
    report_id = response.json()["id"]

    projections = await client.get(f"/api/wiki/reports/projections?feature_id={feature_id}")
    projection = next(item for item in projections.json()["items"] if item["report_id"] == report_id)

    response = await client.get(f"/api/wiki/reports/by-node/{projection['node_id']}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["report_id"] == report_id
    assert body["node_id"] == projection["node_id"]
    assert "body from wiki report ref" in body["body_markdown"]
