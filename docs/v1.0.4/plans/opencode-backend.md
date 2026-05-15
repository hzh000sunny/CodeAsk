# OpenCode Agent Backend 实施计划

> 版本：v1.0.4
> 状态：Draft
> 关联：[系统设计](../design/opencode-backend.md) | [交互流程](../specs/opencode-interaction-flow.md)

---

## 模块实现确认

v1.0.4 的开发只在 `src/codeask/agent/opencode_compat/` 下新增 opencode 兼容模块，并在 API、DB、前端会话页做必要接入。不抽取公共 agent backend，不复用旧 Agent runtime 的工具、阶段机或 prompt。

| 模块 | 实现内容 | 验收输出 |
|---|---|---|
| `backend.py` | `OpenCodeCompat` 主入口，串联 sessions、workspace、config、process、http、events | fake opencode 完整 run 集成测试 |
| `sessions.py` | `ExternalAgentSession` CRUD、CodeAsk session 到 opencode session 的绑定、状态、端口、workspace、config hash、错误摘要 | DB 集成测试覆盖创建、恢复、更新、删除 |
| `workspace.py` | 创建会话 workspace、附件目录、Wiki symlink、配置目录、日志目录；`workspace/wiki` 被删后可恢复 | 单元测试 + Phase 0 symlink 删除恢复记录 |
| `config.py` | 生成 `opencode.json`：provider、model、MCP remote、permission deny Bash/Edit/Write、headers、timeout；生成 `AGENTS.md` 注入 CodeAsk 使用规则 | 快照测试覆盖 OpenAI、Anthropic、MCP token、permission |
| `profiles.py` | 提供少量用户可见 OpenCode Provider：`default`、`openai-native`、`openai-compatible`、`anthropic-native`、`anthropic-compatible-bearer`、`anthropic-compatible-v1-bearer`、`openrouter`；`default` 走 opencode native provider；会话只使用用户显式选择，不做隐式轮转 | 真实配置矩阵映射测试；同 URL 双协议回归；显式 provider 测试按钮；未知 provider 明确失败 |
| `process.py` | 一个 shared `opencode serve` 常驻进程、Basic Auth、健康检查、端口分配、崩溃重启、换端口恢复 | fake process 单测 + live health smoke |
| `http.py` | opencode HTTP client：`/global/health`、`/session`、`/session/:id/prompt_async`、`/session/:id/message`、`/global/event`、`abort/revert` | fake opencode HTTP server 集成测试 |
| `events.py` | 读取 `/global/event`，按 `directory + sessionID` 归属事件，归档 raw JSONL，映射前端事件，折叠 `sync` | event mapper 单测 + MCP tool event 样本回放 |
| `worktrees.py` | 调用现有 `WorktreeManager` 准备仓库 worktree，并以 workspace 相对路径暴露给 opencode | 真实 repo smoke + 清理测试 |
| `mcp/server.py` | FastAPI 内注册 StreamableHTTP MCP endpoint，支持 initialize、tools/list、tools/call | MCP 集成测试，remote MCP live smoke |
| `mcp/auth.py` | 会话级 Bearer token 校验和跨会话隔离 | token 正反例测试 |
| `mcp/tools/*` | 独立实现 opencode 专用工具：特性信息、仓库准备、附件读取、特性绑定；不提供 Wiki/报告检索读取封装 | 每个 tool handler 单测 + MCP tools/list schema 快照 |
| 前端会话页 | opencode 文本流、行动轨迹、展开详情、错误弹窗、模型/上下文信息、会话切换恢复 | Vitest + Playwright 真实浏览器 E2E |

### 遗留增强项，不进入第一版主线

- provider profile 后台定期重测和更完整诊断面板。
- `abort + revert` 深度上下文回滚的完整产品化；第一版先保证停止输出、状态清理和审计事件。
- ACP 接入。
- 外部 RAG MCP。
- 高并发压测和长期守护进程指标面板。

## 实施阶段

### Phase 0：opencode 版本与接口 Spike

目标：在写主功能代码前，用目标 opencode 版本验证真实 server API、事件流、MCP、真实 LLM 配置、Wiki 挂载、worktree 准备和权限基础语义。ACP 暂不进入 v1.0.4 实现范围；`abort + revert` 暂列遗留增强项，不阻塞主功能开发。

