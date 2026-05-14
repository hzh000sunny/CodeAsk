import pytest
from pydantic import BaseModel

from codeask.agent.chat_runtime.retrieval import LightweightRetrievalService
from codeask.agent.chat_runtime.runtime import ChatRuntime
from codeask.agent.chat_runtime.tool_contracts import ToolContext, ToolResult, ToolSpec
from codeask.agent.chat_runtime.tool_registry import ToolRegistry
from codeask.llm.types import LLMEvent, LLMMessage, ToolDef
from tests.mocks.mock_llm import ScriptedLLM


class _QueryInput(BaseModel):
    query: str


class _RepoQueryInput(BaseModel):
    query: str | None = None


@pytest.mark.asyncio
async def test_default_chat_runtime_tools_declare_runtime_contracts(app) -> None:  # type: ignore[no-untyped-def]
    registry = app.state.chat_runtime._tool_registry
    specs = {spec.name: spec for spec in registry.available_tools()}

    assert {
        "search_wiki",
        "read_wiki_node",
        "search_reports",
        "read_report",
        "list_session_attachments",
        "read_session_attachment",
        "list_code_repos",
        "search_code",
        "inspect_repo_tree",
        "list_code_paths",
        "read_code_file",
    } <= set(specs)
    expected_budgets = {
        "search_wiki": 8_000,
        "read_wiki_node": 14_000,
        "search_reports": 8_000,
        "read_report": 14_000,
        "list_session_attachments": 6_000,
        "read_session_attachment": 14_000,
        "list_code_repos": 6_000,
        "search_code": 12_000,
        "inspect_repo_tree": 6_000,
        "list_code_paths": 8_000,
        "read_code_file": 16_000,
    }
    for name, budget in expected_budgets.items():
        spec = specs[name]
        assert spec.read_only is True
        assert spec.concurrency_safe is True
        assert spec.requires_confirmation is False
        assert spec.requires_user_interaction is False
        assert spec.max_result_size_chars == budget


class _BudgetAwareLLM:
    def __init__(self, *, max_seen_message_chars: int, tool_rounds: int) -> None:
        self.max_seen_message_chars = max_seen_message_chars
        self.tool_rounds = tool_rounds
        self.calls: list[int] = []

    async def stream(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDef],
        max_tokens: int,
        temperature: float,
    ):
        size = sum(len(message.model_dump_json()) for message in messages)
        self.calls.append(size)
        assert size <= self.max_seen_message_chars
        if len(self.calls) <= self.tool_rounds:
            call_no = len(self.calls)
            yield LLMEvent(type="message_start", data={})
            yield LLMEvent(
                type="tool_call_done",
                data={
                    "id": f"call_{call_no}",
                    "name": "search_code",
                    "arguments": {"query": f"query_{call_no}"},
                },
            )
            yield LLMEvent(type="message_stop", data={"stop_reason": "tool_call"})
            return
        yield LLMEvent(type="message_start", data={})
        yield LLMEvent(type="text_delta", data={"delta": "已基于压缩后的工具摘要回答。"})
        yield LLMEvent(type="message_stop", data={"stop_reason": "end_turn"})


class _ContextOverflowThenAnswerLLM:
    def __init__(self) -> None:
        self.calls: list[int] = []

    async def stream(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDef],
        max_tokens: int,
        temperature: float,
    ):
        size = sum(len(message.model_dump_json()) for message in messages)
        self.calls.append(size)
        if len(self.calls) == 1:
            yield LLMEvent(type="message_start", data={})
            yield LLMEvent(
                type="tool_call_done",
                data={
                    "id": "call_1",
                    "name": "search_code",
                    "arguments": {"query": "claude"},
                },
            )
            yield LLMEvent(type="message_stop", data={"stop_reason": "tool_call"})
            return
        if len(self.calls) == 2:
            yield LLMEvent(
                type="error",
                data={
                    "error_code": "BadRequestError",
                    "message": "Input length 233250 exceeds the maximum length 202752",
                    "retryable": False,
                },
            )
            return
        yield LLMEvent(type="message_start", data={})
        yield LLMEvent(type="text_delta", data={"delta": "没有发现电子宠物功能。"})
        yield LLMEvent(type="message_stop", data={"stop_reason": "end_turn"})


