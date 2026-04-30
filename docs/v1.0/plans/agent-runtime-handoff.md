# Agent Runtime Hand-off — 给 05 / 06 / 07 后续计划

本文记录 `agent-runtime` 完成后交给 `frontend-workbench`、`metrics-eval`、`deployment` 的稳定契约。后续计划优先消费这些接口；如需改动，需要新开 migration 或兼容层，不要直接破坏已落地行为。

## 1. SSE 事件契约

消费方：`05 frontend-workbench`。

事件类型清单已锁定，前端按这 10 个值分发：

```text
stage_transition | text_delta | tool_call | tool_result | evidence | scope_detection | sufficiency_judgement | ask_user | done | error
```

通用格式由 `SSEMultiplexer.format(event)` 输出：

```text
event: <type>
data: <json>

```

关键 `data` 字段约定：

| event | data |
|---|---|
| `stage_transition` | `{from, to, message}`，`from` / `to` 使用 `AgentState.value` 的 snake_case |
| `scope_detection` | `{feature_ids, confidence, reason}` |
| `sufficiency_judgement` | `{verdict, reason, next, forced_code_investigation?}` |
| `tool_call` | `{id, name, arguments}` |
| `tool_result` | `{id, result}`，`result` 是 `ToolResult.model_dump()` |
| `evidence` | `{item}`，`item.id` 是稳定证据 ID |
| `ask_user` | `{ask_id, question, options, reason?}`；收到此事件后本轮 SSE 结束，不会再发 `done` |
| `text_delta` | `{delta}` |
| `done` | `{turn_id}` |
| `error` | `{code, message, stage?}` |

## 2. agent_traces 表

消费方：`06 metrics-eval`。

`event_type` 枚举值已锁定：

```text
stage_enter | stage_exit | llm_input | llm_event | tool_call | tool_result | scope_decision | sufficiency_decision | user_feedback
```

eval 数据点：

- A2 ScopeDetection：聚合 `event_type='scope_decision'` 的 payload，并结合后续用户是否改特性。
- A3 SufficiencyJudgement：聚合 `event_type='sufficiency_decision'` 的 payload，并结合用户是否触发“再深查一下”。
- “再深查一下”已通过 `POST /api/sessions/{id}/messages` 的 `force_code_investigation=true` 支持；前端只需要把用户意图透传。

## 3. ORM 表

本计划新增 8 张表：

- `llm_configs`
- `skills`
- `sessions`
- `session_features`
- `session_repo_bindings`
- `session_turns`
- `session_attachments`
- `agent_traces`

后续计划不要直接改这些表的既有列语义；如需扩展，新增 migration。

## 4. Runtime API

已落地接口：

- `/api/llm-configs`：`POST` / `GET list` / `GET by id` / `PATCH` / `DELETE`；所有 GET 响应只返回 masked key。
- `/api/skills`：`POST` / `GET list` / `GET by id` / `PATCH` / `DELETE`；`scope` 与 `feature_id` 一致性由 Pydantic + DB check 双层约束。
- `/api/sessions`：`POST` / `GET list` / `GET by id`。
- `/api/sessions/{id}/messages`：写入 user turn 后返回 SSE 流。
- `/api/sessions/{id}/attachments`：一期支持 `.log` / `.txt` / `.md` / `.png` / `.jpg` / `.jpeg`，单文件不超过 10MB。

## 5. 未在本计划落地的接口

消费方：`06 metrics-eval`。

本计划未实现 `/api/feedback`、`/api/audit-log`、`/api/frontend-events`。`metrics-eval` 计划负责新增：

- `feedback` 表：`session_id`、`turn_id`、`subject_id`、`verdict`、`note`。
- `POST /api/sessions/{id}/turns/{turn_id}/feedback`。
- 写入 feedback 后调用 `AgentTraceLogger.log_user_feedback`，让 `agent_traces` 也保留一行 `event_type='user_feedback'`。
- `audit_log` 与 `frontend_events` 表及对应 API。

## 6. 真实 LLM Smoke

消费方：`07 deployment`。

本计划的自动化测试全部使用 `MockLLMClient`，不依赖外部模型服务。部署计划需要补一个真实 provider smoke：

1. 读取 `CODEASK_SMOKE_LLM_CONFIG_ID` 或通过 `/api/llm-configs` 创建临时配置。
2. 创建 session。
3. 发送一条 hello-world 消息。
4. 验证 SSE 至少返回 `scope_detection` 或明确的 `ask_user` / `error`，并且服务不崩溃。

## 7. 后续工具扩展边界

- 多模态附件：一期只记录 image metadata，不解析图片内容。
- LSP / 调用图：不在一期 Agent 工具内，后续通过 `ToolRegistry` 新增工具，保持阶段白名单约束。
- 二期代码上下文优化：参考 `docs/v1.0/design/code-index.md` §7.1 / §7.2 与 `docs/v1.0/design/tools.md` §8，不改变底层工具安全边界。