| # | 任务 | 产出 | 依赖 |
|---|------|------|------|
| 0.1 | 记录目标 opencode 版本、安装方式和 `opencode --version` 输出 | spike 记录 | 用户提供版本或本机安装 |
| 0.2 | 验证 `opencode serve` 启动、Basic Auth、端口分配 | spike 脚本/记录 | 0.1 |
| 0.3 | 验证 session 创建、`/session/:id/message`、`/session/:id/prompt_async` | API 行为记录 | 0.2 |
| 0.4 | 验证事件流端点：`/event`、`/global/event` 的真实差异 | 事件样本 JSONL | 0.3 |
| 0.5 | 验证 remote MCP 配置 URL 应指向根路径还是 message endpoint | MCP 连通性记录 | 0.2 |
| 0.6 | 验证 permission 禁用 Bash/Write/Edit 是否真实生效 | 安全验证记录 | 0.3 |
| 0.7 | 记录 abort + revert 已知行为，列为遗留增强项 | 遗留项记录 | 0.3 |
| 0.8 | 验证一个 server 多 session 是否能隔离 workspace、LLM 配置、MCP token 和历史 | server 形态决策 | 0.3, 0.5 |
| 0.9 | 验证 opencode SQLite 跨进程重启后的 session history | 恢复验证记录 | 0.3 |
| 0.10 | 使用 CodeAsk DB 中真实 LLM 配置做 opencode provider smoke matrix | provider 映射记录 | 0.2 |
| 0.11 | 验证 shared server 下不同 workspace 独立 `opencode.json` 是否能隔离 provider | shared server 配置隔离记录 | 0.8 |
| 0.12 | 验证少量 Anthropic provider profiles：原始 URL + Bearer、`/v1` + Bearer 等通用选项；默认不改写用户配置 URL | provider profile 决策 | 0.10 |
| 0.13 | 验证 `workspace/wiki` 零复制挂载被删除后可恢复 | Wiki 恢复记录 | 0.3 |
| 0.14 | 验证现有 WorktreeManager 可为 opencode 会话准备独立 worktree | worktree 准备记录 | 0.3 |
| 0.15 | 记录显式 OpenCode Provider 选择策略；保存配置时不自动测试，提供管理页手动测试按钮 | 决策记录 | 0.10 |
| 0.16 | 验证 remote StreamableHTTP MCP URL、headers、tools/list、tools/call | MCP 主路径记录 | 0.5 |
| 0.17 | 验证 `/global/event` 中 MCP 工具调用、reasoning、sync 噪声样本 | 事件映射输入样本 | 0.16 |
| 0.18 | 验证 shared server 重启后原 session 可读取并继续 | 恢复策略记录 | 0.9 |
| 0.19 | 验证 shared server 三会话并发真实 LLM smoke | 并发隔离记录 | 0.8, 0.10 |
| 0.20 | 验证 shared server 下 remote MCP endpoint/token 按 workspace 隔离 | MCP token 隔离记录 | 0.16 |

ACP 相关验证已经有探索记录，但当前不作为 v1.0.4 任务。

Phase 0 主路径已经完成，实测记录见 `../specs/opencode-1.14.48-phase0-spike.md`。后续进入 `opencode_compat` 业务实现。`abort + revert` 深度回滚不阻塞主功能。

### Phase 1：基础设施 (foundation)

目标：数据库表、会话数据目录、Wiki 持久化工作区、opencode 独立兼容模块骨架。

| # | 任务 | 产出 | 依赖 |
|---|------|------|------|
| 1.1 | 创建 Alembic migration: `external_agent_sessions` 表 | migration 文件 | — |
| 1.2 | 实现 `opencode_compat/sessions.py` (CRUD 与状态) | DB 操作层 | 1.1 |
| 1.3 | 实现 `opencode_compat/workspace.py` | 会话 workspace、Wiki 零复制链接、附件目录 | — |
| 1.4 | 实现 Wiki 工作区更新触发 | Wiki 写入/删除/导入后更新文件工作区 | 1.3 |
| 1.5 | 在 `opencode_compat/workspace.py` 中实现 Wiki 链接恢复 | 删除链接后可恢复 | 1.3 |
| 1.6 | 实现 `opencode_compat/process.py` 的端口范围分配 | 端口分配 | Phase 0 |
| 1.7 | 在 `stream_agent_response` 中接入 `opencode_compat` | 集成点；不经过通用 backend router | — |

### Phase 2：OpenCode 进程管理 (process)

目标：启动、停止、重启 opencode 子进程。

