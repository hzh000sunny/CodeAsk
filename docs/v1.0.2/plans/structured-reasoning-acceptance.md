# Structured Reasoning 验收清单与真实 E2E 测试计划

> 状态：Active
> 版本归属：v1.0.2
> 范围：OpenAI-compatible / Anthropic 结构化 reasoning 隔离、UI Leak Guard、真实前后端交互、真实模型池验收

## 1. 验收目标

本计划是 v1.0.2 structured reasoning 开发前的验收门禁。实现代码前必须先确认本文件中的 checklist 和 E2E 场景；开发完成后必须逐项回填执行结果。

目标不是“把 `<think>` 藏起来”，而是让 CodeAsk 建立稳定的四层边界：

1. **协议适配层**：只消费 OpenAI-compatible / Anthropic 的结构化 reasoning 字段。
2. **Request Profile 层**：通过配置决定是否启用 thinking / reasoning 请求参数。
3. **模型服务 / 网关 Parser 层**：私有 raw thinking 应在 vLLM、模型服务或网关层转成结构化字段。
4. **UI Leak Guard 层**：只做显示层兜底保护，不修改数据库，不污染上下文，不算协议接入成功。

## 1.1 2026-05-10 实施进度

已完成：

- `src/codeask/llm/reasoning.py`：OpenAI-compatible `reasoning_content/reasoning/thinking/content` 和 Anthropic `thinking_delta/redacted_thinking/signature_delta/text_delta` 的 provider-neutral 归一化。
- `src/codeask/llm/request_profiles.py`：`none`、`volcengine_thinking`、`vllm_enable_thinking`、`anthropic_budget_thinking`、`custom_json` 请求 profile。
- `llm_configs` 配置持久化：新增 `reasoning_profile/reasoning_profile_json`，前后端表单、API、Repo、Gateway 均已透传。
- `ChatRuntime`：`reasoning_delta` 转为 `reasoning_observed` 诊断事件，不进入正式回答拼接。
- `frontend/src/components/session/reasoning-leak-guard.ts`：显示层 `disabled | warn_only | mask_in_ui` 兜底保护。
- 行动轨迹：`reasoning_observed` 和 `reasoning_leak_detected` 只展示元数据，不展示 raw reasoning。

已执行聚焦验证：

```bash
uv run pytest tests/unit/test_llm_reasoning.py tests/unit/test_llm_request_profiles.py tests/unit/test_agent_chat_runtime_reasoning.py tests/unit/test_llm_client_adapter.py tests/unit/test_llm_gateway.py::test_gateway_passes_reasoning_profile_to_client_factory tests/integration/test_llm_config_repo.py tests/integration/test_llm_configs_api.py::test_create_llm_config_uses_runtime_defaults tests/integration/test_llm_configs_api.py::test_create_list_default_flip_and_delete_llm_config tests/integration/test_agent_chat_runtime_sse.py::test_post_message_stream_isolates_structured_reasoning -q
corepack pnpm --dir frontend exec vitest run tests/reasoning-leak-guard.test.ts tests/session-model.test.ts tests/sse.test.ts
corepack pnpm --dir frontend exec tsc --noEmit
```

2026-05-10 最终验收补充：

- 已新增完整 live E2E 文件 `frontend/e2e/agent-reasoning-protocol-live.spec.ts`，该用例默认跳过，设置 `CODEASK_RUN_LIVE_REASONING_PROTOCOL_E2E=1` 后执行。
- 已用当前 admin 的 6 个真实 LLM 配置执行真实 API 会话流验证：逐个只启用一个配置，发送 `请只回复 OK。`，检查 SSE / `session_turns` / traces 均无 `<think>/<thinking>/<reasoning>` 标签泄漏，且都有 assistant turn。
- 已用真实浏览器连接 `http://127.0.0.1:5173` 执行 admin 登录、会话发送、回答渲染和页面文本检查，聊天气泡和行动轨迹未出现 `<think>/<thinking>/<reasoning>` 标签泄漏。
- 已执行全量后端测试 `uv run pytest -q`，退出码为 0。
- 已执行全量前端测试 `corepack pnpm --dir frontend test:run`，37 个测试文件、185 条用例通过。
- 已执行前端类型检查 `corepack pnpm --dir frontend exec tsc --noEmit`，退出码为 0。
- 已执行生产构建 `corepack pnpm --dir frontend build`，退出码为 0；仅有 Vite chunk size warning。
- 已执行 touched-file ruff 检查和 `git diff --check`，退出码为 0。
- 后续发布流水线可用 `frontend/e2e/agent-reasoning-protocol-live.spec.ts` 在具备真实 LLM 配置的数据目录中重复验证。

