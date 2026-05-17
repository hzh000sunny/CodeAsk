# v1.0.4 OpenCode Backend 验收清单

> 状态：Manual Acceptance Completed
> 版本：v1.0.4
> 范围：opencode 兼容模块、shared opencode server、workspace/Wiki/worktree、remote MCP、前端会话行动轨迹、多环境 E2E
> 项目级验收规则：见 `../../DEVELOPMENT_ACCEPTANCE.md`

---

## 0. 验收原则

状态标记：

- `[x]` 已验证并有记录。
- `[ ]` 未完成或未执行。
- `[~]` 部分完成，仍需补测试或产品接入。

v1.0.4 收口前必须满足：

- `open-issues-and-optimization-backlog.md` 中所有 `P0` 项已关闭，或由用户明确同意延期并迁移到 future / 下一版本。
- 新会话默认走 `src/codeask/agent/opencode_compat/`，不静默回退 native Agent。
- 一个 shared `opencode serve` 常驻进程服务多个 CodeAsk 会话。
- 每个 CodeAsk 会话有独立 workspace、`opencode.json`、opencode session 和 MCP token。
- 所有 opencode HTTP 请求携带 `directory=<workspace>`。
- Wiki 主路径是 opencode grep/read `./wiki/`，不是旧 `search_wiki`。
- MCP tools 面向 opencode 重写，不包装旧 Agent tools。
- 前端行动轨迹按 opencode 原始事件重新设计。
- 每个环境的 E2E 测试必须记录执行命令、数据目录、模型配置、会话 id 和结论。

---

## 1. Phase 0 已完成验证

- [x] opencode 版本：`1.14.48`。
- [x] `opencode serve` 可启动，`/global/health` 返回健康。
- [x] Basic Auth 生效，未授权请求返回 401。
- [x] `POST /session` 可创建 session。
- [x] 主发送路径使用 `POST /session/:id/prompt_async`，返回 `204`。
- [x] 消息读取路径是 `GET /session/:id/message`，不是 `/messages`。
- [x] `/global/event` 带 `directory`，适合 shared server 多 workspace 归属。
- [x] 真实 LLM 配置矩阵已验证：OpenAI-compatible、Anthropic Bearer、Anthropic `/v1` Bearer 等显式 provider 可通过对应配置。
- [x] 同 URL 双协议网关回归：OpenAI 和 Anthropic 均不得由 CodeAsk 改写用户配置的 `base_url`。
- [x] provider profile 手动测试结果写入配置；保存配置时不自动联网测试。
- [x] shared server 三会话并发真实 LLM smoke 通过。
- [x] shared server 下 workspace 级 provider 配置隔离通过。
- [x] shared server 下 workspace 级 remote MCP endpoint/token 隔离通过。
- [x] remote StreamableHTTP MCP `initialize`、`tools/list`、`tools/call` 通过。
- [x] `/global/event` 中 MCP tool、reasoning、sync 噪声样本已记录。
- [x] Wiki symlink 挂载可被 opencode read。
- [x] 删除 `workspace/wiki` symlink 不删除真实 Wiki，重新创建后可恢复。
- [x] 现有 `WorktreeManager` 可创建和清理 session worktree。
- [x] shared server 换端口重启后，可读取原 session message 并继续第二轮 prompt。
- [x] deny Bash/Edit/Write 时，模型尝试 Bash 会得到 `invalid` tool 事件，不会静默失败。

证据文档：`../specs/opencode-1.14.48-phase0-spike.md`。

### 1.1 2026-05-15 显式 Agent 适配方式回归记录

- [x] 迁移后所有旧 LLM 配置默认值为 `default`，按新策略不会隐式轮转。
- [x] 使用 live smoke 验证当前 `default` 真实行为：DeepSeek Anthropic native 通过；DeepSeek/火山 OpenAI-compatible 与火山 Anthropic-compatible 需要用户显式选择对应 provider。
- [x] 本地真实配置已按显式选择更新：OpenAI-compatible 网关使用 `openai-compatible`；火山 Anthropic 使用 `anthropic-compatible-v1-bearer`；DeepSeek Anthropic 保持 `default`。
- [x] `CODEASK_LIVE_LLM_CONFIG_SMOKE=1 CODEASK_LIVE_LLM_SMOKE_TIMEOUT=180 uv run pytest tests/live/test_live_opencode_llm_configs.py -q -s` 已覆盖 9 条真实 LLM 配置，包括 disabled 配置，全部通过。
- [x] 真实浏览器 E2E 已验证：管理员登录、设置页展示 Agent 适配方式、点击“测试连接”、发送一轮真实会话；成功会话 `sess_600c127c5732b621`，模型 `glm-5.1`，provider `anthropic-compatible-v1-bearer`，落库 2 个 turn、7 条 Agent trace。

### 1.2 2026-05-15 opencode 会话 LLMGateway 调度回归

