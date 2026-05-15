"""End-to-end /api/llm-configs tests."""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient


class FakeOpenCodeCompat:
    def __init__(self) -> None:
        self.tested = []

    async def test_llm_config(self, config, *, timeout_seconds: float = 90.0):  # type: ignore[no-untyped-def]
        self.tested.append((config, timeout_seconds))
        return {
            "profile_id": config.opencode_provider_profile,
            "provider_npm": "@ai-sdk/openai-compatible",
            "text_preview": "OK",
            "retries": [],
        }


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
    assert body["max_tokens"] == 8192
    assert body["temperature"] == 0.2
    assert body["is_default"] is False
    assert body["rpm_limit"] is None
    assert body["quota_remaining"] is None
    assert body["reasoning_profile"] == "none"
    assert body["reasoning_profile_json"] is None
    assert body["opencode_provider_profile"] == "default"
    assert body["opencode_provider_status"] == "unknown"


@pytest.mark.asyncio
async def test_admin_can_test_explicit_opencode_provider(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    fake = FakeOpenCodeCompat()
    app.state.opencode_compat = fake
    await client.post("/api/auth/admin/login", json={"password": "admin"})
    created = await client.post(
        "/api/admin/llm-configs",
        json={
            "name": "provider-test",
            "protocol": "openai",
            "base_url": "https://gateway.example.test/v1",
            "api_key": "sk-provider",
            "model_name": "model-a",
            "opencode_provider_profile": "openai-compatible",
        },
    )
    assert created.status_code == 201, created.text

    tested = await client.post(f"/api/admin/llm-configs/{created.json()['id']}/test")

    assert tested.status_code == 200, tested.text
    body = tested.json()
    assert body["status"] == "ok"
    assert body["profile_id"] == "openai-compatible"
    assert fake.tested[0][0].opencode_provider_profile == "openai-compatible"
    listed = await client.get("/api/admin/llm-configs")
    item = next(row for row in listed.json() if row["id"] == created.json()["id"])
    assert item["opencode_provider_status"] == "ok"
    assert item["opencode_provider_error"] is None


@pytest.mark.asyncio
async def test_admin_can_test_unsaved_llm_config_draft(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    fake = FakeOpenCodeCompat()
    app.state.opencode_compat = fake
    await client.post("/api/auth/admin/login", json={"password": "admin"})

    tested = await client.post(
        "/api/admin/llm-configs/test-draft",
        json={
            "name": "draft-provider-test",
            "protocol": "anthropic",
            "base_url": "https://gateway.example.test",
            "api_key": "sk-draft",
            "model_name": "model-draft",
            "opencode_provider_profile": "anthropic-compatible-bearer",
        },
    )

    assert tested.status_code == 200, tested.text
    body = tested.json()
    assert body["status"] == "ok"
    assert body["profile_id"] == "anthropic-compatible-bearer"
    assert fake.tested[0][0].id == "draft"
    assert fake.tested[0][0].api_key == "sk-draft"
    assert fake.tested[0][0].model_name == "model-draft"
    listed = await client.get("/api/admin/llm-configs")
    assert listed.json() == []


@pytest.mark.asyncio
async def test_admin_can_test_update_draft_then_save_result(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    fake = FakeOpenCodeCompat()
    app.state.opencode_compat = fake
    await client.post("/api/auth/admin/login", json={"password": "admin"})
    created = await client.post(
        "/api/admin/llm-configs",
        json={
            "name": "stored-provider-test",
            "protocol": "openai",
            "base_url": "https://old.example.test/v1",
            "api_key": "sk-stored",
            "model_name": "old-model",
            "opencode_provider_profile": "openai-native",
        },
    )
    assert created.status_code == 201, created.text

    tested = await client.post(
        f"/api/admin/llm-configs/{created.json()['id']}/test-draft",
        json={
            "protocol": "anthropic",
            "base_url": "https://new.example.test",
            "model_name": "new-model",
            "opencode_provider_profile": "anthropic-compatible-v1-bearer",
        },
    )
    assert tested.status_code == 200, tested.text
    config_under_test = fake.tested[0][0]
    assert config_under_test.id == created.json()["id"]
    assert config_under_test.api_key == "sk-stored"
    assert config_under_test.protocol == "anthropic"
    assert config_under_test.base_url == "https://new.example.test"
    assert config_under_test.model_name == "new-model"
    assert config_under_test.opencode_provider_profile == "anthropic-compatible-v1-bearer"
    listed_after_test = await client.get("/api/admin/llm-configs")
    stored_after_test = next(
        item for item in listed_after_test.json() if item["id"] == created.json()["id"]
    )
    assert stored_after_test["protocol"] == "openai"
    assert stored_after_test["model_name"] == "old-model"
    assert stored_after_test["opencode_provider_status"] == "unknown"

    body = tested.json()
    updated = await client.patch(
        f"/api/admin/llm-configs/{created.json()['id']}",
        json={
            "protocol": "anthropic",
            "base_url": "https://new.example.test",
            "model_name": "new-model",
            "opencode_provider_profile": "anthropic-compatible-v1-bearer",
            "opencode_provider_status": body["status"],
            "opencode_provider_tested_at": body["tested_at"],
            "opencode_provider_error": body["error"],
            "opencode_provider_test_result_json": body["result"],
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["opencode_provider_status"] == "ok"

    listed = await client.get("/api/admin/llm-configs")
    stored = next(item for item in listed.json() if item["id"] == created.json()["id"])
    assert stored["protocol"] == "anthropic"
    assert stored["model_name"] == "new-model"
    assert stored["opencode_provider_status"] == "ok"


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
            "reasoning_profile": "custom_json",
            "reasoning_profile_json": '{"extra_body":{"include_reasoning":true}}',
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
            "reasoning_profile": "custom_json",
            "reasoning_profile_json": '{"extra_body":{"include_reasoning":true}}',
        },
    )
    assert second_response.status_code == 201, second_response.text
    second = second_response.json()
    assert second["reasoning_profile"] == "custom_json"
    assert second["reasoning_profile_json"] == '{"extra_body":{"include_reasoning":true}}'

    listed = await client.get("/api/admin/llm-configs")
    assert listed.status_code == 200
    by_id = {item["id"]: item for item in listed.json()}
    assert by_id[first["id"]]["is_default"] is False
    assert by_id[second["id"]]["is_default"] is True
    assert by_id[second["id"]]["api_key_masked"] == "loc...ret"

    patched = await client.patch(
        f"/api/admin/llm-configs/{second['id']}",
        json={
            "model_name": "local-model-v2",
            "api_key": "rotated-secret",
            "enabled": False,
            "reasoning_profile": "volcengine_thinking",
            "reasoning_profile_json": None,
        },
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["model_name"] == "local-model-v2"
    assert patched.json()["api_key_masked"] == "rot...ret"
    assert patched.json()["enabled"] is False
    assert patched.json()["reasoning_profile"] == "volcengine_thinking"
    assert patched.json()["reasoning_profile_json"] is None

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

    member_login = await client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "secret1"},
        headers={"X-Subject-Id": "alice@device"},
    )
    assert member_login.status_code == 200, member_login.text
    user_id = member_login.json()["subject_id"]

    user_created = await client.post(
        "/api/me/llm-configs",
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
    assert user_created.json()["owner_subject_id"] == user_id

    alice_list = await client.get("/api/me/llm-configs")
    assert [item["name"] for item in alice_list.json()] == ["alice-private"]

    await client.post("/api/auth/logout")
    await client.post(
        "/api/auth/login",
        json={"username": "bob", "password": "secret1"},
        headers={"X-Subject-Id": "bob@device"},
    )
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
