# v1.0.4 OpenCode Backend 验收清单

> 状态：Draft
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
- [x] 真实 LLM 配置矩阵已验证：OpenAI-compatible 通过，Anthropic 使用 `anthropic-compatible-v1-bearer` 通过。
- [x] provider profile 缓存不进入第一版，已列为遗留增强项。
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

---

## 2. 模块验收清单

### 2.0 `backend.py`

- [x] `OpenCodeCompat.initialize_session(...)` 创建 opencode session 绑定。
- [x] `OpenCodeCompat.run_turn(...)` 发送 `prompt_async` 并消费 `/global/event`。
- [~] shared server 崩溃或端口变化后恢复：当前每轮初始化/运行都会取最新 server handle，并在请求前等待 `/global/health`；长期恢复策略待增强。
- [ ] `OpenCodeCompat.cleanup_session(...)` 只清理会话级资源，不关闭 shared server。
- [x] opencode 不可用时返回 SSE `error`，前端走居中错误弹窗，不回退 native runtime。
- [x] 测试：`initialize_session`、最小 `run_turn`、异常转 SSE error、启动健康等待、真实浏览器 smoke 已覆盖。

### 2.1 `sessions.py`

- [x] 创建 `external_agent_sessions` migration。
- [x] `ExternalAgentSession` 记录 CodeAsk session id、opencode session id、workspace、server url/port、config hash、状态和错误摘要。
- [x] CodeAsk session 重复发送消息时复用原 opencode session，配置变化时才重建。
- [x] opencode server 重启换端口后，初始化路径会更新记录中的当前 server handle。
- [~] 删除 CodeAsk session 时，当前会清理 opencode workspace 目录；绑定记录依赖 DB 外键级联，长期 worktree 精细清理待补。
- [x] 测试：DB create/upsert/mark_error、server binding 更新、缺失查询、删除 workspace 已覆盖。

### 2.2 `workspace.py`

- [x] 创建会话目录：`workspace/`、`attachments/`、`config/`、`logs/`。
- [x] `workspace/wiki` 指向持久化 Wiki 工作区，零复制，不复制整库。
- [x] `workspace/wiki` symlink 被删除后，下次 `prepare_workspace` 自动恢复。
- [x] Wiki 工作区导出会清理路径片段中的越界和分隔符，不允许 `../` 写出工作区。
- [x] 测试：symlink 创建、删除恢复、重复调用幂等、真实 Wiki/报告导出已覆盖。

### 2.3 `config.py` / `profiles.py`

- [x] 生成 workspace 级 `opencode.json`。
- [x] OpenAI/OpenAI-compatible 协议使用 `@ai-sdk/openai-compatible`。
- [x] Anthropic 协议默认使用 `anthropic-compatible-v1-bearer`。
- [x] `anthropic-default` 只作为 fallback 或显式兼容项。
- [x] 不根据厂商名、模型名、URL 域名做业务特判。
- [x] 不做 provider profile 成功结果缓存。
- [x] `permission` 默认 deny Bash/Edit/Write，allow read/grep/glob。
- [x] remote MCP 配置包含会话级 Bearer token 和 session header。
- [x] 测试：OpenAI/Anthropic 配置快照、permission 快照、MCP 快照、未知协议错误。

### 2.4 `process.py`

- [x] 启动一个 shared `opencode serve` 常驻进程。
- [x] 进程退出后重启并允许重新分配端口；请求前等待 `/global/health`。
- [x] CodeAsk 退出时关闭 shared opencode server。
- [ ] 单个会话闲置清理不关闭 shared server。
- [ ] opencode bin 不存在或版本不匹配时返回明确错误。
- [~] 测试：端口分配、进程退出重启、健康等待已覆盖；版本检查待补。

### 2.5 `http.py`

- [x] 封装 `/global/health`。
- [x] 封装 `POST /session?directory=<workspace>`。
- [x] 封装 `POST /session/:id/prompt_async?directory=<workspace>`。
- [x] 封装 `GET /session/:id/message?directory=<workspace>`。
- [x] 封装 `/global/event` SSE 消费。
- [x] 封装基础 `abort`；深度 `abort + revert` 回滚列遗留增强项。
- [x] 所有已实现请求都必须携带 `directory`。
- [~] 测试：fake opencode HTTP 验证已实现路径、参数和 SSE；abort/错误映射待补。

### 2.6 `events.py`

- [x] 原始 `/global/event` 事件写入 JSONL。
- [x] 按 `directory + sessionID` 归属事件。
- [x] 折叠或降噪 `sync` 事件。
- [x] 映射 text delta 到聊天气泡。
- [x] 映射 opencode 内置工具到行动轨迹。
- [x] 映射 CodeAsk MCP tool 到行动轨迹。
- [x] 映射 reasoning 为可审计观察事件，不展示 raw reasoning 原文。
- [x] 同一个 reasoning part 已做降噪：只保留首个非空观察和大幅增长观察，避免“模型推理已隔离”刷屏。
- [x] 错误事件必须能触发居中错误弹窗。
- [x] 测试：tool part、reasoning part、sync 折叠、raw JSONL、前端错误弹窗路径已覆盖。

