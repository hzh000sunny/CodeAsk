# M10 — 同步任务信息人话化 + 修复 cancelled 任务困死

> 版本：v1.0.5
> 状态：Planned
> 关联：[m8 仪表盘事件流人话化/降噪](./m8-dashboard-ux.md) · [m6 同步完整性与事件](./m6-sync-completeness-and-events.md) · [m11 代码仓同步](./m11-repo-openviking-sync.md) · [m12 同步覆盖补全](./m12-sync-coverage-completion.md) · [acceptance §3.1](./acceptance-checklist.md)
> 来源：2026-05-30 终验复盘——事件流已完成人话化/降噪/补字段，同步任务卡片仍是"机器视角"，需对齐；复盘时发现 `cancelled` 任务在 UI 上无重试入口的真缺口。同次复盘还挖出"代码仓 / feature_readme / 全局目录"等 `source_type` 设计了却从未实现（架构拆分时遗漏），但那是**数据面缺口**而非 UX，已另拆 m11 / m12，**不并入本里程碑**避免范围膨胀。

---

## 0. 背景

M8 把**事件流**做了一轮人话化（中文标题、错误前置、归因+建议+操作按钮）、降噪（默认重点视图、聚合、retention）、补字段（payload 结构化展开）、测试解耦（`data-event-type`）。

但**同步任务卡片**（`OpenVikingSyncJobsCard` / `SyncJobStatusGroup` / `SyncJobItem`）几乎没享受到这轮优化，仍是机器视角：

| 维度 | 事件流（已做） | 同步任务（现状） |
|---|---|---|
| 状态文案 | 中文标题 + badge i18n | `pending/running/failed/indexed` 裸英文，StatusPill、Badge、`状态 {job.status}` 三处都是机器词 |
| 错误信息 | 错误前置 + 人话归因 + 建议 + 操作按钮 | `job.error` 原样 dump 进 `<small title>`，无归因、无"我能干啥" |
| 关键字段 | payload 结构化展开 | `attempts` / `next_retry_at` 后端已返回但前端**完全没渲染** |
| 降噪 | 默认重点视图 | 无进度时仍显示 `ETA —`、`状态 xxx` 冗余行 |
| 测试解耦 | `data-event-type` | 无 `data-status`，e2e 只能按展示文案选行 |

复盘还发现一个 **cancelled 任务困死** 的真缺口（详见 §2）。

---

## 1. 范围与分批

按"价值 / 必要性"分两批：

- **第一批（信息缺口 + 真 bug，价值最高、改动集中）**：§2 cancelled 困死修复、§3 露出 `attempts` / `next_retry_at`。
- **第二批（体验对齐）**：§4 状态/错误人话化、§5 降噪、§6 测试解耦。

非目标：不改后端同步调度逻辑、不改 retry 自愈策略、不动 retention/事件生产策略（M8 已定）。本里程碑只动**展示层 + cancelled 的可操作性**。

**明确不在本里程碑（边界）**：代码仓 → OpenViking 内容同步（`source_type=repo`）属数据面缺失功能，见 [m11](./m11-repo-openviking-sync.md)；`feature_readme` / `wiki_dir` / `global_index` 三类同步覆盖见 [m12](./m12-sync-coverage-completion.md)。本里程碑的 UX 是**前向兼容**的——m11 落地后 `repo` 类任务无需改前端即自动走本里程碑的人话化/状态/降噪展示。

---

## 2. ⚠️ 修复 cancelled 任务在 UI 上被困死（第一批·真 bug）

### 现象与根因（已核对代码）

`cancelled` = 连续失败达 `max_repeat_failures`（默认 5）后自动放弃（`sync.py:615-616`），是 `TERMINAL_STATUSES = {"indexed", "cancelled"}`（`sync.py:28`）里"最需要人介入"的终态。但 UI 把它困死了：

1. 单任务 `重试` 按钮只在 `job.status === "failed"` 时渲染（`OpenVikingDashboard.tsx:871`）——cancelled 行**没有任何单条重试入口**。
2. 顶部"重试失败"批量接口只扫 `status == "failed"`（`openviking_status.py:227`），**不含 cancelled**。
3. 而 StatusPill 又把 `failed + cancelled` 合并成一个"失败"计数显示（`OpenVikingDashboard.tsx:736`）。

结果：管理员看到"失败: 3"，点"重试失败"，cancelled 的那几条根本不动，又找不到单条入口 → 卡死，只能删除或走"重排同步队列"全量重来。

注意：后端单任务 `retry` 接口 `_reset_job_for_retry` **本来就能复活 cancelled**（`openviking_status.py:152` → `:409`，无状态限制；删除接口也允许 `cancelled or failed`，`:193`）。所以这是纯前端可操作性缺口，**无需改后端**。

### 改法

- `SyncJobItem`：把单条 `重试` 按钮的渲染条件从 `status === "failed"` 放宽到 `status === "failed" || status === "cancelled"`。
- 文案区分两种终态语义，避免管理员误以为 cancelled 会自愈：
  - `failed` → "失败（将自动重试）"
  - `cancelled` → "已停止重试（需手动）"
- StatusPill 的合并计数：保留"失败"主数字，但把 cancelled 拆出来单独可见（如副标 "其中 N 已停止重试"），让"需手动介入"的数量不被淹没。
- 顶部"重试失败"批量**不纳入 cancelled**（2026-05-30 已定）：保持"重试失败"按字面只重试 `failed`，cancelled 靠单条按钮覆盖。理由：cancelled 是系统连试 5 次后**有意放弃**的终态，一键批量重启会把已放弃的任务全部唤醒造成刷屏，应由管理员逐条确认。→ **后端 `openviking_status.py:227` 不动**。