6 个真实配置验证摘要：

| 配置 | 结果 | reasoning_observed | SSE/turns/traces raw `<think>` |
|---|---:|---:|---:|
| 火山-Anthropic-minimax-m2.7 | 通过 | 3 | 0 |
| 火山-Anthropic-glm-5.1 | 通过 | 156 | 0 |
| 火山-OpenAI-minimax-m2.7 | 通过 | 6 | 0 |
| 火山-OpenAI-glm-5.1 | 通过 | 11 | 0 |
| DeepSeek-OpenAI | 通过 | 12 | 0 |
| DeepSeek-Anthropic | 通过 | 35 | 0 |

验证中发现 `DeepSeek-Anthropic` 对 ChatRuntime 工具 schema 返回过 `tools[0]: unknown variant custom`。已补通用兼容保护：只有 provider 在首包前明确拒绝 tools schema 时，才重试一次无工具请求，避免简单问答失败；该行为有 `tests/unit/test_llm_client_adapter.py::test_initial_tool_schema_error_retries_once_without_tools` 覆盖。

## 2. 当前真实模型池基线

2026-05-10 已通过 admin 配置并完成最小 smoke test 的 6 个配置：

| 配置名称 | 协议 | base_url | 模型 | smoke 结果 | 观察结论 |
|---|---|---|---|---|---|
| 火山-Anthropic-minimax-m2.7 | `anthropic` | `https://ark.cn-beijing.volces.com/api/coding` | `minimax-m2.7` | 通过 | 返回 `reasoning_content` 与干净 `content` |
| 火山-Anthropic-glm-5.1 | `anthropic` | `https://ark.cn-beijing.volces.com/api/coding` | `glm-5.1` | 通过 | 正常会话中返回 `reasoning_content` 与干净 `content`；极简请求中曾出现 `</think>` 泄漏 |
| 火山-OpenAI-minimax-m2.7 | `openai` | `https://ark.cn-beijing.volces.com/api/coding/v3` | `minimax-m2.7` | 通过 | 返回 `reasoning_content` 与干净 `content` |
| 火山-OpenAI-glm-5.1 | `openai` | `https://ark.cn-beijing.volces.com/api/coding/v3` | `glm-5.1` | 通过 | 极简请求中曾出现 `</think>` 泄漏与重复输出 |
| DeepSeek-OpenAI | `openai` | `https://api.deepseek.com` | `deepseek-v4-flash` | 通过 | 返回 `reasoning_content` 与干净 `content` |
| DeepSeek-Anthropic | `anthropic` | `https://api.deepseek.com/anthropic` | `deepseek-v4-flash` | 通过 | 返回 `reasoning_content` 与干净 `content` |

验收时必须覆盖这 6 个配置。若某配置被禁用或删除，测试记录必须说明原因，不能静默跳过。

## 3. 功能验收 Checklist

### 3.1 协议与 Adapter

- [x] OpenAI-compatible `delta.reasoning_content` 转为内部 `reasoning_delta`。
- [x] OpenAI-compatible `delta.reasoning` 转为内部 `reasoning_delta`。
- [x] OpenAI-compatible 结构化 `delta.thinking` 转为内部 `reasoning_delta`。
- [x] OpenAI-compatible `delta.content` 转为内部 `text_delta`。
- [x] 同一个 OpenAI-compatible chunk 同时包含 reasoning 和 content 时，必须同时发出 `reasoning_delta` 与 `text_delta`，不能二选一。
- [x] `delta.content` 中出现 `<think>`、`</think>`、`<thinking>`、`<reasoning>` 时，后端不得扫描、删除或拆分。
- [x] Anthropic `thinking_delta` 转为内部 `reasoning_delta`。
- [x] Anthropic `redacted_thinking` 转为内部 redacted reasoning 事件。
- [x] Anthropic `signature_delta` 不进入普通回答，不展示给普通用户。
- [x] Anthropic `text_delta` 转为内部 `text_delta`。
- [x] 未识别的 provider 字段只进入 shape diagnostic，不得混入回答正文。

### 3.2 Request Profile

- [x] 默认 profile 为 `none`，不能对所有 OpenAI-compatible 配置硬塞 thinking 参数。
- [x] `volcengine_thinking` 只对需要的火山配置生效。
- [x] `vllm_enable_thinking` 使用 `extra_body.chat_template_kwargs.enable_thinking=true`，只对 vLLM / 网关配置生效。
- [x] `anthropic_budget_thinking` 只对明确支持 Anthropic thinking 的配置生效。
- [x] `custom_json` 能承载用户配置的 provider 特殊请求体。
- [x] profile 参数记录在 diagnostic 中，便于排查某次请求是否开启 thinking。
- [x] profile 不能由后端根据模型名硬编码决定。