- [x] 根因确认：opencode 会话路径曾直接调用 `llm_config_repo.get_default_or(None, ...)`，当多条全局 LLM 配置同时启用且没有默认配置时，会触发 `Multiple rows were found when one or none was required`。
- [x] 修复边界：opencode 路径只复用 `LLMGateway` 的配置选择、全局池随机选择、会话粘性、最大连接数和失败冷却能力，不复用旧 native LLM 请求执行链路。
- [x] `agent_runtime_profile`、`protocol`、`base_url`、`model_name` 等配置字段由网关选中后原样传给 `opencode_compat`，provider 配置生成仍由 opencode 兼容模块独立负责；历史 `opencode_provider_profile` 保留为兼容别名。
- [x] 禁止“多条启用配置取第一条”的兜底；没有个人配置时必须从启用全局池随机选择。
- [x] 自动化回归：`uv run pytest tests/unit/test_llm_gateway.py tests/integration/test_opencode_session_stream.py tests/integration/test_llm_config_repo.py -q` -> `32 passed`。
- [x] 全量后端回归：`uv run pytest -q` -> 通过，live LLM smoke 按默认跳过。
- [x] 格式和 lint：`uv run ruff format --check src tests`、`uv run ruff check src tests` -> 通过。
- [x] 真实 LLM 配置 E2E：`CODEASK_LIVE_LLM_CONFIG_SMOKE=1 CODEASK_LIVE_LLM_SMOKE_TIMEOUT=180 uv run pytest tests/live/test_live_opencode_llm_configs.py -q -s` -> 当前数据库 9 条配置全部通过。
- [x] 真实会话 API E2E：会话 `sess_0fb72d2fb7d6912c`，turn `turn_gateway_e2e_001`，经全局池选择 `cfg_24bc87bc49e75ed9` / `minimax-m2.7` / `anthropic`，成功返回 `done`，未再出现多行配置查询错误。
- [x] 真实浏览器 E2E：`CODEASK_RUN_LIVE_OPENCODE_E2E=1 CODEASK_REALDATA_BASE_URL=http://127.0.0.1:5173 corepack pnpm --dir frontend exec playwright test -c playwright.realdata.config.ts e2e/opencode-backend-live.spec.ts --project=chromium` -> 通过；会话 `sess_45de5ee331161238`。测试已按全局池随机选择更新为“命中任一启用配置”，不再假设第一条启用配置。

### 1.3 2026-05-15 LLM 配置新增/编辑态测试状态回归

- [x] 根因确认：新增/编辑表单“测试连接”曾只产生前端临时提示或草稿测试结果，没有把 `opencode_provider_status` 写入数据库；刷新后列表会回到 `未测试`。后续临时修正又把编辑态“测试连接”做成先保存再测试，违反表单语义。
- [x] 最终数据流：列表行“测试连接”测试已保存配置并立即落库；新增/编辑表单“测试连接”只测试当前表单草稿，不提前保存 provider；测试结果作为隐藏表单状态，用户点击保存时和表单字段一起提交落库。
- [x] API 语义：新增通用 `agent_runtime_profile` / `agent_runtime_status` / `agent_runtime_*` 响应字段；前端新增/编辑表单提交通用 `agent_runtime_profile`，不再把 OpenCode 字段作为主语义。历史 `opencode_provider_*` 继续返回和接收，作为 v1.0.4 向后兼容层。
- [x] 状态字段：新增和更新保存时允许提交测试状态；后端创建时直接写入 `llm_runtime_adapters` 并同步历史 `opencode_provider_status`、`opencode_provider_tested_at`、`opencode_provider_error`、`opencode_provider_test_result_json`；更新时在连接字段变化后如果本次 PATCH 同时携带测试状态，则以表单测试状态为准。
- [x] 列表数据源：`/api/*/llm-configs` 列表优先读取 `llm_runtime_adapters` 中对应 runtime backend 的 profile/status/test result，避免新 adapter 表和旧 `llm_configs.opencode_*` 字段不一致时 UI 显示旧状态。
- [x] 访客配置：浏览器本地访客 LLM 配置改为保存 `agent_runtime_profile`；读取旧版本 `opencode_provider_profile` 时自动迁移为通用字段；会话发送和后端 `GuestLLMConfigIn` 均支持通用字段。
- [x] 前端边界：新增/编辑表单内协议、Base URL、API Key、模型名称、Agent 适配方式或配置名称变化时，清空上一次草稿测试结果，避免旧测试状态污染新配置。
- [x] UI 约束：列表只展示数据库返回的真实状态 `连接正常` / `连接失败` / `未测试`；不再展示“当前表单测试通过”这类非持久化状态。
- [x] 自动化回归：`uv run pytest tests/integration/test_llm_configs_api.py -q` -> `12 passed`；`corepack pnpm --dir frontend exec vitest run tests/guest-llm-config.test.ts tests/sse.test.ts tests/settings-page.test.tsx` -> `19 passed`。
- [x] 静态检查：`uv run ruff check ...`、`uv run ruff format --check ...`、`corepack pnpm --dir frontend exec eslint ...`、`corepack pnpm --dir frontend exec tsc --noEmit` 均通过。
- [x] 真实浏览器验证：管理员登录设置页，配置 `火山-Anthropic-minimax-m2.7` 初始显示 `未测试`；编辑表单点击“测试连接”命中 `/test-draft` 并返回 `ok`，列表仍显示 `未测试`；点击“保存修改”后数据库写入 `opencode_provider_status=ok`；刷新后列表显示 `连接正常`。新增表单已补自动化回归，要求测试后保存请求携带并落库同一组状态字段。

### 1.4 2026-05-16 P0 收敛自动化回归记录