| # | 任务 | 产出 | 依赖 |
|---|------|------|------|
| 2.1 | 实现 `config.py` | opencode.json + AGENTS.md 生成 | 1.3 |
| 2.2 | 实现 `process.py` shared server manager (start/health/restart/stop) | 一个常驻 opencode serve 生命周期 | 1.4, 2.1 |
| 2.3 | 实现 `http.py` | opencode HTTP API 封装 | — |
| 2.4 | 实现 `backend.py` 的 `initialize_session` | 阶段 0 完整流程 | 1.2, 2.2, 2.3 |
| 2.5 | 实现 opencode 版本记录和兼容性 warning | 后台日志和管理诊断 | Phase 0 |
| 2.6 | 实现显式 OpenCode Provider 选择、手动测试接口、测试状态记录和会话 provider 绑定 | LLM 兼容验证能力 | 2.1, 2.3, 2.4 |

### Phase 3：opencode 事件流与前端行动轨迹 (streaming)

目标：基于 opencode 原始事件重新设计前端 Agent 行动轨迹，不保留旧 CodeAsk Agent 阶段流。

| # | 任务 | 产出 | 依赖 |
|---|------|------|------|
| 3.1 | 实现 `events.py` SSE consumer | SSE 事件消耗（HTTP 流式读取） | 2.3 |
| 3.2 | 实现 `events.py` raw event store | 原始事件 JSONL + DB 快照 | 3.1 |
| 3.3 | 实现 `events.py` event mapping | opencode raw event → 前端规范化事件 | 3.1 |
| 3.4 | 重构前端 Agent 行动轨迹 | 展示 opencode 工具、MCP、错误、状态、耗时 | 3.3 |
| 3.5 | 实现 `backend.py` 的 `run` 方法 | 阶段 1-2 完整流程 | 2.4, 3.1, 3.2, 3.3 |
| 3.6 | 停止生成主路径：先做到停止输出和状态清理；`abort + revert` 深度回滚列遗留项 | 基础停止能力 | Phase 0 |

### Phase 4：MCP Server (mcp)

目标：CodeAsk MCP tools 可供 opencode 调用。

| # | 任务 | 产出 | 依赖 |
|---|------|------|------|
| 4.1 | 实现 `mcp/server.py` (StreamableHTTP transport) | MCP endpoint | — |
| 4.2 | 实现 `mcp/auth.py` (Bearer token 校验) | MCP 认证 | — |
| 4.3 | 实现 `mcp/tools/list_features.py` | MCP tool | 1.2 |
| 4.4 | 实现 `mcp/tools/get_feature_info.py` | MCP tool | 1.2 |
| 4.5 | 实现 `mcp/tools/list_feature_repos.py` | MCP tool | 1.2 |
| 4.6 | 实现 `mcp/tools/prepare_worktree.py` | MCP tool | — |
| 4.7 | 实现 `mcp/tools/bind_session_features.py` | MCP tool | 1.2 |
| 4.8 | 实现 `mcp/tools/list_session_attachments.py` | MCP tool | — |
| 4.9 | 实现 `mcp/tools/read_session_attachment.py` | MCP tool | — |
| 4.10 | 在 Wiki workspace 中导出 `problem-reports/verified/` 与 `problem-reports/drafts/` | Wiki 文件目录 | — |
| 4.11 | 在 system prompt / `AGENTS.md` 中说明 Wiki 与问题报告目录结构 | 上下文提示 | 4.10 |
| 4.12 | 在 `opencode.json` 生成中加入 MCP server 配置 | 集成 | 4.1, 4.2 |
| 4.13 | 在 FastAPI app 中注册 MCP routes | 集成 | 4.1 |

### Phase 5：生命周期管理 (lifecycle)

目标：空闲清理、会话恢复、配置变更检测。

| # | 任务 | 产出 | 依赖 |
|---|------|------|------|
| 5.1 | 实现配置变更检测 (`config_hash`) | 哈希对比逻辑 | 2.1 |
| 5.2 | 实现 `ensure_running` (会话恢复) | 阶段 5 流程 | 2.2, 5.1 |
| 5.3 | 实现 `cleanup_session` (空闲清理) | 阶段 4 流程 | 2.2 |
| 5.4 | 实现定时清理任务 (app lifespan hook) | 周期性检查 | 5.3 |
| 5.5 | 实现会话删除时的资源释放 | on_delete cascade | 5.3 |

### Phase 6：测试与验收 (testing)

目标：覆盖所有阶段的测试和真实 LLM 端到端验证。