### 3.3 持久化与上下文隔离

- [x] `reasoning_delta` 不写入 `session_turns.content`。
- [x] `reasoning_delta` 不进入下一轮普通 LLM messages。
- [x] `reasoning_delta` 不进入会话标题生成 prompt。
- [x] `reasoning_delta` 不进入问题报告生成 prompt。
- [x] `reasoning_delta` 不进入普通会话摘要 / compact 结果。
- [x] `reasoning_delta` 不进入用户可见 Markdown 复制内容。
- [x] 停止生成后，本轮 reasoning diagnostic 跟随本轮 trace 一起回滚。
- [x] 删除会话后，本会话 reasoning diagnostic 一起删除。

### 3.4 日志与诊断

- [x] 生产日志默认不打印 raw `reasoning_content_preview`。
- [x] diagnostic 允许记录字段名、字段长度、是否 redacted、provider、model、config id、request profile、session id、turn id。
- [x] diagnostic 不记录 raw reasoning 原文。
- [x] `reasoning_observed` 只对管理员 / debug 模式可见。
- [x] 普通用户只看到公开行动轨迹，不看到模型私有思考链。
- [x] 如果 content 中出现疑似 raw thinking，必须记录 `reasoning_leak_detected` 或等价事件。

### 3.5 UI Leak Guard

- [x] 支持 `disabled` 模式：不遮蔽显示，便于调试暴露上游问题。
- [x] 支持 `warn_only` 模式：不修改显示内容，但显示/记录泄漏诊断。
- [x] 支持 `mask_in_ui` 模式：只在前端显示层遮蔽疑似 raw thinking。
- [x] 默认建议 `mask_in_ui`，保护普通用户体验。
- [x] UI Leak Guard 不修改后端返回的 SSE 内容。
- [x] UI Leak Guard 不修改数据库内容。
- [x] UI Leak Guard 不修改复制到下一轮上下文的内容。
- [x] UI Leak Guard 触发不能算 structured reasoning 协议适配成功。
- [x] UI Leak Guard 必须能处理跨 chunk 的 `<think>` / `</think>` 泄漏。
- [x] UI Leak Guard 必须避免误伤普通 Markdown 代码示例中的 `<think>` 标签；误伤风险必须有测试说明。

### 3.6 Agent 行动轨迹

- [x] 行动轨迹可以展示 `llm_input`，说明本轮请求前的消息数量、可用工具数量、上下文规模和最近工具结果摘要。
- [x] `llm_input` 不展示 prompt 原文、用户完整隐私数据或 raw reasoning，只展示有界结构化摘要。
- [x] 行动轨迹调试摘要必须由 Runtime 事件字段确定性生成，不能为每个事件额外调用 LLM 做摘要。
- [x] 行动轨迹可以展示 `context_prepared`，说明注入了多少特性、Wiki、报告、附件、仓库候选。
- [x] 行动轨迹可以展示 `analysis_note`，但必须来自公开上下文、工具事件、证据链或正式回答。
- [x] `analysis_note.raw_reasoning_used` 必须为 `false`。
- [x] 行动轨迹可以展示 `evidence_selected`、`uncertainty`、`next_step_hint`。
- [x] 行动轨迹不能展示 raw `reasoning_content`。
- [x] 行动轨迹展开详情不能泄漏 raw reasoning。
- [x] 工具结果展开详情可以展示结果条数和有限结果预览，便于审计模型是否拿到了正确仓库、路径和证据。
- [x] 行动轨迹不能因为关键词命中生成“代码证据要求 / 回答约束”等强制代码调查事件；代码工具是否调用仍由模型基于上下文和工具说明决策。
- [x] 行动轨迹按 turn 分组；切换会话、刷新、停止、删除时状态一致。

### 3.7 错误与失败判定

- [x] 鉴权失败、模型名错误、base_url 错误要显示明确失败弹窗或错误气泡。
- [x] 资源繁忙不能持久化成正常 assistant 回答。
- [x] provider 返回 raw thinking 到 content 时，本轮可继续回答，但 E2E 记录应标记为 `provider_content_leak`。
- [x] provider 不返回 reasoning 字段也不算失败，只要 content 正常，按普通模型处理。
- [x] structured reasoning 验收通过的必要条件是“结构化字段被隔离”，不是“前端看不到 `<think>`”。

## 4. 自动化测试 Checklist

### 4.1 后端单元测试

