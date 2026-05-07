# Agent Chat Runtime 实施计划

> **给 agent 执行者：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务执行本计划。步骤使用 checkbox（`- [ ]`）记录状态。

**目标：** 将 CodeAsk 默认会话从固定调查状态机迁移到正常聊天优先、RAG 增强、模型决定工具调用的 Agent Chat Runtime。

**架构：** 新增独立 `src/codeask/agent/chat_runtime/` 模块承载上下文组装、工具契约、工具执行器、运行时 loop、行动轨迹和审计；旧 `src/codeask/agent/stages/` 与 `AgentOrchestrator` 先保留为 legacy 兼容。前端新增 `frontend/src/components/session/action-trace/`，用真实 runtime 事件替代固定“调查进度”。

**技术栈：** Python 3.11+, FastAPI, SQLAlchemy async, Pydantic, pytest, uv, React, TypeScript, Vite, SSE。

**验收基线：** E2E 端到端测试是每个开发验收阶段的基本要求。涉及默认会话、Agent 工具、登录权限、刷新恢复或源码仓库检索的改动，必须在验收清单中记录对应浏览器 E2E 或 live E2E 通道、运行方式和执行结果。Agent runtime 改动还必须使用 spy LLM 断言实际发给模型的 `messages`，不能用前端历史展示或数据库 turns 替代模型上下文验收。项目级规则见 `../../DEVELOPMENT_ACCEPTANCE.md`。

---

## 当前实施状态

截至 2026-05-07：

- 任务 1-8 已完成：`chat_runtime` 基础模型、上下文、prompt、轻量召回、工具注册、工具执行器和第一批工具模块已落地并有单元测试。
- 任务 9 已完成：默认会话发送接口已切换到 `ChatRuntime`，旧 `AgentOrchestrator` 保留为 legacy 兼容。
- 任务 10 已完成：前端固定“调查进度”已替换为 `Agent 行动轨迹`，新增 `frontend/src/components/session/action-trace/` 组件模块。
- 任务 11 已完成：PRD、系统设计、验收清单和 v1.0 历史设计标注已补齐，已完成回归验证。
- 追加修复已完成：生产默认 `ChatToolRegistry` 接入只读代码工具，runtime 工具调用事件持久化为 `agent_traces`，达到工具轮次上限时改为关闭工具并生成最终回答。
- 已用前端真实 LLM 会话验证 `references/claude-code/claude-code` 和 `references/anything-llm` 两个源码仓库。
- 已新增基础问答评测库 `evals/basic_qa/cases/seed_001.jsonl`，覆盖 10 类 30 个通用模型能力问题。该评测只统计模型是否主动触发 Wiki/代码工具，允许不超过 10% 的少量偏差，不在运行时代码中加入关键字拦截或强制禁止工具。
- 已用管理员账号和真实 GLM-5.1 配置，在同一个会话 `sess_edf3fda647d77a83` 完成 30 题实测：工具触发偏差 0、错误 0。
- 已将 AnythingLLM 的 RAG 上传资料处理链路和 Claude Code 的长上下文压缩机制纳入 v1.0.2 设计，形成 `specs/rag-context-budget-lessons.md`。
- 已修复单个工具结果预算：超大 `ToolResult` 进入模型前会真实裁剪，避免再次出现 input length 超限。
- 已实现第一版 `compaction.py`：每轮调用模型前估算 active context，超过阈值才压缩旧工具结果；供应商返回 input length / prompt too long / context length 错误时，执行一次更严格的 reactive compact retry。
- 已修复连续会话后端上下文装配缺陷：同一会话第二轮追问时，模型会看到上一轮 user / assistant / tool action summary。该修复已有 API + spy LLM 测试覆盖，并已新增 `frontend/e2e/agent-conversation-continuity-live.spec.ts` 作为连续追问 live E2E 通道。
- 已完成真实浏览器 + GLM-5.1 连续会话验收：会话 `sess_096f8685b5997d38` 覆盖第一轮代码工具查询、第二轮追问是否查询代码、刷新后第三轮继续追问。
- 已补齐结构化 RAG 上下文注入：`retrieval_context` 每轮包含 `feature_catalog` 活跃特性目录和 `feature_knowledge_index` 特性知识索引，避免模型在没有直接命中特性名称时只能盲目搜索代码。
- 已明确后续外部 RAG 服务替换边界：外部服务应实现 `RetrievalService.retrieve(...)` 等价输出，保持 `feature_catalog`、`feature_knowledge_index`、`feature_candidates`、`wiki_hits`、`report_hits`、`attachment_candidates`、`repo_candidates` 结构稳定。

> 注意：本文保留原始 checklist 作为实施过程记录，已完成任务不逐条改写，以免丢失 TDD 执行轨迹。

---

## 0. 文件结构

后端新增：

```text
src/codeask/agent/chat_runtime/
├── __init__.py
├── compaction.py
├── context.py
├── events.py
├── loop.py
├── prompt.py
├── retrieval.py
├── runtime.py
├── tool_contracts.py
├── tool_executor.py
├── tool_registry.py
├── trace.py
└── tools/
    ├── __init__.py
    ├── attachments.py
    ├── code.py
    ├── live_code.py
    ├── policies.py
    ├── reports.py
    ├── report_actions.py
    ├── user_interaction.py
    └── wiki.py
```

说明：`compaction.py` 已完成 v1.0.2 第一版，负责 active context 估算、Claude Code 风格阈值、旧工具结果 micro-compact 和上下文超限后的 reactive compact retry。完整会话级 `conversation_summary`、历史 auto-compact 和手动 compact UI 仍是后续优化目标。

后端修改：

```text
src/codeask/api/sessions.py
src/codeask/sessions/messages.py
src/codeask/llm/types.py
src/codeask/app.py
```

测试新增：

```text
tests/unit/chat_runtime/
├── test_context_assembler.py
├── test_compaction.py
├── test_events.py
├── test_prompt.py
├── test_retrieval.py
├── test_tool_contracts.py
├── test_tool_executor.py
├── test_tool_registry.py
└── tools/
    ├── test_attachments.py
    ├── test_code.py
    ├── test_policies.py
    ├── test_reports.py
    ├── test_report_actions.py
    ├── test_user_interaction.py
    └── test_wiki.py

tests/integration/test_agent_chat_runtime.py
tests/integration/test_agent_chat_runtime_sse.py
tests/integration/test_basic_qa_baseline.py
```

评测新增：

```text
evals/basic_qa/
├── __init__.py
├── cases/seed_001.jsonl
└── score.py
```

Live E2E 新增：

```text
frontend/e2e/basic-model-qa-live.spec.ts
```

规格新增：

```text
docs/v1.0.2/specs/rag-context-budget-lessons.md
```

前端新增：

```text
frontend/src/components/session/action-trace/
├── ActionTracePanel.tsx
├── ActionTraceEvent.tsx
├── ClarificationEvent.tsx
├── EvidenceEvent.tsx
├── RetrievalEvent.tsx
├── ToolCallEvent.tsx
├── ToolResultEvent.tsx
└── action-trace-model.ts
```

前端修改：

```text
frontend/src/components/session/InvestigationPanel.tsx
frontend/src/components/session/SessionWorkspace.tsx
frontend/src/components/session/session-model.ts
frontend/src/components/session/useSessionMessageStream.ts
frontend/src/types/sse.ts
frontend/src/styles/globals.css
```

