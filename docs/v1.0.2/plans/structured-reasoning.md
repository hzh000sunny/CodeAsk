# Structured Reasoning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 在 v1.0.2 内实现同时适配 OpenAI-compatible 与 Anthropic 协议的结构化 reasoning 隔离能力，替代 CodeAsk 后端基于 `<think>` 正文标签强匹配的临时方案。

**Status 2026-05-10:** 已完成实现和验收。后端协议适配、request profile、配置持久化、runtime 隔离事件、前端 UI Leak Guard、专项单元/集成测试、全量后端测试、全量前端测试、生产构建、6 个真实 LLM 配置 API 流式验证和真实浏览器烟测均已执行。最新执行记录见 `structured-reasoning-acceptance.md`。

**Architecture:** LLM adapter 层负责把不同协议的结构化 reasoning/thinking 字段统一归一为 `reasoning_delta`，把用户可见回答归一为 `text_delta`。Agent Runtime、前端聊天气泡、报告生成、标题生成和上下文压缩默认只使用 `text_delta`、工具事件和证据；reasoning 默认隐藏，不进入普通会话历史。模型原始 `<think>` 私有文本格式必须在模型服务 / vLLM / 网关层解析成结构化字段，CodeAsk 后端不扫描 `content` / `text` 正文标签。

UI 层允许增加受控 Reasoning Leak Guard：它只在模型服务不合规、把 raw thinking 混入 `content/text` 时保护显示效果，并记录诊断。它不是协议解析器，不修改数据库，不进入下一轮上下文，也不能作为 structured reasoning 验收成功的证据。

**Tech Stack:** Python 3.11, LiteLLM, FastAPI SSE, Pydantic, pytest, pyright, ruff, React / TypeScript, Playwright live E2E。

**References:** `../specs/model-provider-reference-lessons.md`、`../../future/structured-reasoning-handling.md`、`../design/agent-chat-runtime.md`、`../plans/e2e-scenarios.md`、`../plans/structured-reasoning-acceptance.md`。

---

## 0. Scope

本计划进入 v1.0.2 当前版本范围。

开发实现前必须先确认 `structured-reasoning-acceptance.md` 中的验收 checklist 和真实前后端 E2E 测试场景。后续代码开发只能按该清单推进，不能用“前端看不到 `<think>`”替代 structured reasoning 验收。

### 0.1 参考驱动要求

本计划不能只按 CodeAsk 内部假设实现。开发时必须对照 `../specs/model-provider-reference-lessons.md` 中的参考结论：

- 对照 Claude Code：确认 Anthropic `thinking_delta`、`text_delta`、`signature_delta` 的结构化处理方式，学习其 UI 默认不展示完整 thinking 的边界。
- 对照 AnythingLLM：学习 provider / request 参数 / stream handler 分层，确认 `reasoning_content`、`reasoning`、`thinking` 等字段的真实 provider 差异；明确不采用 AnythingLLM 的 `<think>` 文本通道作为主协议，前端只允许受控 UI Leak Guard。
- 对照 vLLM reasoning outputs：确认私有模型 raw thinking 的解析责任在模型服务 / 网关层，不落入 CodeAsk 后端正文扫描。
- 对照真实模型：实现和验收阶段必须记录 observed stream fields，至少覆盖用户提供的火山 MiniMax、火山 GLM、DeepSeek v4；如果用户提供 Anthropic 协议配置，也必须记录 Anthropic stream events。

PR / commit / 验收记录中必须说明实际参考了哪些资料、观察到哪些字段、为什么选择当前 adapter / request profile 处理方式。

必须实现：

- OpenAI-compatible 结构化字段：
  - `delta.reasoning`
  - `delta.reasoning_content`
  - 结构化 `delta.thinking`
  - `delta.content`
- Anthropic 结构化 block / delta：
  - `thinking_delta`
  - `redacted_thinking`
  - `signature_delta`
  - `text_delta`
- CodeAsk 内部事件：
  - `reasoning_start`
  - `reasoning_delta`
  - `reasoning_stop`
  - `text_delta`
- Reasoning 请求 profile：
  - `none`
  - `volcengine_thinking`
  - `vllm_enable_thinking`
  - `anthropic_budget_thinking`
  - `custom_json`