- [x] 动态上下文：每轮 opencode turn 注入 CodeAsk session/workspace、已绑定特性、活跃特性目录、仓库目录、附件摘要、Wiki 入口、MCP 工具摘要，并写入 `CODEASK_CONTEXT.md`。
- [x] 动态上下文快照：每轮 opencode turn 在发送 prompt 前记录 `codeask_context_snapshot` 摘要，只保存 prompt/context 字符数和 Wiki manifest 元数据，不保存上下文原文。
- [x] MCP 工具契约：`list_features`、`get_feature_info`、`list_feature_repos`、`prepare_worktree` 已支持自然语言场景下的 query/name/repo_name/reason，并返回候选和 recovery hint，不替模型做业务判断。
- [x] opencode 进程输出：默认 `opencode serve` stdout/stderr 写入 `data/agent_sessions/opencode/logs/opencode-server.log`，不再保留无人消费的 PIPE。
- [x] opencode 诊断：`OpenCodeProcessManager.describe()` 返回 configured/resolved bin、version、pid、port、log file、last error、last health time；`GET /api/admin/opencode/status` 仅 admin 可访问且无副作用。
- [x] opencode 不可用分类：`bin missing/start failed/process exited/health timeout/version unsupported` 均有稳定错误 code；SSE `error` 会保留该 code 给前端诊断。
- [x] 会话清理：`OpenCodeCompat.cleanup_session` 清理 session workspace 和 `data/repos/*/worktrees/<session_id>`；单删和批量删除均调用统一入口。
- [x] 前端会话流：active stream state/snapshot 提升为模块级 store；切换会话时消息、行动轨迹、模型状态同步恢复；前端主链路不再执行 `<think>` 标签过滤。
- [x] reasoning 语义：opencode 结构化 reasoning part 继续映射为 `reasoning_observed`；正文中泄漏的 `<think>` 仅作为 `reasoning_leak_detected` / `backend_content_guard` 异常防线记录，不再冒充正常 reasoning。
- [x] MCP schema 防漂移：新增 `tools/list` 契约快照，固定 v1.0.4 工具名称和关键 JSON 参数，同时确认旧报告检索 wrapper 不再暴露给 opencode。
- [x] runtime context 指标：新增 `context_used/context_window/context_unit/context_metric_source`，旧字段保留兼容。
- [x] context window 默认 200k 但不再写死：`CODEASK_MODEL_CONTEXT_WINDOW_TOKENS` 可覆盖，初始 runtime_state 和 opencode usage runtime_state 共用该配置。
- [x] 自动化验证：`uv run pytest tests/unit/test_opencode_compat_context.py tests/unit/test_opencode_compat_backend.py tests/unit/test_opencode_compat_mcp_feature_tools.py tests/unit/test_opencode_compat_mcp_worktree_tools.py tests/unit/test_opencode_compat_mcp_session_tools.py tests/unit/test_opencode_compat_process.py tests/unit/test_opencode_compat_worktrees.py tests/integration/test_opencode_mcp_app_integration.py tests/integration/test_opencode_session_stream.py -q` -> 通过。
- [x] 2026-05-16 P1 诊断回归：`uv run pytest tests/unit/test_opencode_compat_backend.py tests/unit/test_opencode_compat_process.py tests/integration/test_healthz.py tests/integration/test_opencode_wiki_workspace.py -q` -> 通过。
- [x] 前端验证：`corepack pnpm --dir frontend exec vitest run tests/session-workspace.test.tsx tests/session-model.test.ts tests/investigation-panel.test.tsx tests/reasoning-leak-guard.test.ts` -> 通过；`corepack pnpm --dir frontend exec tsc --noEmit` -> 通过。
- [x] 真实浏览器验证：`CODEASK_RUN_LIVE_OPENCODE_E2E=1 CODEASK_REALDATA_BASE_URL=http://127.0.0.1:5173 CODEASK_REAL_DATA_DIR=/home/hzh/.codeask corepack pnpm --dir frontend exec playwright test -c playwright.realdata.config.ts e2e/opencode-backend-live.spec.ts --project=chromium` -> 通过；最新会话 `sess_b9d211700d576a2b`。
- [x] 刷新后继续追问验证：`opencode-backend-live.spec.ts` 已扩展为第一轮完成后进入会话页、刷新浏览器、继续第二轮追问，并验证 DB turn 顺序为 `user/agent/user/agent`；最新通过会话 `sess_b4d80f36a5122639`。
- [x] 停止生成真实浏览器验证：`corepack pnpm --dir frontend exec playwright test e2e/session-stop.spec.ts --project=chromium` -> 通过；验证点击“停止”后 abort 请求发出，临时 user/assistant 消息和临时行动轨迹从 UI 回滚。
- [x] opencode 不可用真实浏览器验证：`corepack pnpm --dir frontend exec playwright test e2e/opencode-unavailable.spec.ts --project=chromium` -> 通过；验证 `opencode_bin_missing` 随失败弹窗展示。
- [x] v1.0.3 升级 smoke：临时数据目录先执行 `uv run alembic upgrade 0025`，再用当前 `start.sh` 启动；结果 `before=0025 after=0028`，`/api/healthz` 正常，opencode shared server 正常拉起。
- [x] 真实浏览器自然语言链路验证：会话 `sess_9c60f250bb43a87f` 按普通用户话术连续提问“anything llm 是怎么处理召回的？”→“源码里对应是怎么实现的？”→“结合源码重新解释一下。”；第一轮模型自主调用 `codeask_list_features`、`codeask_get_feature_info`、`codeask_bind_session_features`、`glob/grep/read`，第二轮自主调用 `codeask_list_feature_repos`、`codeask_prepare_worktree`、`grep/read`，第三轮基于已有上下文直接回答。
- [x] 全量前端回归：`corepack pnpm --dir frontend exec vitest run` -> 42 个测试文件、217 条测试全部通过。
- [x] 全量后端回归：`uv run pytest -q` -> 通过；live LLM config smoke 因未设置 `CODEASK_LIVE_LLM_CONFIG_SMOKE=1` 按设计跳过 1 条。
- [x] 真实 LLM 配置 smoke：`CODEASK_LIVE_LLM_CONFIG_SMOKE=1 CODEASK_LIVE_LLM_SMOKE_TIMEOUT=180 uv run pytest tests/live/test_live_opencode_llm_configs.py -q -s` -> 当前数据库 9 条配置全部通过，覆盖 DeepSeek Anthropic/OpenAI、火山 Anthropic/OpenAI、GLM 5.1、MiniMax M2.7。
- [x] 2026-05-16 最终真实 LLM 配置 smoke 重跑：同一命令再次覆盖 9 条配置，全部 `PASS`。
- [x] 2026-05-16 最终真实浏览器 live E2E 重跑：`CODEASK_RUN_LIVE_OPENCODE_E2E=1 CODEASK_REALDATA_BASE_URL=http://127.0.0.1:5173 CODEASK_REAL_DATA_DIR=/home/hzh/.codeask corepack pnpm --dir frontend exec playwright test -c playwright.realdata.config.ts e2e/opencode-backend-live.spec.ts --project=chromium` -> `1 passed`。

### 1.5 2026-05-17 设置页子路由与生产构建回归

