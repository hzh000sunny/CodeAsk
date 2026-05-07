# v1.0.2 Agent Chat Runtime 系统设计

> 状态：Draft
> 版本：v1.0.2
> 范围：后端 ChatRuntime、工具契约、SSE 事件、前端 Action Trace

## 1. 总体架构

v1.0.2 新增独立模块：

```text
src/codeask/agent/chat_runtime/
├── context.py
├── events.py
├── prompt.py
├── retrieval.py
├── runtime.py
├── tool_contracts.py
├── tool_executor.py
├── tool_registry.py
└── tools/
```

旧模块保留：

```text
src/codeask/agent/stages/
src/codeask/agent/orchestrator.py
```

默认 `/api/sessions/{session_id}/messages` 已切换到 `ChatRuntime`。旧 `AgentOrchestrator` 作为 legacy 兼容保留，便于旧测试、评估和后续迁移参考。

## 2. ChatRuntime 职责

`ChatRuntime` 负责一轮 assistant turn 的执行：

1. 读取用户输入。
2. 调用轻量召回服务生成 `retrieval_context`。
3. 组装 system prompt 和 user message。
4. 把可用工具定义传给 LLM。
5. 流式转发 `text_delta`。
6. 收集模型工具调用。
7. 调用 `ToolExecutor` 执行工具。
8. 把工具结果作为 tool message 追加回模型上下文。
9. 循环直到模型停止调用工具或达到最大轮数。
10. 输出 `done` 或 `error`。

`ChatRuntime` 不负责判断：

- 问题属于哪个特性。
- Wiki 是否足够回答。
- 是否必须查代码。
- 是否应该生成报告。

这些判断都交给模型。

## 3. LLM 适配

运行时定义 `StreamingLLM` 协议：

```text
stream(messages, tools, max_tokens, temperature) -> AsyncIterator[LLMEvent]
```

生产环境通过 `GatewayStreamingLLM` 适配现有 `LLMGateway`，并将 `subject_id` 放入 request metadata，使 LLM 配置选择仍然遵循当前管理员 / 用户配置规则。

测试环境可以注入脚本化 LLM，验证工具循环、SSE 事件和消息持久化。

## 4. 工具契约

工具由三部分组成：

| 组件 | 作用 |
|---|---|
| `ToolSpec` | 工具给模型看的能力说明和 schema |
| `ToolContext` | 当前 session、turn、subject、显式约束 |
| `ToolResult` | 工具执行后的结构化结果 |

工具默认 fail-closed：

```text
read_only = false
concurrency_safe = false
requires_confirmation = true
requires_user_interaction = false
```

只有明确声明为只读且不需要确认的工具，才能默认暴露给模型自由调用。

## 5. 工具执行器

`ToolExecutor` 的职责：

- 根据工具名查找 `ToolRegistry`。
- 使用 Pydantic input model 校验参数。
- 阻止未确认的确认型工具。
- 捕获工具错误并转为结构化 `ToolResult.error`。
- 保证模型拿到可继续处理的错误类型。

典型错误类型：

```text
invalid_input
not_found
out_of_scope
permission_denied
needs_clarification
version_unknown
too_large
transient_error
internal_error
```

## 6. 第一批工具模块

v1.0.2 已建立以下工具模块和单元测试：

| 模块 | 工具 |
|---|---|
| `tools/wiki.py` | `search_wiki`, `read_wiki_node` |
| `tools/reports.py` | `search_reports`, `read_report` |
| `tools/attachments.py` | `list_session_attachments`, `read_session_attachment` |
| `tools/code.py` | `inspect_repo_tree`, `search_code`, `read_code_file`, `resolve_code_scope` |
| `tools/user_interaction.py` | `ask_user` |
| `tools/policies.py` | `load_analysis_policy` |
| `tools/report_actions.py` | `propose_report` |

当前实现优先完成统一契约、工具循环和测试隔离。后续需要继续把生产数据源接入默认 app registry，尤其是真实 Wiki、报告和代码搜索服务。

## 7. SSE 事件

默认会话 SSE 支持：

```text
retrieval_context
text_delta
tool_call
tool_result
evidence
assistant_action
needs_clarification
done
error
```

legacy SSE 事件仍保留类型兼容：

```text
stage_transition
wiki_scope_resolution
scope_detection
sufficiency_judgement
ask_user
```

前端默认面板不再把 legacy stage 当作固定流程渲染。

## 8. 前端 Action Trace

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

设计原则：

- `action-trace-model.ts` 负责把 SSE 转成可渲染事件。
- 组件只负责展示，按事件类型拆分。
- 右侧面板标题为 `Agent 行动轨迹`。
- 事件详情用悬浮弹窗，避免面板被长 JSON 撑开。
- 工具结果显示成功、失败和证据，不直接展示原始 JSON。
- 附件区域保留在同一右侧面板中。

## 9. 当前验证

已验证：

- `tests/unit/chat_runtime`
- `tests/integration/test_agent_chat_runtime.py`
- `tests/integration/test_agent_chat_runtime_sse.py`
- `tests/integration/test_sessions_api.py`
- `tests/integration/test_orchestrator_sufficient.py`
- `tests/integration/test_orchestrator_insufficient.py`
- `frontend test:run`
- `frontend build`

## 10. 后续设计方向

1. 把真实 Wiki / 报告 / 代码 service 接入默认 `ChatToolRegistry`。
2. 将工具结果原始内容落审计存储，并通过 `raw_result_ref` 回查。
3. 为 `needs_clarification` 建立前端待答复状态，而不是只追加 assistant 文本。
4. 增加真实 LLM 端到端评测：普通问答、Wiki 足够回答、Wiki 不足但不确定仓库、代码读取后回答。
5. 继续压缩旧 `session-model.ts` 中 legacy stage helper，避免长期保留两套模型。
