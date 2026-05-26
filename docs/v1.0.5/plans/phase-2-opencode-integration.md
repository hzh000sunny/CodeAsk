# Phase 2 — opencode 主链路接入 OpenViking（交付里程碑 M2）

> 版本：v1.0.5
> 里程碑：**M2**（交付阶梯见 [phase-1 §1](./phase-1-sync-adapter.md)；顺序 M1 → **M2** → M3 → M4 → M5）
> 状态：M2 implementation verified（M2.0 spike signed；M2.1–M2.6 coded；live E2E passed on 2026-05-25）
> 关联：[PRD](../prd/rag-knowledge.md) · [设计](../design/openviking-integration.md) · [Phase 0](./phase-0-spike.md) · [Phase 1](./phase-1-sync-adapter.md) · [收口验收](./acceptance-checklist.md)

---

## 0. 前置条件

- **M1 完成**（不是整个 Phase 1）：CodeAsk 后端能稳定运行 OpenViking server、手动同步真实数据、admin 诊断可见。M2 只依赖 M1；native 隔离 (M3) / FTS5 删除 (M4) / 写路径 hook (M5) 排在 M2 之后，不阻塞 opencode 接入
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
- 失败语义：OpenViking 是增强、不是 hard dep——不可用时 opencode 模型自行退回 native `read/grep/glob`；动态上下文 / `opencode.json` 在 OpenViking 不健康时不注入 OpenViking 段落；admin 仪表盘标 degraded 但用户路径不弹窗中断（详见 §6）
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

### 2.0 M2.0 Spike 结论（2026-05-25）

本节结论基于 OpenViking 0.3.17 源码、opencode 1.14.48 源码，以及本机真实 OpenViking server / opencode CLI 验证。

#### OpenViking MCP endpoint

- endpoint：`http://127.0.0.1:1933/mcp`
- transport：OpenViking 使用 `FastMCP.streamable_http_app()` 暴露 MCP，实际是 **streamable HTTP**。opencode 1.14.48 对 remote MCP 会先尝试 `StreamableHTTPClientTransport`，失败后才尝试 `SSEClientTransport`；本机验证命中 `StreamableHTTP`。
- auth：`/mcp` 复用 REST API 的 `openviking.server.auth.resolve_identity`。CodeAsk M1 生成的 `ov.conf` 是 `server.auth_mode="trusted"`，未配置 root api key 时，需要传：
  - `X-OpenViking-Account`
  - `X-OpenViking-User`
  - `X-OpenViking-Agent`
- Bearer：OpenViking 本身也支持 `Authorization: Bearer <api-key>` / `X-Api-Key`。但在 CodeAsk 管理的本地 trusted 模式下，M2 默认使用 trusted identity headers；如果后续把 OpenViking 切到 api_key 模式或 trusted+root key，再补 Bearer。

真实 MCP `tools/list` 输出：

```text
["find", "search", "read", "list", "remember", "add_resource", "grep", "glob", "forget", "health"]
```

一次成功 MCP 调用样本：

```text
call_tool("health", {})
=> OpenViking is healthy (service initialized, storage: VikingFS)

call_tool("find", {"query":"CodeAsk OpenViking M1","target_uri":"viking://","limit":3})
=> Found 3 item(s):
   - [resource 59%] viking://resources/codeask/.overview.md
   - [resource 59%] viking://resources/codeask/features/m1-smoke/knowledge-base/m1-smoke-1779713473981.md/m1-smoke-1779713473981.md
   - [resource 52%] viking://resources/codeask/features/m1-smoke/.overview.md
```

真实 opencode 连接样本：

```text
opencode mcp list
=> openviking connected
=> http://127.0.0.1:1933/mcp
=> service=mcp key=openviking transport=StreamableHTTP connected
=> service=mcp key=openviking toolCount=10 create() successfully created client
```

#### remote MCP 工具命名

opencode 1.14.48 在 `packages/opencode/src/mcp/index.ts` 中按以下规则生成模型可见工具名：

```ts
result[sanitize(clientName) + "_" + sanitize(mcpTool.name)] = convertMcpTool(...)
```

因此 CodeAsk 使用 MCP server key `openviking` 时，模型侧工具名是：

```text
openviking_find
openviking_search
openviking_read
openviking_list
openviking_remember
openviking_add_resource
openviking_grep
openviking_glob
openviking_forget
openviking_health
```

前端行动轨迹识别必须以 `openviking_` 前缀处理，不使用 `openviking.find` 或 `openviking:find`。

#### opencode permission 白名单语义

opencode 的 `permission` 可以对 remote MCP 工具做单工具 deny，使用的是模型可见的 prefixed tool name，例如：

```json
{
  "permission": {
    "openviking_remember": "deny",
    "openviking_add_resource": "deny",
    "openviking_forget": "deny"
  }
}
```

源码依据：