- [x] 根因确认：设置页内部 admin 子页面曾只保存在组件本地 `useState("runtime")` 中，浏览器刷新后组件重建，导致无论刷新前选择哪个设置子页面，都会回到“运行状态”。
- [x] 修复边界：设置页子页面进入 hash route query，例如 `#/settings?page=llm`、`#/settings?page=repos`；刷新、复制链接、重新挂载 App 后均按 URL 恢复子页面。
- [x] 自动化回归：`corepack pnpm --dir frontend exec vitest run tests/settings-page.test.tsx tests/wiki-routing.test.ts` -> `18 passed`；`corepack pnpm --dir frontend exec tsc --noEmit` -> 通过；相关文件 eslint -> 通过。
- [x] 开发服务器真实浏览器验证：登录 admin，进入设置页，切换到 `LLM 配置`，URL 变为 `#/settings?page=llm`，刷新后仍停留在 `LLM 配置`；输出 `browser-settings-subpage-refresh: PASS`。
- [x] 生产构建验证：先执行 `corepack pnpm --dir frontend build`，再用 `start.sh` 服务 `frontend/dist`，临时空库真实浏览器验证同样通过；输出 `temp-start-admin-settings: PASS`。
- [x] 部署注意：`start.sh` 只在 `frontend/dist/index.html` 不存在时自动构建。离线替换代码升级时，如果已有旧 `frontend/dist`，必须按升级文档先执行前端 build，否则后端会继续服务旧构建产物。

### 1.6 2026-05-18 Agent 事件路径脱敏与人工验收收口

- [x] 根因确认：前端行动轨迹卡片和 Network 中的 Agent 事件可能展示 opencode workspace 或宿主机上的绝对路径，例如 `CODEASK_DATA_DIR/agent_sessions/opencode/<session_id>/workspace/...`。
- [x] 修复边界：只在返回给前端的数据出口做脱敏；数据库 `agent_traces.payload`、raw opencode JSONL、opencode 工具参数、模型上下文、报告生成链路均保留原始事实，不受影响。
- [x] SSE 返回脱敏：`/api/sessions/{id}/messages` 流中的非 `text_delta/done` Agent 事件在返回前使用 payload 副本脱敏。
- [x] 历史行动轨迹脱敏：`/api/sessions/{id}/traces` 返回前对 `payload` 副本脱敏。
- [x] 当前会话目录内绝对路径显示为会话相对路径；非当前会话或外部宿主机绝对路径显示为 `[外部绝对路径已隐藏]`。
- [x] 前端保留展示层兜底脱敏，防止旧接口或历史数据绕过后端出口脱敏。
- [x] 验证：`uv run pytest tests/unit/test_session_trace_redaction.py -q` -> `2 passed`。
- [x] 验证：`corepack pnpm --dir frontend exec vitest run tests/action-trace-scope.test.tsx` -> `7 passed`。
- [x] 验证：`uv run ruff check src/codeask/sessions/trace_redaction.py src/codeask/sessions/messages.py src/codeask/api/sessions.py tests/unit/test_session_trace_redaction.py` -> `All checks passed!`。
- [x] 验证：`uv run ruff format --check src/codeask/sessions/trace_redaction.py src/codeask/sessions/messages.py src/codeask/api/sessions.py tests/unit/test_session_trace_redaction.py` -> 通过。
- [x] 验证：`corepack pnpm --dir frontend exec eslint src/components/session/action-trace/ActionTraceEvent.tsx src/components/session/action-trace/path-redaction.ts tests/action-trace-scope.test.tsx --max-warnings=0` -> 通过。
- [x] 验证：`corepack pnpm --dir frontend exec tsc --noEmit` -> 通过。
- [x] 人工验收：用户已确认人工验证和版本验收完成；本次提交只推送 `main`，不推送 `v1.0.4` 分支。

---

## 2. 模块验收清单

### 2.0 `backend.py`

- [x] `OpenCodeCompat.initialize_session(...)` 创建 opencode session 绑定。
- [x] `OpenCodeCompat.run_turn(...)` 发送 `prompt_async` 并消费 `/global/event`。
- [x] shared server 崩溃或端口变化后恢复：每轮初始化/运行都会取最新 server handle，并在请求前等待 `/global/health`；同配置同 workspace 下复用原 external session，只更新记录中的 server url/port/pid。
- [x] `OpenCodeCompat.cleanup_session(...)` 只清理会话级资源，不关闭 shared server。
- [x] opencode 不可用时返回 SSE `error`，前端走居中错误弹窗，不回退 native runtime。
- [x] 测试：`initialize_session`、最小 `run_turn`、异常转 SSE error、启动健康等待、真实浏览器 smoke 已覆盖。

### 2.1 `sessions.py`

- [x] 创建 `external_agent_sessions` migration。
- [x] `ExternalAgentSession` 记录 CodeAsk session id、opencode session id、workspace、server url/port、config hash、状态和错误摘要。
- [x] CodeAsk session 重复发送消息时复用原 opencode session，配置变化时才重建。
- [x] opencode server 重启换端口后，初始化路径会更新记录中的当前 server handle。
- [x] 删除 CodeAsk session 时，当前会清理 opencode workspace 目录和 session worktree；绑定记录依赖 DB 外键级联。
- [x] 测试：DB create/upsert/mark_error、server binding 更新、缺失查询、删除 workspace、批量删除 cleanup 已覆盖。

### 2.2 `workspace.py`

- [x] 创建会话目录：`workspace/`、`attachments/`、`config/`、`logs/`。
- [x] `workspace/wiki` 指向持久化 Wiki 工作区，零复制，不复制整库。
- [x] `workspace/wiki` symlink 被删除后，下次 `prepare_workspace` 自动恢复。
- [x] Wiki 工作区导出会清理路径片段中的越界和分隔符，不允许 `../` 写出工作区。
- [x] 测试：symlink 创建、删除恢复、重复调用幂等、真实 Wiki/报告导出已覆盖。

### 2.3 `config.py` / `profiles.py`