### 2.7 `worktrees.py`

- [x] 复用 `codeask.code_index.worktree.WorktreeManager`。
- [x] 支持用户显式指定仓库时准备 worktree。
- [x] 支持模型通过 MCP 请求准备某个特性关联仓库。
- [x] workspace 内暴露相对路径，方便 opencode grep/read。
- [ ] 清理会话时清理对应 worktree。
- [~] 测试：路径暴露和清理委托已覆盖；真实 repo smoke 待 E2E。

### 2.8 `mcp/server.py` / `mcp/auth.py`

- [x] FastAPI 注册 opencode 专用 MCP endpoint。
- [x] 支持 StreamableHTTP `initialize`。
- [x] 支持 `notifications/initialized`。
- [x] 支持 `tools/list`。
- [x] 支持 `tools/call`。
- [x] Bearer token 与 CodeAsk session 绑定，跨会话 token 拒绝。
- [x] headers 中保留 `X-CodeAsk-Session` 可审计 session 信息。
- [x] 测试：MCP protocol 集成、token 正反例、跨会话拒绝。

### 2.8.1 FastAPI 生命周期接入

- [x] app lifespan 注册 `opencode_mcp_server`。
- [x] app lifespan 注册 `opencode_compat`，但保持 opencode 进程懒启动。
- [x] app shutdown 调用 shared opencode process manager 清理。
- [x] 默认 MCP base URL 使用后端本机地址，可通过 `CODEASK_OPENCODE_MCP_BASE_URL` 覆盖。
- [x] 测试：app 集成测试覆盖 MCP server、工具列表和 `opencode_compat` 状态注册。

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
- [x] 每个工具参数必须是简单 JSON object。
- [x] 工具只返回事实、候选和错误恢复建议，不替模型做业务判断。
- [x] 测试：每个工具 handler 单测、schema 快照、错误分支。

### 2.10 前端会话页

- [x] 会话发送走 opencode backend 返回的事件流。
- [x] 文本增量正常显示。
- [x] 右侧行动轨迹显示 opencode tool、MCP tool、状态、错误；耗时统计待后续增强。
- [x] 每个卡片可展开查看完整参数、结果摘要、错误详情。
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

- [ ] 命令记录：
  - `CODEASK_DATA_DIR=/tmp/codeask-e2e-empty-... ./start.sh`
  - `corepack pnpm --dir frontend test:e2e -- <v104-empty.spec.ts> --project=chromium`
- [ ] 验证匿名用户能打开会话页。
- [ ] 验证 opencode 未安装或禁用时，发送消息显示居中错误。
- [ ] 验证 admin 登录后设置页可见，但不影响匿名会话路径。

### 3.2 真实数据只读 E2E

- [ ] 命令记录：
  - `CODEASK_REAL_DATA_DIR=/home/hzh/.codeask corepack pnpm --dir frontend exec playwright test -c playwright.realdata.config.ts <v104-realdata-readonly.spec.ts> --project=chromium`
- [ ] 验证真实特性列表可见。
- [ ] 验证真实 Wiki 文档可打开。
- [ ] 验证真实 LLM 配置列表可见。
- [ ] 验证真实仓库列表可见。
- [ ] 验证不创建、不删除、不修改真实业务数据。

### 3.3 真实数据可写沙箱 E2E

- [ ] 使用真实数据副本或测试前缀会话。
- [ ] 创建会话并发送普通问题。
- [ ] 生成 opencode workspace。
- [ ] 行动轨迹写入当前会话。
- [ ] 删除测试会话后，消息、行动轨迹、临时 worktree 和 workspace 清理。

### 3.4 真实 LLM / opencode E2E

- [x] 记录 opencode 版本：`opencode --version` -> `1.14.48`。
- [x] 记录模型配置名称、协议、模型名：本轮真实浏览器 smoke 使用当前默认启用配置 `glm-5.1` / `anthropic`。
- [x] 使用 Anthropic 协议配置完成一轮真实问答。
- [~] 使用 OpenAI 协议配置完成一轮真实问答：Phase 0 已完成 OpenAI-compatible 矩阵；本轮 UI live smoke 未重复切换默认配置。
- [x] 验证回答文本不泄漏 raw reasoning。
- [x] 验证行动轨迹可见 reasoning 观察事件，但不展示 raw reasoning 原文。
- [x] 验证 `/global/event` 事件能归属到正确 session。
- [x] 执行记录：
  - `CODEASK_RUN_LIVE_OPENCODE_E2E=1 CODEASK_REAL_DATA_DIR=/home/hzh/.codeask corepack pnpm --dir frontend exec playwright test -c playwright.realdata.config.ts e2e/opencode-backend-live.spec.ts --project=chromium`
  - 结果：`1 passed`。