- [x] `tests/unit/test_llm_reasoning.py`
  - `reasoning_content -> reasoning_delta`
  - `reasoning -> reasoning_delta`
  - `thinking -> reasoning_delta`
  - `content -> text_delta`
  - 同 chunk reasoning + content 双事件
  - content 中 `<think>` 不被后端解析
- [x] `tests/unit/test_llm_request_profiles.py`
  - `none`
  - `volcengine_thinking`
  - `vllm_enable_thinking`
  - `anthropic_budget_thinking`
  - `custom_json`
- [x] `tests/unit/test_llm_client_adapter.py`
  - OpenAI-compatible stream shape
  - Anthropic stream shape
  - 工具调用与 reasoning 同时出现时不互相污染

### 4.2 后端集成测试

- [x] `tests/integration/test_agent_chat_runtime_sse.py`
  - SSE 不向普通聊天发送 `reasoning_delta`。
  - SSE 可以发送 diagnostic 事件，但不含 raw reasoning。
- [x] `tests/integration/test_sessions_api.py`
  - `session_turns.content` 只保存正式回答。
  - 停止生成回滚 reasoning diagnostic。
  - 删除会话清理 reasoning diagnostic。
- [x] `tests/integration/test_session_report_generation.py`
  - 报告 prompt 不包含 raw reasoning。
  - 报告正文不包含 raw reasoning。
  - 标题生成不包含 raw reasoning。
- [x] `tests/integration/test_agent_chat_runtime.py`
  - 下一轮模型 messages 不包含上一轮 raw reasoning。

### 4.3 前端组件测试

- [x] `frontend/tests/reasoning-leak-guard.test.ts`
  - `disabled`
  - `warn_only`
  - `mask_in_ui`
  - 跨 chunk 泄漏
  - Markdown 代码示例误伤防护
- [x] `frontend/tests/session-workspace.test.tsx`
  - `reasoning_delta` 不进入聊天气泡。
  - `reasoning_leak_detected` 进入行动轨迹或诊断提示。
  - 停止生成后本轮诊断回滚。
- [x] `frontend/tests/action-trace-analysis-note.test.tsx`
  - `analysis_note` 展示公开摘要。
  - `reasoning_observed` 普通用户不可见 raw 内容。

## 5. 真实前后端 E2E 场景

真实 E2E 必须从浏览器发起请求，经 Vite dev server / FastAPI / LLMGateway / 真实模型完整链路返回，不允许只用后端脚本代替。

推荐文件：

```text
frontend/e2e/agent-reasoning-protocol-live.spec.ts
```

显式运行命令：

```bash
CODEASK_RUN_LIVE_REASONING_PROTOCOL_E2E=1 \
CODEASK_LIVE_REASONING_MODELS='volcengine-anthropic-minimax,volcengine-anthropic-glm,volcengine-openai-minimax,volcengine-openai-glm,deepseek-openai,deepseek-anthropic' \
corepack pnpm --dir frontend exec playwright test frontend/e2e/agent-reasoning-protocol-live.spec.ts --workers=1
```

### E2E-022-A 配置可用性与真实字段观测

步骤：

1. 使用 admin 登录前端。
2. 打开设置页，确认 6 个 LLM 配置存在且启用。
3. 对每个配置创建独立会话。
4. 发送 `请只回复 OK。`
5. 等待回答完成。
6. 从后端 diagnostic / trace / test hook 读取 observed stream fields。

验收：

- 6 个配置都能完成请求，或失败时记录明确失败原因。
- 每个配置记录：
  - config id；
  - config name；
  - protocol；
  - model；
  - base_url host；
  - request profile；
  - observed fields/events；
  - answer preview；
  - 是否出现 `reasoning_delta`；
  - 是否出现 `reasoning_leak_detected`。
- 如果 content 中出现 `</think>`，该配置标记为 `provider_content_leak`，不能标记为协议适配成功。

### E2E-022-B OpenAI-compatible 结构化字段隔离

覆盖配置：

- 火山-OpenAI-minimax-m2.7
- 火山-OpenAI-glm-5.1
- DeepSeek-OpenAI

步骤：

1. 在前端选择或临时指定 OpenAI-compatible 配置。
2. 新建会话。
3. 发送 `你好，请用一句话介绍你自己。`
4. 等待流式输出完成。
5. 刷新页面。
6. 追问 `你刚刚回答了什么？`
7. 打开生成问题报告弹窗，生成报告草稿。

验收：

- 聊天气泡只显示 `content` 正式回答。
- `reasoning_content/reasoning/thinking` 不显示在聊天气泡。
- 刷新后历史消息不包含 raw reasoning。
- 追问时模型能看到正式回答历史，但看不到 raw reasoning。
- 报告草稿不包含 raw reasoning。
- 自动标题不包含 raw reasoning。
- 行动轨迹只展示公开分析摘要和 diagnostic 元数据。

