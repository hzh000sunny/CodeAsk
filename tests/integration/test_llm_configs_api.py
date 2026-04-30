"""End-to-end /api/llm-configs tests."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_list_default_flip_and_delete_llm_config(client: AsyncClient) -> None:
    created = await client.post(
        "/api/llm-configs",
        json={
            "name": "default",
            "protocol": "openai",
            "base_url": None,
            "api_key": "sk-secret-1",
            "model_name": "gpt-test",
            "max_tokens": 1024,
            "temperature": 0.1,
            "is_default": True,
        },
    )
    assert created.status_code == 201, created.text
    first = created.json()
    assert first["api_key_masked"] == "sk-...t-1"
    assert first["is_default"] is True

    second_response = await client.post(
        "/api/llm-configs",
        json={
            "name": "fallback",
            "protocol": "openai_compatible",
            "base_url": "http://llm.local/v1",
            "api_key": "local-secret",
            "model_name": "local-model",
            "max_tokens": 2048,
            "temperature": 0.0,
            "is_default": True,
        },
    )
    assert second_response.status_code == 201, second_response.text
    second = second_response.json()

    listed = await client.get("/api/llm-configs")
    assert listed.status_code == 200
    by_id = {item["id"]: item for item in listed.json()}
    assert by_id[first["id"]]["is_default"] is False
    assert by_id[second["id"]]["is_default"] is True
    assert by_id[second["id"]]["api_key_masked"] == "loc...ret"

    patched = await client.patch(
        f"/api/llm-configs/{second['id']}",
        json={"model_name": "local-model-v2", "api_key": "rotated-secret"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["model_name"] == "local-model-v2"
    assert patched.json()["api_key_masked"] == "rot...ret"

    deleted = await client.delete(f"/api/llm-configs/{first['id']}")
    assert deleted.status_code == 204

    listed_after_delete = await client.get("/api/llm-configs")
    assert all(item["id"] != first["id"] for item in listed_after_delete.json())
