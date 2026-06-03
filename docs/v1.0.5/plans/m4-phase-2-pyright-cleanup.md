# M4 阶段二 — pyright strict 清债到 0

> 版本：v1.0.5
> 状态：Completed（2026-06-03 release 复核：`uv run pyright src/codeask evals` 已为 0 errors；仍保留本文作为分批清债历史计划）
> 关联：[Phase 1 计划](./phase-1-sync-adapter.md) · [验收 checklist §3.10](./acceptance-checklist.md) · [设计](../design/openviking-integration.md)

M4 分两阶段交付。**阶段一**（删 FTS5；UI 搜索曾短暂 OpenViking-first/ILIKE 兜底，M11 后收敛回 SQL ILIKE）已完成并验收（commit `ec1414e`）。本文是**阶段二**：把 `src/codeask` 的历史 pyright strict 类型债清零，让 CI 的 pyright gate 重新成为有意义的硬约束。

阶段二已完成。2026-06-03 文档复核时，聚焦 v1.0.5 相关模块的 pyright 子集为 `0 errors, 0 warnings, 0 informations`，acceptance §3.10 也已按完成状态勾选。下方批次计划保留为执行过程记录。

---

## 1. 目标与硬约束

- **目标**：`uv run pyright src/codeask evals` 从基线降到 **0 errors**。
- `native_backend` 维持 exclude（已在 `pyproject.toml [tool.pyright]` 配好，是冻结参考代码，唯一例外）。
- **禁止"假绿"**：
  - 不许大面积撒 `# type: ignore`
  - 不许在 `pyproject.toml` 全局关闭任何 `reportXxx` 规则
  - 不许收窄 `strict` 范围来绕过
  - 要**真修**，否则只是换姿势攒债
- **只做类型修复，不改运行时行为**：用类型标注 / `cast` / None 守卫 / `list()` 包裹等手段解决。**若某处必须改逻辑才能修类型，先停下来标记给评审**，不要静默改行为。
- **不动** `frontend/`、不动 `native_backend/`。
- **分批提交**：每批一个 commit / PR。**每批退出条件** = 该批文件 pyright 0 + `uv run pytest -q` 全绿 + ruff 绿，达标再进下一批。

---

## 2. 基线（snapshot，开工前请重新量）

> 以下为 commit `ec1414e` 时的快照；随批次推进会变化，**开工与每批前用 `uv run pyright src/codeask evals` 重新量**。

总计 **646 errors**。

按规则：

| 规则 | 数量 | 占比 |
|---|---|---|
| reportArgumentType | 185 | 29% |
| reportUnknownMemberType | 178 | 27% |
| reportUnknownVariableType | 136 | 21% |
| reportUnknownArgumentType | 70 | 11% |
| reportOptionalMemberAccess | 25 | 4% |
| reportAttributeAccessIssue | 22 | 3% |
| reportReturnType | 13 | 2% |
| 其余（private / call / unused 等） | ~17 | — |

Unknown* 家族（≈60%）与大部分 `reportArgumentType` **同源**：未标注的数据流（`dict.get` / `json.loads` / ORM 动态属性 / 无标注 helper 返回）。**从源头标注，下游 ArgumentType 会大批连带消掉**，不要逐条按报错点硬塞 `cast`。

---

## 3. 修法 cookbook（按规则）

- **reportReturnType（Sequence vs list）**：`(...).scalars().all()` 返回 `Sequence[T]`，函数标 `-> list[T]`。修：`return list(...)` 或把返回标注改成 `Sequence[T]`。最易，可先全局扫这类。
- **reportUnknownMemberType / reportUnknownVariableType**：值是 `Unknown`（多来自 `dict.get` / JSON / 无标注三方）。修：在**数据进入点**给 dict 标 `dict[str, X]` 或 `TypedDict`、给 `json.loads` 结果 `cast(...)`、给变量显式标注。优先收口边界。
- **reportArgumentType**：把 `Unknown` / `X | None` / 错类型传给已标注参数。多数随 Unknown 修好自动消；残余用 None 守卫或精确 `cast`。
- **reportOptionalMemberAccess**：对 `X | None` 取 `.attr`。修：`if x is None` 守卫 / `assert x is not None`（有不变量时）/ 显式 narrow。
- **reportAttributeAccessIssue**：pyright 认为属性不存在（常见 ORM / 动态）。修：正确标注或在边界 `cast` 到正确模型类型。
- **reportPrivateUsage**：跨模块用 `_private`。修：把需要的 API 提成 public，别跨模块够私有。
- **reportUnnecessaryIsInstance / reportUnusedFunction**：冗余 / 死代码，直接删。

