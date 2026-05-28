import pytest
from fastapi import FastAPI
from httpx import AsyncClient

import codeask.sessions.messages as session_messages
from codeask.db.models import AgentTrace, SessionConversationSummary, SessionTurn
from codeask.llm.types import LLMEvent
from codeask.sessions.messages import summarize_tool_actions
from tests.mocks.mock_llm import MockLLMClient, text_message

pytestmark = pytest.mark.skip(
    reason=(
        "legacy native request-stream tests retained for reference; "
        "v1.0.5 request path is opencode-only"
    )
)


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

    mock = MockLLMClient(
        [
            [
                LLMEvent(type="message_start", data={}),
                LLMEvent(type="text_delta", data={"delta": "这是"}),
                LLMEvent(type="text_delta", data={"delta": "普通"}),
                LLMEvent(type="text_delta", data={"delta": "回答。"}),
                LLMEvent(type="message_stop", data={"stop_reason": "end_turn"}),
            ]
        ]
    )
    app.state.llm_gateway.client_factory.provider_clients["openai"] = lambda **_: mock

    response = await client.post(
        f"/api/sessions/{session_id}/messages",
        json={"content": "普通问题"},
        headers=headers,
    )

    assert response.status_code == 200
    assert "event: runtime_state" in response.text
    assert response.text.count('"update_reason":"assistant_delta"') >= 3
    assert '"update_reason":"assistant_final"' in response.text
    assert "event: retrieval_context" in response.text
    assert "event: text_delta" in response.text
    assert "event: scope_detection" not in response.text
    assert "范围判断" not in response.text
    assert "充分性判断" not in response.text

    traces = await client.get(f"/api/sessions/{session_id}/traces", headers=headers)
    assert traces.status_code == 200, traces.text
    trace_types = [item["event_type"] for item in traces.json()]
    assert "runtime_state" in trace_types
    assert "retrieval_context" in trace_types
    runtime_state_reasons = [
        item["payload"].get("update_reason")
        for item in traces.json()
        if item["event_type"] == "runtime_state"
    ]
    assert "assistant_final" in runtime_state_reasons
    assert "assistant_delta" not in runtime_state_reasons


