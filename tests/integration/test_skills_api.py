"""End-to-end /api/skills tests."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_and_list_global_and_feature_skills(client: AsyncClient) -> None:
    forbidden_global = await client.post(
        "/api/skills",
        json={
            "name": "global-debugger",
            "scope": "global",
            "feature_id": None,
            "stage": "all",
            "enabled": True,
            "priority": 10,
            "prompt_template": "Always cite evidence.",
        },
    )
    assert forbidden_global.status_code == 403

    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200
    global_response = await client.post(
        "/api/skills",
        json={
            "name": "global-debugger",
            "scope": "global",
            "feature_id": None,
            "stage": "answer_finalization",
            "enabled": True,
            "priority": 10,
            "prompt_template": "Always cite evidence.",
        },
    )
    assert global_response.status_code == 201, global_response.text
    assert global_response.json()["stage"] == "answer_finalization"
    assert global_response.json()["enabled"] is True
    assert global_response.json()["priority"] == 10

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
            "stage": "code_investigation",
            "enabled": False,
            "priority": 30,
            "prompt_template": "Use order-domain terminology.",
        },
    )
    assert feature_response.status_code == 201, feature_response.text

    updated = await client.patch(
        f"/api/skills/{feature_response.json()['id']}",
        json={"enabled": True, "priority": 5, "stage": "all"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["enabled"] is True
    assert updated.json()["priority"] == 5
    assert updated.json()["stage"] == "all"

    listed = await client.get("/api/skills")
    assert listed.status_code == 200
    names = {item["name"] for item in listed.json()}
    assert names == {"global-debugger", "order-debugger"}