### 3.5 Wiki + MCP + Worktree E2E

- [ ] 询问一个可从 Wiki grep/read 回答的问题，确认 opencode 读取 `./wiki/`。
- [ ] 询问一个需要参考历史报告的问题，确认 opencode 使用 `glob/grep/read ./wiki/<feature_slug>/problem-reports/`，且 MCP 工具列表不包含 `search_reports/read_report`。
- [ ] 用户显式指定某个仓库，确认 MCP `prepare_worktree` 成功。
- [ ] opencode 在 worktree 中 grep/read 文件。
- [ ] 行动轨迹中显示 repo id/path/version 信息。

### 3.6 会话连续性 E2E

- [x] 第一轮询问问题并等待完成。
- [ ] 第二轮追问“你刚刚查阅了哪些资料？”。
- [ ] 刷新浏览器后再追问“上一轮用了什么证据？”。
- [x] 切换到其它会话再切回，消息和行动轨迹不串屏。
- [ ] shared server 重启后，原会话可继续追问。

### 3.7 停止生成 E2E

- [ ] 发送长回答问题。
- [ ] 点击停止生成。
- [ ] 前端停止输出，状态回到可输入。
- [ ] 行动轨迹记录停止事件。
- [ ] 本版本不要求完整 `abort + revert` 深度回滚；若实现，则必须额外验证上下文不残留。

### 3.8 升级部署 E2E

- [ ] 从上一版本代码替换为当前版本代码。
- [ ] 执行 `uv sync`。
- [ ] 执行前端 build。
- [ ] 执行 `./start.sh`。
- [ ] 确认数据库 migration 自动执行。
- [ ] 确认旧 `CODEASK_DATA_KEY` 和缓存 key 不丢。
- [ ] 确认真实特性、Wiki、LLM、仓库仍可见。

---

## 4. 自动化测试门禁

- [ ] `uv run pytest tests/unit -q`
- [ ] `uv run pytest tests/integration -q`
- [x] `uv run pytest tests/unit/test_opencode_compat*.py tests/integration/test_opencode_compat*.py -q`
- [x] `uv run pytest tests/unit/test_opencode_compat_*.py tests/integration/test_opencode_external_sessions.py tests/integration/test_opencode_mcp_app_integration.py -q` (38 passed)
- [x] `uv run pytest tests/unit/test_session_report_generation.py tests/integration/test_session_report_generation.py -q` (18 passed)
- [x] `uv run ruff check src/codeask/sessions/report_generation.py tests/unit/test_session_report_generation.py`
- [ ] `corepack pnpm --dir frontend test:run`
- [ ] `corepack pnpm --dir frontend typecheck`
- [ ] `corepack pnpm --dir frontend build`
- [ ] `corepack pnpm --dir frontend test:e2e -- <v104-opencode.spec.ts> --project=chromium`
- [ ] `git diff --check`

若 `corepack` 不可用，按 `start.sh` 兼容策略使用系统 `pnpm` 执行同等命令。

---

## 5. 人工验收列表

开发完成后，交付给用户人工验收的列表必须包含：

- [ ] 当前 opencode 版本。
- [ ] 当前 CodeAsk 后端端口和前端地址。
- [ ] 当前真实数据目录。
- [ ] 当前使用的 LLM 配置名称、协议和模型。
- [ ] 测试会话 id。
- [ ] 创建会话后发送普通问答，确认可回答。
- [ ] 询问 Wiki 中已有问题，确认 Agent 行动轨迹出现 Wiki 文件读取。
- [ ] 询问需要代码调查的问题，确认先出现 worktree 准备，再出现 grep/read。
- [ ] 生成中切换会话，再切回，确认消息和行动轨迹不丢不串。
- [ ] 刷新页面后继续追问，确认上下文存在。
- [ ] opencode 不可用时，确认显示居中错误弹窗。
- [ ] 删除测试会话，确认右侧行动轨迹、消息和临时资源清理。

---

## 6. 收口条件

v1.0.4 只有在以下条件全部满足时才能关闭：

- [ ] PRD、Design、Plan、Acceptance Checklist 口径一致。
- [ ] 每个模块都有自动化测试或明确 live E2E 覆盖。
- [ ] 多环境 E2E 矩阵完成，未执行项有明确原因和风险。
- [ ] 真实 LLM / opencode E2E 至少覆盖 OpenAI 和 Anthropic 两类协议。
- [ ] 真实浏览器 E2E 通过，且没有隐藏错误提示。
- [ ] shared server 多会话不串 workspace、provider、MCP token、事件流。
- [ ] 旧 native Agent 不作为 v1.0.4 新会话 fallback。
- [ ] 未完成项全部列入 future 或下一版本计划，不能伪装成已完成。