- [x] 生成 workspace 级 `opencode.json`。
- [x] `default` 使用 opencode native provider：OpenAI -> `@ai-sdk/openai`，Anthropic -> `@ai-sdk/anthropic`。
- [x] 支持显式选择 `openai-compatible`、`anthropic-compatible-bearer`、`anthropic-compatible-v1-bearer`、`openrouter`。
- [x] `anthropic-compatible-v1-bearer` 只有在用户显式选择时追加 `/v1`，不作为默认无条件 URL 改写。
- [x] 不根据厂商名、模型名、URL 域名做业务特判。
- [x] 会话启动只使用当前显式选择的 provider，不做隐式轮转或 fallback。
- [x] 配置新增/修改时不自动联网测试；协议、URL、API Key、模型名、provider 变化时清理旧测试状态。
- [x] LLM 配置管理页提供“测试连接”按钮，只测试当前显式 provider；列表行测试直接写入成功/失败状态，新增/编辑表单测试只写入表单隐藏状态并在保存时落库。
- [x] `permission` 默认 deny Bash/Edit/Write，allow read/grep/glob。
- [x] remote MCP 配置包含会话级 Bearer token 和 session header。
- [x] 测试：OpenAI/Anthropic 配置快照、permission 快照、MCP 快照、未知 provider 错误、手动测试接口。
- [x] external directory allowlist 不暴露整个数据目录：`external_directory` 固定 `* = deny`，只放行当前 session 的 Wiki symlink target 和 worktree target pattern。

### 2.4 `process.py`

- [x] 启动一个 shared `opencode serve` 常驻进程。
- [x] 进程退出后重启并允许重新分配端口；请求前等待 `/global/health`。
- [x] CodeAsk 退出时关闭 shared opencode server。
- [x] 单个会话闲置清理不关闭 shared server。
- [x] opencode bin 不存在或版本不匹配时返回明确错误：bin missing / start failed / process exited / health timeout / version unsupported 均已分类。
- [x] `describe()` 可返回 opencode 版本、日志文件和最近一次 health 成功时间；admin 诊断接口可读取该状态。
- [x] 测试：端口分配、进程退出重启、健康等待、stdout/stderr 日志写入、启动失败分类、健康超时、版本不支持、版本记录和 admin 状态接口已覆盖。

### 2.5 `http.py`

- [x] 封装 `/global/health`。
- [x] 封装 `POST /session?directory=<workspace>`。
- [x] 封装 `POST /session/:id/prompt_async?directory=<workspace>`。
- [x] 封装 `GET /session/:id/message?directory=<workspace>`。
- [x] 封装 `/global/event` SSE 消费。
- [x] 封装基础 `abort`；深度 `abort + revert` 回滚列遗留增强项。
- [x] 所有已实现请求都必须携带 `directory`。
- [x] 测试：fake opencode HTTP 验证已实现路径、参数和 SSE；abort 基础委托、opencode unavailable、SSE error 映射已覆盖。

### 2.6 `events.py`

- [x] 原始 `/global/event` 事件写入 JSONL。
- [x] 按 `directory + sessionID` 归属事件。
- [x] 折叠或降噪 `sync` 事件。
- [x] 映射 text delta 到聊天气泡。
- [x] 映射 opencode 内置工具到行动轨迹。
- [x] 映射 CodeAsk MCP tool 到行动轨迹。
- [x] 映射结构化 reasoning 为可审计观察事件，不展示 raw reasoning 原文；正文 `<think>` 泄漏只记异常 guard 事件。
- [x] 同一个 reasoning part 已做降噪：只保留首个非空观察和大幅增长观察，避免“模型推理已隔离”刷屏。
- [x] 错误事件必须能触发居中错误弹窗。
- [x] 测试：tool part、reasoning part、sync 折叠、raw JSONL、前端错误弹窗路径已覆盖。

### 2.7 `worktrees.py`

- [x] 复用 `codeask.code_index.worktree.WorktreeManager`。
- [x] 支持用户显式指定仓库时准备 worktree。
- [x] 支持模型通过 MCP 请求准备某个特性关联仓库。
- [x] workspace 内暴露相对路径，方便 opencode grep/read。
- [x] 清理会话时清理对应 worktree。
- [x] 测试：路径暴露、清理委托、API 删除 cleanup 已覆盖；local_dir repo 真实 prepare_worktree 集成 E2E 已覆盖。

### 2.8 `mcp/server.py` / `mcp/auth.py`

- [x] FastAPI 注册 opencode 专用 MCP endpoint。
- [x] 支持 StreamableHTTP `initialize`。
- [x] 支持 `notifications/initialized`。
- [x] 支持 `tools/list`。
- [x] 支持 `tools/call`。
- [x] Bearer token 与 CodeAsk session 绑定，跨会话 token 拒绝。
- [x] headers 中保留 `X-CodeAsk-Session` 可审计 session 信息。
- [x] 测试：MCP protocol 集成、token 正反例、跨会话拒绝。
- [x] FastAPI app 集成路径已验证跨 session MCP token 拒绝：`sess_allowed` token 请求 `sess_other` 返回 `401 invalid mcp token`。

### 2.8.1 FastAPI 生命周期接入

- [x] app lifespan 注册 `opencode_mcp_server`。
- [x] app lifespan 注册 `opencode_compat`。
- [x] app lifespan 在 `agent_backend=opencode` 时 best-effort 拉起 shared `opencode serve`，并注册 `opencode_keepalive` 定时任务；失败只记录错误，不阻塞 CodeAsk 主服务启动。
- [x] app shutdown 调用 shared opencode process manager 清理。
- [x] 默认 MCP base URL 使用后端本机地址，可通过 `CODEASK_OPENCODE_MCP_BASE_URL` 覆盖。
- [x] 测试：app 集成测试覆盖 MCP server、工具列表、`opencode_compat` 状态注册、启动即拉起 opencode 和 keepalive job。

### 2.9 `mcp/tools/*`

