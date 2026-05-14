from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from codeask.agent.chat_runtime.events import ChatRuntimeEvent
from codeask.db.models import SessionTurn


@dataclass
class FakeOpenCodeCompat:
    calls: list[dict[str, object]]
    fail_run: bool = False
    fail_initialize: bool = False

    async def initialize_session(self, session_id, llm_config):  # type: ignore[no-untyped-def]
        if self.fail_initialize:
            raise RuntimeError("opencode is not reachable")
        self.calls.append(
            {
                "method": "initialize_session",
                "session_id": session_id,
                "model": llm_config.model_name,
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
                "system": system,
            }
        )
        yield ChatRuntimeEvent(type="text_delta", data={"delta": "opencode answer"})
        yield ChatRuntimeEvent(type="done", data={"backend": "opencode"})

    async def abort_turn(self, session_id):  # type: ignore[no-untyped-def]
        self.calls.append({"method": "abort_turn", "session_id": session_id})


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
    assert "event: runtime_state" in response.text
    assert "gpt-test" in response.text
    assert "event: text_delta" in response.text
    assert "opencode answer" in response.text
    assert "event: done" in response.text
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
async def test_abort_session_turn_calls_opencode_before_rollback(
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
    assert turn is None


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