- `session/prompt.ts` 会把 `mcp.tools()` 返回的工具加入模型工具集，key 为 `openviking_*`
- `session/llm.ts::resolveTools()` 调 `Permission.disabled(Object.keys(input.tools), ...)`，对 `pattern="*"` 且 `action="deny"` 的工具在发送给模型前过滤
- `session/prompt.ts` 在 MCP 工具执行前也会 `ctx.ask({ permission: key, patterns: ["*"] })`，因此即使工具定义漏出，执行层仍会被 deny 拦住

结论：M2.2 采用 **选项 a：opencode permission deny 写工具**，暂不增加 CodeAsk 后端 MCP proxy。注意 `opencode mcp list` 仍会显示 OpenViking server 原始 10 个工具，这是 MCP 连接诊断视角；模型实际可见工具集会被 `permission` 过滤为只读子集。M2.2 需要补配置快照测试，断言 `opencode.json.permission` 含上述 3 个 deny，并在 live E2E 通过真实行动轨迹确认模型只调用只读工具。

实现选项：

- a) 在 opencode 工具白名单（`opencode.json.permission.tool.*` 或同等机制）中显式 deny 三个写工具
- b) 通过 OpenViking server 配置（如果支持 per-token tool ACL）限定 mcp token 可见工具集
- c) CodeAsk 后端为 OpenViking MCP 加一层 proxy，过滤 tools/list

Phase 2 spike 已确认 opencode 1.14.48 支持按 prefixed tool name 做 per-tool deny，采用 (a)。只有当后续真实 E2E 发现模型仍能看到或调用写工具时，才回退到 (c)。

---

## 3. 上下文注入

`opencode_compat/context.py.build_dynamic_codeask_context` 追加 SDD §8 的 Markdown 段落。具体要写入：

- OpenViking 根 URI
- verified vs draft 权重原则
- 代码证据走 `codeask_prepare_worktree` 的硬约束
- OpenViking `read` 与"真实源码"语义差异
- 失败时不要假装命中

并在每轮 system prompt 中同步注入；写入 `CODEASK_CONTEXT.md` 的部分照旧。

实现记录（2026-05-25）：

- `src/codeask/app.py` 在 OpenViking `process.running` 且 `/health` healthy 时才给 `OpenCodeCompat` 注入 OpenViking MCP resolver；degraded/disabled 时返回 `None`
- `src/codeask/agent/opencode_compat/config.py` 生成 `mcp.openviking` remote entry，显式 `"oauth": false`，trusted headers 为 `X-OpenViking-Account/User/Agent`
- `permission` 显式 deny `openviking_remember` / `openviking_add_resource` / `openviking_forget`，且不追加 `"*": "allow"` 这类会覆盖 deny 语义的规则
- `build_dynamic_codeask_context(..., openviking_available=True)` 才注入 `## OpenViking Knowledge`；不可用时整段省略，保持 v1.0.4 行为
- 系统提示补充：OpenViking 是只读语义召回；`OpenViking read` 是知识快照，不等同真实源码；代码证据仍需 `prepare_worktree`

---

## 4. 前端

`frontend/src/components/session/action-trace/`：

- `ActionTraceEvent.tsx` 识别 `openviking_*` 工具
- `ToolCallEvent.tsx` / `ToolResultEvent.tsx` 展示 OpenViking URI、score、耗时
- 路径脱敏沿用 `path-redaction.ts`
- admin 设置页 OpenViking 卡片（Phase 1 已建）增加"会话调用统计"小节（可选）

**会话视图边界**（PRD §10.6）：

- 会话页 Agent 行动轨迹**只**展示 opencode 调 OpenViking MCP 的工具事件（`find/search/read/grep/glob/list`）
- **不**展示后台同步事件（`wiki_doc_changed` / `scheduled_refresh` / `ollama_recovery` 等）—— 这些只在 admin OpenViking 仪表盘可见
- 不在普通用户会话里暴露 admin 视角的事件，避免污染主视图

实现记录（2026-05-25）：

- 前端按 `openviking_` 前缀识别工具，展示为 `OpenViking 语义检索 / 读取 / 列表 / Grep / Glob / 健康检查`
- 工具结果详情展示 `viking://` URI、score、耗时；路径脱敏继续由 `path-redaction.ts` 统一处理
- 后端 `opencode_compat/events.py` 保留 opencode 工具结果的结构化 `output` 到 `tool_result.result`，避免前端只能从字符串解析 OpenViking 结果

---

## 5. live E2E

新增 `frontend/e2e/openviking-rag-live.spec.ts`，默认跳过，显式 `CODEASK_RUN_LIVE_OPENVIKING_E2E=1` 后执行：

- 真实 LLM、真实 opencode、真实 OpenViking、真实 Ollama
- 真实 Feature Wiki 已同步
- 用例：用户描述业务问题 → 模型调用 `openviking_search` → 读 Wiki → 给出带 `viking://` 来源的回答
- 用例：用户问代码问题 → 模型先 `openviking_search` 命中 repo 候选 → 调 `codeask_prepare_worktree` → opencode 原生 read 真实文件 → 输出
- 用例：OpenViking server 关停 → 模型自动退回 native `read/grep/glob`，会话继续；admin 仪表盘标 degraded；用户路径不弹窗中断

当前实现已新增 live spec 框架，并覆盖：

