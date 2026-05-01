"""End-to-end /api/llm-configs tests."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_llm_config_uses_runtime_defaults(client: AsyncClient) -> None:
    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200

    created = await client.post(
        "/api/admin/llm-configs",
        json={
            "name": "minimal",
            "protocol": "anthropic",
            "base_url": None,
            "api_key": "sk-minimal",
            "model_name": "claude-test",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["protocol"] == "anthropic"
    assert body["max_tokens"] == 200 * 1024
    assert body["temperature"] == 0.2
    assert body["is_default"] is False
    assert body["rpm_limit"] is None
    assert body["quota_remaining"] is None


@pytest.mark.asyncio
async def test_create_list_default_flip_and_delete_llm_config(client: AsyncClient) -> None:
    created = await client.post(
        "/api/admin/llm-configs",
        json={
            "name": "default",
            "protocol": "openai",
            "base_url": None,
            "api_key": "sk-secret-1",
            "model_name": "gpt-test",
            "max_tokens": 1024,
            "temperature": 0.1,
            "enabled": True,
            "is_default": True,
        },
    )
    assert created.status_code == 403

    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200

    created = await client.post(
        "/api/admin/llm-configs",
        json={
            "name": "default",
            "protocol": "openai",
            "base_url": None,
            "api_key": "sk-secret-1",
            "model_name": "gpt-test",
            "max_tokens": 1024,
            "temperature": 0.1,
            "enabled": True,
            "is_default": True,
        },
    )
    assert created.status_code == 201, created.text
    first = created.json()
    assert first["api_key_masked"] == "sk-...t-1"
    assert first["scope"] == "global"
    assert first["owner_subject_id"] is None
    assert first["enabled"] is True
    assert first["is_default"] is True

    second_response = await client.post(
        "/api/admin/llm-configs",
        json={
            "name": "fallback",
            "protocol": "openai_compatible",
            "base_url": "http://llm.local/v1",
            "api_key": "local-secret",
            "model_name": "local-model",
            "max_tokens": 2048,
            "temperature": 0.0,
            "enabled": True,
            "is_default": True,
        },
    )
    assert second_response.status_code == 201, second_response.text
    second = second_response.json()

    listed = await client.get("/api/admin/llm-configs")
    assert listed.status_code == 200
    by_id = {item["id"]: item for item in listed.json()}
    assert by_id[first["id"]]["is_default"] is False
    assert by_id[second["id"]]["is_default"] is True
    assert by_id[second["id"]]["api_key_masked"] == "loc...ret"

    patched = await client.patch(
        f"/api/admin/llm-configs/{second['id']}",
        json={"model_name": "local-model-v2", "api_key": "rotated-secret", "enabled": False},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["model_name"] == "local-model-v2"
    assert patched.json()["api_key_masked"] == "rot...ret"
    assert patched.json()["enabled"] is False

    deleted = await client.delete(f"/api/admin/llm-configs/{first['id']}")
    assert deleted.status_code == 204

    listed_after_delete = await client.get("/api/admin/llm-configs")
    assert all(item["id"] != first["id"] for item in listed_after_delete.json())


@pytest.mark.asyncio
async def test_member_llm_configs_are_scoped_and_do_not_expose_global_configs(
    client: AsyncClient,
) -> None:
    await client.post("/api/auth/admin/login", json={"password": "admin"})
    global_created = await client.post(
        "/api/admin/llm-configs",
        json={
            "name": "global-openai",
            "protocol": "openai",
            "base_url": None,
            "api_key": "sk-global",
            "model_name": "gpt-global",
            "max_tokens": 1024,
            "temperature": 0.1,
            "enabled": True,
            "is_default": True,
        },
    )
    assert global_created.status_code == 201, global_created.text
    await client.post("/api/auth/logout")

    listed_global_as_member = await client.get(
        "/api/admin/llm-configs",
        headers={"X-Subject-Id": "alice@device"},
    )
    assert listed_global_as_member.status_code == 403

    user_created = await client.post(
        "/api/me/llm-configs",
        headers={"X-Subject-Id": "alice@device"},
        json={
            "name": "alice-private",
            "protocol": "openai_compatible",
            "base_url": "http://llm.alice/v1",
            "api_key": "sk-alice",
            "model_name": "alice-model",
            "max_tokens": 2048,
            "temperature": 0.2,
            "enabled": True,
            "is_default": True,
        },
    )
    assert user_created.status_code == 201, user_created.text
    assert user_created.json()["scope"] == "user"
    assert user_created.json()["owner_subject_id"] == "alice@device"

    alice_list = await client.get("/api/me/llm-configs", headers={"X-Subject-Id": "alice@device"})
    assert [item["name"] for item in alice_list.json()] == ["alice-private"]

    bob_list = await client.get("/api/me/llm-configs", headers={"X-Subject-Id": "bob@device"})
    assert bob_list.json() == []


@pytest.mark.asyncio
async def test_admin_cannot_use_personal_llm_config_endpoints(client: AsyncClient) -> None:
    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200

    listed = await client.get("/api/me/llm-configs")
    assert listed.status_code == 403

    created = await client.post(
        "/api/me/llm-configs",
        json={
            "name": "admin-personal",
            "protocol": "openai",
            "base_url": None,
            "api_key": "sk-admin",
            "model_name": "gpt-admin",
            "max_tokens": 1024,
            "temperature": 0.1,
            "enabled": True,
            "is_default": True,
        },
    )
    assert created.status_code == 403