- Stream shape debug：
  - 只记录字段名、结构化 reasoning 是否存在、短 preview。
  - 不把 preview 用作正文标签解析。
- Agent 运行事件扩展：
  - 可以展示公开 `analysis_note`、`context_prepared`、`evidence_selected`、`uncertainty`、`next_step_hint`。
  - 这些事件必须基于用户问题、注入上下文、工具事件、证据和公开回答，不得使用 raw reasoning 原文。
- UI Reasoning Leak Guard：
  - 支持 `disabled | warn_only | mask_in_ui`。
  - 默认建议 `mask_in_ui`，用于防止 raw `<think>` 等内容直接暴露给用户。
  - 必须产生 `reasoning_leak_detected` 本地诊断或等价行动轨迹项。
  - 不修改后端返回内容，不写回数据库，不进入后续上下文。
- 自动化测试和 live E2E 测试计划。

明确不实现：

- 不在 CodeAsk 后端解析 `<think>`、`</think>`、`<thinking>`、`<reasoning>` 等正文标签。
- 不把前端 leak guard 当作后端协议解析能力。
- 不按模型名 hardcode parser。
- 不把 reasoning 展示到普通聊天气泡。
- 不把 raw reasoning 写入 `session_turns`、报告正文、会话标题或普通上下文摘要。

## 1. File Structure

后端新增：

```text
src/codeask/llm/reasoning.py
src/codeask/llm/request_profiles.py
tests/unit/test_llm_reasoning.py
tests/unit/test_llm_request_profiles.py
```

后端修改：

```text
src/codeask/llm/types.py
src/codeask/llm/client.py
src/codeask/llm/gateway.py
src/codeask/agent/chat_runtime/runtime.py
src/codeask/sessions/title_generation.py
src/codeask/sessions/report_generation.py
```

集成测试修改 / 新增：

```text
tests/unit/test_llm_client_adapter.py
tests/integration/test_agent_chat_runtime_sse.py
tests/integration/test_sessions_api.py
tests/integration/test_session_report_generation.py
```

前端修改 / 新增：

```text
frontend/src/types/sse.ts
frontend/src/components/session/reasoning-leak-guard.ts
frontend/src/components/session/useSessionMessageStream.ts
frontend/src/components/session/action-trace/ActionTracePanel.tsx
frontend/src/components/session/action-trace/ActionTraceDetails.tsx
frontend/tests/reasoning-leak-guard.test.ts
frontend/tests/session-message-stream.test.tsx
frontend/tests/action-trace-analysis-note.test.tsx
```

Live E2E 新增：

```text
frontend/e2e/agent-reasoning-protocol-live.spec.ts
```

文档修改：

```text
docs/v1.0.2/README.md
docs/v1.0.2/specs/model-provider-reference-lessons.md
docs/v1.0.2/plans/acceptance-checklist.md
docs/v1.0.2/plans/e2e-scenarios.md
docs/future/structured-reasoning-handling.md
```

## 2. Task 1: 定义 provider-neutral reasoning 类型

**Files:**

- Modify: `src/codeask/llm/types.py`
- Create: `src/codeask/llm/reasoning.py`
- Test: `tests/unit/test_llm_reasoning.py`

- [x] **Step 1: 写 failing tests**

```python
from codeask.llm.reasoning import normalize_openai_delta


def test_openai_reasoning_content_becomes_reasoning_delta() -> None:
    events = normalize_openai_delta({"reasoning_content": "内部思考"})
    assert events == [("reasoning_delta", {"delta": "内部思考", "field": "reasoning_content"})]


def test_openai_content_becomes_text_delta() -> None:
    events = normalize_openai_delta({"content": "正式回答"})
    assert events == [("text_delta", {"delta": "正式回答"})]


def test_content_with_think_tag_is_not_parsed() -> None:
    events = normalize_openai_delta({"content": "<think>内部</think>正式回答"})
    assert events == [("text_delta", {"delta": "<think>内部</think>正式回答"})]
```

Run:

```bash
uv run pytest tests/unit/test_llm_reasoning.py -q
```

Expected: fails because `codeask.llm.reasoning` does not exist.

- [x] **Step 2: 实现最小 normalization**

`src/codeask/llm/reasoning.py`:

```python
from __future__ import annotations

from typing import Any, Literal

ReasoningEventName = Literal["reasoning_delta", "text_delta"]


def normalize_openai_delta(delta: dict[str, Any]) -> list[tuple[ReasoningEventName, dict[str, Any]]]:
    events: list[tuple[ReasoningEventName, dict[str, Any]]] = []
    for field in ("reasoning", "reasoning_content", "thinking"):
        value = delta.get(field)
        if isinstance(value, str) and value:
            events.append(("reasoning_delta", {"delta": value, "field": field}))
    content = delta.get("content")
    if isinstance(content, str) and content:
        events.append(("text_delta", {"delta": content}))
    return events
```

- [x] **Step 3: 扩展 `LLMEvent.type`**

在 `src/codeask/llm/types.py` 的事件类型中加入：

```python
"reasoning_start"
"reasoning_delta"
"reasoning_stop"
```

- [x] **Step 4: 验证**

```bash
uv run pytest tests/unit/test_llm_reasoning.py -q
uv run pyright src/codeask/llm/reasoning.py src/codeask/llm/types.py
uv run ruff check src/codeask/llm/reasoning.py src/codeask/llm/types.py tests/unit/test_llm_reasoning.py
```

Expected: all pass.

## 3. Task 2: OpenAI-compatible adapter 消费结构化 reasoning 字段

**Files:**

- Modify: `src/codeask/llm/client.py`
- Modify: `tests/unit/test_llm_client_adapter.py`

- [x] **Step 1: 写 OpenAI-compatible streaming tests**

新增测试：

```python
async def test_openai_compatible_stream_emits_reasoning_delta_without_text(monkeypatch):
    async def fake_acompletion(**kwargs):
        async def gen():
            yield _chunk_with_delta({"reasoning_content": "先分析"})
            yield _chunk_with_delta({"content": "正式回答"})
            yield _chunk_with_delta({}, finish_reason="stop")
        return gen()

    import codeask.llm.client as mod
    monkeypatch.setattr(mod, "acompletion", fake_acompletion)

    client = OpenAICompatibleClient(api_key="x", model_name="m")
    events = [
        event
        async for event in client.stream(
            messages=[LLMMessage(role="user", content=[TextBlock(type="text", text="hi")])],
            tools=[],
            max_tokens=100,
            temperature=0.0,
        )
    ]

    assert [e.type for e in events] == [
        "message_start",
        "reasoning_delta",
        "text_delta",
        "message_stop",
    ]
    assert events[1].data["delta"] == "先分析"
    assert events[2].data["delta"] == "正式回答"
```

新增反向测试：

```python
async def test_openai_compatible_does_not_parse_think_tags(monkeypatch):
    async def fake_acompletion(**kwargs):
        async def gen():
            yield _chunk(content="<think>内部</think>正式回答")
            yield _chunk(finish_reason="stop")
        return gen()

    import codeask.llm.client as mod
    monkeypatch.setattr(mod, "acompletion", fake_acompletion)

    client = OpenAICompatibleClient(api_key="x", model_name="m")
    events = [
        event
        async for event in client.stream(
            messages=[LLMMessage(role="user", content=[TextBlock(type="text", text="hi")])],
            tools=[],
            max_tokens=100,
            temperature=0.0,
        )
    ]

    text = "".join(str(e.data["delta"]) for e in events if e.type == "text_delta")
    assert text == "<think>内部</think>正式回答"
    assert not any(e.type == "reasoning_delta" for e in events)
```

- [x] **Step 2: 修改 adapter**

在 `src/codeask/llm/client.py` 中：

- 删除或停用 `_ReasoningTagFilter`。
- 对每个 OpenAI delta 先取结构化字段：

```python
raw_delta = _delta_to_dict(delta)
for event_type, data in normalize_openai_delta(raw_delta):
    yield LLMEvent(type=event_type, data=data)
```

- `tool_calls` 仍按现有逻辑处理。
- `content` 内标签不解析。

- [x] **Step 3: 验证**

```bash
uv run pytest tests/unit/test_llm_client_adapter.py tests/unit/test_llm_reasoning.py -q
uv run pyright src/codeask/llm/client.py src/codeask/llm/reasoning.py
uv run ruff check src/codeask/llm/client.py src/codeask/llm/reasoning.py tests/unit/test_llm_client_adapter.py tests/unit/test_llm_reasoning.py
```