文档修改：

```text
../README.md
docs/v1.0/design/agent-runtime.md
docs/v1.0/design/frontend-workbench.md
docs/v1.0/design/wiki-search.md
```

## 任务 1: 定义 Runtime 事件和工具契约

**文件：**
- 新建：`src/codeask/agent/chat_runtime/__init__.py`
- 新建：`src/codeask/agent/chat_runtime/events.py`
- 新建：`src/codeask/agent/chat_runtime/tool_contracts.py`
- 测试：`tests/unit/chat_runtime/test_events.py`
- 测试：`tests/unit/chat_runtime/test_tool_contracts.py`

- [ ] **步骤 1：写事件模型测试**

```python
from codeask.agent.chat_runtime.events import (
    ChatRuntimeEvent,
    EvidenceRef,
    ToolResultEventData,
)


def test_tool_result_event_contains_audit_ready_fields() -> None:
    event = ChatRuntimeEvent(
        type="tool_result",
        data=ToolResultEventData(
            tool_call_id="call_1",
            tool_name="search_wiki",
            ok=True,
            summary="命中 2 篇 Wiki",
            evidence_refs=[EvidenceRef(type="wiki", title="小米病历", path="小米 / 知识库 / 小米病历")],
            warnings=[],
            truncated=False,
            raw_result_ref="tool_result_1",
        ),
    )

    payload = event.model_dump()
    assert payload["type"] == "tool_result"
    assert payload["data"]["tool_name"] == "search_wiki"
    assert payload["data"]["evidence_refs"][0]["type"] == "wiki"
```

- [ ] **步骤 2：写工具契约测试**

```python
from pydantic import BaseModel

from codeask.agent.chat_runtime.tool_contracts import (
    ToolContext,
    ToolErrorType,
    ToolSpec,
    ToolResult,
)


class SearchInput(BaseModel):
    query: str


def test_tool_spec_defaults_are_fail_closed() -> None:
    spec = ToolSpec(name="search_wiki", description="搜索 Wiki", input_model=SearchInput)

    assert spec.read_only is False
    assert spec.concurrency_safe is False
    assert spec.requires_confirmation is True
    assert spec.requires_user_interaction is False


def test_tool_result_error_is_model_actionable() -> None:
    result = ToolResult.error(
        tool="read_code_file",
        error_type=ToolErrorType.NEEDS_CLARIFICATION,
        message="无法确定仓库",
        suggested_user_question="你希望我查看哪个仓库？",
    )

    assert result.ok is False
    assert result.error_type == ToolErrorType.NEEDS_CLARIFICATION
    assert result.suggested_user_question == "你希望我查看哪个仓库？"
```

- [ ] **步骤 3：运行测试确认失败**

运行：

```bash
uv run pytest tests/unit/chat_runtime/test_events.py tests/unit/chat_runtime/test_tool_contracts.py -q
```

预期：import 失败，因为 `chat_runtime` 模块还不存在。

- [ ] **步骤 4：实现最小模型**

新建 `events.py`，包含以下 Pydantic 模型：

```text
ChatRuntimeEvent
RetrievalContextEventData
ToolCallEventData
ToolResultEventData
EvidenceEventData
ClarificationEventData
AssistantActionEventData
EvidenceRef
```

新建 `tool_contracts.py`，包含：

```text
ToolErrorType
ToolContext
ToolSpec
ToolCall
ToolResult
ToolHandler
```

`ToolSpec` 默认值：

```text
read_only = false
concurrency_safe = false
requires_confirmation = true
requires_user_interaction = false
max_result_size_chars = 12000
```

- [ ] **步骤 5：运行测试确认通过**

运行：

```bash
uv run pytest tests/unit/chat_runtime/test_events.py tests/unit/chat_runtime/test_tool_contracts.py -q
```

预期：全部测试通过.

- [ ] **步骤 6：提交**

```bash
git add src/codeask/agent/chat_runtime tests/unit/chat_runtime
git commit -m "feat(agent): add chat runtime contracts"
```

## 任务 2: 实现 ToolRegistry 和 ToolExecutor

**文件：**
- 新建：`src/codeask/agent/chat_runtime/tool_registry.py`
- 新建：`src/codeask/agent/chat_runtime/tool_executor.py`
- 测试：`tests/unit/chat_runtime/test_tool_registry.py`
- 测试：`tests/unit/chat_runtime/test_tool_executor.py`

- [ ] **步骤 1：写 registry 测试**

```python
from pydantic import BaseModel

from codeask.agent.chat_runtime.tool_contracts import ToolSpec
from codeask.agent.chat_runtime.tool_registry import ToolRegistry


class EmptyInput(BaseModel):
    pass


async def fake_handler(args, ctx):
    raise AssertionError("not called")


def test_registry_lists_only_enabled_tools() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(name="search_wiki", description="搜索 Wiki", input_model=EmptyInput, read_only=True, requires_confirmation=False),
        fake_handler,
    )
    registry.register(
        ToolSpec(name="write_wiki", description="写 Wiki", input_model=EmptyInput, enabled=False),
        fake_handler,
    )

    assert [tool.name for tool in registry.available_tools()] == ["search_wiki"]
```

- [ ] **步骤 2：写 executor 测试**

```python
from pydantic import BaseModel
import pytest

from codeask.agent.chat_runtime.tool_contracts import ToolContext, ToolResult, ToolSpec
from codeask.agent.chat_runtime.tool_executor import ToolExecutor
from codeask.agent.chat_runtime.tool_registry import ToolRegistry


class SearchInput(BaseModel):
    query: str


async def ok_handler(args: SearchInput, ctx: ToolContext) -> ToolResult:
    return ToolResult.ok(tool="search_wiki", summary=f"query={args.query}", items=[])


@pytest.mark.asyncio
async def test_executor_validates_schema_and_returns_structured_error() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(name="search_wiki", description="搜索 Wiki", input_model=SearchInput, read_only=True, requires_confirmation=False),
        ok_handler,
    )
    executor = ToolExecutor(registry)

    result = await executor.execute("search_wiki", {"query": 123}, ToolContext(session_id="sess_1", turn_id="turn_1"))

    assert result.ok is False
    assert result.error_type.value == "invalid_input"


@pytest.mark.asyncio
async def test_executor_runs_valid_tool() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(name="search_wiki", description="搜索 Wiki", input_model=SearchInput, read_only=True, requires_confirmation=False),
        ok_handler,
    )
    executor = ToolExecutor(registry)

    result = await executor.execute("search_wiki", {"query": "timeout"}, ToolContext(session_id="sess_1", turn_id="turn_1"))

    assert result.ok is True
    assert result.summary == "query=timeout"
```

- [ ] **步骤 3：运行测试确认失败**

运行：

```bash
uv run pytest tests/unit/chat_runtime/test_tool_registry.py tests/unit/chat_runtime/test_tool_executor.py -q
```

预期：import 失败.

- [ ] **步骤 4：实现 registry 和 executor**

`ToolRegistry` must support:

```text
register(spec, handler)
get(name)
available_tools()
tool_defs_for_llm()
```

`ToolExecutor.execute()` must perform:

```text
lookup
Pydantic input validation
confirmation guard
handler call
result size budget
exception to ToolResult.error
ChatRuntimeEvent 的 tool_call/tool_result 事件生成钩子
```