@pytest.mark.asyncio
async def test_runtime_can_answer_without_tools() -> None:
    llm = ScriptedLLM([{"type": "assistant_text", "content": "这是普通回答。"}])
    runtime = ChatRuntime.for_test(llm=llm)

    events = [event async for event in runtime.run("sess_1", "turn_1", "这个配置是什么意思？")]

    assert any(event.type == "text_delta" for event in events)
    assert not any(event.type == "tool_call" for event in events)
    assert events[-1].type == "done"
    assert llm.calls[0]["max_tokens"] == 8192


@pytest.mark.asyncio
async def test_runtime_executes_tool_and_continues_model_loop() -> None:
    llm = ScriptedLLM(
        [
            {
                "type": "tool_call",
                "id": "call_1",
                "name": "search_wiki",
                "input": {"query": "小米"},
            },
            {"type": "assistant_text", "content": "根据 Wiki，小米体重下降，需要关注。"},
        ]
    )
    runtime = ChatRuntime.for_test(llm=llm, fake_tools={"search_wiki": "命中小米病历"})

    events = [event async for event in runtime.run("sess_1", "turn_1", "小米病情趋势？")]

    assert [event.type for event in events].count("tool_call") == 1
    assert [event.type for event in events].count("tool_result") == 1
    assert events[-1].type == "done"
    assert llm.calls[1]["messages"][-2]["role"] == "assistant"
    assert llm.calls[1]["messages"][-2]["content"][0]["type"] == "tool_call"
    assert llm.calls[1]["messages"][-1]["role"] == "tool"


@pytest.mark.asyncio
async def test_runtime_exposes_tool_validation_message_to_trace_and_model() -> None:
    registry = ToolRegistry()

    async def search_wiki(args: _QueryInput, ctx: ToolContext) -> ToolResult:
        return ToolResult.ok(tool="search_wiki", summary=f"query={args.query}", items=[])

    registry.register(
        ToolSpec(
            name="search_wiki",
            description="搜索 Wiki",
            input_model=_QueryInput,
            read_only=True,
            requires_confirmation=False,
        ),
        search_wiki,
    )
    llm = ScriptedLLM(
        [
            {
                "type": "tool_call",
                "id": "call_bad",
                "name": "search_wiki",
                "input": {},
            },
            {"type": "assistant_text", "content": "我会根据工具错误修正参数。"},
        ]
    )
    runtime = ChatRuntime(
        llm=llm,
        tool_registry=registry,
        retrieval_service=LightweightRetrievalService(),
    )

    events = [event async for event in runtime.run("sess_1", "turn_1", "查询主备重建 Wiki")]
    tool_result = next(event for event in events if event.type == "tool_result")

    assert tool_result.data.error_type == "invalid_input"
    assert tool_result.data.message
    assert "query" in tool_result.data.message
    tool_message = llm.calls[1]["messages"][-1]
    assert tool_message["role"] == "tool"
    assert "query" in str(tool_message["content"])


