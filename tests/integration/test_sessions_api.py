"""End-to-end /api/sessions tests."""

import asyncio
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select

from codeask.db.models import (
    AgentTrace,
    Report,
    Session,
    SessionConversationSummary,
    SessionRepoBinding,
    SessionTurn,
)
from codeask.sessions.messages import (
    persist_agent_turn,
    persist_runtime_audit_payload,
    persist_runtime_event_trace,
    rollback_session_turn,
)
from tests.mocks.mock_llm import MockLLMClient, text_message


async def _session_title(app: FastAPI, session_id: str) -> tuple[str, str]:
    async with app.state.session_factory() as db:
        row = await db.get(Session, session_id)
        assert row is not None
        return row.title, row.title_source


async def _wait_for_session_title(
    app: FastAPI,
    session_id: str,
    expected_title: str,
    *,
    timeout_seconds: float = 1.0,
) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        title, _ = await _session_title(app, session_id)
        if title == expected_title:
            return
        await asyncio.sleep(0.02)
    title, source = await _session_title(app, session_id)
    raise AssertionError(f"expected title {expected_title!r}, got {title!r} ({source})")


@pytest.mark.asyncio
async def test_session_message_sse_and_attachment(
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
    logout = await client.post("/api/auth/logout")
    assert logout.status_code == 204

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

    mock = MockLLMClient([text_message("结论：订单 500 可以先检查上下文。")])
    app.state.llm_gateway.client_factory.provider_clients["openai"] = lambda **_: mock

    message = await client.post(
        f"/api/sessions/{session_id}/messages",
        json={
            "content": "为什么订单偶发 500",
            "client_turn_id": "turn_client_contract",
            "feature_ids": [feature_id],
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert message.status_code == 200, message.text
    assert message.headers["X-CodeAsk-Turn-Id"] == "turn_client_contract"
    body = message.text
    assert "event: retrieval_context" in body
    assert "event: text_delta" in body
    assert "event: done" in body
    assert "event: scope_detection" not in body

    attachment = await client.post(
        f"/api/sessions/{session_id}/attachments",
        files={"file": ("app.log", b"ERROR order failed", "text/plain")},
        data={"kind": "log"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert attachment.status_code == 201, attachment.text
    uploaded = attachment.json()
    assert uploaded["kind"] == "log"
    assert uploaded["display_name"] == "app.log"
    assert Path(uploaded["file_path"]).exists()


@pytest.mark.asyncio
async def test_default_session_title_is_generated_after_first_completed_exchange(
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
    logout = await client.post("/api/auth/logout")
    assert logout.status_code == 204

    created = await client.post(
        "/api/sessions",
        json={"title": "新的研发会话"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["title_source"] == "default"
    session_id = created.json()["id"]

    mock = MockLLMClient(
        [
            text_message("list 是可变序列，tuple 是不可变序列。"),
            text_message("Python list 与 tuple 区别"),
        ]
    )
    app.state.llm_gateway.client_factory.provider_clients["openai"] = lambda **_: mock

    message = await client.post(
        f"/api/sessions/{session_id}/messages",
        json={
            "content": "Python 中 list 和 tuple 的区别是什么？",
            "client_turn_id": "turn_client_title_auto",
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert message.status_code == 200, message.text
    assert "event: done" in message.text

    await _wait_for_session_title(app, session_id, "Python list 与 tuple 区别")
    assert len(mock.calls) == 2
    assert mock.calls[1]["tools"] == []
    title_prompt = "\n".join(
        block["text"]
        for message in mock.calls[1]["messages"]
        for block in message["content"]
        if block["type"] == "text"
    )
    assert "只输出标题文本" in title_prompt
    assert "Python 中 list 和 tuple 的区别是什么" in title_prompt

    turns = await client.get(
        f"/api/sessions/{session_id}/turns",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert turns.status_code == 200, turns.text
    assert [turn["role"] for turn in turns.json()] == ["user", "agent"]
    assert all("只输出标题文本" not in turn["content"] for turn in turns.json())


@pytest.mark.asyncio
async def test_manual_session_title_is_not_overwritten_by_auto_generation(
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
    logout = await client.post("/api/auth/logout")
    assert logout.status_code == 204

    created = await client.post(
        "/api/sessions",
        json={"title": "新的研发会话"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]
    renamed = await client.patch(
        f"/api/sessions/{session_id}",
        json={"title": "我手动命名的会话"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["title_source"] == "manual"

    mock = MockLLMClient([text_message("这里是正常回答。")])
    app.state.llm_gateway.client_factory.provider_clients["openai"] = lambda **_: mock

    message = await client.post(
        f"/api/sessions/{session_id}/messages",
        json={
            "content": "写一个函数反转字符串",
            "client_turn_id": "turn_client_title_manual",
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert message.status_code == 200, message.text
    await asyncio.sleep(0.05)

    title, source = await _session_title(app, session_id)
    assert title == "我手动命名的会话"
    assert source == "manual"
    assert len(mock.calls) == 1


@pytest.mark.asyncio
async def test_explicit_session_title_generation_returns_updated_session(
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
    logout = await client.post("/api/auth/logout")
    assert logout.status_code == 204

    created = await client.post(
        "/api/sessions",
        json={"title": "新的研发会话"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    async with app.state.session_factory() as db:
        db.add(
            SessionTurn(
                id="turn_title_user",
                session_id=session_id,
                turn_index=0,
                role="user",
                content="介绍一下 CodeAsk 能做什么",
            )
        )
        db.add(
            SessionTurn(
                id="turn_title_agent",
                session_id=session_id,
                turn_index=1,
                role="agent",
                content="CodeAsk 可以结合 Wiki、问题报告和代码仓库辅助研发排障。",
            )
        )
        db.add(
            SessionTurn(
                id="turn_title_follow_user",
                session_id=session_id,
                turn_index=2,
                role="user",
                content="再讲讲代码检索",
            )
        )
        db.add(
            SessionTurn(
                id="turn_title_follow_agent",
                session_id=session_id,
                turn_index=3,
                role="agent",
                content="CodeAsk 可以基于仓库索引检索代码文件。",
            )
        )
        await db.commit()

    mock = MockLLMClient([text_message("CodeAsk 能力介绍")])
    app.state.llm_gateway.client_factory.provider_clients["openai"] = lambda **_: mock

    generated = await client.post(
        f"/api/sessions/{session_id}/title/generate",
        headers={"X-Subject-Id": "alice@dev-1"},
    )

    assert generated.status_code == 200, generated.text
    assert generated.json()["title"] == "CodeAsk 能力介绍"
    assert generated.json()["title_source"] == "auto"
    assert generated.json()["title_generated_at"] is not None
    assert len(mock.calls) == 1
    assert mock.calls[0]["tools"] == []
    assert mock.calls[0]["max_tokens"] == 2048
    turns = await client.get(
        f"/api/sessions/{session_id}/turns",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert turns.status_code == 200, turns.text
    assert [turn["role"] for turn in turns.json()] == ["user", "agent", "user", "agent"]


@pytest.mark.asyncio
async def test_session_message_injects_current_session_attachments_into_llm_context(
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
    logout = await client.post("/api/auth/logout")
    assert logout.status_code == 204

    created = await client.post(
        "/api/sessions",
        json={"title": "附件上下文"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    uploaded = await client.post(
        f"/api/sessions/{session_id}/attachments",
        files={"file": ("service.log", b"ERROR42 node-a failed", "text/plain")},
        data={"kind": "log", "description": "数据库节点 A 日志"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert uploaded.status_code == 201, uploaded.text
    attachment_id = uploaded.json()["id"]
    renamed = await client.patch(
        f"/api/sessions/{session_id}/attachments/{attachment_id}",
        json={"display_name": "db-node-a.log"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert renamed.status_code == 200, renamed.text

    mock = MockLLMClient([text_message("我会先查看 db-node-a.log。")])
    app.state.llm_gateway.client_factory.provider_clients["openai"] = lambda **_: mock

    message = await client.post(
        f"/api/sessions/{session_id}/messages",
        json={"content": "请先看上传的日志"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert message.status_code == 200, message.text

    first_call_text = "\n".join(
        block["text"]
        for message in mock.calls[0]["messages"]
        for block in message["content"]
        if block["type"] == "text"
    )
    assert "【会话附件候选】" in first_call_text
    assert "db-node-a.log" in first_call_text
    assert "service.log" in first_call_text
    assert "数据库节点 A 日志" in first_call_text


@pytest.mark.asyncio
async def test_session_turns_can_be_listed_for_the_session_owner(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    created = await client.post(
        "/api/sessions",
        json={"title": "历史问答"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    async with app.state.session_factory() as db:
        db.add_all(
            [
                SessionTurn(
                    id="turn_history_user",
                    session_id=session_id,
                    turn_index=0,
                    role="user",
                    content="为什么服务启动失败？",
                    evidence=None,
                ),
                SessionTurn(
                    id="turn_history_agent",
                    session_id=session_id,
                    turn_index=1,
                    role="agent",
                    content="先检查配置文件是否缺失。",
                    evidence={"items": [{"id": "ev_1", "source": "wiki"}]},
                ),
            ]
        )
        await db.commit()

    forbidden = await client.get(
        f"/api/sessions/{session_id}/turns",
        headers={"X-Subject-Id": "bob@dev-1"},
    )
    assert forbidden.status_code == 404

    listed = await client.get(
        f"/api/sessions/{session_id}/turns",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert listed.status_code == 200, listed.text
    rows = listed.json()
    assert [row["id"] for row in rows] == ["turn_history_user", "turn_history_agent"]
    assert [row["role"] for row in rows] == ["user", "agent"]
    assert rows[0]["content"] == "为什么服务启动失败？"
    assert rows[1]["content"] == "先检查配置文件是否缺失。"
    assert rows[1]["evidence"] == {"items": [{"id": "ev_1", "source": "wiki"}]}


@pytest.mark.asyncio
async def test_rollback_session_turn_removes_interrupted_turn_and_traces(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    created = await client.post(
        "/api/sessions",
        json={"title": "中断回滚"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    async with app.state.session_factory() as db:
        db.add(
            SessionTurn(
                id="turn_interrupted",
                session_id=session_id,
                turn_index=0,
                role="user",
                content="需要中断的长任务",
                evidence=None,
            )
        )
        await db.flush()
        db.add(
            AgentTrace(
                id="tr_interrupted",
                session_id=session_id,
                turn_id="turn_interrupted",
                stage="chat_runtime",
                event_type="retrieval_context",
                payload={"feature_candidates": [], "wiki_hits": [], "report_hits": []},
            )
        )
        await db.commit()

    await rollback_session_turn(app.state.session_factory, session_id, "turn_interrupted")

    async with app.state.session_factory() as db:
        turns = (
            await db.execute(
                select(SessionTurn).where(SessionTurn.session_id == session_id)
            )
        ).scalars().all()
        traces = (
            await db.execute(
                select(AgentTrace).where(AgentTrace.session_id == session_id)
            )
        ).scalars().all()
    assert turns == []
    assert traces == []


@pytest.mark.asyncio
async def test_list_session_traces_compacts_legacy_reasoning_diagnostics(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    created = await client.post(
        "/api/sessions",
        json={"title": "推理诊断聚合"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    async with app.state.session_factory() as db:
        db.add(
            SessionTurn(
                id="turn_reasoning_legacy",
                session_id=session_id,
                turn_index=0,
                role="user",
                content="测试推理诊断",
                evidence=None,
            )
        )
        await db.flush()
        db.add_all(
            [
                AgentTrace(
                    id="tr_reasoning_1",
                    session_id=session_id,
                    turn_id="turn_reasoning_legacy",
                    stage="chat_runtime",
                    event_type="reasoning_observed",
                    payload={
                        "field": "reasoning_content",
                        "length": 2,
                        "redacted": False,
                        "raw_reasoning_used": False,
                    },
                ),
                AgentTrace(
                    id="tr_reasoning_2",
                    session_id=session_id,
                    turn_id="turn_reasoning_legacy",
                    stage="chat_runtime",
                    event_type="reasoning_observed",
                    payload={
                        "field": "reasoning_content",
                        "length": 3,
                        "redacted": False,
                        "raw_reasoning_used": False,
                    },
                ),
                AgentTrace(
                    id="tr_reasoning_3",
                    session_id=session_id,
                    turn_id="turn_reasoning_legacy",
                    stage="chat_runtime",
                    event_type="reasoning_observed",
                    payload={
                        "field": "reasoning_content",
                        "length": 4,
                        "redacted": True,
                        "raw_reasoning_used": False,
                    },
                ),
                AgentTrace(
                    id="tr_tool",
                    session_id=session_id,
                    turn_id="turn_reasoning_legacy",
                    stage="chat_runtime",
                    event_type="tool_call",
                    payload={"tool_name": "search_wiki"},
                ),
            ]
        )
        await db.commit()

    listed = await client.get(
        f"/api/sessions/{session_id}/traces",
        headers={"X-Subject-Id": "alice@dev-1"},
    )

    assert listed.status_code == 200, listed.text
    rows = listed.json()
    reasoning_rows = [row for row in rows if row["event_type"] == "reasoning_observed"]
    assert len(reasoning_rows) == 1
    assert reasoning_rows[0]["payload"] == {
        "field": "reasoning_content",
        "length": 9,
        "chunks": 3,
        "redacted": True,
        "raw_reasoning_used": False,
    }
    assert [row["event_type"] for row in rows].count("tool_call") == 1


@pytest.mark.asyncio
async def test_abort_session_turn_endpoint_removes_interrupted_turn_and_traces(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    created = await client.post(
        "/api/sessions",
        json={"title": "中断接口"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    async with app.state.session_factory() as db:
        db.add(
            SessionTurn(
                id="turn_abort_api",
                session_id=session_id,
                turn_index=0,
                role="user",
                content="需要中断的长任务",
                evidence=None,
            )
        )
        await db.flush()
        db.add(
            AgentTrace(
                id="tr_abort_api",
                session_id=session_id,
                turn_id="turn_abort_api",
                stage="chat_runtime",
                event_type="retrieval_context",
                payload={"feature_candidates": [], "wiki_hits": [], "report_hits": []},
            )
        )
        await db.commit()

    forbidden = await client.post(
        f"/api/sessions/{session_id}/turns/turn_abort_api/abort",
        headers={"X-Subject-Id": "bob@dev-1"},
    )
    assert forbidden.status_code == 404

    aborted = await client.post(
        f"/api/sessions/{session_id}/turns/turn_abort_api/abort",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert aborted.status_code == 204, aborted.text

    async with app.state.session_factory() as db:
        turns = (
            await db.execute(
                select(SessionTurn).where(SessionTurn.session_id == session_id)
            )
        ).scalars().all()
        traces = (
            await db.execute(
                select(AgentTrace).where(AgentTrace.session_id == session_id)
            )
        ).scalars().all()
    assert turns == []
    assert traces == []


@pytest.mark.asyncio
async def test_interrupted_turn_cannot_persist_late_agent_response(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    created = await client.post(
        "/api/sessions",
        json={"title": "中断后禁止迟到回答"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    async with app.state.session_factory() as db:
        db.add(
            SessionTurn(
                id="turn_late_abort",
                session_id=session_id,
                turn_index=0,
                role="user",
                content="换一种",
                evidence=None,
            )
        )
        await db.commit()

    await rollback_session_turn(app.state.session_factory, session_id, "turn_late_abort")
    request = SimpleNamespace(app=SimpleNamespace(state=app.state))
    await persist_agent_turn(
        request,
        session_id,
        "这是已经被中断的一轮迟到回答，不应进入历史上下文。",
        parent_turn_id="turn_late_abort",
    )

    async with app.state.session_factory() as db:
        turns = (
            await db.execute(
                select(SessionTurn).where(SessionTurn.session_id == session_id)
            )
        ).scalars().all()
    assert turns == []


@pytest.mark.asyncio
async def test_interrupted_turn_cannot_persist_late_tool_results(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    created = await client.post(
        "/api/sessions",
        json={"title": "中断后禁止迟到工具结果"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    async with app.state.session_factory() as db:
        db.add(
            SessionTurn(
                id="turn_late_tool_abort",
                session_id=session_id,
                turn_index=0,
                role="user",
                content="停止前已经开始查代码",
                evidence=None,
            )
        )
        await db.flush()
        db.add(
            AgentTrace(
                id="tr_late_tool_call",
                session_id=session_id,
                turn_id="turn_late_tool_abort",
                stage="chat_runtime",
                event_type="tool_call",
                payload={
                    "tool_call_id": "call_late",
                    "tool_name": "search_code",
                    "arguments_summary": {"query": "better-sqlite3"},
                },
            )
        )
        await db.commit()

    await rollback_session_turn(app.state.session_factory, session_id, "turn_late_tool_abort")
    request = SimpleNamespace(app=SimpleNamespace(state=app.state))
    await persist_runtime_event_trace(
        request,
        session_id,
        "turn_late_tool_abort",
        "tool_result",
        {
            "tool_call_id": "call_late",
            "tool_name": "search_code",
            "ok": True,
            "summary": "迟到工具结果不应进入历史",
        },
    )
    await persist_runtime_audit_payload(
        request,
        session_id,
        "turn_late_tool_abort",
        "tool_result",
        SimpleNamespace(
            audit_raw_result={
                "tool_call_id": "call_late",
                "raw_result_ref": "raw_tool_result:late",
            }
        ),
    )

    async with app.state.session_factory() as db:
        traces = (
            await db.execute(
                select(AgentTrace).where(AgentTrace.session_id == session_id)
            )
        ).scalars().all()
    assert traces == []


@pytest.mark.asyncio
async def test_session_traces_can_be_listed_for_the_session_owner(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    created = await client.post(
        "/api/sessions",
        json={"title": "历史运行事件"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    async with app.state.session_factory() as db:
        db.add(
            SessionTurn(
                id="turn_trace_user",
                session_id=session_id,
                turn_index=0,
                role="user",
                content="为什么服务启动失败？",
                evidence=None,
            )
        )
        await db.flush()
        db.add_all(
            [
                AgentTrace(
                    id="tr_scope_enter",
                    session_id=session_id,
                    turn_id="turn_trace_user",
                    stage="scope_detection",
                    event_type="stage_enter",
                    payload={"context": {"question": "为什么服务启动失败？"}},
                ),
                AgentTrace(
                    id="tr_scope_decision",
                    session_id=session_id,
                    turn_id="turn_trace_user",
                    stage="scope_detection",
                    event_type="scope_decision",
                    payload={
                        "output": {
                            "feature_ids": [7],
                            "confidence": 0.9,
                            "reason": "命中支付特性",
                        }
                    },
                ),
                AgentTrace(
                    id="tr_scope_exit",
                    session_id=session_id,
                    turn_id="turn_trace_user",
                    stage="scope_detection",
                    event_type="stage_exit",
                    payload={"result": {"next": "knowledge_retrieval"}},
                ),
            ]
        )
        await db.commit()

    forbidden = await client.get(
        f"/api/sessions/{session_id}/traces",
        headers={"X-Subject-Id": "bob@dev-1"},
    )
    assert forbidden.status_code == 404

    listed = await client.get(
        f"/api/sessions/{session_id}/traces",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert listed.status_code == 200, listed.text
    rows = listed.json()
    assert [row["id"] for row in rows] == [
        "tr_scope_enter",
        "tr_scope_decision",
        "tr_scope_exit",
    ]
    assert rows[1]["event_type"] == "scope_decision"
    assert rows[1]["payload"]["output"]["reason"] == "命中支付特性"


@pytest.mark.asyncio
async def test_session_message_persists_repo_binding_and_streams_answer(
    app: FastAPI,
    client: AsyncClient,
    tmp_path: Path,
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

    repo_src = _bootstrap_repo(tmp_path / "repo-src")
    commit = subprocess.check_output(
        ["git", "-C", str(repo_src), "rev-parse", "HEAD"],
        text=True,
    ).strip()
    repo_id = await _register_repo_and_wait_ready(client, repo_src)
    logout = await client.post("/api/auth/logout")
    assert logout.status_code == 204

    feature = await client.post(
        "/api/features",
        json={
            "name": "Code Tools",
            "slug": "code-tools-session",
            "description": "Code investigation feature",
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert feature.status_code == 201, feature.text
    feature_id = feature.json()["id"]

    created = await client.post(
        "/api/sessions",
        json={"title": "代码调查"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    mock = MockLLMClient(
        [text_message("结论：payment timeout 可以先查看 app.py 的 handle_payment。")]
    )
    app.state.llm_gateway.client_factory.provider_clients["openai"] = lambda **_: mock

    message = await client.post(
        f"/api/sessions/{session_id}/messages",
        json={
            "content": "请调查 payment timeout 是在哪里处理的",
            "feature_ids": [feature_id],
            "repo_bindings": [{"repo_id": repo_id, "ref": "HEAD"}],
            "force_code_investigation": True,
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert message.status_code == 200, message.text
    body = message.text
    assert "event: retrieval_context" in body
    assert "event: text_delta" in body
    assert "TOOL_NOT_CONFIGURED" not in body
    assert "payment timeout" in body

    async with app.state.session_factory() as session:
        binding = (
            await session.execute(
                select(SessionRepoBinding).where(
                    SessionRepoBinding.session_id == session_id,
                    SessionRepoBinding.repo_id == repo_id,
                )
            )
        ).scalar_one()
    assert binding.commit_sha == commit
    assert Path(binding.worktree_path).is_dir()


@pytest.mark.asyncio
async def test_session_attachments_can_be_listed_renamed_and_deleted(
    client: AsyncClient,
) -> None:
    first = await client.post(
        "/api/sessions",
        json={"title": "节点 A 排障"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    second = await client.post(
        "/api/sessions",
        json={"title": "节点 B 排障"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    first_id = first.json()["id"]
    second_id = second.json()["id"]

    first_upload = await client.post(
        f"/api/sessions/{first_id}/attachments",
        files={"file": ("service.log", b"node-a ERROR", "text/plain")},
        data={"kind": "log"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    second_upload = await client.post(
        f"/api/sessions/{first_id}/attachments",
        files={"file": ("service.log", b"node-b ERROR", "text/plain")},
        data={"kind": "log"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    other_session_upload = await client.post(
        f"/api/sessions/{second_id}/attachments",
        files={"file": ("service.log", b"other session", "text/plain")},
        data={"kind": "log"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert first_upload.status_code == 201, first_upload.text
    assert second_upload.status_code == 201, second_upload.text
    assert other_session_upload.status_code == 201, other_session_upload.text

    first_attachment = first_upload.json()
    second_attachment = second_upload.json()
    assert first_attachment["display_name"] == "service.log"
    assert second_attachment["display_name"] == "service.log"
    assert first_attachment["id"] != second_attachment["id"]
    assert Path(first_attachment["file_path"]).parent.name == first_id
    assert Path(other_session_upload.json()["file_path"]).parent.name == second_id
    manifest_path = Path(first_attachment["file_path"]).parent / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["session_id"] == first_id
    assert manifest["storage_dir"] == str(manifest_path.parent)
    manifest_rows = {row["id"]: row for row in manifest["attachments"]}
    assert manifest_rows[first_attachment["id"]]["original_filename"] == "service.log"
    assert manifest_rows[first_attachment["id"]]["display_name"] == "service.log"
    assert manifest_rows[first_attachment["id"]]["aliases"] == ["service.log"]
    assert manifest_rows[second_attachment["id"]]["original_filename"] == "service.log"
    assert manifest_rows[second_attachment["id"]]["display_name"] == "service.log"
    assert manifest_rows[second_attachment["id"]]["aliases"] == ["service.log"]

    forbidden_list = await client.get(
        f"/api/sessions/{first_id}/attachments",
        headers={"X-Subject-Id": "bob@dev-1"},
    )
    assert forbidden_list.status_code == 404

    listed = await client.get(
        f"/api/sessions/{first_id}/attachments",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert listed.status_code == 200, listed.text
    assert [row["display_name"] for row in listed.json()] == ["service.log", "service.log"]

    renamed = await client.patch(
        f"/api/sessions/{first_id}/attachments/{first_attachment['id']}",
        json={"display_name": "db-node-a.log"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["display_name"] == "db-node-a.log"
    assert renamed.json()["aliases"] == ["service.log", "db-node-a.log"]
    manifest_after_rename = json.loads(manifest_path.read_text())
    renamed_row = {row["id"]: row for row in manifest_after_rename["attachments"]}[
        first_attachment["id"]
    ]
    assert renamed_row["display_name"] == "db-node-a.log"
    assert renamed_row["original_filename"] == "service.log"
    assert renamed_row["aliases"] == [
        "service.log",
        "db-node-a.log",
    ]
    assert renamed_row["reference_names"] == [
        first_attachment["id"],
        "db-node-a.log",
        "service.log",
        "att_" + first_attachment["id"].removeprefix("att_") + ".log",
    ]

    described = await client.patch(
        f"/api/sessions/{first_id}/attachments/{first_attachment['id']}",
        json={"description": "数据库节点 A 的服务日志"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert described.status_code == 200, described.text
    assert described.json()["display_name"] == "db-node-a.log"
    assert described.json()["description"] == "数据库节点 A 的服务日志"
    assert described.json()["aliases"] == ["service.log", "db-node-a.log"]
    manifest_after_description = json.loads(manifest_path.read_text())
    described_row = {row["id"]: row for row in manifest_after_description["attachments"]}[
        first_attachment["id"]
    ]
    assert described_row["description"] == "数据库节点 A 的服务日志"

    deleted_path = Path(second_attachment["file_path"])
    deleted = await client.delete(
        f"/api/sessions/{first_id}/attachments/{second_attachment['id']}",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert deleted.status_code == 204, deleted.text
    assert not deleted_path.exists()
    manifest_after_delete = json.loads(manifest_path.read_text())
    assert [row["id"] for row in manifest_after_delete["attachments"]] == [first_attachment["id"]]

    after_delete = await client.get(
        f"/api/sessions/{first_id}/attachments",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert [row["display_name"] for row in after_delete.json()] == ["db-node-a.log"]

    other_session = await client.get(
        f"/api/sessions/{second_id}/attachments",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert [row["display_name"] for row in other_session.json()] == ["service.log"]


def _bootstrap_repo(root: Path) -> Path:
    root.mkdir(parents=True)
    subprocess.run(
        ["git", "init", "--initial-branch=main", str(root)],
        check=True,
        capture_output=True,
    )
    (root / "app.py").write_text(
        "def handle_payment(error: str) -> str:\n"
        "    if error == 'payment timeout':\n"
        "        return 'retry'\n"
        "    return 'fail'\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(root), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "-m", "init"],
        check=True,
        capture_output=True,
    )
    return root


async def _register_repo_and_wait_ready(client: AsyncClient, src: Path) -> str:
    response = await client.post(
        "/api/repos",
        json={"name": "code-tools-demo", "source": "local_dir", "local_path": str(src)},
    )
    assert response.status_code == 201, response.text
    repo_id = response.json()["id"]
    for _ in range(80):
        status_response = await client.get(f"/api/repos/{repo_id}")
        assert status_response.status_code == 200, status_response.text
        if status_response.json()["status"] == "ready":
            return repo_id
        await asyncio.sleep(0.25)
    raise AssertionError("repo never reached ready")


@pytest.mark.asyncio
async def test_delete_session_is_scoped_to_owner(client: AsyncClient) -> None:
    created = await client.post(
        "/api/sessions",
        json={"title": "待删除会话"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    forbidden = await client.delete(
        f"/api/sessions/{session_id}",
        headers={"X-Subject-Id": "bob@dev-1"},
    )
    assert forbidden.status_code == 404

    deleted = await client.delete(
        f"/api/sessions/{session_id}",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert deleted.status_code == 204

    deleted_again = await client.delete(
        f"/api/sessions/{session_id}",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert deleted_again.status_code == 204

    listed = await client.get(
        "/api/sessions",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert listed.status_code == 200
    assert all(row["id"] != session_id for row in listed.json())


@pytest.mark.asyncio
async def test_delete_session_removes_storage_dir_from_attachment_paths(
    app: FastAPI,
    client: AsyncClient,
    tmp_path: Path,
) -> None:
    created = await client.post(
        "/api/sessions",
        json={"title": "历史目录清理"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    uploaded = await client.post(
        f"/api/sessions/{session_id}/attachments",
        files={"file": ("service.log", b"node-a ERROR", "text/plain")},
        data={"kind": "log"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert uploaded.status_code == 201, uploaded.text
    storage_dir = Path(uploaded.json()["file_path"]).parent
    assert storage_dir.exists()

    app.state.settings.data_dir = tmp_path / "new-runtime-data-dir"

    deleted = await client.delete(
        f"/api/sessions/{session_id}",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert deleted.status_code == 204
    assert not storage_dir.exists()


@pytest.mark.asyncio
async def test_delete_session_removes_turns_traces_and_attachments(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    created = await client.post(
        "/api/sessions",
        json={"title": "带历史的会话"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    uploaded = await client.post(
        f"/api/sessions/{session_id}/attachments",
        files={"file": ("history.log", b"ERROR with history", "text/plain")},
        data={"kind": "log"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert uploaded.status_code == 201, uploaded.text
    storage_dir = Path(uploaded.json()["file_path"]).parent
    assert storage_dir.exists()

    async with app.state.session_factory() as db:
        db.add_all(
            [
                SessionTurn(
                    id="turn_delete_user",
                    session_id=session_id,
                    turn_index=0,
                    role="user",
                    content="告诉我小米病情的变化趋势",
                    evidence=None,
                ),
                SessionTurn(
                    id="turn_delete_agent",
                    session_id=session_id,
                    turn_index=1,
                    role="agent",
                    content="趋势需要结合病历时间线判断。",
                    evidence=None,
                ),
            ]
        )
        await db.flush()
        db.add(
            AgentTrace(
                id="trace_delete_1",
                session_id=session_id,
                turn_id="turn_delete_agent",
                stage="chat_runtime",
                event_type="retrieval_context",
                payload={"wiki_hits": [{"title": "小米病历"}]},
            )
        )
        db.add(
            SessionConversationSummary(
                session_id=session_id,
                summary="删除会话时也需要清理长期摘要。",
                covered_turn_index=1,
                covered_turn_count=2,
                covered_trace_count=1,
                consecutive_failures=0,
            )
        )
        await db.commit()

    deleted = await client.delete(
        f"/api/sessions/{session_id}",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert deleted.status_code == 204, deleted.text
    assert not storage_dir.exists()

    turns = await client.get(
        f"/api/sessions/{session_id}/turns",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert turns.status_code == 404

    async with app.state.session_factory() as db:
        summary = await db.get(SessionConversationSummary, session_id)
    assert summary is None


@pytest.mark.asyncio
async def test_update_pin_bulk_delete_and_generate_report_are_owner_scoped(
    app: FastAPI,
    client: AsyncClient,
    tmp_path: Path,
) -> None:
    created = await client.post(
        "/api/sessions",
        json={"title": "初始会话"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    forbidden_patch = await client.patch(
        f"/api/sessions/{session_id}",
        json={"title": "越权改名"},
        headers={"X-Subject-Id": "bob@dev-1"},
    )
    assert forbidden_patch.status_code == 404

    patched = await client.patch(
        f"/api/sessions/{session_id}",
        json={"title": "支付启动失败", "pinned": True},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["title"] == "支付启动失败"
    assert patched.json()["pinned"] is True

    feature = await client.post(
        "/api/features",
        json={"name": "Payment", "description": "payment feature"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert feature.status_code == 201, feature.text
    feature_id = feature.json()["id"]

    empty_report = await client.post(
        f"/api/sessions/{session_id}/reports",
        json={
            "feature_id": feature_id,
            "title": "支付启动失败定位报告",
            "body_markdown": "# 草稿",
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert empty_report.status_code == 400

    null_feature = await client.post(
        f"/api/sessions/{session_id}/reports",
        json={
            "feature_id": None,
            "title": "支付启动失败定位报告",
            "body_markdown": "# 草稿",
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert null_feature.status_code == 400

    async with app.state.session_factory() as db:
        db.add_all(
            [
                SessionTurn(
                    id="turn_report_user",
                    session_id=session_id,
                    turn_index=0,
                    role="user",
                    content="支付服务启动失败",
                    evidence=None,
                ),
                SessionTurn(
                    id="turn_report_agent",
                    session_id=session_id,
                    turn_index=1,
                    role="agent",
                    content="检查配置缺失。",
                    evidence=None,
                ),
            ]
        )
        await db.commit()

    report = await client.post(
        f"/api/sessions/{session_id}/reports",
        json={
            "feature_id": feature_id,
            "title": "支付启动失败定位报告",
            "body_markdown": "# 支付启动失败定位报告",
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert report.status_code == 201, report.text
    assert report.json()["title"] == "支付启动失败定位报告"
    assert report.json()["feature_id"] == feature_id
    assert report.json()["created_by_subject_id"] == "alice@dev-1"

    uploaded = await client.post(
        f"/api/sessions/{session_id}/attachments",
        files={"file": ("payment.log", b"payment ERROR", "text/plain")},
        data={"kind": "log"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert uploaded.status_code == 201, uploaded.text
    storage_dir = Path(uploaded.json()["file_path"]).parent
    assert storage_dir.exists()

    app.state.settings.data_dir = tmp_path / "bulk-new-runtime-data-dir"

    bulk_forbidden = await client.post(
        "/api/sessions/bulk-delete",
        json={"session_ids": [session_id]},
        headers={"X-Subject-Id": "bob@dev-1"},
    )
    assert bulk_forbidden.status_code == 200
    assert bulk_forbidden.json()["deleted_ids"] == []
    assert storage_dir.exists()

    bulk_deleted = await client.post(
        "/api/sessions/bulk-delete",
        json={"session_ids": [session_id]},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert bulk_deleted.status_code == 200
    assert bulk_deleted.json()["deleted_ids"] == [session_id]
    assert not storage_dir.exists()


@pytest.mark.asyncio
async def test_session_generated_report_with_code_evidence_can_be_verified(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    feature = await client.post(
        "/api/features",
        json={"name": "LLM 调用链", "description": "llm runtime"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert feature.status_code == 201, feature.text
    feature_id = feature.json()["id"]
    created = await client.post(
        "/api/sessions",
        json={"title": "LLM 调用链排查"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    code_evidence = {
        "items": [
            {
                "id": "ev_code_1",
                "type": "code",
                "summary": "LLMGateway passes base_url into the LiteLLM client",
                "data": {
                    "result": {
                        "data": {
                            "repo_id": "repo_codeask",
                            "commit_sha": "abc1234",
                            "path": "src/codeask/llm/gateway.py",
                        }
                    }
                },
            }
        ]
    }
    async with app.state.session_factory() as db:
        db.add_all(
            [
                SessionTurn(
                    id="turn_report_code_user",
                    session_id=session_id,
                    turn_index=0,
                    role="user",
                    content="LLM 配置如何进入 LiteLLM？",
                    evidence=code_evidence,
                ),
                SessionTurn(
                    id="turn_report_code_agent",
                    session_id=session_id,
                    turn_index=1,
                    role="agent",
                    content="结论：LLMGateway 读取配置并创建 LiteLLM client。",
                    evidence=None,
                ),
            ]
        )
        await db.commit()

    report = await client.post(
        f"/api/sessions/{session_id}/reports",
        json={
            "feature_id": feature_id,
            "title": "LLM 调用链定位报告",
            "body_markdown": "# LLM 调用链定位报告",
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert report.status_code == 201, report.text
    body = report.json()
    assert body["metadata_json"]["evidence"][0]["type"] == "code"
    assert body["metadata_json"]["evidence"][0]["source"]["commit_sha"] == "abc1234"

    verified = await client.post(
        f"/api/reports/{body['id']}/verify",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["status"] == "verified"


@pytest.mark.asyncio
async def test_legacy_session_report_backfills_metadata_before_verification(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    feature = await client.post(
        "/api/features",
        json={"name": "历史报告", "description": "legacy reports"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert feature.status_code == 201, feature.text
    feature_id = feature.json()["id"]
    created = await client.post(
        "/api/sessions",
        json={"title": "历史报告验证"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    async with app.state.session_factory() as db:
        db.add_all(
            [
                SessionTurn(
                    id="turn_legacy_report_user",
                    session_id=session_id,
                    turn_index=0,
                    role="user",
                    content="历史报告为什么验证失败？",
                    evidence={
                        "items": [
                            {
                                "id": "ev_code_legacy",
                                "type": "code",
                                "summary": (
                                    "ReportService can derive metadata from session evidence"
                                ),
                                "data": {
                                    "result": {
                                        "data": {
                                            "repo_id": "repo_codeask",
                                            "commit_sha": "def5678",
                                            "path": "src/codeask/wiki/reports.py",
                                        }
                                    }
                                },
                            }
                        ]
                    },
                ),
                SessionTurn(
                    id="turn_legacy_report_agent",
                    session_id=session_id,
                    turn_index=1,
                    role="agent",
                    content="结论：验证时应回填会话证据。",
                    evidence=None,
                ),
            ]
        )
        report = Report(
            feature_id=feature_id,
            title="历史稀疏 metadata 报告",
            body_markdown="# 历史稀疏 metadata 报告\n\n结论：验证时应回填会话证据。",
            metadata_json={"source": "session", "session_id": session_id},
            status="rejected",
            verified=False,
            created_by_subject_id="alice@dev-1",
        )
        db.add(report)
        await db.commit()
        report_id = report.id

    verified = await client.post(
        f"/api/reports/{report_id}/verify",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert verified.status_code == 200, verified.text
    body = verified.json()
    assert body["status"] == "verified"
    assert body["metadata_json"]["evidence"][0]["source"]["commit_sha"] == "def5678"
