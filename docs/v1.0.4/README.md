# CodeAsk 文档 — v1.0.4

| 字段 | 值 |
|---|---|
| 版本 | v1.0.4 |
| 起始日期 | 2026-05-12 |
| 状态 | Implementing |
| 主题 | OpenCode Agent Backend 对接 |
| 基线版本 | `../v1.0.3/` |
| 目标 | 引入 opencode 作为 CodeAsk 的外部 Agent 执行引擎，CodeAsk 负责知识管理平台层（权限、审计、数据、生命周期），opencode 负责 Agent 执行层（LLM 调用、工具编排、代码分析） |

## 版本定位

v1.0.2 完成了 Agent harness 修正（模型主导的工具调用运行时）。v1.0.3 完成了鉴权和访问控制。v1.0.4 不再继续增强 CodeAsk 自研 Agent 能力，而是引入成熟的 opencode coding agent 作为执行引擎。

本版本采用 `v1.0.4`，语义是：

> CodeAsk 成为研发知识管理平台，提供 Wiki、特性、报告、附件、代码仓库的环境管理和审计能力；opencode 作为独立兼容的 Agent 执行引擎，在 CodeAsk 准备好的隔离环境中自主调查。

## 目录结构

```text
v1.0.4/
├── README.md
├── prd/
│   └── opencode-backend.md        # 产品契约
├── design/
│   └── opencode-backend.md        # 系统设计
├── plans/
│   ├── opencode-backend.md        # 实施计划
│   └── acceptance-checklist.md    # 多环境 E2E 与收口验收清单
└── specs/
    ├── opencode-interaction-flow.md       # 完整交互流程规格
    └── opencode-1.14.48-phase0-spike.md   # opencode 1.14.48 实测记录
```

## 与 v1.0.3 的关系

v1.0.3 完成了用户认证、特性权限和会话基础设施。v1.0.4 在此基础上：

- 保留 CodeAsk 的所有现有能力（Wiki、特性、报告、附件、会话）
- 新增 `src/codeask/agent/opencode_compat/` 独立兼容模块
- 不新增通用 AgentBackend 抽象层，不为未来 agent 工具抽公共 backend
- 会话创建时初始化 opencode workspace、会话绑定和数据目录；不暴露用户可见的 Backend 选择
- 废弃旧 AgentOrchestrator 作为默认会话的后端；opencode 不可用时明确报错，不静默回退 native
- 新增持久化 Wiki 文件工作区，特性为一级目录，会话通过零复制方式挂载到 `workspace/wiki`
- 前端 Agent 行动轨迹基于 opencode 原始事件重设计，不继续沿用旧 Agent 阶段流

## 推荐阅读顺序

1. `specs/opencode-1.14.48-phase0-spike.md` — 目标 opencode 版本实测记录
2. `specs/opencode-interaction-flow.md` — 完整交互流程（端到端场景）
3. `prd/opencode-backend.md` — 产品契约
4. `design/opencode-backend.md` — 系统设计
5. `plans/opencode-backend.md` — 实施计划
6. `plans/acceptance-checklist.md` — 模块验收与多环境 E2E 门禁

## 当前硬前置

正式开发 opencode 主功能前，必须先完成 `plans/opencode-backend.md` 中的 Phase 0 主路径 spike：确认目标 opencode 版本的 HTTP server API、真实 LLM 配置矩阵、单 server 多 workspace/provider/MCP token 隔离、Wiki 零复制挂载、worktree 准备方式和基础事件流。

当前 Phase 0 主路径已经完成，结论是：

- opencode 版本固定验证为 `1.14.48`。
- 主路径采用一个 shared `opencode serve` 常驻进程。
- 每个 CodeAsk 会话对应独立 workspace、独立 `opencode.json`、独立 opencode session 和独立 MCP token。
- 所有 opencode HTTP 请求必须携带 `directory=<workspace>`。
- ACP 暂不纳入实现范围和硬前置。
- `abort + revert` 深度上下文回滚作为遗留增强项，不阻塞主功能落地；第一版先保证停止输出、状态清理和审计可见。

