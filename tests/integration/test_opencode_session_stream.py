from __future__ import annotations

import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from codeask.agent.chat_runtime.events import ChatRuntimeEvent
from codeask.agent.opencode_compat.process import OpenCodeProcessError
from codeask.api import sessions as sessions_api
from codeask.api.schemas.session import MessageCreate
from codeask.db.models import SessionTurn


@dataclass
class FakeOpenCodeCompat:
    calls: list[dict[str, object]]
    fail_run: bool = False
    fail_initialize: bool = False
    fail_initialize_code: str | None = None
    fail_abort: bool = False
    scripted_run_events_by_model: dict[str, list[ChatRuntimeEvent]] = field(default_factory=dict)

    async def initialize_session(  # type: ignore[no-untyped-def]
        self,
        session_id,
        llm_config,
        *,
        provider_config_pool=(),
        force_new_external_session=False,
    ):
        if self.fail_initialize_code is not None:
            raise OpenCodeProcessError(self.fail_initialize_code, "classified opencode failure")
        if self.fail_initialize:
            raise RuntimeError("opencode is not reachable")
        self.calls.append(
            {
                "method": "initialize_session",
                "session_id": session_id,
                "model": llm_config.model_name,
                "opencode_provider_profile": llm_config.opencode_provider_profile,
                "provider_config_pool": [config.model_name for config in provider_config_pool],
                "force_new_external_session": force_new_external_session,
            }
        )
        return object()

    async def run_turn(  # type: ignore[no-untyped-def]
        self,
        *,
        session_id,
        user_message,
        llm_config,
        system=None,
        context_window_tokens=200_000,
        binding=None,
    ):
        if self.fail_run:
            yield ChatRuntimeEvent(
                type="error",
                data={"backend": "opencode", "error": "opencode unavailable"},
            )
            return
        self.calls.append(
            {
                "method": "run_turn",
                "session_id": session_id,
                "user_message": user_message,
                "model": llm_config.model_name,
                "opencode_provider_profile": llm_config.opencode_provider_profile,
                "system": system,
                "context_window_tokens": context_window_tokens,
            }
        )
        scripted = self.scripted_run_events_by_model.get(llm_config.model_name)
        if scripted is not None:
            for event in scripted:
                yield event
            return
        yield ChatRuntimeEvent(type="text_delta", data={"delta": "opencode answer"})
        yield ChatRuntimeEvent(type="done", data={"backend": "opencode"})

    async def abort_turn(self, session_id):  # type: ignore[no-untyped-def]
        if self.fail_abort:
            raise RuntimeError("opencode abort failed")
        self.calls.append({"method": "abort_turn", "session_id": session_id})

    async def cleanup_session(self, session_id):  # type: ignore[no-untyped-def]
        self.calls.append({"method": "cleanup_session", "session_id": session_id})
        return {"session_id": session_id, "removed": []}


class FakeProcessManager:
    def __init__(self, events: list[str]) -> None:
        self.calls = 0
        self.events = events

    def ensure_server(self):  # type: ignore[no-untyped-def]
        self.calls += 1
        self.events.append("ensure_server")
        return object()


