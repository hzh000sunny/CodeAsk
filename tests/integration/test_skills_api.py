"""End-to-end /api/skills tests."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_and_list_global_and_feature_skills(client: AsyncClient) -> None:
    global_response = await client.post(
        "/api/skills",
        json={
            "name": "global-debugger",
            "scope": "global",
            "feature_id": None,
            "prompt_template": "Always cite evidence.",
        },
    )
    assert global_response.status_code == 201, global_response.text

    invalid = await client.post(
        "/api/skills",
        json={
            "name": "broken-feature-skill",
            "scope": "feature",
            "feature_id": None,
            "prompt_template": "Feature only.",
        },
    )
    assert invalid.status_code == 422

    feature = await client.post(
        "/api/features",
        json={"name": "Order", "slug": "order-skill", "description": "core"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert feature.status_code == 201
    feature_id = feature.json()["id"]

    feature_response = await client.post(
        "/api/skills",
        json={
            "name": "order-debugger",
            "scope": "feature",
            "feature_id": feature_id,
            "prompt_template": "Use order-domain terminology.",
        },
    )
    assert feature_response.status_code == 201, feature_response.text

    listed = await client.get("/api/skills")
    assert listed.status_code == 200
    names = {item["name"] for item in listed.json()}
    assert names == {"global-debugger", "order-debugger"}