Expected: all pass.

## 4. Task 3: Reasoning request profile

**Files:**

- Create: `src/codeask/llm/request_profiles.py`
- Modify: `src/codeask/llm/client.py`
- Test: `tests/unit/test_llm_request_profiles.py`

- [x] **Step 1: 写 profile tests**

```python
from codeask.llm.request_profiles import build_reasoning_request_kwargs


def test_volcengine_thinking_profile() -> None:
    assert build_reasoning_request_kwargs("volcengine_thinking") == {
        "extra_body": {"thinking": {"type": "enabled"}}
    }


def test_vllm_enable_thinking_profile() -> None:
    assert build_reasoning_request_kwargs("vllm_enable_thinking") == {
        "extra_body": {"chat_template_kwargs": {"enable_thinking": True}}
    }


def test_none_profile() -> None:
    assert build_reasoning_request_kwargs("none") == {}
```

- [x] **Step 2: 实现 profile builder**

`src/codeask/llm/request_profiles.py`:

```python
from __future__ import annotations

from typing import Any, Literal

ReasoningRequestProfile = Literal[
    "none",
    "volcengine_thinking",
    "vllm_enable_thinking",
    "anthropic_budget_thinking",
]


def build_reasoning_request_kwargs(profile: ReasoningRequestProfile) -> dict[str, Any]:
    if profile == "none":
        return {}
    if profile == "volcengine_thinking":
        return {"extra_body": {"thinking": {"type": "enabled"}}}
    if profile == "vllm_enable_thinking":
        return {"extra_body": {"chat_template_kwargs": {"enable_thinking": True}}}
    if profile == "anthropic_budget_thinking":
        return {"thinking": {"type": "enabled", "budget_tokens": 4096}}
    raise ValueError(f"unknown reasoning request profile: {profile}")
```

- [x] **Step 3: 接入默认策略**

第一版不增加复杂 UI。默认行为：

```text
OpenAI-compatible:
  默认 none
  通过后端配置 / 环境开关 / 测试夹具选择 volcengine_thinking 或 vllm_enable_thinking

Anthropic:
  默认 none
  后续按 Anthropic adapter 能力启用 anthropic_budget_thinking
```

注意：不能再在所有 OpenAI-compatible 请求里硬塞 `extra_body={"thinking": {"type":"enabled"}}`。

- [x] **Step 4: 验证**

```bash
uv run pytest tests/unit/test_llm_request_profiles.py tests/unit/test_llm_client_adapter.py -q
```

Expected: all pass.

## 5. Task 4: Anthropic 协议结构化 thinking 适配

**Files:**

- Modify: `src/codeask/llm/client.py`
- Modify: `tests/unit/test_llm_client_adapter.py`

- [x] **Step 1: 写 Anthropic event tests**

用 fake stream 模拟 Anthropic SDK 事件或 LiteLLM passthrough 后的事件对象，覆盖：

```text
content_block_start(type=thinking) -> reasoning_start
content_block_delta(type=thinking_delta) -> reasoning_delta
content_block_delta(type=text_delta) -> text_delta
content_block_delta(type=signature_delta) -> no visible event
redacted_thinking -> reasoning_delta(redacted=true)
```

最低测试代码形态：

```python
async def test_anthropic_stream_thinking_delta_is_reasoning_delta(monkeypatch):
    async def fake_acompletion(**kwargs):
        async def gen():
            yield _anthropic_event("content_block_start", content_block={"type": "thinking"})
            yield _anthropic_event("content_block_delta", delta={"type": "thinking_delta", "thinking": "内部"})
            yield _anthropic_event("content_block_delta", delta={"type": "text_delta", "text": "回答"})
            yield _anthropic_event("message_stop")
        return gen()

    ...
    assert [e.type for e in events] == [
        "message_start",
        "reasoning_start",
        "reasoning_delta",
        "text_delta",
        "message_stop",
    ]
```

- [x] **Step 2: 实现 Anthropic stream normalizer**

建议不要把 Anthropic 事件逻辑塞进 OpenAI choices 分支。拆成小函数：

```python
def _is_anthropic_stream_event(chunk: object) -> bool: ...
def _normalize_anthropic_event(chunk: object) -> list[LLMEvent]: ...
```