---

## 4. 分批（由小到大、低风险→高风险；每批独立 commit）

> 文件后括号是 `ec1414e` 时的错误数快照，仅供排期参考。

### 批 1 — `llm/`（热身，验证 cookbook）≈30
`llm/gateway.py`(14) · `llm/api_service.py`(7) · `llm/client.py`(5) · `llm/reasoning.py`(4)
锚定测试：LLM gateway / pool / client 相关。

### 批 2 — `wiki/` 核心（非 imports）≈40
`wiki/sources/service.py`(15) · `wiki/documents/service.py`(13) · `wiki/documents/markdown_refs.py`(5) · `wiki/report_projection.py`(4) · `wiki/tree/*`（剩余）
锚定：`test_wiki_documents_api`、`test_wiki_*`、tree 相关。

### 批 3 — `api/wiki` 端点（非 imports）≈51
`api/wiki/documents.py`(19) · `api/wiki/versions.py`(15) · `api/wiki/drafts.py`(10) · `api/wiki/assets.py`(7)
锚定：wiki documents / versions / drafts API 测试。

### 批 4 — imports 子系统 ≈123
`api/wiki/imports.py`(88) · `wiki/imports/session_service.py`(24) · `wiki/imports/service.py`(11)
锚定：import 相关集成测试。批较大，可把 `api/wiki/imports.py` 单独再拆一批。

### 批 5 — `sessions/`（活、敏感）≈131
`api/sessions.py`(103) · `sessions/messages.py`(23) · `sessions/trace_redaction.py`(5)
锚定：`test_sessions_api`、message-stream 集成测试。`api/sessions.py` 重，建议单独成批，改完务必跑会话流集成测试。

### 批 6 — 杂项收尾 ≈19
`app.py`(6) · `api/opencode_status.py`(8) · `agent/chat_runtime/events.py`(5)
锚定：app 启动集成测试 + 既有 chat_runtime events 测试（共享层，别改行为）。

### 批 7 — `opencode_compat` 主链路（最后，最敏感）≈258
`opencode_compat/backend.py`(207) · `events.py`(40) · `http.py`(5) · `mcp/server.py`(6)
⚠️ **M2 刚上线的活主链路、单测覆盖最弱（多靠集成 / e2e）**。要求：
- 把 `backend.py` 再**内部拆几批**（207 不要一把梭）
- 每批后跑 opencode 集成测试，有条件跑一次 `CODEASK_RUN_LIVE_OPENVIKING_E2E=1` 的 live e2e
- **只动类型、严禁顺手改逻辑**
这批是整个阶段二的风险中心。

> 批次顺序可调，但**强烈建议把批 7 放最后**：前 6 批把 cookbook 跑顺、把 Unknown* 收口套路验证好，再啃 `backend.py` 的 207。

---

## 5. 阶段二最终验收（见 acceptance §3.10）

- `uv run pyright src/codeask evals` = **0 errors**
- `.github/workflows/backend.yml` 的 Pyright step 仍是硬 gate（**没加** `continue-on-error`）；`strict` 范围未被收窄；`native_backend` 仍 exclude
- 全量 `pytest` 绿、ruff check / format 绿、前端 tsc / vitest 不受影响、`frontend/src` 与 `api.ts` 未改
- **diff 抽查**：无新增 `# type: ignore`、`pyproject.toml` 未全局禁用任何 `reportXxx`、无静默逻辑变更（纯类型修复）

---

## 6. 工作量提示

646 条、跨多目录含主链路，`backend.py` 单文件 207——**阶段二大概率比阶段一还重**。务必分批、每批绿了再走，别攒大 PR。