@pytest.mark.asyncio
async def test_runtime_turns_malformed_tool_arguments_into_actionable_tool_error() -> None:
    llm = ScriptedLLM(
        [
            {
                "type": "tool_call",
                "id": "call_bad_json",
                "name": "search_wiki",
                "input": {},
            },
            {"type": "assistant_text", "content": "我会重新按 schema 调用。"},
        ]
    )
    runtime = ChatRuntime.for_test(llm=llm, fake_tools={"search_wiki": "命中"})

    async def patched_stream(messages, tools, max_tokens, temperature):  # type: ignore[no-untyped-def]
        if len(llm.calls) == 0:
            llm.calls.append(
                {
                    "messages": [message.model_dump() for message in messages],
                    "tools": [tool.model_dump() for tool in tools],
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                }
            )
            yield LLMEvent(type="message_start", data={})
            yield LLMEvent(
                type="tool_call_done",
                data={
                    "id": "call_bad_json",
                    "name": "search_wiki",
                    "arguments": {},
                    "arguments_parse_error": "Expecting value",
                    "raw_arguments": '{"query":',
                },
            )
            yield LLMEvent(type="message_stop", data={"stop_reason": "tool_call"})
            return
        async for event in ScriptedLLM(
            [{"type": "assistant_text", "content": "我会重新按 schema 调用。"}]
        ).stream(messages, tools, max_tokens, temperature):
            yield event

    llm.stream = patched_stream  # type: ignore[method-assign]

    events = [event async for event in runtime.run("sess_1", "turn_1", "查询 Wiki")]
    tool_result = next(event for event in events if event.type == "tool_result")

    assert tool_result.data.error_type == "invalid_input"
    assert "工具参数不是合法 JSON" in str(tool_result.data.message)
    assert "raw_arguments" in str(tool_result.data.message)


@pytest.mark.asyncio
async def test_runtime_audits_model_input_with_tool_result_repo_items() -> None:
    registry = ToolRegistry()

    async def list_repos(args: BaseModel, ctx: ToolContext) -> ToolResult:
        return ToolResult.ok(
            tool="list_code_repos",
            summary="可用代码仓库 1 个",
            items=[
                {
                    "repo_id": "repo_anything_llm",
                    "name": "Manual continuity anything-llm 1778137237804",
                }
            ],
            version_info={"scope_source": "feature_scope", "feature_ids": [3]},
        )

    registry.register(
        ToolSpec(
            name="list_code_repos",
            description="fake repo listing",
            input_model=_RepoQueryInput,
            read_only=True,
            requires_confirmation=False,
        ),
        list_repos,
    )
    llm = ScriptedLLM(
        [
            {
                "type": "tool_call",
                "id": "call_repos",
                "name": "list_code_repos",
                "input": {"query": "anything-llm"},
            },
            {"type": "assistant_text", "content": "已经拿到仓库信息。"},
        ]
    )
    runtime = ChatRuntime(
        llm=llm,
        tool_registry=registry,
        retrieval_service=LightweightRetrievalService(),
    )

    events = [event async for event in runtime.run("sess_1", "turn_1", "查 AnythingLLM 代码")]

    llm_input_events = [event for event in events if event.type == "llm_input"]
    assert len(llm_input_events) == 2
    assert llm_input_events[1].data["recent_tool_results"] == [
        {
            "tool": "list_code_repos",
            "ok": True,
            "summary": "可用代码仓库 1 个",
            "items_count": 1,
            "repos": [
                {
                    "repo_id": "repo_anything_llm",
                    "repo_name": "Manual continuity anything-llm 1778137237804",
                }
            ],
            "version_info": {"scope_source": "feature_scope", "feature_ids": [3]},
        }
    ]
    tool_messages = [message for message in llm.calls[1]["messages"] if message["role"] == "tool"]
    assert "repo_anything_llm" in str(tool_messages)
    assert "Manual continuity anything-llm 1778137237804" in str(tool_messages)


@pytest.mark.asyncio
async def test_runtime_does_not_emit_keyword_based_code_investigation_constraint() -> None:
    llm = ScriptedLLM([{"type": "assistant_text", "content": "我会基于当前上下文回答。"}])
    runtime = ChatRuntime(
        llm=llm,
        tool_registry=ToolRegistry(),
        retrieval_service=LightweightRetrievalService(),
    )

    events = [
        event async for event in runtime.run("sess_1", "turn_1", "通过查阅代码，给我更详细的回答")
    ]

    actions = [event for event in events if event.type == "assistant_action"]
    assert len(llm.calls) == 1
    assert all(event.data.action not in {"代码证据要求", "回答约束"} for event in actions)