- [x] `list_features`：返回模型可见的活跃特性目录和轻量说明。
- [x] `get_feature_info`：返回特性详情、Wiki 入口、关联仓库摘要。
- [x] `list_feature_repos`：返回某特性的仓库列表。
- [x] `prepare_worktree`：准备并返回 workspace 相对路径、repo id、版本信息。
- [x] `bind_session_features`：由模型确认后绑定一个或多个特性。
- [x] `list_session_attachments`：列出当前会话附件。
- [x] `read_session_attachment`：读取可文本化附件内容。
- [x] opencode runtime 不暴露 `search_reports/read_report`；问题报告通过 `./wiki/<feature_slug>/problem-reports/` 文件目录访问。
- [x] Wiki workspace 导出 `knowledge-base/`、`problem-reports/verified/`、`problem-reports/drafts/`。
- [x] Wiki workspace 根目录导出 `_manifest.json`，记录 schema version、live view、exported_at、特性/文档/报告数量和每个特性的文件路径摘要。
- [x] 每个工具参数必须是简单 JSON object。
- [x] 工具只返回事实、候选和错误恢复建议，不替模型做业务判断。
- [x] 测试：每个工具 handler 单测、schema 快照、错误分支。

### 2.10 前端会话页

- [x] 会话发送走 opencode backend 返回的事件流。
- [x] 文本增量正常显示。
- [x] 右侧行动轨迹显示 opencode tool、MCP tool、状态、错误；耗时统计待后续增强。
- [x] 每个卡片可展开查看完整参数、结果摘要、错误详情。
- [x] Agent 行动轨迹和 `/traces` 接口返回不展示宿主机绝对路径；当前会话目录内文件只显示会话相对路径。
- [x] `sync` 等高频事件不刷屏。
- [x] 会话生成中切换会话，消息和行动轨迹不串屏。
- [x] 切回正在生成的会话，恢复最新生成内容和行动轨迹。
- [x] 失败使用居中弹窗，不使用顶部一闪而过提示。
- [x] 成功使用低密度居中浮层。
- [x] 测试：Vitest + Playwright live smoke。

### 2.11 问题报告生成回归

- [x] 报告标题必须保持 `YYYY-MM-DD 问题描述`，不得在模型已返回标题时退化为 `未命名问题`。
- [x] 报告正文不得保存 raw JSON 或 fenced JSON；模型返回固定 schema 时应恢复 `body_markdown`。
- [x] 长报告输出被截断时，如果 `title_description` / `body_markdown` 已经出现，应做固定 schema 容错恢复。
- [x] 报告生成输出预算已提升，避免普通 4096 输出上限过早截断长报告。
- [x] 已修复真实会话 `sess_512f3e10aabd6dee` 生成的错误报告标题和正文。
- [x] 测试：`tests/unit/test_session_report_generation.py` 增加截断 JSON-like 输出恢复用例。
- [x] 验证：`uv run pytest tests/unit/test_session_report_generation.py tests/integration/test_session_report_generation.py -q` -> `18 passed`。
- [x] 验证：`uv run ruff check src/codeask/sessions/report_generation.py tests/unit/test_session_report_generation.py` -> `All checks passed!`。

### 2.12 Wiki Mermaid 流程图渲染回归

- [x] `MarkdownRenderer` 识别 fenced code block `language-mermaid`，不再作为普通代码块展示。
- [x] Mermaid 按需动态加载，仅在文档实际包含流程图时加载渲染库，避免影响普通 Markdown 首屏。
- [x] Mermaid 渲染失败时，在原位置显示错误提示和原始流程图文本，页面不能空白。
- [x] 复杂大图按可读宽度展示，外层容器允许横向滚动，不挤压 Wiki / 特性页布局。
- [x] 已在 AnythingLLM Reference 知识库创建真实验证文档：`2026-05-14 Mermaid复杂流程图渲染验证`。
- [x] Wiki 工作台真实浏览器验证：`/#/wiki?feature=3&node=259`，SVG 1 个，Mermaid 代码块 0 个，控制台无错误。
- [x] 特性页知识库预览真实浏览器验证：AnythingLLM Reference -> 知识库 -> `2026-05-14 Mermaid复杂流程图渲染验证`，SVG 1 个，Mermaid 代码块 0 个，控制台无错误。
- [x] 验证截图：`/tmp/codeask-mermaid-wiki.png`、`/tmp/codeask-mermaid-feature.png`。
- [x] 自动化测试：`corepack pnpm --dir frontend exec vitest run tests/wiki/markdown-renderer.test.tsx` -> `7 passed`。

---

## 3. 多环境 E2E 基线

每个环境都必须记录命令、数据目录、模型配置、会话 id、执行结果。若未执行，必须写明跳过原因和剩余风险。

| 环境 | 是否必跑 | 目标 | 计划测试通道 | 通过标准 |
|---|---:|---|---|---|
| 临时空库环境 | 是 | 首次启动、migration、默认 admin/匿名会话、opencode unavailable 错误 | Playwright + 临时 `CODEASK_DATA_DIR` | 前后端启动，页面可进入，会话错误提示正确 |
| 真实数据只读环境 | 是 | 旧数据升级后，特性、Wiki、LLM、仓库仍可读 | `playwright.realdata.config.ts` 或等价只读 E2E | 能看到真实特性/Wiki/LLM/repo，不改写数据 |
| 真实数据可写沙箱 | 是 | 新会话、报告、绑定特性、worktree、事件写入可清理 | 真实数据副本或测试前缀 E2E | 写入只影响测试会话，清理后无残留 |
| 真实浏览器环境 | 是 | UI 路由、会话切换、行动轨迹、弹窗、刷新恢复 | Playwright Chromium，必要时人工浏览器 | 没有空白页、串屏、隐藏错误、残留禁用状态 |
| 真实 LLM / opencode 环境 | 是，默认可显式开启 | 真实模型 + opencode `prompt_async` + `/global/event` | `CODEASK_RUN_LIVE_LLM_E2E=1` | 至少 OpenAI 协议和 Anthropic 协议各一条通过 |
| 外部工具环境 | 是 | remote MCP、Wiki symlink、worktree、shared server 重启 | 后端 live smoke + Playwright | MCP token 不串，Wiki 可读，repo 可 grep/read |
| 升级部署环境 | 是 | 从 v1.0.3/v1.0.4 前一提交替换代码后可启动 | 离线部署 smoke / start.sh smoke | `uv sync`、前端 build、migration、start.sh 成功 |