- 手动同步一条 Wiki 知识 → 会话自然语言提问 → 期望模型调用 `openviking_*` 只读工具，且不调用三个写工具
- OpenViking 召回源码候选 → `codeask_prepare_worktree` → opencode 原生 `grep/read` 读取准备好的真实仓库
- OpenViking degraded / 不健康 → opencode 会话不注入 OpenViking MCP 与上下文段，模型通过 workspace wiki 的 native `read/grep/glob` 继续回答

2026-05-25 实测记录：

```bash
CODEASK_RUN_LIVE_OPENVIKING_E2E=1 \
CODEASK_REALDATA_BASE_URL=http://127.0.0.1:5173 \
CODEASK_REAL_DATA_DIR=/home/hzh/.codeask \
corepack pnpm --dir frontend exec playwright test \
  -c playwright.realdata.config.ts \
  e2e/openviking-dashboard-live.spec.ts \
  e2e/openviking-rag-live.spec.ts \
  --project=chromium
```

结果：4 passed（admin dashboard、Wiki semantic recall、source bridge、degraded fallback）。

同日补充执行真实库 LLM 配置 smoke：

```bash
CODEASK_LIVE_LLM_CONFIG_SMOKE=1 \
CODEASK_LIVE_LLM_SMOKE_TIMEOUT=180 \
uv run pytest tests/live/test_live_opencode_llm_configs.py -q -s
```

结果：DeepSeek 4 条配置通过；火山 5 条配置均返回外部服务 `InvalidSubscription`（账号无有效 CodingPlan subscription 或订阅过期）。该项不判定为 M2 OpenViking 主链路代码失败，但不能在验收记录中写成"所有 LLM 配置通过"；修复外部账号状态后需复跑。

落地坑记录：

- **全局 LLM 池重试不能重写同一个 workspace 的 `opencode.json`。** 实测在同一 opencode workspace 中先用坏 provider 触发 `session.error`，再把 `opencode.json` 重写成另一个 provider 后，opencode 会只记录新 user message，不产出 assistant。M2 修复为：全局池会把当前所有 enabled global configs 写成稳定 provider set；单轮重试只切换 `prompt_async` 的 provider/model，并强制创建新的 external session，不重写 provider set。
- **opencode 会把用户消息的 text part 也作为 `message.part.updated` 事件发出。** 该事件不能算 assistant 可见输出，否则坏 provider 在真正回答前报错时会被误判为"已经输出正文"，从而阻止全局池轮转。M2 修复为：后端维护 `message.updated.info.role`，明确跳过 `role=user` 的 text part / delta。
- **源码桥接 E2E 不能把测试 marker 写入 Feature 元数据。** 初版用例把 marker / PermissionMode 线索写入 Feature 名称或描述，模型可以直接从动态特性目录定位并 prepare worktree，绕过 OpenViking。最终用例只注册仓库，把 `marker -> repo_id` 映射写入 OpenViking 资源，断言模型先调用 `openviking_*` 再 `codeask_prepare_worktree` / native `grep/read`。
- **OpenViking health 探针不能在同一轮重复执行。** 初版 `app.py` 中 MCP resolver 与动态上下文可用性判断各自调用 `_resolve_openviking_mcp_config`，当 OpenViking 进程还活着但 `/health` 卡住时，degraded 用户路径会叠加两次 2s 超时。M2 修复为：`initialize_session` 解析一次 OpenViking MCP config 并写入 opencode binding；`run_turn` 从 binding 的 `config_json.mcp.openviking` 推导 `openviking_available` 传给 context builder，不再重复探针。

---

## 6. 失败语义

OpenViking 是 v1.0.5 的**增强**，按 PRD §8 / SDD §9 graceful degrade。Phase 2 接入 opencode 后失败语义如下：

| 分类 | 触发 | 用户路径 | admin 仪表盘 |
|---|---|---|---|
| bin missing | `openviking-server` 找不到 | opencode `opencode.json` 不注入 OpenViking MCP；动态上下文不注入 OpenViking 段落；模型走 native `read/grep/glob` | 卡片标红 `bin_missing` |
| start failed | `process.ensure_server` 多次失败 | 同上 | 卡片标红 `start_failed` |
| process exited | keepalive 检测到崩溃 | 当前轮 MCP 调用返回 error → opencode 模型自行退回 native 工具；不中断会话 | 仪表盘事件 `openviking_restart_detected` + 进度从中断点续传 |
| health timeout | `/health` 多次超时 | 同上 | 同上 |
| embedding unhealthy | Ollama 不可达；OpenViking 报错 | 已索引内容继续可查；新内容暂不入；用户路径无感 | 卡片标黄 `embedding_unhealthy` |
| version unsupported | 版本与 `openviking_verified_version` 不一致 | 阻止启动场景下进入 `backend_unavailable`，同样兜底 | warning |

错误事件经 SSE 透传给前端用于行动轨迹展示（沿用 v1.0.4 `error` 事件结构，含 `backend: "openviking"` 字段）；但**不**因为 OpenViking 整体不可用而向普通用户弹窗——降级状态仅在 admin 仪表盘可见。

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