@pytest.mark.asyncio
async def test_runtime_tool_result_event_exposes_bounded_repo_item_preview() -> None:
    registry = ToolRegistry()

    async def list_repos(args: BaseModel, ctx: ToolContext) -> ToolResult:
        return ToolResult.ok(
            tool="list_code_repos",
            summary="可用代码仓库 1 个",
            items=[
                {
                    "repo_id": "repo_anything_llm",
                    "name": "Manual continuity anything-llm 1778137237804",
                    "status": "ready",
                }
            ],
            version_info={"scope_source": "feature_scope", "feature_ids": [3]},
        )

    registry.register(
        ToolSpec(
            name="list_code_repos",
            description="fake repo listing",
            input_model=_RepoQueryInput,
            read_only=True,
            requires_confirmation=False,
        ),
        list_repos,
    )
    llm = ScriptedLLM(
        [
            {
                "type": "tool_call",
                "id": "call_repos",
                "name": "list_code_repos",
                "input": {"query": "anything-llm"},
            },
            {"type": "assistant_text", "content": "已列出仓库。"},
        ]
    )
    runtime = ChatRuntime(
        llm=llm,
        tool_registry=registry,
        retrieval_service=LightweightRetrievalService(),
    )

    events = [event async for event in runtime.run("sess_1", "turn_1", "列出 AnythingLLM 仓库")]
    tool_result = next(event for event in events if event.type == "tool_result")

    assert tool_result.data.items_count == 1
    assert tool_result.data.items_preview == [
        {
            "repo_id": "repo_anything_llm",
            "repo_name": "Manual continuity anything-llm 1778137237804",
            "status": "ready",
        }
    ]


@pytest.mark.asyncio
async def test_runtime_injects_retrieval_context_into_model_messages() -> None:
    llm = ScriptedLLM([{"type": "assistant_text", "content": "我会先基于小米特性回答。"}])
    runtime = ChatRuntime(
        llm=llm,
        tool_registry=ToolRegistry(),
        retrieval_service=LightweightRetrievalService(
            feature_catalog=[
                {
                    "feature_id": 3,
                    "name": "小米",
                    "description": "小米病历和治疗记录",
                },
                {
                    "feature_id": 7,
                    "name": "Claude Code",
                    "description": "Claude Code 源码分析",
                },
            ],
            feature_knowledge_index=[
                {
                    "feature_id": 3,
                    "wiki_titles": ["小米病历"],
                    "wiki_paths": ["knowledge-base/小米病历"],
                    "report_titles": ["小米病情趋势报告"],
                    "keywords": ["小米", "体重", "肥大细胞瘤"],
                }
            ],
            feature_candidates=[
                {
                    "feature_id": 3,
                    "name": "小米",
                    "description": "小米病历和治疗记录",
                    "linked_repos": [{"repo_id": "repo_xiaomi", "name": "xiaomi-service"}],
                }
            ],
            wiki_hits=[
                {
                    "feature_id": 3,
                    "node_id": 150,
                    "document_id": 29,
                    "title": "小米病历",
                    "path": "knowledge-base/小米病历",
                    "heading_path": "基本情况",
                    "snippet": "体重下降，肥大细胞瘤治疗历史。",
                }
            ],
            report_hits=[
                {
                    "feature_id": 3,
                    "title": "小米病情趋势报告",
                    "status": "verified",
                }
            ],
            repo_candidates=[
                {
                    "repo_id": "repo_claude",
                    "name": "E2E claude-code 1778123017269",
                    "source": "local_dir",
                    "status": "ready",
                }
            ],
        ),
    )

    events = [event async for event in runtime.run("sess_1", "turn_1", "小米病情趋势？")]

    assert events[-1].type == "done"
    first_call_text = "\n".join(
        block["text"]
        for message in llm.calls[0]["messages"]
        for block in message["content"]
        if block["type"] == "text"
    )
    assert "【RAG候选上下文】" in first_call_text
    assert "【特性目录】" in first_call_text
    assert "feature_id=3" in first_call_text
    assert "feature_id=7" in first_call_text
    assert "Claude Code" in first_call_text
    assert "【特性知识索引】" in first_call_text
    assert "wiki_titles=小米病历" in first_call_text
    assert "keywords=小米、体重、肥大细胞瘤" in first_call_text
    assert "node_id=150" in first_call_text
    assert "document_id=29" in first_call_text
    assert "heading=基本情况" in first_call_text
    assert "xiaomi-service" in first_call_text
    assert "代码仓库候选" in first_call_text
    assert "repo_id=repo_claude" in first_call_text
    assert "E2E claude-code 1778123017269" in first_call_text
    assert "调用代码工具时，把你判断相关的 feature_id 填入 feature_ids" in first_call_text
    assert first_call_text.index("【RAG候选上下文】") < first_call_text.index("小米病情趋势？")