- [x] **Step 3: 验证**

```bash
uv run pytest tests/unit/test_llm_client_adapter.py -q -k "anthropic or reasoning"
uv run pyright src/codeask/llm/client.py
```

Expected: all pass.

## 6. Task 5: Runtime / persistence 隔离 reasoning

**Files:**

- Modify: `src/codeask/agent/chat_runtime/runtime.py`
- Modify: `src/codeask/sessions/traces.py`
- Modify: `src/codeask/sessions/title_generation.py`
- Modify: `src/codeask/sessions/report_generation.py`
- Test: `tests/integration/test_agent_chat_runtime_sse.py`
- Test: `tests/integration/test_sessions_api.py`
- Test: `tests/integration/test_session_report_generation.py`

- [x] **Step 1: 写 runtime SSE 测试**

```python
async def test_reasoning_delta_is_not_persisted_as_agent_turn(app_client, mock_llm):
    mock_llm.events = [
        LLMEvent(type="message_start", data={}),
        LLMEvent(type="reasoning_delta", data={"delta": "内部思考"}),
        LLMEvent(type="text_delta", data={"delta": "正式回答"}),
        LLMEvent(type="message_stop", data={"stop_reason": "end_turn"}),
    ]

    ...
    turns = await load_turns(session_id)
    assert [turn.content for turn in turns if turn.role == "agent"] == ["正式回答"]
```

- [x] **Step 2: 写标题 / 报告反污染测试**

```python
def test_title_generation_uses_visible_turns_only(...):
    # session_turns 里只应有 text_delta 形成的 agent 内容
    # reasoning 不得作为第一轮 assistant 内容进入 title prompt
    assert "内部思考" not in captured_title_prompt
```

```python
def test_report_generation_context_excludes_reasoning(...):
    assert "内部思考" not in captured_report_prompt
    assert "正式回答" in captured_report_prompt
```

- [x] **Step 3: 修改 runtime**

规则：

```text
reasoning_delta:
  不追加到 assistant_text_buffer
  不写 session_turns
  默认不发普通聊天气泡
  可写 debug trace 摘要，但不写完整 raw reasoning

text_delta:
  追加到 assistant_text_buffer
  发给前端聊天
  完成后写 session_turns
```

- [x] **Step 4: 扩展 Agent 运行事件的公开分析摘要**

新增或复用 `agent_traces.payload` 字段表达公开分析思路。允许的事件：

```text
context_prepared    本轮注入给模型的候选上下文摘要
analysis_note       基于可见上下文、工具事件和证据链生成的简短分析方向
evidence_selected   被采用的 Wiki / 报告 / 附件 / 代码证据摘要
uncertainty         当前不确定点或需要用户确认的范围
next_step_hint      下一步可能动作，例如读取 Wiki、读报告、查代码、追问
reasoning_observed  仅管理员 / debug，用于记录 structured reasoning 字段名和长度
```

写入规则：

```text
analysis_note.raw_reasoning_used 必须为 false。
analysis_note.summary 不得来自 reasoning_delta 原文。
reasoning_observed 不得保存 raw reasoning，只保存字段名、长度、redacted 标记和 provider。
context_prepared 可以列出 feature_catalog、wiki_hits、report_hits、attachment_candidates、repo_candidates 的数量和标题。
evidence_selected 必须引用真实工具结果或 RAG 候选，不得伪造模型没有使用的证据。
```

最小测试：

```python
async def test_analysis_note_trace_does_not_use_reasoning(app_client, mock_llm):
    mock_llm.events = [
        LLMEvent(type="message_start", data={}),
        LLMEvent(type="reasoning_delta", data={"delta": "不要泄露的原始思考"}),
        LLMEvent(type="text_delta", data={"delta": "正式回答"}),
        LLMEvent(type="message_stop", data={"stop_reason": "end_turn"}),
    ]

    ...
    traces = await load_traces(session_id)
    analysis_notes = [t for t in traces if t.event_type == "analysis_note"]
    assert all(t.payload.get("raw_reasoning_used") is False for t in analysis_notes)
    assert "不要泄露的原始思考" not in json.dumps([t.payload for t in traces], ensure_ascii=False)
```

- [x] **Step 5: 验证**