### 验收

- cancelled 任务行出现可用的"重试"按钮，点击后该任务回到 `pending` 并最终被调度。
- failed 与 cancelled 在文案/计数上可区分。
- 新增/调整对应单测或 e2e：构造一条 cancelled 任务，断言行内重试按钮存在且点击后状态流转。

---

## 3. 露出 `attempts` / `next_retry_at`（第一批·信息缺口）

### 现状

后端 `to_dict` 已返回 `attempts` 与 `next_retry_at`（`sync.py:591` 一带），`OpenVikingSyncJob` 类型也已声明（`types/api.ts:268-269`），但 `SyncJobItem` 前端**完全没渲染**这两个字段。管理员因此无法回答最关心的问题——"它还会不会自己重试、什么时候重试"。

### 改法

`SyncJobItem` 增补一行只读元信息（紧凑展示）：

- 重试次数："已重试 N / max 次"（max 取 `max_repeat_failures`，前端可用常量 5 或后端透出）。
- 下次重试："下次约 14:30 自动重试"（`next_retry_at` 存在且 `status === "failed"` 时）；cancelled 时改为"已停止自动重试"。
- 可顺带展示 `last_indexed_at` / `last_synced_at`（相对时间），但不是必须，避免行过长。

纯前端、零后端改动、零风险。

### 验收

- failed 任务行显示重试进度与下次重试时间；cancelled 显示"已停止自动重试"。
- 单测覆盖 `attempts` / `next_retry_at` 的渲染与 cancelled 分支。

---

## 4. 状态 / 错误人话化（第二批·对齐事件流）

### 状态文案单一来源

抽 `SYNC_STATUS_LABELS`（与事件流 `EVENT_LABELS` / `OUTCOME_LABELS` 同款）：

```
pending   → 等待中
running   → 运行中
failed    → 失败
cancelled → 已停止重试
indexed   → 已索引
```

StatusPill（`:732-739`）、Badge（`:870`）、行内 `状态 {job.status}`（`:866`）三处共用，消除当前"组标题是中文、pill/badge 是英文"的不一致。

### 错误人话化 + 建议

把事件流 `describeEvent` / `eventRemediation` 的模式搬到同步任务：错误原因前置，给归因 + "你能做什么"。至少覆盖：

- cancelled：「已连续失败 5 次自动停止。请检查 OpenViking 服务是否在线、Embedding 配置是否正确后手动重试。」
- 常见 `job.error` 模式（服务不可达 / Embedding 维度不符 / 鉴权失败等）映射到人话；未知错误 fallback 到原文（保留 `title` 全文）。

### 验收

- 三处状态文案统一中文且来源单一。
- cancelled / 常见失败给出可读归因与建议；未知错误不丢信息。

---

## 5. 降噪（第二批）

- 无进度时折叠 `ETA —` / `状态 xxx` 冗余行（`:864-869`），只在有进度或有 ETA 时展示进度块。
- `indexed` 组保持默认折叠且不轮询（现状 `:791`、`:803` 已如此，**保留**，仅确认不回退）。

---

## 6. 测试解耦（第二批）

- `SyncJobItem` 的 `<li>` 加 `data-status={job.status}`（必要时再加 `data-job-id`），让 e2e 按机器枚举选行，与展示文案解耦——与事件流 `data-event-type` 对齐。
- 现有 live e2e（E3 sync job 重试）若依赖展示文案选行，改用 `data-status`。

---

## 7. 影响面 / 涉及文件

- `frontend/src/components/settings/OpenVikingDashboard.tsx`：`SyncJobItem`、`OpenVikingSyncJobsCard`（StatusPill）、新增 `SYNC_STATUS_LABELS` / 状态文案与建议映射。
- `frontend/tests/openviking-dashboard.test.tsx`：补 cancelled 重试、`attempts`/`next_retry_at` 渲染、状态文案单测。
- `frontend/e2e/openviking-dashboard-management-live.spec.ts`：`data-status` 解耦（如改）。
- 后端：**零改动**（retry/删除接口已支持 cancelled；批量"重试失败"已定不纳入 cancelled，`openviking_status.py:227` 不动）。本里程碑是纯前端。

---

## 8. 决策记录（2026-05-30 已定）

1. **分批**：第一批 §2 + §3（真 bug + 信息缺口），第二批 §4–§6（体验对齐）。
2. **"重试失败"批量不纳入 cancelled**：保持只重试 `failed`，cancelled 靠 §2 单条按钮覆盖，避免批量唤醒已放弃任务刷屏。后端 `openviking_status.py:227` 不动。
3. **分工**：由新开发实现 + 自测，架构（Claude）做 review / 最终验收；本里程碑纯前端，开发不碰后端。

---

## 9. 验收清单（汇总）

- [ ] cancelled 任务行有可用重试按钮，点击后回到调度（§2）
- [ ] failed / cancelled 文案与计数可区分（§2）
- [ ] failed 行显示重试次数 + 下次重试时间；cancelled 显示已停止（§3）
- [ ] 状态文案三处统一中文、单一来源（§4）
- [ ] cancelled / 常见失败给出人话归因 + 建议，未知错误不丢信息（§4）
- [ ] 无进度时不再显示冗余 `ETA —` / `状态` 行（§5）
- [ ] 行带 `data-status`，e2e 解耦（§6）
- [ ] 前端 vitest / e2e 全绿，tsc / eslint clean