第一版可以串行执行工具。

- [ ] **步骤 5：运行测试确认通过**

运行：

```bash
uv run pytest tests/unit/chat_runtime/test_tool_registry.py tests/unit/chat_runtime/test_tool_executor.py -q
```

预期：全部测试通过.

- [ ] **步骤 6：提交**

```bash
git add src/codeask/agent/chat_runtime/tool_registry.py src/codeask/agent/chat_runtime/tool_executor.py tests/unit/chat_runtime
git commit -m "feat(agent): add chat runtime tool execution"
```

## 任务 3: 实现上下文组装和轻量召回

**文件：**
- 新建：`src/codeask/agent/chat_runtime/context.py`
- 新建：`src/codeask/agent/chat_runtime/retrieval.py`
- 新建：`src/codeask/agent/chat_runtime/prompt.py`
- 测试：`tests/unit/chat_runtime/test_context_assembler.py`
- 测试：`tests/unit/chat_runtime/test_retrieval.py`
- 测试：`tests/unit/chat_runtime/test_prompt.py`

- [ ] **步骤 1：写上下文组装测试**

```python
from codeask.agent.chat_runtime.context import ContextAssembler, SessionMessage


def test_context_assembler_keeps_recent_history_and_candidate_context() -> None:
    assembler = ContextAssembler(max_history_messages=2)
    context = assembler.assemble(
        user_message="小米最近病情趋势是什么？",
        history=[
            SessionMessage(role="user", content="第一轮"),
            SessionMessage(role="assistant", content="第一轮回答"),
            SessionMessage(role="user", content="第二轮"),
        ],
        retrieval_context={"wiki_hits": [{"title": "小米病历", "snippet": "体重下降"}]},
        attachments=[],
        explicit_constraints={},
    )

    assert "小米最近病情趋势是什么？" in context.current_user_message
    assert len(context.recent_history) == 2
    assert context.retrieval_context["wiki_hits"][0]["title"] == "小米病历"
```

- [ ] **步骤 2：写 prompt 策略测试**

```python
from codeask.agent.chat_runtime.prompt import build_system_prompt


def test_prompt_hides_legacy_stage_terms() -> None:
    prompt = build_system_prompt()

    assert "正常聊天优先" in prompt
    assert "ScopeDetection" not in prompt
    assert "SufficiencyJudgement" not in prompt
    assert "code_investigation" not in prompt
```

- [ ] **步骤 3：运行测试确认失败**

运行：

```bash
uv run pytest tests/unit/chat_runtime/test_context_assembler.py tests/unit/chat_runtime/test_retrieval.py tests/unit/chat_runtime/test_prompt.py -q
```

预期：import 失败.

- [ ] **步骤 4：实现 context/retrieval/prompt**

`retrieval.py` 第一版暴露：

```text
LightweightRetrievalService.retrieve(user_message, session_summary, attachments)
```

它只返回候选上下文：

```text
feature_candidates
wiki_hits
report_hits
```

It must not return:

```text
insufficient
next_step
scope_detection
```

- [ ] **步骤 5：运行测试确认通过**

运行：

```bash
uv run pytest tests/unit/chat_runtime/test_context_assembler.py tests/unit/chat_runtime/test_retrieval.py tests/unit/chat_runtime/test_prompt.py -q
```

预期：全部测试通过.

- [ ] **步骤 6：提交**

```bash
git add src/codeask/agent/chat_runtime/context.py src/codeask/agent/chat_runtime/retrieval.py src/codeask/agent/chat_runtime/prompt.py tests/unit/chat_runtime
git commit -m "feat(agent): add chat context assembly"
```

## 任务 4: 实现 Chat Runtime Loop 和 mock LLM 测试

**文件：**
- 新建：`src/codeask/agent/chat_runtime/loop.py`
- 新建：`src/codeask/agent/chat_runtime/runtime.py`
- 测试：`tests/integration/test_agent_chat_runtime.py`
- 修改：`tests/mocks/mock_llm.py`

- [ ] **步骤 1：写直接回答测试**

```python
import pytest

from codeask.agent.chat_runtime.runtime import ChatRuntime
from tests.mocks.mock_llm import ScriptedLLM


@pytest.mark.asyncio
async def test_runtime_can_answer_without_tools() -> None:
    llm = ScriptedLLM([{"type": "assistant_text", "content": "这是普通回答。"}])
    runtime = ChatRuntime.for_test(llm=llm)

    events = [event async for event in runtime.run("sess_1", "turn_1", "这个配置是什么意思？")]

    assert any(event.type == "text_delta" for event in events)
    assert not any(event.type == "tool_call" for event in events)
    assert events[-1].type == "done"
```

- [ ] **步骤 2：写工具调用测试**

```python
@pytest.mark.asyncio
async def test_runtime_executes_tool_and_continues_model_loop() -> None:
    llm = ScriptedLLM(
        [
            {"type": "tool_call", "id": "call_1", "name": "search_wiki", "input": {"query": "小米"}},
            {"type": "assistant_text", "content": "根据 Wiki，小米体重下降，需要关注。"},
        ]
    )
    runtime = ChatRuntime.for_test(llm=llm, fake_tools={"search_wiki": "命中小米病历"})

    events = [event async for event in runtime.run("sess_1", "turn_1", "小米病情趋势？")]

    assert [event.type for event in events].count("tool_call") == 1
    assert [event.type for event in events].count("tool_result") == 1
    assert events[-1].type == "done"
```

- [ ] **步骤 3：运行测试确认失败**

运行：

```bash
uv run pytest tests/integration/test_agent_chat_runtime.py -q
```

预期：import 失败 or missing `ScriptedLLM` behavior.

- [ ] **步骤 4：实现 loop**

Runtime loop 必须支持：

```text
assemble context
lightweight retrieval event
call model
stream text_delta
collect tool_call
execute tool_call
append tool_result to model context
continue until assistant final text or max_turns
emit done
```

Set `max_tool_rounds = 6` for v1.0.2 to avoid infinite loops.

- [ ] **步骤 5：运行测试确认通过**

运行：

```bash
uv run pytest tests/integration/test_agent_chat_runtime.py -q
```

预期：全部测试通过.

- [ ] **步骤 6：提交**

```bash
git add src/codeask/agent/chat_runtime tests/integration/test_agent_chat_runtime.py tests/mocks/mock_llm.py
git commit -m "feat(agent): add chat runtime loop"
```

## 任务 5: 接入 Wiki 和报告只读工具

**文件：**
- 新建：`src/codeask/agent/chat_runtime/tools/wiki.py`
- 新建：`src/codeask/agent/chat_runtime/tools/reports.py`
- 测试：`tests/unit/chat_runtime/tools/test_wiki.py`
- 测试：`tests/unit/chat_runtime/tools/test_reports.py`
- 修改：`src/codeask/agent/chat_runtime/tool_registry.py`

- [ ] **步骤 1：写 Wiki 工具测试**

```python
import pytest

from codeask.agent.chat_runtime.tool_contracts import ToolContext
from codeask.agent.chat_runtime.tools.wiki import build_wiki_tools


@pytest.mark.asyncio
async def test_search_wiki_returns_snippets_not_sufficiency() -> None:
    tools = build_wiki_tools(fake_search_results=[{"node_id": 10, "title": "小米病历", "snippet": "体重下降"}])
    result = await tools["search_wiki"].handler({"query": "小米", "limit": 5}, ToolContext(session_id="sess_1", turn_id="turn_1"))

    assert result.ok is True
    assert result.items[0]["title"] == "小米病历"
    assert "insufficient" not in result.model_dump_json()
```