### 3.1 临时空库 E2E

- [x] 命令记录：
  - `TMP_DIR=$(mktemp -d /tmp/codeask-v104-start-XXXXXX)`
  - `CODEASK_DATA_DIR="$TMP_DIR" CODEASK_DATA_KEY=<generated-fernet-key> CODEASK_PORT=8031 CODEASK_OPENCODE_PORT_RANGE=4331-4331 ./start.sh`
  - 停止后再次执行：`CODEASK_DATA_DIR="$TMP_DIR" CODEASK_PORT=8031 CODEASK_OPENCODE_PORT_RANGE=4331-4331 ./start.sh`，验证不传 `CODEASK_DATA_KEY` 时可读取 `$TMP_DIR/secrets/data.key`。
  - `corepack pnpm --dir frontend build`
  - 使用 Playwright Chromium 访问 `http://127.0.0.1:8031`。
- [x] 验证结果：`/api/healthz` 返回 `status=ok`、`db=ok`、`agent_backend=opencode`，opencode `1.14.48` 在 `4331` 端口 running。
- [x] 验证数据库 migration：临时空库启动后 `alembic_version=0029`。
- [x] 验证 `CODEASK_DATA_KEY` 缓存：首次启动后生成 `$TMP_DIR/secrets/data.key`，第二次启动未传环境变量仍可启动。
- [x] 验证匿名用户能打开会话页：真实浏览器可见“会话输入”。
- [x] 验证默认 admin 能登录并打开设置页：`admin/admin` 登录成功，设置页“运行状态”可见。
- [x] 验证设置页子路由刷新：切到“LLM 配置”后 URL 为 `#/settings?page=llm`，刷新后仍在“LLM 配置”；输出 `temp-start-admin-settings: PASS`。
- [x] 验证 opencode 未安装或禁用时显示居中错误：由 `e2e/opencode-unavailable.spec.ts` 在专门场景覆盖，避免破坏本轮 start.sh 正常启动验证。

### 3.2 真实数据只读 E2E

- [x] 命令记录：
  - `CODEASK_REALDATA_BASE_URL=http://127.0.0.1:5173 CODEASK_REAL_DATA_DIR=/home/hzh/.codeask`。
  - Playwright Chromium 登录 admin 后只执行 GET 请求读取 `/api/features`、`/api/admin/llm-configs`、`/api/repos`、`/api/wiki/tree`。
- [x] 验证真实特性列表可见：读取到 `18` 个特性。
- [x] 验证真实 Wiki 树可见：读取到 `170` 个 Wiki 节点。
- [x] 验证真实 LLM 配置列表可见：admin 可见 `8` 条 LLM 配置。
- [x] 验证真实仓库列表可见：读取到 `14` 个仓库。
- [x] 验证不创建、不删除、不修改真实业务数据：该脚本只发起同源 GET 请求；输出 `realdata-readonly: PASS {"featureCount":18,"llmCount":8,"repoCount":14,"wikiNodeCount":170}`。

### 3.3 真实数据可写沙箱 E2E

- [x] 使用真实数据测试前缀会话：`v104 writable sandbox <timestamp>`。
- [x] 创建会话并发送普通问题：真实浏览器通过 `/api/sessions/{id}/messages` 发送“请用一句话回答：CodeAsk 当前是否能创建测试会话？”。
- [x] 生成 opencode workspace：发送完成后确认 `/home/hzh/.codeask/agent_sessions/opencode/<session_id>` 存在。
- [x] 行动轨迹写入当前会话：测试会话 `sess_1fdee30d8087a7f2` 落库 `2` 个 turn、`25` 条 trace。
- [x] 删除测试会话后清理：通过 `DELETE /api/sessions/sess_1fdee30d8087a7f2` 删除后，session workspace 不再存在；输出 `realdata-writable-sandbox: PASS session=sess_1fdee30d8087a7f2 turns=2 traces=25`。
- [x] 脚本失败残留清理：第一次脚本自身解析函数作用域错误留下 `sess_92648296ac56a56e`，已通过正式 API 删除并确认无 `v104 writable sandbox%` 残留会话。

### 3.4 真实 LLM / opencode E2E

- [x] 记录 opencode 版本：`opencode --version` -> `1.14.48`。
- [x] 记录模型配置名称、协议、模型名：本轮真实浏览器 smoke 使用当前默认启用配置 `glm-5.1` / `anthropic`。
- [x] 使用 Anthropic 协议配置完成一轮真实问答。
- [x] 使用 OpenAI 协议配置完成一轮真实问答：Phase 0 已完成 OpenAI-compatible 矩阵；全量真实 LLM smoke 覆盖 OpenAI 协议配置。
- [x] 验证回答文本不泄漏 raw reasoning。
- [x] 验证行动轨迹可见 reasoning 观察事件，但不展示 raw reasoning 原文。
- [x] 验证 `/global/event` 事件能归属到正确 session。
- [x] 新增可重复执行的全量真实 LLM 配置 smoke：
  - `CODEASK_LIVE_LLM_CONFIG_SMOKE=1 CODEASK_LIVE_LLM_SMOKE_TIMEOUT=180 uv run pytest tests/live/test_live_opencode_llm_configs.py -q -s`
  - 覆盖范围：当前 CodeAsk DB 中所有 LLM 配置，包括 disabled 配置。
  - 当前实测结果：9 条配置全部通过；DeepSeek Anthropic 使用 `anthropic-compatible-bearer`，火山 Anthropic 使用 `anthropic-compatible-v1-bearer`，OpenAI 协议使用 `openai-compatible`。
- [x] 执行记录：
  - `CODEASK_RUN_LIVE_OPENCODE_E2E=1 CODEASK_REAL_DATA_DIR=/home/hzh/.codeask corepack pnpm --dir frontend exec playwright test -c playwright.realdata.config.ts e2e/opencode-backend-live.spec.ts --project=chromium`
  - 结果：`1 passed`。