| # | 任务 | 产出 | 依赖 |
|---|------|------|------|
| 6.1 | 单元测试：event mapper | 测试文件 | 3.2 |
| 6.2 | 单元测试：config generator | 测试文件 | 2.1 |
| 6.3 | 单元测试：port allocator | 测试文件 | 1.6 |
| 6.4 | 单元测试：WikiWorkspaceExporter 和零复制挂载 | 测试文件 | 1.3, 1.5 |
| 6.5 | 单元测试：MCP tool handlers (每个 tool 独立) | 测试文件 | Phase 4 |
| 6.6 | 集成测试：FakeOpenCodeServer + 完整 run 流程 | 测试文件 | Phase 3, 6.1 |
| 6.7 | 集成测试：会话创建 → 清理 → 恢复 | 测试文件 | Phase 5 |
| 6.8 | 集成测试：配置变更检测与重启 | 测试文件 | 5.1 |
| 6.9 | 端到端：E2E 场景 1 (会话创建 + 首次问答 + opencode 事件流) | Playwright live test | Phase 5 |
| 6.10 | 端到端：E2E 场景 2 (grep/read wiki 与问题报告文件 + MCP 获取特性元数据) | Playwright live test | 6.9 |
| 6.11 | 端到端：E2E 场景 3 (用户显式指定仓库 + prepare_worktree) | Playwright live test | 6.9 |
| 6.12 | 端到端：E2E 场景 4 (多轮追问 + 特性绑定) | Playwright live test | 6.9 |
| 6.13 | 端到端：E2E 场景 5 (停止生成基础能力；abort/revert 深度回滚暂列遗留) | Playwright live test | 6.9 |
| 6.14 | 端到端：E2E 场景 6 (空闲清理 + 会话恢复) | Playwright live test | 6.9 |
| 6.15 | 多环境 E2E：临时空库、真实数据只读、真实数据可写沙箱、真实浏览器、真实 LLM/opencode、升级部署 | `acceptance-checklist.md` 记录 | Phase 5 |
| 6.16 | 外部工具 E2E：shared opencode server、remote MCP、worktree、Wiki symlink | Playwright live + 后端 live smoke | Phase 5 |
| 6.17 | Live LLM 配置全量 smoke：读取 DB 中所有 LLM 配置，包括 disabled 配置，只测试当前显式选择的 OpenCode Provider | `tests/live/test_live_opencode_llm_configs.py` | 2.6 |

### Phase 7：文档与收口 (closure)

| # | 任务 | 产出 | 依赖 |
|---|------|------|------|
| 7.1 | 更新 `docs/v1.0.4/README.md` 实施状态 | 文档 | Phase 6 |
| 7.2 | 更新 `docs/README.md` 当前版本指针 | 文档 | 7.1 |
| 7.3 | 编写并维护 v1.0.4 验收清单 | `plans/acceptance-checklist.md` | Phase 0 起持续更新 |
| 7.4 | 归档 `docs/future/opencode-integration.md` 引用 | 文档 | 7.1 |

---

## 依赖图

```text
Phase 0 (spike)
    ↓
Phase 1 (foundation)
    ↓
Phase 2 (process) + Phase 3 (streaming) [可并行]
    ↓                    ↓
Phase 4 (mcp) ←─────────┘
    ↓
Phase 5 (lifecycle)
    ↓
Phase 6 (testing)
    ↓
Phase 7 (closure)
```

### 可并行任务组

- **Phase 2 和 Phase 3 可并行** — `process.py` 和 `events.py` 互不依赖，但都必须等待 Phase 0
- **Phase 4 中的 MCP tool 实现可并行** — 每个 tool 独立实现
- **Phase 6 中的单元测试可并行** — 每个测试独立

---

## 关键风险

| 风险 | 缓解措施 |
|------|---------|
| opencode SSE 事件格式与预期不符 | Phase 0 先用真实 opencode 导出事件样本，Phase 3 再写 mapper |
| opencode MCP client 连接 CodeAsk MCP server 有问题 | Phase 0 先用真实 remote MCP 验证 URL、header、transport |
| shared server 长期运行资源或配置缓存异常 | shared server 优先；保留 per-session server 作为排障/回退模式，并加入进程健康检查 |
| opencode 版本升级导致行为变化 | 声明 CodeAsk v1.0.4 已验证 opencode 版本；启动时记录并 warning |
| Wiki 工作区占用额外空间或准备慢 | 使用持久化工作区 + symlink/bind mount，不在会话创建时复制 Wiki |
| 停止生成后上下文残留 | 列入遗留增强；主功能阶段先保证停止输出、状态清理和事件审计 |