- [ ] **步骤 2：写报告工具测试**

```python
@pytest.mark.asyncio
async def test_search_reports_prefers_verified_reports() -> None:
    tools = build_report_tools(fake_reports=[{"report_id": 1, "status": "verified", "title": "历史定位报告"}])
    result = await tools["search_reports"].handler({"query": "timeout", "limit": 3}, ToolContext(session_id="sess_1", turn_id="turn_1"))

    assert result.ok is True
    assert result.items[0]["status"] == "verified"
```

- [ ] **步骤 3：运行测试确认失败**

运行：

```bash
uv run pytest tests/unit/chat_runtime/tools/test_wiki.py tests/unit/chat_runtime/tools/test_reports.py -q
```

预期：import 失败.

- [ ] **步骤 4：实现 Wiki / 报告工具**

实现：

```text
search_wiki
read_wiki_node
search_reports
read_report
```

四个工具都必须：

- `read_only = true`
- `requires_confirmation = false`
- return evidence refs
- enforce `limit` or `max_chars`
- never return sufficiency judgement

- [ ] **步骤 5：运行测试确认通过**

运行：

```bash
uv run pytest tests/unit/chat_runtime/tools/test_wiki.py tests/unit/chat_runtime/tools/test_reports.py -q
```

预期：全部测试通过.

- [ ] **步骤 6：提交**

```bash
git add src/codeask/agent/chat_runtime/tools/wiki.py src/codeask/agent/chat_runtime/tools/reports.py tests/unit/chat_runtime/tools
git commit -m "feat(agent): add wiki and report tools"
```

## 任务 6: 接入会话附件只读工具

**文件：**
- 新建：`src/codeask/agent/chat_runtime/tools/attachments.py`
- 测试：`tests/unit/chat_runtime/tools/test_attachments.py`
- 修改：`src/codeask/agent/chat_runtime/tool_registry.py`

- [ ] **步骤 1：写附件隔离测试**

```python
import pytest

from codeask.agent.chat_runtime.tool_contracts import ToolContext
from codeask.agent.chat_runtime.tools.attachments import build_attachment_tools


@pytest.mark.asyncio
async def test_list_session_attachments_is_session_scoped() -> None:
    tools = build_attachment_tools(
        fake_attachments=[
            {"id": "att_1", "session_id": "sess_1", "display_name": "node1.log"},
            {"id": "att_2", "session_id": "sess_2", "display_name": "node2.log"},
        ]
    )
    result = await tools["list_session_attachments"].handler({}, ToolContext(session_id="sess_1", turn_id="turn_1"))

    assert [item["id"] for item in result.items] == ["att_1"]
```

- [ ] **步骤 2：写附件读取测试**

```python
@pytest.mark.asyncio
async def test_read_session_attachment_preserves_file_mapping() -> None:
    tools = build_attachment_tools(
        fake_attachments=[
            {
                "id": "att_1",
                "session_id": "sess_1",
                "display_name": "数据库节点 1",
                "original_filename": "server.log",
                "description": "客户说这是主节点日志",
                "content": "ERROR timeout",
            }
        ]
    )
    result = await tools["read_session_attachment"].handler({"attachment_id": "att_1", "query": "ERROR", "limit": 20}, ToolContext(session_id="sess_1", turn_id="turn_1"))

    assert result.ok is True
    assert result.items[0]["original_filename"] == "server.log"
    assert result.items[0]["display_name"] == "数据库节点 1"
```

- [ ] **步骤 3：运行测试确认失败**

运行：

```bash
uv run pytest tests/unit/chat_runtime/tools/test_attachments.py -q
```

预期：import 失败.

- [ ] **步骤 4：实现附件工具**

实现：

```text
list_session_attachments
read_session_attachment
```

附件结果必须包含：

```text
attachment_id
display_name
original_filename
description
size
created_at
```

- [ ] **步骤 5：运行测试确认通过**

运行：

```bash
uv run pytest tests/unit/chat_runtime/tools/test_attachments.py -q
```

预期：全部测试通过.

- [ ] **步骤 6：提交**

```bash
git add src/codeask/agent/chat_runtime/tools/attachments.py tests/unit/chat_runtime/tools/test_attachments.py
git commit -m "feat(agent): add session attachment tools"
```

## 任务 7: 接入代码只读工具和版本解析

**文件：**
- 新建：`src/codeask/agent/chat_runtime/tools/code.py`
- 测试：`tests/unit/chat_runtime/tools/test_code.py`
- 修改：`src/codeask/agent/chat_runtime/tool_registry.py`

- [ ] **步骤 1：写代码版本解析测试**

```python
from codeask.agent.chat_runtime.tools.code import resolve_code_scope


def test_resolve_code_scope_prefers_user_constraints() -> None:
    scope = resolve_code_scope(
        explicit_constraints={"repo_id": 7, "ref": "release-1.2.3"},
        candidate_feature_repos=[{"repo_id": 3, "default_ref": "main"}],
        global_repos=[{"repo_id": 1, "default_ref": "main"}],
    )

    assert scope.repo_id == 7
    assert scope.ref == "release-1.2.3"
    assert scope.status == "explicit"
```

- [ ] **步骤 2：写代码搜索工具测试**

```python
import pytest

from codeask.agent.chat_runtime.tool_contracts import ToolContext
from codeask.agent.chat_runtime.tools.code import build_code_tools


@pytest.mark.asyncio
async def test_search_code_returns_version_warning_for_default_ref() -> None:
    tools = build_code_tools(fake_matches=[{"path": "src/app.py", "line": 42, "snippet": "timeout"}])
    result = await tools["search_code"].handler({"query": "timeout", "case_insensitive": True, "limit": 20}, ToolContext(session_id="sess_1", turn_id="turn_1"))

    assert result.ok is True
    assert result.version_info is not None
    assert "默认" in result.version_info["warning"]
```

- [ ] **步骤 3：运行测试确认失败**

运行：

```bash
uv run pytest tests/unit/chat_runtime/tools/test_code.py -q
```

预期：import 失败.

- [ ] **步骤 4：实现代码工具**

实现：

```text
inspect_repo_tree
search_code
read_code_file
```

代码范围解析优先级：

```text
confirmed session features
explicit user repo
model-selected candidate features from Feature RAG Pack
union of selected feature linked repos
needs_feature_scope
```

代码工具不得直接从全局 ready 仓库池模糊检索源码。全局仓库池只用于管理员配置、特性关联和用户显式仓库解析；默认 Agent 代码检索必须由模型先选择相关特性，后端再校验这些特性关联仓库。用户明确要求通过某个仓库查询时，该仓库可作为本轮显式代码范围。

所有代码工具必须：

- be read-only
- exclude VCS directories
- support result limits
- return repo/ref/commit information
- warn when using default/current code

- [ ] **步骤 5：运行测试确认通过**

运行：

```bash
uv run pytest tests/unit/chat_runtime/tools/test_code.py -q tests/unit/test_ripgrep.py tests/unit/test_file_reader.py
```

预期：全部测试通过.

- [ ] **步骤 6：提交**

