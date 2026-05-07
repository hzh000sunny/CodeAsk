# Agent Chat Runtime 实施计划

> **给 agent 执行者：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务执行本计划。步骤使用 checkbox（`- [ ]`）记录状态。

**目标：** 将 CodeAsk 默认会话从固定调查状态机迁移到正常聊天优先、RAG 增强、模型决定工具调用的 Agent Chat Runtime。

**架构：** 新增独立 `src/codeask/agent/chat_runtime/` 模块承载上下文组装、工具契约、工具执行器、运行时 loop、行动轨迹和审计；旧 `src/codeask/agent/stages/` 与 `AgentOrchestrator` 先保留为 legacy 兼容。前端新增 `frontend/src/components/session/action-trace/`，用真实 runtime 事件替代固定“调查进度”。

**技术栈：** Python 3.11+, FastAPI, SQLAlchemy async, Pydantic, pytest, uv, React, TypeScript, Vite, SSE。

---

## 0. 文件结构

后端新增：

```text
src/codeask/agent/chat_runtime/
├── __init__.py
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
    ├── policies.py
    ├── reports.py
    ├── report_actions.py
    ├── user_interaction.py
    └── wiki.py
```

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
explicit session constraints
candidate feature repo default ref
global repo default ref
registered local repo current checkout
needs_clarification
```

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