```bash
uv run pytest tests/integration/test_agent_chat_runtime_sse.py tests/integration/test_sessions_api.py tests/integration/test_session_report_generation.py -q
```

Expected: all pass.

## 7. Task 6: Frontend 忽略 reasoning_delta 并保留 debug 入口

**Files:**

- Modify: `frontend/src/types/sse.ts`
- Modify: `frontend/src/components/session/useSessionMessageStream.ts`
- Modify: `frontend/src/components/session/action-trace/ActionTracePanel.tsx`
- Modify: `frontend/src/components/session/action-trace/ActionTraceDetails.tsx`
- Test: `frontend/tests/session-message-stream.test.tsx`
- Test: `frontend/tests/action-trace-analysis-note.test.tsx`

- [x] **Step 1: 写前端测试**

```tsx
it("does not append reasoning_delta to visible assistant message", async () => {
  const stream = [
    { type: "message_start", data: {} },
    { type: "reasoning_delta", data: { delta: "内部思考" } },
    { type: "text_delta", data: { delta: "正式回答" } },
    { type: "done", data: {} },
  ];

  renderSessionWithStream(stream);
  expect(screen.queryByText("内部思考")).not.toBeInTheDocument();
  expect(screen.getByText("正式回答")).toBeInTheDocument();
});
```

- [x] **Step 2: 修改 SSE 类型**

```ts
export type SessionStreamEvent =
  | { type: "reasoning_delta"; data: { delta: string; field?: string; redacted?: boolean } }
  | ExistingEvents;
```

- [x] **Step 3: 修改 stream reducer**

规则：

```text
reasoning_delta:
  不追加到 assistant message
  不显示普通 toast
  可在 dev/debug trace 数据结构中累计长度和字段名
```

- [x] **Step 4: 展示公开分析思路**

`Agent 行动轨迹` 中新增对以下事件的摘要展示：

```text
context_prepared    显示“已准备 N 条上下文”，展开后显示候选类型和标题
analysis_note       显示“分析方向”，展开后显示公开 summary
evidence_selected   显示“采用证据”，展开后显示路径、标题、片段摘要
uncertainty         显示“不确定点”，展开后显示需要确认的范围
next_step_hint      显示“下一步”，展开后显示模型公开计划或工具方向
reasoning_observed  默认不对普通用户显示；管理员 debug 模式只显示字段名和长度
```

前端测试要求：

```tsx
it("renders public analysis note without raw reasoning", async () => {
  renderTracePanel([
    {
      event_type: "analysis_note",
      payload: {
        title: "分析方向",
        summary: "本轮先读取 AnythingLLM 的 ingestion Wiki，再查看召回相关证据。",
        raw_reasoning_used: false,
      },
    },
    {
      event_type: "reasoning_observed",
      payload: {
        fields: ["reasoning_content"],
        length: 128,
      },
    },
  ]);

  expect(screen.getByText("分析方向")).toBeInTheDocument();
  expect(screen.getByText(/ingestion Wiki/)).toBeInTheDocument();
  expect(screen.queryByText("reasoning_content")).not.toBeInTheDocument();
});
```

- [x] **Step 5: 验证**

```bash
corepack pnpm --dir frontend test:run -- session-message-stream
corepack pnpm --dir frontend test:run -- action-trace-analysis-note
corepack pnpm --dir frontend typecheck
```

Expected: pass.

## 8. Task 7: Live E2E 协议矩阵

**Files:**

- Create: `frontend/e2e/agent-reasoning-protocol-live.spec.ts`
- Modify: `docs/v1.0.2/plans/e2e-scenarios.md`

- [x] **Step 1: 新增 live E2E 开关**

新增环境变量：

```text
CODEASK_RUN_LIVE_REASONING_PROTOCOL_E2E=1
CODEASK_LIVE_REASONING_MODELS=minimax,glm,deepseek-v4
```

测试默认跳过；开启后由管理员在前端配置可用 LLM。

- [x] **Step 2: E2E 场景**

每次执行从可用 LLM 配置中随机选择一个，覆盖用户提供的真实模型池：

```text
火山引擎 MiniMax
火山引擎 GLM
DeepSeek v4 服务
OpenAI-compatible 协议
Anthropic 协议
```

测试问题：