@pytest.mark.asyncio
async def test_message_stream_emits_received_event_without_starting_opencode_before_preflight(
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app.state.settings.agent_backend = "opencode"
    preflight_started = False
    events: list[str] = []

    async def blocked_load_session(request, session_id):  # type: ignore[no-untyped-def]
        nonlocal preflight_started
        preflight_started = True
        events.append("preflight")
        raise AssertionError("preflight should not run before the first SSE event")

    monkeypatch.setattr(sessions_api, "_load_session", blocked_load_session)
    fake_process_manager = FakeProcessManager(events)
    app.state.opencode_process_manager = fake_process_manager
    request = SimpleNamespace(
        app=app,
        state=SimpleNamespace(subject_id="alice@dev-1", authenticated=False),
    )
    payload = MessageCreate(content="hello opencode", client_turn_id="turn_preflight")

    stream = sessions_api._stream_post_message_response(  # type: ignore[attr-defined]
        cast(Any, request),
        "sess_preflight",
        "turn_preflight",
        payload,
    )
    first_chunk = await anext(stream)
    second_chunk = await anext(stream)
    await stream.aclose()

    assert preflight_started is True
    assert fake_process_manager.calls == 0
    assert events == ["preflight"]
    assert b"event: assistant_action" in first_chunk
    assert b"agent_request_received" in first_chunk
    assert b"turn_preflight" in first_chunk
    assert b"event: error" in second_chunk


@pytest.mark.asyncio
async def test_post_message_stream_uses_opencode_backend_by_setting(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    app.state.settings.agent_backend = "opencode"
    fake = FakeOpenCodeCompat(calls=[])
    app.state.opencode_compat = fake

    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200
    config = await client.post(
        "/api/admin/llm-configs",
        json={
            "name": "opencode-default",
            "protocol": "openai",
            "base_url": "http://llm.test/v1",
            "api_key": "sk-secret",
            "model_name": "gpt-test",
            "is_default": True,
        },
    )
    assert config.status_code == 201, config.text
    await client.post("/api/auth/logout")

    headers = {"X-Subject-Id": "alice@dev-1"}
    created = await client.post("/api/sessions", json={"title": "OpenCode"}, headers=headers)
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    response = await client.post(
        f"/api/sessions/{session_id}/messages",
        json={"content": "hello opencode", "client_turn_id": "turn_opencode"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert "event: assistant_action" in response.text
    assert "event: runtime_state" in response.text
    assert "gpt-test" in response.text
    assert "event: text_delta" in response.text
    assert "opencode answer" in response.text
    assert "event: done" in response.text
    stream_events = _parse_sse_events(response.text)
    assert stream_events
    assert all("timing" in event["data"] for event in stream_events)
    done_event = next(event for event in stream_events if event["event"] == "done")
    assert done_event["data"]["timing"]["response_observed"] is True
    assert done_event["data"]["timing"]["total_elapsed_ms"] >= 0
    assert [call["method"] for call in fake.calls] == ["initialize_session", "run_turn"]

    async with app.state.session_factory() as session:
        turns = (
            (
                await session.execute(
                    SessionTurn.__table__.select()
                    .where(SessionTurn.session_id == session_id)
                    .order_by(SessionTurn.turn_index.asc())
                )
            )
            .mappings()
            .all()
        )
    assert [turn["role"] for turn in turns] == ["user", "agent"]
    assert turns[1]["content"] == "opencode answer"
    async with app.state.session_factory() as session:
        traces = (
            (
                await session.execute(
                    sessions_api.AgentTrace.__table__.select()
                    .where(sessions_api.AgentTrace.session_id == session_id)
                    .order_by(sessions_api.AgentTrace.created_at.asc())
                )
            )
            .mappings()
            .all()
        )
    assert traces
    assert all("timing" in trace["payload"] for trace in traces)
    assert traces[-1]["payload"]["timing"]["response_observed"] is True


@pytest.mark.asyncio
async def test_opencode_read_tool_paths_are_redacted_in_sse_and_traces(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    app.state.settings.agent_backend = "opencode"
    fake = FakeOpenCodeCompat(calls=[])
    app.state.opencode_compat = fake

    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200
    config = await client.post(
        "/api/admin/llm-configs",
        json={
            "name": "opencode-read-redaction",
            "protocol": "openai",
            "base_url": "http://llm.test/v1",
            "api_key": "sk-secret",
            "model_name": "gpt-test",
            "is_default": True,
        },
    )
    assert config.status_code == 201, config.text
    created = await client.post("/api/sessions", json={"title": "OpenCode read redaction"})
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]
    absolute_path = (
        f"/home/hzh/.codeask/agent_sessions/opencode/sessions/{session_id}/"
        "workspace/repos/app/src/main.ts"
    )
    slashless_path = absolute_path.lstrip("/")
    fake.scripted_run_events_by_model = {
        "gpt-test": [
            ChatRuntimeEvent(
                type="tool_call",
                data={
                    "tool_call_id": "call_read",
                    "tool_name": "read",
                    "arguments_summary": {"filePath": absolute_path},
                },
            ),
            ChatRuntimeEvent(
                type="tool_result",
                data={
                    "tool_call_id": "call_read",
                    "tool_name": "read",
                    "ok": True,
                    "summary": slashless_path,
                    "message": f"Opened {slashless_path}",
                    "path": absolute_path,
                },
            ),
            ChatRuntimeEvent(type="text_delta", data={"delta": "done"}),
            ChatRuntimeEvent(
                type="done",
                data={
                    "backend": "opencode",
                    "log_path": absolute_path,
                },
            ),
        ]
    }

    response = await client.post(
        f"/api/sessions/{session_id}/messages",
        json={"content": "read file", "client_turn_id": "turn_read_redact"},
    )

    assert response.status_code == 200, response.text
    assert "/home/hzh" not in response.text
    assert session_id not in response.text
    assert "workspace/repos/app/src/main.ts" in response.text

    traces = await client.get(f"/api/sessions/{session_id}/traces")
    assert traces.status_code == 200, traces.text
    trace_payload_text = json.dumps(
        [trace["payload"] for trace in traces.json()],
        ensure_ascii=False,
    )
    assert "/home/hzh" not in trace_payload_text
    assert session_id not in trace_payload_text
    assert "workspace/repos/app/src/main.ts" in trace_payload_text


@pytest.mark.asyncio
async def test_post_message_stream_passes_configured_context_window_to_opencode(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    app.state.settings.agent_backend = "opencode"
    app.state.settings.model_context_window_tokens = 131_072
    fake = FakeOpenCodeCompat(calls=[])
    app.state.opencode_compat = fake

    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200
    config = await client.post(
        "/api/admin/llm-configs",
        json={
            "name": "opencode-default",
            "protocol": "openai",
            "base_url": "http://llm.test/v1",
            "api_key": "sk-secret",
            "model_name": "gpt-test",
            "is_default": True,
        },
    )
    assert config.status_code == 201, config.text
    await client.post("/api/auth/logout")

    headers = {"X-Subject-Id": "alice@dev-1"}
    created = await client.post("/api/sessions", json={"title": "OpenCode"}, headers=headers)
    session_id = created.json()["id"]

    response = await client.post(
        f"/api/sessions/{session_id}/messages",
        json={"content": "hello opencode", "client_turn_id": "turn_context_window"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    run_call = next(call for call in fake.calls if call["method"] == "run_turn")
    assert run_call["context_window_tokens"] == 131_072
    assert "131k" in response.text


@pytest.mark.asyncio
async def test_post_message_stream_uses_gateway_global_pool_for_opencode_configs(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    app.state.settings.agent_backend = "opencode"
    fake = FakeOpenCodeCompat(calls=[])
    app.state.opencode_compat = fake
    app.state.llm_gateway._random_choice = lambda configs: configs[1]  # pyright: ignore[reportPrivateUsage]

    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200
    first = await client.post(
        "/api/admin/llm-configs",
        json={
            "name": "opencode-pool-a",
            "protocol": "openai",
            "base_url": "http://llm-a.test/v1",
            "api_key": "sk-a",
            "model_name": "model-a",
            "enabled": True,
            "is_default": False,
        },
    )
    assert first.status_code == 201, first.text
    second = await client.post(
        "/api/admin/llm-configs",
        json={
            "name": "opencode-pool-b",
            "protocol": "anthropic",
            "base_url": "http://llm-b.test",
            "api_key": "sk-b",
            "model_name": "model-b",
            "enabled": True,
            "is_default": False,
            "opencode_provider_profile": "anthropic-compatible-bearer",
        },
    )
    assert second.status_code == 201, second.text
    await client.post("/api/auth/logout")

    headers = {"X-Subject-Id": "alice@dev-1"}
    created = await client.post("/api/sessions", json={"title": "OpenCode"}, headers=headers)
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    response = await client.post(
        f"/api/sessions/{session_id}/messages",
        json={"content": "hello opencode", "client_turn_id": "turn_opencode_pool"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert "Multiple rows were found" not in response.text
    assert "event: runtime_state" in response.text
    assert "model-b" in response.text
    init_call = fake.calls[0]
    run_call = fake.calls[1]
    assert init_call["method"] == "initialize_session"
    assert init_call["model"] == "model-b"
    assert init_call["opencode_provider_profile"] == "anthropic-compatible-bearer"
    assert run_call["method"] == "run_turn"
    assert run_call["model"] == "model-b"
    assert run_call["opencode_provider_profile"] == "anthropic-compatible-bearer"


@pytest.mark.asyncio
async def test_opencode_global_pool_uses_single_unhealthy_config_in_degraded_mode(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    app.state.settings.agent_backend = "opencode"
    fake = FakeOpenCodeCompat(calls=[])
    app.state.opencode_compat = fake

    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200
    created_config = await client.post(
        "/api/admin/llm-configs",
        json={
            "name": "opencode-single-degraded",
            "protocol": "openai",
            "base_url": "http://llm-single.test/v1",
            "api_key": "sk-single",
            "model_name": "model-single",
            "enabled": True,
            "is_default": False,
        },
    )
    assert created_config.status_code == 201, created_config.text
    config_id = created_config.json()["id"]
    await client.post("/api/auth/logout")
    for _ in range(3):
        app.state.llm_gateway._global_usage.record_failure(config_id)  # pyright: ignore[reportPrivateUsage]

    headers = {"X-Subject-Id": "alice@dev-1"}
    created = await client.post("/api/sessions", json={"title": "OpenCode"}, headers=headers)
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    response = await client.post(
        f"/api/sessions/{session_id}/messages",
        json={"content": "hello opencode", "client_turn_id": "turn_opencode_degraded"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert "当前资源繁忙" not in response.text
    assert "opencode answer" in response.text
    assert [
        (call["method"], call["model"])
        for call in fake.calls
        if call["method"] in {"initialize_session", "run_turn"}
    ] == [
        ("initialize_session", "model-single"),
        ("run_turn", "model-single"),
    ]


@pytest.mark.asyncio
async def test_opencode_global_pool_retries_next_config_only_before_text(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    app.state.settings.agent_backend = "opencode"
    fake = FakeOpenCodeCompat(
        calls=[],
        scripted_run_events_by_model={
            "model-a": [
                ChatRuntimeEvent(
                    type="error",
                    data={"backend": "opencode", "error": "model-a failed before text"},
                )
            ]
        },
    )
    app.state.opencode_compat = fake
    app.state.llm_gateway._random_choice = lambda configs: configs[0]  # pyright: ignore[reportPrivateUsage]

    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200
    for suffix, model_name in [("a", "model-a"), ("b", "model-b")]:
        created_config = await client.post(
            "/api/admin/llm-configs",
            json={
                "name": f"opencode-pool-{suffix}",
                "protocol": "openai",
                "base_url": f"http://llm-{suffix}.test/v1",
                "api_key": f"sk-{suffix}",
                "model_name": model_name,
                "enabled": True,
                "is_default": False,
            },
        )
        assert created_config.status_code == 201, created_config.text
    await client.post("/api/auth/logout")

    headers = {"X-Subject-Id": "alice@dev-1"}
    created = await client.post("/api/sessions", json={"title": "OpenCode"}, headers=headers)
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    response = await client.post(
        f"/api/sessions/{session_id}/messages",
        json={"content": "hello opencode", "client_turn_id": "turn_opencode_retry"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert "model-a failed before text" not in response.text
    assert "opencode answer" in response.text
    assert [
        (call["method"], call["model"])
        for call in fake.calls
        if call["method"] in {"initialize_session", "run_turn"}
    ] == [
        ("initialize_session", "model-a"),
        ("run_turn", "model-a"),
        ("initialize_session", "model-b"),
        ("run_turn", "model-b"),
    ]
    initialize_calls = [call for call in fake.calls if call["method"] == "initialize_session"]
    assert initialize_calls[0]["provider_config_pool"] == ["model-a", "model-b"]
    assert initialize_calls[0]["force_new_external_session"] is False
    assert initialize_calls[1]["provider_config_pool"] == ["model-a", "model-b"]
    assert initialize_calls[1]["force_new_external_session"] is True


@pytest.mark.asyncio
async def test_opencode_global_pool_retries_next_config_after_non_text_events(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    app.state.settings.agent_backend = "opencode"
    fake = FakeOpenCodeCompat(
        calls=[],
        scripted_run_events_by_model={
            "model-a": [
                ChatRuntimeEvent(
                    type="assistant_action",
                    data={"action": "opencode_busy", "summary": "busy"},
                ),
                ChatRuntimeEvent(
                    type="tool_call",
                    data={"tool_name": "openviking_search", "tool_call_id": "call_1"},
                ),
                ChatRuntimeEvent(
                    type="error",
                    data={
                        "backend": "opencode",
                        "error": {
                            "name": "APIError",
                            "data": {"message": "InvalidSubscription"},
                        },
                    },
                ),
            ]
        },
    )
    app.state.opencode_compat = fake
    app.state.llm_gateway._random_choice = lambda configs: configs[0]  # pyright: ignore[reportPrivateUsage]

    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200
    for suffix, model_name in [("a", "model-a"), ("b", "model-b")]:
        created_config = await client.post(
            "/api/admin/llm-configs",
            json={
                "name": f"opencode-pool-non-text-{suffix}",
                "protocol": "openai",
                "base_url": f"http://llm-non-text-{suffix}.test/v1",
                "api_key": f"sk-{suffix}",
                "model_name": model_name,
                "enabled": True,
                "is_default": False,
            },
        )
        assert created_config.status_code == 201, created_config.text
    await client.post("/api/auth/logout")

    headers = {"X-Subject-Id": "alice@dev-1"}
    created = await client.post("/api/sessions", json={"title": "OpenCode"}, headers=headers)
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    response = await client.post(
        f"/api/sessions/{session_id}/messages",
        json={"content": "hello opencode", "client_turn_id": "turn_opencode_non_text_retry"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert "InvalidSubscription" not in response.text
    assert "opencode answer" in response.text
    assert [
        (call["method"], call["model"])
        for call in fake.calls
        if call["method"] in {"initialize_session", "run_turn"}
    ] == [
        ("initialize_session", "model-a"),
        ("run_turn", "model-a"),
        ("initialize_session", "model-b"),
        ("run_turn", "model-b"),
    ]


@pytest.mark.asyncio
async def test_opencode_global_pool_can_try_all_global_configs_once(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    app.state.settings.agent_backend = "opencode"
    bad_events = [
        ChatRuntimeEvent(
            type="assistant_action",
            data={"action": "opencode_busy", "summary": "busy"},
        ),
        ChatRuntimeEvent(
            type="error",
            data={
                "backend": "opencode",
                "error": {
                    "name": "APIError",
                    "data": {"message": "InvalidSubscription"},
                },
            },
        ),
    ]
    fake = FakeOpenCodeCompat(
        calls=[],
        scripted_run_events_by_model={
            **{f"model-{idx}": bad_events for idx in range(5)},
        },
    )
    app.state.opencode_compat = fake
    app.state.llm_gateway._random_choice = lambda configs: configs[0]  # pyright: ignore[reportPrivateUsage]

    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200
    for idx in range(6):
        created_config = await client.post(
            "/api/admin/llm-configs",
            json={
                "name": f"opencode-pool-many-failures-{idx}",
                "protocol": "openai",
                "base_url": f"http://llm-many-failures-{idx}.test/v1",
                "api_key": f"sk-{idx}",
                "model_name": f"model-{idx}",
                "enabled": True,
                "is_default": False,
            },
        )
        assert created_config.status_code == 201, created_config.text
    await client.post("/api/auth/logout")

    headers = {"X-Subject-Id": "alice@dev-1"}
    created = await client.post("/api/sessions", json={"title": "OpenCode"}, headers=headers)
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    response = await client.post(
        f"/api/sessions/{session_id}/messages",
        json={"content": "hello opencode", "client_turn_id": "turn_opencode_try_all"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert "InvalidSubscription" not in response.text
    assert "opencode answer" in response.text
    assert [
        (call["method"], call["model"])
        for call in fake.calls
        if call["method"] in {"initialize_session", "run_turn"}
    ] == [
        ("initialize_session", "model-0"),
        ("run_turn", "model-0"),
        ("initialize_session", "model-1"),
        ("run_turn", "model-1"),
        ("initialize_session", "model-2"),
        ("run_turn", "model-2"),
        ("initialize_session", "model-3"),
        ("run_turn", "model-3"),
        ("initialize_session", "model-4"),
        ("run_turn", "model-4"),
        ("initialize_session", "model-5"),
        ("run_turn", "model-5"),
    ]


@pytest.mark.asyncio
async def test_opencode_global_pool_does_not_switch_after_visible_text(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    app.state.settings.agent_backend = "opencode"
    fake = FakeOpenCodeCompat(
        calls=[],
        scripted_run_events_by_model={
            "model-a": [
                ChatRuntimeEvent(type="text_delta", data={"delta": "partial answer"}),
                ChatRuntimeEvent(
                    type="error",
                    data={"backend": "opencode", "error": "model-a failed after text"},
                ),
            ]
        },
    )
    app.state.opencode_compat = fake
    app.state.llm_gateway._random_choice = lambda configs: configs[0]  # pyright: ignore[reportPrivateUsage]

    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200
    for suffix, model_name in [("a", "model-a"), ("b", "model-b")]:
        created_config = await client.post(
            "/api/admin/llm-configs",
            json={
                "name": f"opencode-pool-after-text-{suffix}",
                "protocol": "openai",
                "base_url": f"http://llm-{suffix}.test/v1",
                "api_key": f"sk-{suffix}",
                "model_name": model_name,
                "enabled": True,
                "is_default": False,
            },
        )
        assert created_config.status_code == 201, created_config.text
    await client.post("/api/auth/logout")

    headers = {"X-Subject-Id": "alice@dev-1"}
    created = await client.post("/api/sessions", json={"title": "OpenCode"}, headers=headers)
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    response = await client.post(
        f"/api/sessions/{session_id}/messages",
        json={"content": "hello opencode", "client_turn_id": "turn_opencode_no_retry"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert "partial answer" in response.text
    assert "model-a failed after text" in response.text
    assert [
        (call["method"], call["model"])
        for call in fake.calls
        if call["method"] in {"initialize_session", "run_turn"}
    ] == [
        ("initialize_session", "model-a"),
        ("run_turn", "model-a"),
    ]


@pytest.mark.asyncio
async def test_post_message_stream_opencode_error_does_not_persist_agent_turn(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    app.state.settings.agent_backend = "opencode"
    app.state.opencode_compat = FakeOpenCodeCompat(calls=[], fail_run=True)

    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200
    config = await client.post(
        "/api/admin/llm-configs",
        json={
            "name": "opencode-default",
            "protocol": "openai",
            "base_url": "http://llm.test/v1",
            "api_key": "sk-secret",
            "model_name": "gpt-test",
            "is_default": True,
        },
    )
    assert config.status_code == 201, config.text
    await client.post("/api/auth/logout")

    headers = {"X-Subject-Id": "alice@dev-1"}
    created = await client.post("/api/sessions", json={"title": "OpenCode"}, headers=headers)
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    response = await client.post(
        f"/api/sessions/{session_id}/messages",
        json={"content": "hello opencode", "client_turn_id": "turn_opencode_error"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert "event: error" in response.text
    assert "opencode unavailable" in response.text
    async with app.state.session_factory() as session:
        turns = (
            (
                await session.execute(
                    SessionTurn.__table__.select()
                    .where(SessionTurn.session_id == session_id)
                    .order_by(SessionTurn.turn_index.asc())
                )
            )
            .mappings()
            .all()
        )
    assert [turn["role"] for turn in turns] == ["user"]


@pytest.mark.asyncio
async def test_post_message_stream_opencode_exception_returns_error_event(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    app.state.settings.agent_backend = "opencode"
    app.state.opencode_compat = FakeOpenCodeCompat(calls=[], fail_initialize=True)

    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200
    config = await client.post(
        "/api/admin/llm-configs",
        json={
            "name": "opencode-default",
            "protocol": "openai",
            "base_url": "http://llm.test/v1",
            "api_key": "sk-secret",
            "model_name": "gpt-test",
            "is_default": True,
        },
    )
    assert config.status_code == 201, config.text
    await client.post("/api/auth/logout")

    headers = {"X-Subject-Id": "alice@dev-1"}
    created = await client.post("/api/sessions", json={"title": "OpenCode"}, headers=headers)
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    response = await client.post(
        f"/api/sessions/{session_id}/messages",
        json={"content": "hello opencode", "client_turn_id": "turn_opencode_init_error"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert "event: error" in response.text
    assert "opencode is not reachable" in response.text
    async with app.state.session_factory() as session:
        turns = (
            (
                await session.execute(
                    SessionTurn.__table__.select()
                    .where(SessionTurn.session_id == session_id)
                    .order_by(SessionTurn.turn_index.asc())
                )
            )
            .mappings()
            .all()
        )
    assert [turn["role"] for turn in turns] == ["user"]


@pytest.mark.asyncio
async def test_post_message_stream_preserves_classified_opencode_error_code(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    app.state.settings.agent_backend = "opencode"
    app.state.opencode_compat = FakeOpenCodeCompat(
        calls=[],
        fail_initialize_code="opencode_health_timeout",
    )

    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200
    config = await client.post(
        "/api/admin/llm-configs",
        json={
            "name": "opencode-default",
            "protocol": "openai",
            "base_url": "http://llm.test/v1",
            "api_key": "sk-secret",
            "model_name": "gpt-test",
            "is_default": True,
        },
    )
    assert config.status_code == 201, config.text
    await client.post("/api/auth/logout")

    headers = {"X-Subject-Id": "alice@dev-1"}
    created = await client.post("/api/sessions", json={"title": "OpenCode"}, headers=headers)
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    response = await client.post(
        f"/api/sessions/{session_id}/messages",
        json={"content": "hello opencode", "client_turn_id": "turn_opencode_classified"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert "event: error" in response.text
    assert "classified opencode failure" in response.text
    assert "opencode_health_timeout" in response.text


@pytest.mark.asyncio
async def test_abort_session_turn_calls_opencode_and_keeps_turn(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    app.state.settings.agent_backend = "opencode"
    fake = FakeOpenCodeCompat(calls=[])
    app.state.opencode_compat = fake

    headers = {"X-Subject-Id": "alice@dev-1"}
    created = await client.post("/api/sessions", json={"title": "OpenCode"}, headers=headers)
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]
    async with app.state.session_factory() as session:
        session.add(
            SessionTurn(
                id="turn_abort",
                session_id=session_id,
                turn_index=0,
                role="user",
                content="abort me",
                evidence=None,
            )
        )
        await session.commit()

    response = await client.post(
        f"/api/sessions/{session_id}/turns/turn_abort/abort",
        headers=headers,
    )

    assert response.status_code == 204, response.text
    assert fake.calls == [{"method": "abort_turn", "session_id": session_id}]
    async with app.state.session_factory() as session:
        turn = await session.get(SessionTurn, "turn_abort")
    assert turn is not None
    assert turn.content == "abort me"


@pytest.mark.asyncio
async def test_abort_session_turn_keeps_turn_even_when_opencode_abort_fails(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    app.state.settings.agent_backend = "opencode"
    app.state.opencode_compat = FakeOpenCodeCompat(calls=[], fail_abort=True)

    headers = {"X-Subject-Id": "alice@dev-1"}
    created = await client.post("/api/sessions", json={"title": "OpenCode"}, headers=headers)
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]
    async with app.state.session_factory() as session:
        session.add(
            SessionTurn(
                id="turn_abort_failed_upstream",
                session_id=session_id,
                turn_index=0,
                role="user",
                content="abort me",
                evidence=None,
            )
        )
        await session.commit()

    response = await client.post(
        f"/api/sessions/{session_id}/turns/turn_abort_failed_upstream/abort",
        headers=headers,
    )

    assert response.status_code == 204, response.text
    async with app.state.session_factory() as session:
        turn = await session.get(SessionTurn, "turn_abort_failed_upstream")
    assert turn is not None
    assert turn.content == "abort me"


@pytest.mark.asyncio
async def test_delete_session_removes_opencode_workspace_dir(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    headers = {"X-Subject-Id": "alice@dev-1"}
    created = await client.post("/api/sessions", json={"title": "OpenCode"}, headers=headers)
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]
    workspace_dir = app.state.settings.data_dir / "agent_sessions" / "opencode" / session_id
    workspace_dir.mkdir(parents=True)
    (workspace_dir / "state.txt").write_text("temp", encoding="utf-8")

    response = await client.delete(f"/api/sessions/{session_id}", headers=headers)

    assert response.status_code == 204, response.text
    assert not workspace_dir.exists()


@pytest.mark.asyncio
async def test_delete_session_calls_opencode_cleanup(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    fake = FakeOpenCodeCompat(calls=[])
    app.state.opencode_compat = fake
    headers = {"X-Subject-Id": "alice@dev-1"}
    created = await client.post("/api/sessions", json={"title": "OpenCode"}, headers=headers)
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    response = await client.delete(f"/api/sessions/{session_id}", headers=headers)

    assert response.status_code == 204, response.text
    assert {"method": "cleanup_session", "session_id": session_id} in fake.calls


@pytest.mark.asyncio
async def test_bulk_delete_sessions_calls_opencode_cleanup_for_owned_sessions(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    fake = FakeOpenCodeCompat(calls=[])
    app.state.opencode_compat = fake
    headers = {"X-Subject-Id": "alice@dev-1"}
    first = await client.post("/api/sessions", json={"title": "A"}, headers=headers)
    second = await client.post("/api/sessions", json={"title": "B"}, headers=headers)
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    session_ids = [first.json()["id"], second.json()["id"]]

    response = await client.post(
        "/api/sessions/bulk-delete",
        json={"session_ids": session_ids},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["deleted_ids"] == session_ids
    cleanup_ids = [call["session_id"] for call in fake.calls if call["method"] == "cleanup_session"]
    assert cleanup_ids == session_ids


def _parse_sse_events(source: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for frame in source.strip().split("\n\n"):
        event_type = ""
        data_lines: list[str] = []
        for line in frame.splitlines():
            if line.startswith("event:"):
                event_type = line.removeprefix("event:").strip()
            elif line.startswith("data:"):
                data_lines.append(line.removeprefix("data:").strip())
        if event_type:
            events.append(
                {
                    "event": event_type,
                    "data": json.loads("\n".join(data_lines)) if data_lines else {},
                }
            )
    return events
