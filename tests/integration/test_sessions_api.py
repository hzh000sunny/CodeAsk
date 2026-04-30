"""End-to-end /api/sessions tests."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from tests.mocks.mock_llm import MockLLMClient, text_message, tool_call_message


@pytest.mark.asyncio
async def test_session_message_sse_and_attachment(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    config = await client.post(
        "/api/llm-configs",
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

    feature = await client.post(
        "/api/features",
        json={"name": "Order", "slug": "order-session", "description": "core"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert feature.status_code == 201
    feature_id = feature.json()["id"]

    created = await client.post(
        "/api/sessions",
        json={"title": "订单排障"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]
    assert created.json()["created_by_subject_id"] == "alice@dev-1"

    mock = MockLLMClient(
        [
            tool_call_message(
                "tc_scope",
                "select_feature",
                {"feature_ids": [feature_id], "confidence": "high", "reason": "order"},
            ),
            text_message(
                '{"verdict":"enough","reason":"docs cover it","next":"answer_finalization"}'
            ),
            text_message("结论：订单 500 可以先检查上下文。"),
        ]
    )
    app.state.llm_gateway.client_factory.provider_clients["openai"] = lambda **_: mock

    message = await client.post(
        f"/api/sessions/{session_id}/messages",
        json={"content": "为什么订单偶发 500", "feature_ids": [feature_id]},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert message.status_code == 200, message.text
    body = message.text
    assert "event: scope_detection" in body
    assert "event: done" in body

    attachment = await client.post(
        f"/api/sessions/{session_id}/attachments",
        files={"file": ("app.log", b"ERROR order failed", "text/plain")},
        data={"kind": "log"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert attachment.status_code == 201, attachment.text
    uploaded = attachment.json()
    assert uploaded["kind"] == "log"
    assert Path(uploaded["file_path"]).exists()