```text
你好，请用一句话介绍你自己。
```

验收：

```text
聊天气泡不出现 raw reasoning。
如果上游返回 reasoning_content/reasoning/thinking，后端事件中存在 reasoning_delta。
session_turns 只保存正式回答。
Agent 行动轨迹不把 reasoning 当工具事件。
Agent 行动轨迹可以展示公开 analysis_note / context_prepared / evidence_selected，但不能展示 raw reasoning。
标题生成不包含 reasoning。
```

- [x] **Step 3: 人工协作验收记录**

每个真实模型至少记录：

```text
model display name
protocol: OpenAI / Anthropic
request profile
observed stream fields
session id
是否出现 reasoning_delta
普通聊天是否隐藏 reasoning
是否保存到 session_turns
行动轨迹中是否存在公开分析摘要
公开分析摘要是否未使用 raw reasoning
```

## 9. Task 8: 文档与收口

**Files:**

- Modify: `docs/v1.0.2/README.md`
- Modify: `docs/v1.0.2/plans/acceptance-checklist.md`
- Modify: `docs/v1.0.2/plans/e2e-scenarios.md`
- Modify: `docs/future/structured-reasoning-handling.md`

- [x] **Step 1: 更新 v1.0.2 README**

把 `plans/structured-reasoning.md` 加入当前记录，并把“当前未完成项”更新为包含 reasoning 协议适配收口。

- [x] **Step 2: 更新验收清单**

新增 v1.0.2 reasoning 验收项：

```text
OpenAI-compatible reasoning_content 不展示、不持久化。
OpenAI-compatible reasoning 不展示、不持久化。
Anthropic thinking_delta 不展示、不持久化。
content/text 不做标签扫描。
Agent 运行事件可以展示公开分析摘要，但不得展示或保存 raw reasoning。
报告和标题不包含 raw reasoning。
真实模型 E2E 覆盖 MiniMax / GLM / DeepSeek v4。
```

- [x] **Step 3: 更新 E2E 场景矩阵**

新增 `E2E-Reasoning-Protocol` 场景，并注明用户会提供多模型、多协议配置供随机测试。

- [x] **Step 4: 最终验证命令**

```bash
uv run pytest tests/unit/test_llm_reasoning.py tests/unit/test_llm_request_profiles.py tests/unit/test_llm_client_adapter.py -q
uv run pytest tests/integration/test_agent_chat_runtime_sse.py tests/integration/test_sessions_api.py tests/integration/test_session_report_generation.py -q
uv run pyright src/codeask/llm src/codeask/agent/chat_runtime src/codeask/sessions
uv run ruff check src/codeask/llm src/codeask/agent/chat_runtime src/codeask/sessions tests/unit tests/integration
corepack pnpm --dir frontend test:run
corepack pnpm --dir frontend test:run -- action-trace-analysis-note
corepack pnpm --dir frontend typecheck
CODEASK_RUN_LIVE_REASONING_PROTOCOL_E2E=1 corepack pnpm --dir frontend exec playwright test frontend/e2e/agent-reasoning-protocol-live.spec.ts --workers=1
```

## 10. Acceptance Gate

本计划完成前，v1.0.2 不允许收口。

必须同时满足：

- 自动化测试通过。
- 至少一次 OpenAI-compatible 火山引擎 MiniMax live E2E 通过。
- 至少一次 OpenAI-compatible 火山引擎 GLM live E2E 通过。
- 至少一次 DeepSeek v4 live E2E 通过。
- 如果用户提供 Anthropic 协议网关配置，至少一次 Anthropic 协议 live E2E 通过。
- 所有 live E2E 记录 session id 和 observed stream fields。
- CodeAsk 后端没有恢复 `<think>` 正文标签强匹配逻辑。

## 11. Self-Review

- 覆盖 OpenAI-compatible：Task 1、2、3、7。
- 覆盖 Anthropic：Task 4、7。
- 覆盖“不解析正文标签”：Task 1、2、5、7、8。
- 覆盖前端隐藏：Task 6、7。
- 覆盖报告 / 标题污染：Task 5。
- 覆盖 Agent 运行事件公开分析摘要：Task 5、6、7。
- 覆盖真实模型测试：Task 7、10。
- 覆盖文档更新：Task 8。