@pytest.mark.asyncio
async def test_runtime_prompt_prevents_false_code_inspection_claims() -> None:
    llm = ScriptedLLM([{"type": "assistant_text", "content": "我会如实说明代码工具使用情况。"}])
    runtime = ChatRuntime(
        llm=llm,
        tool_registry=ToolRegistry(),
        retrieval_service=LightweightRetrievalService(),
    )

    events = [
        event async for event in runtime.run("sess_1", "turn_1", "通过查阅代码，给我更详细的回答")
    ]

    assert events[-1].type == "done"
    system_text = "\n".join(
        block["text"]
        for message in llm.calls[0]["messages"]
        if message["role"] == "system"
        for block in message["content"]
        if block["type"] == "text"
    )
    assert "用户明确要求查阅代码或源码时，由你判断是否需要调用代码工具获取证据" in system_text
    assert "没有成功调用代码工具" in system_text
    assert "不能声称已经查阅代码、源码或仓库结构" in system_text
    assert "上一轮代码工具失败" in system_text
    assert "用户明确要求查阅代码或源码时，优先调用代码工具获取证据" not in system_text


@pytest.mark.asyncio
async def test_runtime_prompt_instructs_tool_argument_repair() -> None:
    llm = ScriptedLLM([{"type": "assistant_text", "content": "我会按工具 schema 调用。"}])
    runtime = ChatRuntime(
        llm=llm,
        tool_registry=ToolRegistry(),
        retrieval_service=LightweightRetrievalService(),
    )

    events = [event async for event in runtime.run("sess_1", "turn_1", "查询 Wiki")]

    assert events[-1].type == "done"
    system_text = "\n".join(
        block["text"]
        for message in llm.calls[0]["messages"]
        if message["role"] == "system"
        for block in message["content"]
        if block["type"] == "text"
    )
    assert "工具参数必须严格符合工具 schema" in system_text
    assert "arguments 必须是标准 JSON object" in system_text
    assert "不要把参数写成 Markdown、自然语言" in system_text
    assert "不完整 JSON" in system_text
    assert "工具参数校验失败" in system_text
    assert "不要重复提交同一组无效参数" in system_text


@pytest.mark.asyncio
async def test_runtime_limits_retrieval_context_before_model_messages() -> None:
    llm = ScriptedLLM([{"type": "assistant_text", "content": "我会基于候选摘要回答。"}])
    runtime = ChatRuntime(
        llm=llm,
        tool_registry=ToolRegistry(),
        retrieval_service=LightweightRetrievalService(
            feature_candidates=[
                {
                    "feature_id": index,
                    "name": f"特性 {index}",
                    "description": "d" * 500,
                }
                for index in range(12)
            ],
            wiki_hits=[
                {
                    "feature_id": 3,
                    "title": f"Wiki {index}",
                    "path": f"knowledge-base/wiki-{index}",
                    "snippet": f"snippet-{index}-" + "x" * 1000,
                }
                for index in range(12)
            ],
            report_hits=[
                {
                    "feature_id": 3,
                    "title": f"Report {index}",
                    "status": "verified",
                }
                for index in range(10)
            ],
            attachment_candidates=[
                {
                    "attachment_id": f"att_{index}",
                    "display_name": f"file-{index}.log",
                    "original_filename": f"raw-{index}.log",
                    "description": "a" * 500,
                }
                for index in range(10)
            ],
        ),
    )

    events = [event async for event in runtime.run("sess_1", "turn_1", "小米病情趋势？")]

    assert events[-1].type == "done"
    first_call_text = "\n".join(
        block["text"]
        for message in llm.calls[0]["messages"]
        for block in message["content"]
        if block["type"] == "text"
    )
    assert "特性 7" in first_call_text
    assert "特性 8" not in first_call_text
    assert "Wiki 7" in first_call_text
    assert "Wiki 8" not in first_call_text
    assert "Report 5" in first_call_text
    assert "Report 6" not in first_call_text
    assert "file-5.log" in first_call_text
    assert "file-6.log" not in first_call_text
    assert "x" * 400 not in first_call_text
    assert len(first_call_text) < 8_000