### E2E-022-C Anthropic 协议结构化字段隔离

覆盖配置：

- 火山-Anthropic-minimax-m2.7
- 火山-Anthropic-glm-5.1
- DeepSeek-Anthropic

步骤：

1. 在前端选择或临时指定 Anthropic 配置。
2. 新建会话。
3. 发送 `你好，请用一句话介绍你自己。`
4. 等待回答完成。
5. 查看行动轨迹详情。
6. 刷新页面后继续追问。

验收：

- `thinking_delta/redacted_thinking/reasoning_content` 不进入聊天气泡。
- `text_delta/content` 正常展示。
- 普通用户看不到 raw thinking。
- 管理员 debug 最多看到字段名、长度和 redacted 标记。
- 刷新后历史和下一轮上下文无 raw reasoning。

### E2E-022-D UI Leak Guard 三模式

步骤：

1. 使用 mock provider 或已知会泄漏的 GLM 请求构造 `content="<think>内部</think>正式回答"`。
2. 设置 leak guard 为 `disabled`。
3. 发送消息，确认泄漏可被测试检测到。
4. 设置 leak guard 为 `warn_only`。
5. 发送消息，确认出现诊断但不遮蔽显示。
6. 设置 leak guard 为 `mask_in_ui`。
7. 发送消息，确认聊天气泡遮蔽 raw thinking，仅显示正式回答或安全占位。

验收：

- 三种模式行为不同且可预测。
- 三种模式都不修改数据库中的原始 assistant content。
- `warn_only` 和 `mask_in_ui` 都记录 `reasoning_leak_detected`。
- `mask_in_ui` 的通过不能让该 provider 标记为 structured reasoning 成功。

### E2E-022-E 停止生成与回滚

步骤：

1. 使用会产生较长 reasoning 的配置创建会话。
2. 发送复杂问题，例如 `解释 CodeAsk 和 AnythingLLM 在 RAG 召回上的差异。`
3. 生成中点击停止。
4. 刷新页面。
5. 追问 `我刚刚问到哪里了？`

验收：

- 本轮 user message 被回滚。
- 本轮 partial assistant message 被回滚。
- 本轮 reasoning diagnostic / analysis note / action trace 被回滚。
- 下一轮模型上下文不知道被停止的那轮内容。

### E2E-022-F 会话报告与标题反污染

步骤：

1. 使用会返回 reasoning 字段的配置创建会话。
2. 完成一轮问答。
3. 等待自动标题生成。
4. 生成问题报告草稿。
5. 保存报告。

验收：

- 标题满足 `YYYY-MM-DD 问题描述` 或用户自定义标题规则。
- 标题不含 raw reasoning。
- 报告正文不含 raw reasoning。
- 报告关联的 Wiki / 问题报告预览不含 raw reasoning。

## 6. E2E 结果记录模板

每次执行真实 E2E 后，在提交说明或验收记录中保留以下信息：

```text
日期：
执行人：
前端地址：
后端地址：
commit：

配置：
- config_id:
- name:
- protocol:
- model:
- request_profile:

会话：
- session_id:
- first_turn_id:
- report_id: 可选

观测：
- observed_fields:
- observed_events:
- has_reasoning_delta:
- has_text_delta:
- has_reasoning_leak_detected:
- visible_answer_preview:
- persisted_turn_preview:
- title_preview:
- report_preview:

判定：
- pass/fail:
- failure_type: auth_error | model_error | provider_content_leak | persistence_leak | ui_leak | context_leak | report_leak | title_leak | unknown
- notes:
```

## 7. 开发准入与收口门禁

开发前必须满足：

- [x] 本文已被用户确认。
- [x] `docs/v1.0.2/plans/structured-reasoning.md` 引用本文。
- [x] `docs/v1.0.2/plans/acceptance-checklist.md` 引用本文。
- [x] `docs/v1.0.2/plans/e2e-scenarios.md` 引用本文。

收口前必须满足：

- [x] 所有后端单元测试通过。
- [x] 所有后端集成测试通过。
- [x] 所有前端组件测试通过。
- [x] `frontend/e2e/agent-reasoning-protocol-live.spec.ts` 至少跑通一次真实前后端交互。
- [x] 6 个真实 LLM 配置全部有测试记录；失败配置有明确原因。
- [x] 任何 raw reasoning 泄漏都能定位到 provider/content leak、UI leak、persistence leak、context leak、report leak 或 title leak。
