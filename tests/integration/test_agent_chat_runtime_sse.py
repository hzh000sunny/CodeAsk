import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from tests.mocks.mock_llm import MockLLMClient, text_message


@pytest.mark.asyncio
async def test_post_message_stream_uses_chat_runtime(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200
    config = await client.post(
        "/api/admin/llm-configs",
        json={
            "name": "default",
            "protocol": "openai",
            "base_url": None,
            "api_key": "sk-secret",
            "model_name": "gpt-test",
            "max_tokens": 1024,
            "temperature": 0.0,
            "is_default": True,
        },
    )
    assert config.status_code == 201, config.text
    await client.post("/api/auth/logout")

    headers = {"X-Subject-Id": "alice@dev-1"}
    created = await client.post("/api/sessions", json={"title": "测试会话"}, headers=headers)
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    mock = MockLLMClient([text_message("这是普通回答。")])
    app.state.llm_gateway.client_factory.provider_clients["openai"] = lambda **_: mock

    response = await client.post(
        f"/api/sessions/{session_id}/messages",
        json={"content": "普通问题"},
        headers=headers,
    )

    assert response.status_code == 200
    assert "event: retrieval_context" in response.text
    assert "event: text_delta" in response.text
    assert "event: scope_detection" not in response.text
    assert "范围判断" not in response.text
    assert "充分性判断" not in response.text