```bash
git add src/codeask/agent/chat_runtime/tools/code.py tests/unit/chat_runtime/tools/test_code.py
git commit -m "feat(agent): add read-only code tools"
```

## 任务 8: 接入 ask_user、分析策略和报告建议工具

**文件：**
- 新建：`src/codeask/agent/chat_runtime/tools/user_interaction.py`
- 新建：`src/codeask/agent/chat_runtime/tools/policies.py`
- 新建：`src/codeask/agent/chat_runtime/tools/report_actions.py`
- 测试：`tests/unit/chat_runtime/tools/test_user_interaction.py`
- 测试：`tests/unit/chat_runtime/tools/test_policies.py`
- 测试：`tests/unit/chat_runtime/tools/test_report_actions.py`

- [ ] **步骤 1：写 ask_user 暂停测试**

```python
import pytest

from codeask.agent.chat_runtime.tool_contracts import ToolContext
from codeask.agent.chat_runtime.tools.user_interaction import AskUserRequired, build_user_interaction_tools


@pytest.mark.asyncio
async def test_ask_user_raises_pause_signal() -> None:
    tools = build_user_interaction_tools()

    with pytest.raises(AskUserRequired) as exc:
        await tools["ask_user"].handler(
            {"question": "使用哪个分支？", "options": [{"label": "默认分支", "value": "default"}], "allow_free_text": True},
            ToolContext(session_id="sess_1", turn_id="turn_1"),
        )

    assert exc.value.question == "使用哪个分支？"
```

- [ ] **步骤 2：写报告建议测试**

```python
@pytest.mark.asyncio
async def test_propose_report_does_not_generate_report() -> None:
    tools = build_report_action_tools()
    result = await tools["propose_report"].handler({"reason": "已有现象和证据", "candidate_feature_ids": [3]}, ToolContext(session_id="sess_1", turn_id="turn_1"))

    assert result.ok is True
    assert result.items[0]["required_confirmation"] is True
```

- [ ] **步骤 3：运行测试确认失败**

运行：

```bash
uv run pytest tests/unit/chat_runtime/tools/test_user_interaction.py tests/unit/chat_runtime/tools/test_policies.py tests/unit/chat_runtime/tools/test_report_actions.py -q
```

预期：import 失败.

- [ ] **步骤 4：实现三个工具模块**

实现：

```text
ask_user
load_analysis_policy
propose_report
```

`ask_user` 需要生成 `needs_clarification` 事件并暂停 runtime。

`propose_report` must not create a report row. It only tells the UI the model suggests generating one.

- [ ] **步骤 5：运行测试确认通过**

运行：

```bash
uv run pytest tests/unit/chat_runtime/tools/test_user_interaction.py tests/unit/chat_runtime/tools/test_policies.py tests/unit/chat_runtime/tools/test_report_actions.py -q
```

预期：全部测试通过.

- [ ] **步骤 6：提交**

```bash
git add src/codeask/agent/chat_runtime/tools tests/unit/chat_runtime/tools
git commit -m "feat(agent): add interaction and policy tools"
```

## 任务 9: 将会话发送接口切换到新 Runtime

**文件：**
- 修改：`src/codeask/app.py`
- 修改：`src/codeask/sessions/messages.py`
- 修改：`src/codeask/api/sessions.py`
- 测试：`tests/integration/test_agent_chat_runtime_sse.py`
- 测试：`tests/integration/test_sessions_api.py`

- [ ] **步骤 1：写 SSE 集成测试**

```python
def test_post_message_stream_uses_chat_runtime(client):
    session = client.post("/api/sessions", json={"title": "测试会话"}).json()

    with client.stream("POST", f"/api/sessions/{session['id']}/messages", json={"content": "普通问题"}) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "event: retrieval_context" in body
    assert "范围判断" not in body
    assert "充分性判断" not in body
```

- [ ] **步骤 2：运行测试确认失败**

运行：

```bash
uv run pytest tests/integration/test_agent_chat_runtime_sse.py tests/integration/test_sessions_api.py -q
```

预期：新的 SSE 断言失败，因为旧 orchestrator 仍在输出 legacy stage 事件.

- [ ] **步骤 3：修改 session streaming 入口**

`stream_agent_response()` 默认调用新的 `ChatRuntime`。

保留一个私有 legacy helper：

```text
stream_legacy_orchestrator_response()
```

本任务不删除旧 `AgentOrchestrator`。

- [ ] **步骤 4：运行测试确认通过**

运行：

```bash
uv run pytest tests/integration/test_agent_chat_runtime_sse.py tests/integration/test_sessions_api.py tests/integration/test_orchestrator_sufficient.py tests/integration/test_orchestrator_insufficient.py -q
```

预期：新 runtime 测试通过；旧 orchestrator 测试通过 legacy 入口继续保持兼容.

- [ ] **步骤 5：提交**

```bash
git add src/codeask/app.py src/codeask/sessions/messages.py src/codeask/api/sessions.py tests/integration
git commit -m "feat(agent): route sessions through chat runtime"
```

## 任务 10: 前端 Action Trace 替换固定调查进度

**文件：**
- 新建：`frontend/src/components/session/action-trace/action-trace-model.ts`
- 新建：`frontend/src/components/session/action-trace/ActionTracePanel.tsx`
- 新建：`frontend/src/components/session/action-trace/ActionTraceEvent.tsx`
- 新建：`frontend/src/components/session/action-trace/RetrievalEvent.tsx`
- 新建：`frontend/src/components/session/action-trace/ToolCallEvent.tsx`
- 新建：`frontend/src/components/session/action-trace/ToolResultEvent.tsx`
- 新建：`frontend/src/components/session/action-trace/EvidenceEvent.tsx`
- 新建：`frontend/src/components/session/action-trace/ClarificationEvent.tsx`
- 修改：`frontend/src/components/session/InvestigationPanel.tsx`
- 修改：`frontend/src/components/session/useSessionMessageStream.ts`
- 修改：`frontend/src/components/session/session-model.ts`
- 修改：`frontend/src/types/sse.ts`
- 修改：`frontend/src/styles/globals.css`

- [ ] **步骤 1：定义前端事件类型**

Add TypeScript types for:

```text
RetrievalContextEvent
ToolCallEvent
ToolResultEvent
EvidenceEvent
ClarificationEvent
AssistantActionEvent
```

- [ ] **步骤 2：修改 SSE parser**

Map new SSE events:

```text
retrieval_context
tool_call
tool_result
evidence
needs_clarification
assistant_action
```

转换为 `RuntimeInsight` 或新的 `ActionTraceEvent` 模型。

- [ ] **步骤 3：新建 ActionTracePanel**

Render:

- candidate context as compact chips
- tool calls as collapsible rows
- tool results with success/failure state
- evidence refs as readable source rows
- clarification as a user-facing question card

不要渲染 legacy 词汇：

```text
范围判断
充分性判断
insufficient
下一步
```

- [ ] **步骤 4：替换 InvestigationPanel 内部进度列表**

保留附件区域，把 stage list 和 runtime event list 替换为 `ActionTracePanel`。

- [ ] **步骤 5：前端构建验证**

运行：

```bash
cd frontend && npm run build
```

预期：构建成功.

- [ ] **步骤 6：手动验收**

Start dev servers on `0.0.0.0`, send a normal question, verify:

- 右侧面板标题是 Agent 行动轨迹
- 不再出现固定 stage list
- 普通回答不会展示 code investigation
- Wiki/tool 事件只在实际使用时出现
- 工具失败会显示为清晰的失败事件

- [ ] **步骤 7：提交**

```bash
git add frontend/src/components/session frontend/src/types/sse.ts frontend/src/styles/globals.css
git commit -m "feat(frontend): show agent action trace"
```

## 任务 11: 回归测试和文档更新

**文件：**
- 修改：`../README.md`
- 新建：`../prd/agent-chat.md`
- 新建：`../design/agent-chat-runtime.md`
- 新建：`acceptance-checklist.md`
- 修改：`docs/v1.0/design/agent-runtime.md`
- 修改：`docs/v1.0/design/frontend-workbench.md`
- 修改：`docs/v1.0/design/wiki-search.md`

- [ ] **步骤 1：写验收清单**

新建 `acceptance-checklist.md`，包含以下必验项：

```text
普通问答不会触发旧固定链路
Wiki 足够回答时不会默认查代码
代码读取只在模型需要时发生
仓库/版本不明确时会追问或标注默认版本
候选特性不强制绑定会话
报告生成仍需用户确认
行动轨迹只展示真实事件
旧 Wiki 工作台功能回归通过
```

- [ ] **步骤 2：更新正式 PRD 和设计文档**

把 specs 中已确认的产品契约和系统设计分别整理到：

```text
../prd/agent-chat.md
../design/agent-chat-runtime.md
```

Specs 目录保留为过程记录。

- [ ] **步骤 3：标注 v1.0 历史设计**

在 v1.0 文档中增加说明：

```text
v1.0.2 起，默认会话迁移到统一 Tool-Calling Chat Runtime；本文件中的固定状态机是 v1.0 历史设计。
```

- [ ] **步骤 4：运行后端测试**

运行：

```bash
uv run pytest tests/unit tests/integration -q
```

预期：全部测试通过.

- [ ] **步骤 5：运行前端构建**

运行：

```bash
cd frontend && npm run build
```

预期：构建成功.

- [ ] **步骤 6：提交**

```bash
git add docs tests src frontend
git commit -m "docs: document v1.0.2 agent runtime"
```

## 任务 12: 会话级 Auto Compact 与 Conversation Summary

> 状态：已完成第一轮实现与自动化验证。剩余可选增强：详情字段复制入口、独立 abort API、partial tool result 的 aborted 审计状态。
> 定位：这是 `compaction.py` 第一版之后的第二层上下文能力，不能和已完成的旧工具结果 micro-compact 混淆。第一版解决“单轮 active context 被累计工具结果打爆”；本任务解决“长会话长期运行后仍能保持语义连续”。

**目标：** 参考 Claude Code 的 auto compact 机制，为 CodeAsk 增加持久化 `conversation_summary`、历史 auto-compact、summary + recent turns 的 active context builder、失败熔断和 live E2E 验收。

**非目标：**

- 不实现 Claude Code 级别 prompt cache editing。
- 不实现手动 compact UI，除非单独确认。
- 不删除原始 turns、traces、attachments 或工具审计结果。
- 不用关键词规则强行改变模型是否调用 Wiki / 代码工具。

**后端建议文件：**

```text
src/codeask/agent/chat_runtime/
├── compaction.py              # 扩展会话级阈值和 auto compact 判定
├── summary.py                 # conversation_summary 生成 prompt 和解析
├── active_context.py          # summary + recent turns + retrieval + current user message
└── context.py                 # 接入 summary 后的上下文装配

src/codeask/sessions/
└── summaries.py               # summary 持久化读写服务

src/codeask/db/models/
└── session_summary.py         # 如果不复用现有表，新增 summary model
```

**测试建议文件：**

```text
tests/unit/chat_runtime/test_summary.py
tests/unit/chat_runtime/test_active_context.py
tests/integration/test_agent_chat_runtime_compaction.py
frontend/e2e/agent-long-context-live.spec.ts
```

- [ ] **步骤 1：设计并落地 summary 数据模型**

最低字段：

```text
session_id
summary_text
covered_turn_start_index
covered_turn_end_index
covered_trace_ids
evidence_refs
tool_action_facts
unresolved_questions
repo_version_context
created_at
updated_at
status
```

验收：

- summary 只表示 active context 的压缩投影，不替代原始 turns 和 traces。
- 删除会话时 summary 一起删除。
- 刷新页面后后端能重新加载 summary。
- summary 能标识覆盖了哪些 turns / traces，避免重复摘要或漏摘要。

- [ ] **步骤 2：设计 summary prompt**

摘要必须保留：

```text
当前用户目标
已确认事实
已上传附件
已检索 Wiki / 报告 / 代码
是否实际读取源码文件
工具失败和失败原因
证据来源
仓库 / 分支 / commit 状态
未解决问题
用户偏好和约束
事实 / 推断 / 未确认信息的边界
```

验收：

- 不能把 `search_code` 误写成 `read_code_file`。
- 不能把 0 命中写成已找到证据。
- 不能把默认 HEAD 写成用户已确认版本。
- 用户追问“刚刚是否查过代码”时，summary 中必须有足够信息回答。

- [ ] **步骤 3：实现 active context builder**

每轮模型输入应由以下内容构成：

```text
system prompt
+ conversation_summary（如果存在）
+ recent turns（默认最近 N 条）
+ 上一轮 tool action summary
+ retrieval_context 候选证据
+ current user message
```

验收：

- 当前 user message 只出现一次。
- summary 和 recent turns 的覆盖范围不能重复到造成大量上下文浪费。
- 前端历史恢复不能作为模型上下文恢复的替代验收；必须用 spy LLM 断言实际 messages。

- [ ] **步骤 4：实现 auto compact 触发策略**

参考 Claude Code：

```text
每轮调用模型前估算 active context
if size >= auto_compact_threshold:
    生成或更新 conversation_summary
    使用 summary + recent turns 重建 active context
if provider prompt-too-long:
    reactive compact once
```

验收：

- 低于阈值不触发 summary。
- 超过阈值触发 summary。
- summary 后 active context 必须小于阈值。
- 如果 summary 生成失败，不应无限重试。

- [ ] **步骤 5：实现失败熔断**

参考 Claude Code 的 consecutive failures 思路：

```text
MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3
```

验收：

- 连续 compact 失败 3 次后停止自动重试。
- 停止重试时给出明确错误，不继续消耗 LLM 调用。
- 后续新 turn 可以根据状态决定是否再次尝试，而不是在同一轮死循环。

- [ ] **步骤 6：补充自动化测试**

必须覆盖：

```text
长历史触发 summary
低于阈值不触发 summary
summary 后继续问答
summary 后追问上一轮工具行为
summary 后区分 list_code_repos / search_code / read_code_file
summary 后刷新继续问答
provider prompt-too-long 后 reactive compact
compact 失败熔断
删除会话清理 summary
```

- [ ] **步骤 7：补充 live E2E**

使用真实前端、真实后端、管理员账号和真实 LLM，至少覆盖：

```text
基础问答
仓库检索
源码读取
追问是否查代码
刷新继续追问
长上下文触发 compact
compact 后继续回答
```

建议用 `references/anything-llm` 和 `references/claude-code/claude-code` 作为参考仓库。

- [ ] **步骤 8：更新文档**

需要同步更新：