## 当前实现进度

截至 2026-05-15，本版本已经进入集成验证阶段：

- 已新增 `src/codeask/agent/opencode_compat/` 独立模块，默认会话后端切到 opencode，旧 native runtime 仅保留为回归测试和诊断路径。
- 已实现 shared `opencode serve` 进程管理：CodeAsk 服务启动时 best-effort 拉起 opencode，后台 keepalive 定时检测并在进程退出后重新拉起；会话运行时仍会取当前 handle 并等待健康。
- 已实现每个会话独立 workspace、`opencode.json`、`AGENTS.md`、MCP token、raw opencode event JSONL。
- 已实现 LLM OpenCode Provider 显式选择：保存配置时不联网测试，会话按用户选择的 provider 生成 `opencode.json`，不在会话启动时隐式轮转；管理页提供“测试连接”按钮用于验证当前选择。列表行测试直接写入配置级连接状态；新增/编辑表单内测试只验证当前表单草稿，测试结果作为隐藏表单状态，必须在用户点击保存后才随配置一起落库。
- 已实现持久化 Wiki 文件工作区导出：`<CODEASK_DATA_DIR>/wiki_workspace/current/<feature-slug>/...`，会话通过 `workspace/wiki` symlink 零复制挂载。
- 已实现 opencode 专用 MCP endpoint 与工具：特性列表/详情、特性仓库、worktree 准备、会话附件、会话特性绑定；Wiki 和历史报告以文件目录暴露，由 opencode 自己 `glob/grep/read`。
- 已接入 `/api/sessions/{id}/messages` 主发送链路，opencode 异常会返回 SSE `error` 事件，前端使用居中错误弹窗展示。
- 已新增 live E2E 通道：`frontend/e2e/opencode-backend-live.spec.ts`，覆盖真实浏览器、真实数据、真实 LLM/opencode、workspace 文件与 wiki symlink。
- 已修复报告草稿生成的长输出解析问题：当模型返回固定 JSON schema 但输出被截断时，后端会从可恢复的 `title_description` / `body_markdown` 中生成正式报告标题和正文，避免保存为 `YYYY-MM-DD 未命名问题` 或 raw JSON。
- 已修复 LLM 配置新增/编辑态连接测试状态不落库问题：表单测试不再显示“当前表单测试通过”等临时列表状态，也不提前保存 provider；只有保存表单后，`opencode_provider_status` / `opencode_provider_tested_at` / `opencode_provider_error` / `opencode_provider_test_result_json` 才会写入数据库，刷新后列表继续显示真实状态。

仍需收口的内容以 `plans/acceptance-checklist.md` 为准，主要集中在更完整的多环境 E2E、长期清理任务、opencode 不可用诊断和后续增强项记录。

## 本轮回归修复

### 2026-05-14 报告标题解析容错

会话 `sess_512f3e10aabd6dee` 生成报告时，模型已经返回了 `title_description`，但报告正文较长，输出在 JSON / fenced code block 闭合前被截断。旧解析器没有恢复这个固定 schema，导致报告保存为 `2026-05-14 未命名问题`，正文也残留 raw JSON。

本轮修复：

- 报告生成输出预算提升到 `12000`，降低长报告被截断概率。
- `parse_prepared_report_payload` 增加截断 JSON-like 输出恢复逻辑，仅针对 `title_description` / `body_markdown` 固定 schema 生效。
- 已补充回归测试，覆盖“标题已返回但 JSON 未闭合”的坏样本。
- 已修复本地真实数据中的报告 `id=7` 和对应 Wiki 报告引用节点标题。

验证记录：

- `uv run pytest tests/unit/test_session_report_generation.py tests/integration/test_session_report_generation.py -q` -> `18 passed`
- `uv run ruff check src/codeask/sessions/report_generation.py tests/unit/test_session_report_generation.py` -> `All checks passed!`