@pytest.mark.asyncio
async def test_runtime_injects_attachment_candidates_into_model_messages() -> None:
    llm = ScriptedLLM([{"type": "assistant_text", "content": "我会先看附件日志。"}])
    runtime = ChatRuntime(
        llm=llm,
        tool_registry=ToolRegistry(),
        retrieval_service=LightweightRetrievalService(
            attachment_candidates=[
                {
                    "attachment_id": "att_123",
                    "display_name": "db-node-a.log",
                    "original_filename": "service.log",
                    "description": "数据库节点 A 日志",
                    "aliases": ["service.log", "db-node-a.log"],
                    "reference_names": ["att_123", "db-node-a.log", "service.log"],
                    "kind": "log",
                    "size_bytes": 2048,
                }
            ],
        ),
    )

    events = [event async for event in runtime.run("sess_1", "turn_1", "请先看这个日志附件")]

    assert events[-1].type == "done"
    first_call_text = "\n".join(
        block["text"]
        for message in llm.calls[0]["messages"]
        for block in message["content"]
        if block["type"] == "text"
    )
    assert "【会话附件候选】" in first_call_text
    assert "db-node-a.log" in first_call_text
    assert "service.log" in first_call_text
    assert "数据库节点 A 日志" in first_call_text


@pytest.mark.asyncio
async def test_runtime_emits_tool_result_version_info_for_action_trace() -> None:
    registry = ToolRegistry()

    async def search(args: BaseModel, ctx: ToolContext) -> ToolResult:
        return ToolResult.ok(
            tool="search_code",
            summary="命中 1 个代码位置",
            items=[{"path": "src/buddy/CompanionSprite.tsx"}],
            version_info={
                "repo_id": "repo_claude_code",
                "scope_source": "feature_scope",
                "feature_ids": [3],
            },
        )

    registry.register(
        ToolSpec(
            name="search_code",
            description="fake search",
            input_model=_QueryInput,
            read_only=True,
            requires_confirmation=False,
        ),
        search,
    )
    llm = ScriptedLLM(
        [
            {
                "type": "tool_call",
                "id": "call_1",
                "name": "search_code",
                "input": {"query": "CompanionSprite"},
            },
            {"type": "assistant_text", "content": "找到了 CompanionSprite。"},
        ]
    )
    runtime = ChatRuntime(
        llm=llm,
        tool_registry=registry,
        retrieval_service=LightweightRetrievalService(),
    )

    events = [event async for event in runtime.run("sess_1", "turn_1", "查代码")]
    tool_result = next(event for event in events if event.type == "tool_result")

    assert tool_result.data.version_info["scope_source"] == "feature_scope"
    assert tool_result.data.version_info["feature_ids"] == [3]


