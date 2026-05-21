# Phase 2 — opencode 主链路接入 OpenViking

> 版本：v1.0.5
> 状态：Framework Draft（待 Phase 0 & Phase 1 完成后细化）
> 关联：[PRD](../prd/rag-knowledge.md) · [设计](../design/openviking-integration.md) · [Phase 0](./phase-0-spike.md) · [Phase 1](./phase-1-sync-adapter.md) · [收口验收](./acceptance-checklist.md)

---

## 0. 前置条件

- Phase 1 退出条件满足：CodeAsk 后端能稳定运行 OpenViking server、同步真实数据、admin 诊断可见
- 锁定 OpenViking 版本、embedding 模型与同步延迟基线
- v1.0.4 opencode 主链路保持稳定（不允许在 Phase 2 同时改造 opencode_compat 内部协议）

---

## 1. 范围

把 OpenViking 接入 opencode 主链路：

- `opencode_compat/config.py`：`opencode.json` 加 OpenViking remote MCP 配置与 token
- `opencode_compat/context.py`：动态上下文加入 OpenViking 资源布局与使用原则
- `opencode_compat/prompts.py`：`AGENTS.md` 同步加入 RAG 使用原则
- 工具白名单：限定 OpenViking 工具子集（详见 PRD §6.2）
- 前端 `frontend/src/components/session/action-trace/...`：识别并展示 OpenViking 工具事件
- live E2E：覆盖真实 OpenViking + Ollama + 真实 LLM
- 失败语义：OpenViking 不可用时明确报错；不静默回退
- 文档：CodeAsk 与 OpenViking 版本绑定记录、AGENTS.md 模板

不包含：

- 不动 v1.0.4 opencode shared server 进程管理
- 不引入 OpenViking 写工具到 opencode（`add_resource / remember / forget` 永远不暴露）
- 不替换 v1.0.4 CodeAsk MCP 工具
- 不删除 v1.0.4 `workspace/wiki` 文件挂载（兜底）
- 不接入 Claude Code backend

---

## 2. 工具白名单实现

OpenViking MCP server 在协议层暴露 10 个工具，但 opencode 实际只允许 7 个（`find / search / read / list / grep / glob / health`）。

实现选项：

- a) 在 opencode 工具白名单（`opencode.json.permission.tool.*` 或同等机制）中显式 deny 三个写工具
- b) 通过 OpenViking server 配置（如果支持 per-token tool ACL）限定 mcp token 可见工具集
- c) CodeAsk 后端为 OpenViking MCP 加一层 proxy，过滤 tools/list

Phase 2 第一步先评估上述哪种更稳定。优先 (a)；如果 opencode 1.14.48 不支持 per-tool deny，再考虑 (c)。spike 阶段已收集 opencode 真实白名单语义。

---

## 3. 上下文注入

`opencode_compat/context.py.build_dynamic_codeask_context` 追加 SDD §8 的 Markdown 段落。具体要写入：

- OpenViking 根 URI
- verified vs draft 权重原则
- 代码证据走 `codeask_prepare_worktree` 的硬约束
- OpenViking `read` 与"真实源码"语义差异
- 失败时不要假装命中

并在每轮 system prompt 中同步注入；写入 `CODEASK_CONTEXT.md` 的部分照旧。

---

## 4. 前端

`frontend/src/components/session/action-trace/`：

- `ActionTraceEvent.tsx` 识别 `openviking_*` 工具
- `ToolCallEvent.tsx` / `ToolResultEvent.tsx` 展示 OpenViking URI、score、耗时
- 路径脱敏沿用 `path-redaction.ts`
- admin 设置页 OpenViking 卡片（Phase 1 已建）增加"会话调用统计"小节（可选）

**会话视图边界**（PRD §10.4）：

- 会话页 Agent 行动轨迹**只**展示 opencode 调 OpenViking MCP 的工具事件（`find/search/read/grep/glob/list`）
- **不**展示后台同步事件（`wiki_doc_changed` / `scheduled_refresh` / `ollama_recovery` 等）—— 这些只在 admin OpenViking 仪表盘可见
- 不在普通用户会话里暴露 admin 视角的事件，避免污染主视图

---

## 5. live E2E

新增 `frontend/e2e/openviking-rag-live.spec.ts`，默认跳过，显式 `CODEASK_RUN_LIVE_OPENVIKING_E2E=1` 后执行：

- 真实 LLM、真实 opencode、真实 OpenViking、真实 Ollama
- 真实 Feature Wiki 已同步
- 用例：用户描述业务问题 → 模型调用 `openviking_search` → 读 Wiki → 给出带 `viking://` 来源的回答
- 用例：用户问代码问题 → 模型先 `openviking_search` 命中 repo 候选 → 调 `codeask_prepare_worktree` → opencode 原生 read 真实文件 → 输出
- 用例：OpenViking server 关停 → 会话明确弹错；不静默回退

---

## 6. 失败语义

OpenViking 不可用的分类沿用 v1.0.4 opencode 失败模型：

| 分类 | 触发 | 用户可见 |
|---|---|---|
| bin missing | `openviking-server` 找不到 | 居中弹窗：知识检索后端未安装 |
| start failed | `process.ensure_server` 多次失败 | 居中弹窗：知识检索后端启动失败 |
| process exited | keepalive 检测到崩溃 | 当前轮会话报错；下一轮自动重试 |
| health timeout | `/health` 多次超时 | 同上 |
| embedding unhealthy | Ollama 不可达；OpenViking 报错 | 居中弹窗：embedding 服务不可用 |
| version unsupported | 版本与 `openviking_verified_version` 不一致 | 仅 admin 可见 warning |

错误事件经 SSE 透传给前端，沿用 v1.0.4 `error` 事件结构（含 `backend: "openviking"` 字段）。

---

## 7. 测试矩阵

| 类型 | 用例 |
|---|---|
| 单元 | 上下文片段渲染；工具白名单过滤；OpenViking 错误分类 |
| 集成 | fake OpenViking + 真 opencode：tools/list 含正确子集；调用真实 OpenViking 工具事件归一化 |
| live E2E | §5 三个用例 |
| 回归 | v1.0.4 不接 OpenViking 时仍可工作；切换 `rag_backend=none` 时退回 v1.0.4 行为 |
| 升级 | 旧会话刷新继续追问；OpenViking 索引尚未完成时的提示行为 |

---

## 8. 退出条件

- §5 三个 live E2E 用例通过
- 长对话 / 刷新 / 切会话不串
- AGENTS.md 与动态上下文片段经真实模型行为复核（模型实际遵循资源边界，不去 `add_resource`）
- admin 诊断面板能定位故障（OpenViking 崩溃 / Ollama 关停 / token 不一致）
- 文档收口：PRD / SDD / Phase 0/1/2 / acceptance-checklist 全部 status=Completed

下一步：提交并标 v1.0.5 收口。