```text
docs/v1.0.2/design/agent-chat-runtime.md
docs/v1.0.2/specs/rag-context-budget-lessons.md
docs/v1.0.2/plans/acceptance-checklist.md
docs/v1.0.2/README.md
docs/DEVELOPMENT_ACCEPTANCE.md（如新增项目级验收规则）
```

## 任务 13: 代码检索工具通用能力增强与反特判约束

> 状态：进行中。代码检索工具的一部分通用能力已落地，后续所有工具优化必须同步遵守 `design/agent-chat-runtime.md` 的“工具优化安全边界”和 `plans/acceptance-checklist.md` 的“工具优化质量门禁”。
> 定位：提升模型主导代码检索的可靠性，但禁止在工具层加入业务语义特判。工具只提供通用观察能力、输入校验和结果治理；“查什么、如何扩展同义词、何时下结论”仍由模型基于 prompt 和上下文决定。

**背景问题：**

用户询问：

```text
claude code里面有实现tui界面的电子宠物功能吗
```

第一次模型用 `pet / tamagotchi / virtual pet / TUI component` 等关键词搜索 0 命中后，过早回答“没有实现”。用户纠正后，模型改用 `buddy / companion` 才找到 `src/buddy/CompanionSprite.tsx` 等实现。

这暴露的问题不是要回到后端固定流程，而是：

```text
模型仍然决策
+ 工具提供更好的通用观察能力
+ prompt 提供更严格的检索策略和证据门槛
+ 测试验证不能仅凭 0 命中下强否定结论
```

**工具层反特判原则：**

工具层只允许提供通用、可组合、可解释的能力；不得根据用户自然语言、仓库名称、领域词或测试样例做业务语义映射。

这条原则不只适用于代码检索。后续 Wiki、报告、附件、外部 RAG adapter、会话行动轨迹和上下文压缩相关优化，都必须遵守同一条边界：

```text
工具只做执行质量、边界校验、结果结构化、预算控制、错误可解释。
工具不做业务判断。
```

允许提升工具质量，但不能把模型该做的推理写进工具层。工具优化要解决的是“模型拿不到足够可执行事实”“错误不可恢复”“结果太大打爆上下文”“行动轨迹不可审计”等工程问题，不是通过后端硬编码把某个自然语言问题映射成固定证据。

允许：

```text
inspect_repo_tree(repo, path, depth, limit)
list_code_paths(repo, path_query, limit)
search_code(mode=literal|regex|any_terms|all_terms)
read_code_file 的路径校验
query 为空、过短、过宽泛时返回 invalid_input
搜索结果按文件聚合、去重、预算裁剪
返回“结果已截断，建议缩小 query/path”的通用提示
```

禁止：

```text
if "电子宠物" in question: search("buddy")
if query in ["pet", "tamagotchi"]: also_search("companion")
if repo_name == "claude-code": return src/buddy/CompanionSprite.tsx
if "sqlite" in question: read("server/prisma/schema.prisma")
if "RAG" in question: search("contextTexts")
为了某个测试样例返回固定路径
工具根据用户自然语言自动补业务同义词
工具绕过模型自行决定下一步调查路线
```

每次工具优化必须同时给出两类验收：

- 正向验收：证明工具的通用执行质量确实提升，例如返回可执行引用、错误类型更清晰、结果受预算控制、0 命中后有通用恢复提示。
- 反向验收：证明工具没有为测试样例、业务词、仓库名、路径名加入 hardcode，例如不能把 `电子宠物`、`sqlite`、`RAG`、`AnythingLLM` 直接映射成固定搜索词或固定文件。

- [ ] **步骤 1：新增生产目录树工具**

建议工具：

```text
inspect_repo_tree(repo_id|repo_name, path="", depth=2, limit=200, ref?)
```

验收：

- 能列出指定目录下的子目录和文件。
- 输出受 `limit` 和预算控制。
- 默认 HEAD 时保留版本不确定 warning。
- 不根据用户问题做任何路径或关键词补全。
- 对不存在路径返回 `not_found`，对文件路径请求目录树返回 `invalid_input` 或明确错误。

- [ ] **步骤 2：新增路径 / 文件名搜索工具**

建议工具：

```text
list_code_paths(repo_id|repo_name, path_query, path_prefix?, limit=100, ref?)
```

验收：

- 只按路径 / 文件名做通用匹配。
- 不做“中文业务词 -> 英文产品命名”的内置映射。
- 支持大小写不敏感匹配。
- 输出按路径去重并受预算控制。

- [ ] **步骤 3：增强 `search_code` 搜索模式**

建议增加：

```text
mode = literal | regex | any_terms | all_terms
```

验收：

- `literal` 保持当前精确文本搜索语义。
- `regex` 明确使用正则语义。
- `any_terms` / `all_terms` 只基于用户或模型传入 terms 做通用组合，不自动补业务词。
- `query="*"`、空 query、过短 query 返回结构化 `invalid_input`，不能返回 `internal_error`。
- 宽泛命中时返回文件聚合摘要和截断提示，不能把大量 snippets 直接塞进模型上下文。

- [ ] **步骤 4：补充 prompt 检索策略**

prompt 可以指导模型如何使用工具，但不能把领域词映射写到工具里。

需要加入：

```text
当用户询问某功能是否存在时：
- 0 命中只代表当前关键词未找到，不能直接证明功能不存在。
- 强否定结论需要更高证据门槛。
- 如果尚未检查目录结构、路径名、命令入口、状态字段、UI 组件、feature flag 或同义命名，不要直接说没有实现。
- 搜索用户原词后，应由模型自行选择英文同义词、产品化命名或入口名继续检索。
- 找到候选文件后，应读取关键文件再给强结论。
```

- [ ] **步骤 5：建立负结论证据门槛**

验收表达：

```text
弱否定：当前关键词未找到相关证据，不能排除使用其他命名实现。
强否定：已检查目录结构、路径名、入口注册、状态字段、UI 组件和相关同义命名，未发现实现。
```

模型不能仅凭若干次 `search_code` 0 命中输出强否定结论。

- [ ] **步骤 6：新增回归测试**

测试用例：

```text
用户：claude code里面有实现tui界面的电子宠物功能吗
仓库：references/claude-code/claude-code
期望：
- 不允许仅凭 pet / tamagotchi 0 命中直接回答没有；
- 应能通过目录、路径或模型自行扩展命名发现 src/buddy/ 或 CompanionSprite.tsx；
- 回答中说明实现命名是 buddy / companion；
- 如果未找到，也必须表达为证据不足，而不是确定没有。
```

测试约束：

- 测试不能依赖工具层 hardcode `电子宠物 -> buddy`。
- 可以使用 spy tool 断言模型是否获得目录 / 路径搜索能力。
- live E2E 可以使用真实 `references/claude-code/claude-code` 仓库验证。

- [ ] **步骤 7：文档同步**

需要同步更新：

```text
docs/v1.0.2/design/agent-chat-runtime.md
docs/v1.0.2/plans/acceptance-checklist.md
docs/v1.0.2/specs/agent-tools-from-claude-code.md
docs/v1.0.2/specs/agent-runtime-source-lessons.md
```

## 任务 14: Agent 行动轨迹、生成中断与输入快捷键

> 状态：未开始。
> 定位：修正前端会话体验，使 `Agent 行动轨迹` 从“单轮进度”升级为“会话级行动时间线”，并补齐生成中断、回滚和输入快捷键。