@pytest.mark.asyncio
async def test_runtime_forces_final_answer_after_tool_round_limit() -> None:
    registry = ToolRegistry()

    async def search(args: BaseModel, ctx: ToolContext) -> ToolResult:
        return ToolResult.ok(
            tool="search_code",
            summary="命中 DataConnectorOption",
            items=[{"path": "frontend/src/components/DataConnectorOption/media/index.js"}],
        )

    registry.register(
        ToolSpec(
            name="search_code",
            description="fake search",
            input_model=_QueryInput,
            read_only=True,
            requires_confirmation=False,
        ),
        search,
    )
    llm = ScriptedLLM(
        [
            {
                "type": "tool_call",
                "id": "call_1",
                "name": "search_code",
                "input": {"query": "DataConnectorOption"},
            },
            {
                "type": "tool_call",
                "id": "call_2",
                "name": "search_code",
                "input": {"query": "DataConnectorOption"},
            },
            {
                "type": "assistant_text",
                "content": "入口在 frontend/src/components/DataConnectorOption/media/index.js。",
            },
        ]
    )
    runtime = ChatRuntime(
        llm=llm,
        tool_registry=registry,
        retrieval_service=LightweightRetrievalService(),
        max_tool_rounds=1,
    )

    events = [
        event async for event in runtime.run("sess_1", "turn_1", "DataConnectorOption 在哪？")
    ]

    assert events[-1].type == "done"
    assert not any(event.type == "error" for event in events)
    assert llm.calls[-1]["tools"] == []
    assert any(
        event.type == "text_delta"
        and "frontend/src/components/DataConnectorOption/media/index.js"
        in str(event.data.get("delta"))
        for event in events
    )


@pytest.mark.asyncio
async def test_runtime_compacts_accumulated_tool_context_before_model_call() -> None:
    registry = ToolRegistry()

    async def search(args: BaseModel, ctx: ToolContext) -> ToolResult:
        return ToolResult.ok(
            tool="search_code",
            summary=f"搜索 {getattr(args, 'query', '')} 返回大量候选",
            items=[
                {
                    "path": f"src/module_{index}.py",
                    "line": index,
                    "snippet": "x" * 700,
                }
                for index in range(12)
            ],
        )

    registry.register(
        ToolSpec(
            name="search_code",
            description="fake search",
            input_model=_QueryInput,
            read_only=True,
            requires_confirmation=False,
            max_result_size_chars=11_500,
        ),
        search,
    )
    llm = _BudgetAwareLLM(max_seen_message_chars=24_000, tool_rounds=6)
    runtime = ChatRuntime(
        llm=llm,
        tool_registry=registry,
        retrieval_service=LightweightRetrievalService(),
        max_tool_rounds=6,
        context_size_budget_chars=24_000,
    )

    events = [
        event
        async for event in runtime.run(
            "sess_1",
            "turn_1",
            "claude code里面有实现tui界面的电子宠物功能吗",
        )
    ]

    assert events[-1].type == "done"
    assert max(llm.calls) <= 24_000
    assert len(llm.calls) == 7


@pytest.mark.asyncio
async def test_runtime_retries_once_after_context_length_error_with_stricter_compaction() -> None:
    registry = ToolRegistry()

    async def search(args: BaseModel, ctx: ToolContext) -> ToolResult:
        return ToolResult.ok(
            tool="search_code",
            summary="宽泛搜索命中大量代码位置",
            items=[
                {
                    "path": f"src/module_{index}.py",
                    "line": index,
                    "snippet": "claude " * 500,
                }
                for index in range(10)
            ],
        )

    registry.register(
        ToolSpec(
            name="search_code",
            description="fake search",
            input_model=_QueryInput,
            read_only=True,
            requires_confirmation=False,
            max_result_size_chars=12_000,
        ),
        search,
    )
    llm = _ContextOverflowThenAnswerLLM()
    runtime = ChatRuntime(
        llm=llm,
        tool_registry=registry,
        retrieval_service=LightweightRetrievalService(),
        context_size_budget_chars=60_000,
    )

    events = [
        event
        async for event in runtime.run(
            "sess_1",
            "turn_1",
            "claude code里面有实现tui界面的电子宠物功能吗",
        )
    ]

    assert events[-1].type == "done"
    assert not any(event.type == "error" for event in events)
    assert len(llm.calls) == 3
    assert llm.calls[2] < llm.calls[1]