### 3.5 Wiki + MCP + Worktree E2E

- [x] 询问一个可从 Wiki grep/read 回答的问题，确认 opencode 读取 `./wiki/`。
- [x] 询问一个需要参考历史报告的问题，确认 opencode 使用 `glob/grep/read ./wiki/<feature_slug>/problem-reports/`，且 MCP 工具列表不包含 `search_reports/read_report`。
- [x] 用户显式指定某个仓库，确认 MCP `prepare_worktree` 成功。
- [x] opencode 在 worktree 中 grep/read 文件。
- [x] 行动轨迹中显示 repo id/path/version 信息。
- [x] local_dir repo 集成 E2E：注册 plain local dir repo、刷新 ready、MCP prepare_worktree、验证 workspace repo 文件可读。

### 3.6 会话连续性 E2E

- [x] 第一轮询问问题并等待完成。
- [x] 第二轮追问“你刚刚查阅了哪些资料？”。
- [x] 刷新浏览器后再追问“上一轮用了什么证据？”。
- [x] 切换到其它会话再切回，消息和行动轨迹不串屏。
- [x] shared server 重启后，原会话可继续追问。

### 3.7 停止生成 E2E

- [x] 发送长回答问题。
- [x] 点击停止生成。
- [x] 前端停止输出，状态回到可输入。
- [x] 因本版本停止语义是“回滚到本轮起点”，行动轨迹中的本轮临时事件被清理；用户可见记录为居中低密度“已停止生成”提示和后端 abort 请求。
- [x] 本版本不要求完整 `abort + revert` 深度回滚；若实现，则必须额外验证上下文不残留。

### 3.8 升级部署 E2E

- [x] 从上一版本代码替换为当前版本代码。
- [x] 执行 `uv sync`。
- [x] 执行前端 build。
- [x] 执行 `./start.sh`。
- [x] 确认数据库 migration 自动执行。
- [x] 确认旧 `CODEASK_DATA_KEY` 和缓存 key 不丢。
- [x] 确认真实特性、Wiki、LLM、仓库仍可见。

---

## 4. 自动化测试门禁

- [x] `uv run pytest -q` (全量后端测试通过；live LLM 测试默认跳过)
- [x] `uv run pytest tests/unit/test_opencode_compat*.py tests/integration/test_opencode_compat*.py -q`
- [x] `uv run pytest tests/unit/test_opencode_compat_*.py tests/integration/test_opencode_external_sessions.py tests/integration/test_opencode_mcp_app_integration.py -q` (38 passed)
- [x] `CODEASK_LIVE_LLM_CONFIG_SMOKE=1 CODEASK_LIVE_LLM_SMOKE_TIMEOUT=180 uv run pytest tests/live/test_live_opencode_llm_configs.py -q -s` (9 passed)
- [x] `uv run pytest tests/unit/test_session_report_generation.py tests/integration/test_session_report_generation.py -q` (18 passed)
- [x] `uv run ruff check src/codeask/sessions/report_generation.py tests/unit/test_session_report_generation.py`
- [x] `corepack pnpm --dir frontend exec vitest run` -> 42 个测试文件、220 条测试通过。
- [x] `corepack pnpm --dir frontend exec tsc --noEmit` -> 通过。
- [x] `corepack pnpm --dir frontend exec eslint src tests e2e --max-warnings=0` -> 通过。
- [x] `corepack pnpm --dir frontend build` -> 通过，Vite 仅提示既有 chunk size warning。
- [x] `corepack pnpm --dir frontend exec playwright test e2e/opencode-unavailable.spec.ts e2e/opencode-permission-deny.spec.ts e2e/session-stop.spec.ts --project=chromium` -> 3 passed。
- [x] `git diff --check` -> 通过。

若 `corepack` 不可用，按 `start.sh` 兼容策略使用系统 `pnpm` 执行同等命令。

---

## 5. 人工验收列表

以下为交付给用户的人工验收清单。2026-05-18 用户已确认人工验证和验收完成；自动化和真实浏览器验收状态以上文第 1-4 节为准。

- [x] 当前 opencode 版本。
- [x] 当前 CodeAsk 后端端口和前端地址。
- [x] 当前真实数据目录。
- [x] 当前使用的 LLM 配置名称、协议和模型。
- [x] 测试会话 id。
- [x] 创建会话后发送普通问答，确认可回答。
- [x] 询问 Wiki 中已有问题，确认 Agent 行动轨迹出现 Wiki 文件读取。
- [x] 询问需要代码调查的问题，确认先出现 worktree 准备，再出现 grep/read。
- [x] Agent 行动轨迹卡片和 Network 中的 Agent 事件返回不暴露宿主机绝对路径。
- [x] 生成中切换会话，再切回，确认消息和行动轨迹不丢不串。
- [x] 刷新页面后继续追问，确认上下文存在。
- [x] opencode 不可用时，确认显示居中错误弹窗。
- [x] 删除测试会话，确认右侧行动轨迹、消息和临时资源清理。

---

## 6. 收口条件

v1.0.4 只有在以下条件全部满足时才能关闭：

- [x] `open-issues-and-optimization-backlog.md` 中所有 P0 项已关闭，或已明确延期并迁移到 future / 下一版本。
- [x] PRD、Design、Plan、Acceptance Checklist 口径一致。
- [x] 每个模块都有自动化测试或明确 live E2E 覆盖。
- [x] 多环境 E2E 矩阵完成，未执行项有明确原因和风险。
- [x] 真实 LLM / opencode E2E 至少覆盖 OpenAI 和 Anthropic 两类协议。
- [x] 真实浏览器 E2E 通过，且没有隐藏错误提示。
- [x] shared server 多会话不串 workspace、provider、MCP token、事件流。
- [x] 旧 native Agent 不作为 v1.0.4 新会话 fallback。
- [x] 未完成项全部列入 future 或下一版本计划，不能伪装成已完成。