@pytest.mark.asyncio
async def test_post_message_stream_streams_and_persists_llm_input_audit(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200
    config = await client.post(
        "/api/admin/llm-configs",
        json={
            "name": "default-audit",
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
    created = await client.post("/api/sessions", json={"title": "审计会话"}, headers=headers)
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    mock = MockLLMClient([text_message("这是普通回答。")])
    app.state.llm_gateway.client_factory.provider_clients["openai"] = lambda **_: mock

    response = await client.post(
        f"/api/sessions/{session_id}/messages",
        json={"content": "普通问题"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert "event: llm_input" in response.text

    traces = await client.get(f"/api/sessions/{session_id}/traces", headers=headers)
    assert traces.status_code == 200, traces.text
    llm_inputs = [item for item in traces.json() if item["event_type"] == "llm_input"]
    assert len(llm_inputs) == 1
    payload = llm_inputs[0]["payload"]
    assert payload["round"] == 1
    assert payload["messages_count"] >= 2
    assert payload["tools_count"] > 0
    assert payload["recent_tool_results"] == []


@pytest.mark.asyncio
async def test_post_message_stream_isolates_structured_reasoning(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200
    config = await client.post(
        "/api/admin/llm-configs",
        json={
            "name": "reasoning-default",
            "protocol": "openai",
            "base_url": None,
            "api_key": "sk-secret",
            "model_name": "gpt-test",
            "is_default": True,
        },
    )
    assert config.status_code == 201, config.text
    await client.post("/api/auth/logout")

    headers = {"X-Subject-Id": "alice@dev-1"}
    created = await client.post("/api/sessions", json={"title": "推理隔离"}, headers=headers)
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    mock = MockLLMClient(
        [
            [
                LLMEvent(type="message_start", data={}),
                LLMEvent(
                    type="reasoning_delta",
                    data={
                        "delta": "内部思考",
                        "field": "reasoning_content",
                        "redacted": False,
                    },
                ),
                LLMEvent(
                    type="reasoning_delta",
                    data={
                        "delta": "不应该落库",
                        "field": "reasoning_content",
                        "redacted": False,
                    },
                ),
                LLMEvent(type="text_delta", data={"delta": "正式回答。"}),
                LLMEvent(type="message_stop", data={"stop_reason": "end_turn"}),
            ]
        ]
    )
    app.state.llm_gateway.client_factory.provider_clients["openai"] = lambda **_: mock

    response = await client.post(
        f"/api/sessions/{session_id}/messages",
        json={"content": "普通问题"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert "event: reasoning_observed" in response.text
    assert "正式回答。" in response.text
    assert "内部思考不应该落库" not in response.text

    turns = await client.get(f"/api/sessions/{session_id}/turns", headers=headers)
    assert turns.status_code == 200, turns.text
    persisted_text = "\n".join(item["content"] for item in turns.json())
    assert "正式回答。" in persisted_text
    assert "内部思考不应该落库" not in persisted_text

    traces = await client.get(f"/api/sessions/{session_id}/traces", headers=headers)
    assert traces.status_code == 200, traces.text
    reasoning_traces = [
        item for item in traces.json() if item["event_type"] == "reasoning_observed"
    ]
    assert len(reasoning_traces) == 1
    assert reasoning_traces[0]["payload"]["field"] == "reasoning_content"
    assert reasoning_traces[0]["payload"]["length"] == 9
    assert reasoning_traces[0]["payload"]["chunks"] == 2
    assert "内部思考不应该落库" not in str(reasoning_traces)


@pytest.mark.asyncio
async def test_post_message_injects_previous_turns_and_tool_actions_into_llm_context(
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
    created = await client.post("/api/sessions", json={"title": "连续会话"}, headers=headers)
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    async with app.state.session_factory() as session:
        session.add_all(
            [
                SessionTurn(
                    id="turn_prev_user",
                    session_id=session_id,
                    turn_index=0,
                    role="user",
                    content="anything llm中，是怎么通过rag处理上传的资料的",
                    evidence=None,
                ),
                SessionTurn(
                    id="turn_prev_agent",
                    session_id=session_id,
                    turn_index=1,
                    role="agent",
                    content="AnythingLLM 会解析、切分、向量化上传资料，再按 workspace 检索。",
                    evidence=None,
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                AgentTrace(
                    id="tr_prev_call",
                    session_id=session_id,
                    turn_id="turn_prev_user",
                    stage="chat_runtime",
                    event_type="tool_call",
                    payload={
                        "tool_call_id": "call_prev",
                        "tool_name": "list_code_repos",
                        "arguments_summary": {"query": "anything llm"},
                    },
                ),
                AgentTrace(
                    id="tr_prev_result",
                    session_id=session_id,
                    turn_id="turn_prev_user",
                    stage="chat_runtime",
                    event_type="tool_result",
                    payload={
                        "tool_call_id": "call_prev",
                        "tool_name": "list_code_repos",
                        "ok": True,
                        "summary": "可用代码仓库 0 个",
                        "warnings": [],
                        "evidence_refs": [],
                        "truncated": False,
                    },
                ),
            ]
        )
        await session.commit()

    mock = MockLLMClient([text_message("上一轮调用了 list_code_repos，但没有读取源码文件。")])
    app.state.llm_gateway.client_factory.provider_clients["openai"] = lambda **_: mock

    response = await client.post(
        f"/api/sessions/{session_id}/messages",
        json={"content": "你刚刚的回答，有查询代码吗"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    messages = mock.calls[0]["messages"]
    text_by_role = [(message["role"], str(message["content"])) for message in messages]
    assert any(
        role == "user" and "anything llm中，是怎么通过rag处理上传的资料的" in text
        for role, text in text_by_role
    )
    assert any(
        role == "assistant" and "AnythingLLM 会解析、切分、向量化上传资料" in text
        for role, text in text_by_role
    )
    assert any(
        "上一轮工具行动摘要" in text and "list_code_repos" in text and "可用代码仓库 0 个" in text
        for _role, text in text_by_role
    )
    assert text_by_role[-1][0] == "user"
    assert "你刚刚的回答，有查询代码吗" in text_by_role[-1][1]
    assert sum("你刚刚的回答，有查询代码吗" in text for _role, text in text_by_role) == 1


@pytest.mark.asyncio
async def test_post_message_injects_persistent_conversation_summary(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200
    config = await client.post(
        "/api/admin/llm-configs",
        json={
            "name": "default-summary",
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
    created = await client.post("/api/sessions", json={"title": "长会话"}, headers=headers)
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    async with app.state.session_factory() as session:
        turns: list[SessionTurn] = []
        for index in range(16):
            turns.append(
                SessionTurn(
                    id=f"turn_long_{index}",
                    session_id=session_id,
                    turn_index=index,
                    role="user" if index % 2 == 0 else "agent",
                    content=f"历史内容 {index}，其中早期事实是用户上传过小米病历和检查报告。",
                    evidence=None,
                )
            )
        session.add_all(turns)
        await session.flush()
        session.add_all(
            [
                AgentTrace(
                    id="tr_summary_call",
                    session_id=session_id,
                    turn_id="turn_long_0",
                    stage="chat_runtime",
                    event_type="tool_call",
                    payload={
                        "tool_call_id": "call_summary",
                        "tool_name": "read_code_file",
                        "arguments_summary": {"path": "src/buddy/CompanionSprite.tsx"},
                    },
                ),
                AgentTrace(
                    id="tr_summary_result",
                    session_id=session_id,
                    turn_id="turn_long_0",
                    stage="chat_runtime",
                    event_type="tool_result",
                    payload={
                        "tool_call_id": "call_summary",
                        "tool_name": "read_code_file",
                        "ok": True,
                        "summary": "读取 src/buddy/CompanionSprite.tsx:1-20",
                    },
                ),
            ]
        )
        await session.commit()

    mock = MockLLMClient([text_message("我会结合较早摘要和最近上下文继续回答。")])
    app.state.llm_gateway.client_factory.provider_clients["openai"] = lambda **_: mock

    response = await client.post(
        f"/api/sessions/{session_id}/messages",
        json={"content": "继续说刚刚的问题"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    messages = mock.calls[0]["messages"]
    text_by_role = [(message["role"], str(message["content"])) for message in messages]
    summary_text = "\n".join(text for _role, text in text_by_role if "会话长期摘要" in text)
    assert "覆盖 turn_index <= 3" in summary_text
    assert "历史内容 0" in summary_text
    assert "read_code_file" in summary_text
    assert "源码读取：是" in summary_text
    assert any("历史内容 15" in text for _role, text in text_by_role)
    assert sum("继续说刚刚的问题" in text for _role, text in text_by_role) == 1

    async with app.state.session_factory() as session:
        summary = await session.get(SessionConversationSummary, session_id)
    assert summary is not None
    assert summary.covered_turn_index == 3
    assert summary.covered_turn_count == 4


@pytest.mark.asyncio
async def test_conversation_summary_failure_uses_existing_summary_and_increments_fuse(
    app: FastAPI,
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200
    config = await client.post(
        "/api/admin/llm-configs",
        json={
            "name": "default-summary-fuse",
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
    created = await client.post("/api/sessions", json={"title": "摘要失败"}, headers=headers)
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    async with app.state.session_factory() as session:
        session.add(
            SessionConversationSummary(
                session_id=session_id,
                summary="已有长期摘要：上一轮实际读取过 read_code_file。",
                covered_turn_index=0,
                covered_turn_count=1,
                covered_trace_count=1,
                consecutive_failures=2,
            )
        )
        session.add_all(
            [
                SessionTurn(
                    id=f"turn_fuse_{index}",
                    session_id=session_id,
                    turn_index=index,
                    role="user" if index % 2 == 0 else "agent",
                    content=f"历史内容 {index}",
                    evidence=None,
                )
                for index in range(16)
            ]
        )
        await session.commit()

    def boom(**_: object) -> str:
        raise RuntimeError("summary builder failed")

    monkeypatch.setattr(session_messages, "_build_extractive_conversation_summary", boom)
    mock = MockLLMClient([text_message("继续回答。")])
    app.state.llm_gateway.client_factory.provider_clients["openai"] = lambda **_: mock

    response = await client.post(
        f"/api/sessions/{session_id}/messages",
        json={"content": "刚刚是否查过代码？"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    messages = mock.calls[0]["messages"]
    assert any("已有长期摘要" in str(message["content"]) for message in messages)
    async with app.state.session_factory() as session:
        summary = await session.get(SessionConversationSummary, session_id)
    assert summary is not None
    assert summary.consecutive_failures == 3


def test_tool_action_summary_distinguishes_code_listing_search_and_file_read() -> None:
    rows = [
        AgentTrace(
            id="tr_list_call",
            session_id="sess_1",
            turn_id="turn_1",
            stage="chat_runtime",
            event_type="tool_call",
            payload={"tool_call_id": "call_list", "tool_name": "list_code_repos"},
        ),
        AgentTrace(
            id="tr_list_result",
            session_id="sess_1",
            turn_id="turn_1",
            stage="chat_runtime",
            event_type="tool_result",
            payload={
                "tool_call_id": "call_list",
                "tool_name": "list_code_repos",
                "ok": True,
                "summary": "可用代码仓库 1 个",
            },
        ),
        AgentTrace(
            id="tr_search_call",
            session_id="sess_1",
            turn_id="turn_1",
            stage="chat_runtime",
            event_type="tool_call",
            payload={"tool_call_id": "call_search", "tool_name": "search_code"},
        ),
        AgentTrace(
            id="tr_search_result",
            session_id="sess_1",
            turn_id="turn_1",
            stage="chat_runtime",
            event_type="tool_result",
            payload={
                "tool_call_id": "call_search",
                "tool_name": "search_code",
                "ok": True,
                "summary": "命中 2 个代码位置",
            },
        ),
        AgentTrace(
            id="tr_read_call",
            session_id="sess_1",
            turn_id="turn_1",
            stage="chat_runtime",
            event_type="tool_call",
            payload={"tool_call_id": "call_read", "tool_name": "read_code_file"},
        ),
        AgentTrace(
            id="tr_read_result",
            session_id="sess_1",
            turn_id="turn_1",
            stage="chat_runtime",
            event_type="tool_result",
            payload={
                "tool_call_id": "call_read",
                "tool_name": "read_code_file",
                "ok": True,
                "summary": "读取 src/index.ts:1-20",
            },
        ),
    ]

    summary = summarize_tool_actions(rows)

    assert summary is not None
    assert "list_code_repos：成功" in summary
    assert "search_code：成功" in summary
    assert "read_code_file：成功" in summary
    assert "list_code_repos：成功，结果：可用代码仓库 1 个，源码读取：否" in summary
    assert "search_code：成功，结果：命中 2 个代码位置，源码读取：否" in summary
    assert "read_code_file：成功，结果：读取 src/index.ts:1-20，源码读取：是" in summary