**背景问题：**

当前发送新消息时，右侧 `Agent 行动轨迹` 会清空并从本轮事件重新开始。这符合旧“单轮调查进度”的实现习惯，但不符合 v1.0.2 的会话级 Agent 行动轨迹定位。

目标行为：

```text
同一会话内：
历史行动轨迹保留
+ 当前 turn 流式追加
+ 按 turn 分组
+ 最近 turn 默认展开，历史 turn 可折叠

切换会话：
加载目标会话自己的 traces

删除会话：
清空右侧行动轨迹
```

### 14.1 行动轨迹保留与分组

- [x] 同一会话发送新消息时，不清空历史 `agent_traces`。
- [x] 新 SSE 事件只追加到当前 turn 分组；流式过程中先进入本轮临时分组，收到 `done.turn_id` 后归档到真实 turn。
- [x] 历史 turn 默认可折叠，最近 turn 默认展开。
- [x] 每个 turn 分组显示摘要：
  - 工具调用数量；
  - 失败数量；
  - 证据数量；
  - 是否读取代码文件；
  - 是否有 warnings。
- [x] 页面刷新后从 `/api/sessions/{session_id}/traces` 恢复完整行动轨迹分组。
- [x] 切换会话时不能残留上一个会话的行动轨迹。
- [x] 删除会话后必须清空右侧行动轨迹。

### 14.2 行动轨迹卡片详情

当前卡片信息过少。卡片默认保持简洁，但点击展开后应展示完整诊断信息。

- [x] 工具调用卡片详情展示：
  - `tool_name`；
  - `tool_call_id`；
  - 参数摘要；
  - 所属 turn；
  - 调用时间。
- [x] 工具结果卡片详情展示：
  - 成功 / 失败；
  - summary；
  - warnings；
  - evidence refs；
  - repo / ref / commit / path / line；
  - truncated；
  - raw_result_ref；
  - error_type；
  - error message。
- [x] retrieval context 卡片详情展示候选来源和截断状态。
- [x] 错误卡片详情展示 provider、error_code、message、retryable 等结构化字段。
- [x] 详情展示不能用长 JSON 直接撑开面板；当前使用悬浮弹窗和结构化字段行展示。
- [ ] 长字段需要复制入口，复制成功在入口旁轻量提示。

### 14.3 生成中断与本轮回滚

需求：会话生成过程中，用户可以中断。中断后必须回滚到本次对话起点，而不是保留半条 user / assistant / trace。

当前实现采用双保险回滚：

- 前端发送消息前生成 `client_turn_id`，后端直接用该 id 创建本轮 user turn，并通过 `X-CodeAsk-Turn-Id` / SSE `turn_id` 回传。
- 前端通过浏览器 `AbortController` 中断当前 SSE，并立即清理本轮本地 user message、partial assistant message 和临时行动轨迹。
- 后端在 StreamingResponse 收到 `asyncio.CancelledError` 时回滚本轮 `SessionTurn` 和 `AgentTrace`。
- 前端停止时额外调用 `POST /api/sessions/{session_id}/turns/{turn_id}/abort`，即使停止发生在 header 或第一条 SSE 返回前，也能基于预生成 `client_turn_id` 清理持久化数据。
- 后端持久化 assistant turn 或 runtime trace 前，必须检查父 user turn 仍然存在；如果 abort 已经删除父 turn，迟到完成的回答和迟到 trace 都不得重新写入会话历史。

已实现契约：

```text
POST /api/sessions/{session_id}/messages
→ 请求体包含 client_turn_id
→ 返回 X-CodeAsk-Turn-Id

POST /api/sessions/{session_id}/turns/{turn_id}/abort
→ 回滚该 turn 的持久化副作用
```

后续如需要跨设备、后台任务或多连接管理，再扩展为能取消后台运行任务的 abort API。

回滚范围：

```text
删除本次 user turn
删除本次 partial assistant turn
删除本次 turn 产生的 agent_traces
删除或标记本次未完成 tool result
保留本次发送前历史 turns / traces / attachments
```

- [x] 前端生成中显示明确中断入口。
- [x] 用户点击中断后，前端停止接收当前 SSE。
- [x] 后端收到 SSE 取消后停止当前 LLM stream 和后续事件持久化。
- [x] 前端停止时调用显式 abort API；停止发生在 SSE turn_id 返回前，也能基于 `client_turn_id` 回滚持久化 turn / traces。
- [x] abort 已删除父 user turn 后，迟到完成的 assistant turn 不得再写入 `session_turns`。
- [x] abort 已删除父 user turn 后，迟到 trace 不得再写入 `agent_traces`。
- [ ] 如果工具已开始执行但未完成，应记录为 aborted 或不进入会话可见历史。
- [x] 中断后会话列表、聊天消息、行动轨迹恢复到本轮发送前状态。
- [x] 中断不能影响上一轮已完成消息和行动轨迹。
- [x] 中断失败必须有明确错误提示。
- [x] 增加集成测试覆盖本轮 user turn 和 traces 回滚。
- [x] 增加前端测试覆盖生成中中断和 UI 状态恢复。

### 14.4 输入框快捷键

目标输入行为：

```text
Enter        发送
Ctrl+Enter   换行
Shift+Enter  换行
```

- [x] 单行输入时按 `Enter` 直接发送。
- [x] 多行输入时按 `Enter` 仍直接发送。
- [x] `Ctrl + Enter` 插入换行。
- [x] `Shift + Enter` 插入换行。
- [x] 空白输入不能发送。
- [x] IME 中文输入 composition 期间按 Enter 不能误发送。
- [x] 生成中若禁止并发发送，Enter 不触发第二个发送，并提供中断入口。
- [x] 增加前端组件测试覆盖快捷键行为。

### 14.5 文档与验收

需要同步更新：

```text
docs/v1.0.2/plans/acceptance-checklist.md
docs/v1.0.2/design/agent-chat-runtime.md
docs/v1.0.2/prd/agent-chat.md
```

## 手动验收清单

- [ ] 打开一个新会话，只问普通概念问题，确认不会出现旧“范围判断 / 充分性判断 / 下一步代码调查”。
- [ ] 问一个 Wiki 已有答案的问题，确认回答引用 Wiki，行动轨迹显示 Wiki 检索或读取。
- [ ] 问一个需要实现细节的问题，确认模型可以调用代码工具，行动轨迹显示 repo/ref/commit 或默认版本警告。
- [ ] 制造仓库版本不明确场景，确认系统追问或标注默认当前代码。
- [ ] 上传会话附件，确认工具只能看到当前会话附件。
- [ ] 要求生成报告，确认模型只能建议，真正生成仍需要用户确认。
- [ ] 刷新页面，确认历史消息和行动轨迹可以稳定恢复。
- [ ] 进入 Wiki 页面，确认 v1.0.1 的导入、编辑、排序、搜索、来源治理仍可用。

## 风险控制

- 不删除旧 orchestrator 和 stages，先通过新入口切换默认行为。
- 每个 task 单独提交，方便回滚。
- mock LLM 测试优先于真实 LLM 联调，避免把外部模型随机性当作测试依据。
- 只读工具先落地，写操作只做建议和确认。
- 前端先新增 action-trace 子模块，再替换 `InvestigationPanel` 内部内容，避免影响会话附件功能。
