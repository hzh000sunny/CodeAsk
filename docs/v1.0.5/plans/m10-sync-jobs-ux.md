# M10 — 同步任务信息人话化 + 修复 cancelled 任务困死

> 版本：v1.0.5
> 状态：实现完成（前端 vitest 253 + 后端集成 + E3 live e2e 全绿，tsc/eslint clean）；待负责人最终验收
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

按"价值 / 必要性"分三批：

- **第一批（信息缺口 + 真 bug，价值最高、改动集中）**：§2 cancelled 困死修复、§3 露出 `attempts` / `next_retry_at`。
- **第二批（体验对齐）**：§4 状态/错误人话化、§5 降噪、§6 测试解耦。
- **第三批（交互改造，2026-05-30 并入）**：§7 列表从"分状态折叠组"改为"筛选 + 分页扁平列表"，对齐事件流并做视觉打磨。

非目标：不改后端同步调度逻辑、不改 retry 自愈策略、不动 retention/事件生产策略（M8 已定）。本里程碑动**展示层 + cancelled 可操作性 + 列表交互形态**，以前端为主，外加**一处后端分页改动**（A5：sync_jobs 列表 cursor→page/offset，见 §7/§9）。

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
- StatusPill 拆成**独立 Pill**（2026-05-30 定）：把现在合并的 `failed`(failed+cancelled) 改成两个——`失败`（只数 `counts.failed`）+ 新增 `已停止重试`（数 `counts.cancelled`，`tone="error"`，count=0 时弱化/不显眼）。理由：下方分组列表（`:744`）本就把"失败任务""已取消"分开，pill 汇总拆开才一致，且让"需人工介入"的数量成为一等信息而非埋在副标。**不要塞 sub-text。**
- `statusOutcome`（`OpenVikingDashboard.tsx:1598`）给 `cancelled` 补 `"error"`（2026-05-30 定）：现在 cancelled 落 default `"info"`（中性 badge），但它是最需介入的终态，应返回 `"error"`，让 Badge 颜色与"困死"语义一致。随 A1/A3 一起改，纳入本节验收。
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
  - 格式 = **绝对本地化时间**（2026-05-30 定）：`next_retry_at` 是 ISO 时间戳，**不要套 `formatSeconds`**（那是给 ETA 秒数的）。新写一个格式化函数：同一天显示 `HH:MM`，跨天带日期。理由：退避最长到 6h，绝对时间比"X 分钟后"更不易误读。
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
- 现有 live e2e（E3 sync job 重试）已从"状态 failed"文案断言改用 `data-status="failed"`，真实浏览器重跑通过。

---

## 7. A5 — 列表交互改造：分组折叠 → 筛选 + 分页（第三批，2026-05-30 并入）

背景：现 `SyncJobStatusGroup` 是 5 个 `<details>` 折叠组 + 每组"加载更多"无限滚，和事件流是两套交互；且顶部 StatusPill 已给各状态计数，分组与之重复。改成和 `OpenVikingEventStream` 一致的"筛选 + 分页扁平列表"，并**做的好看点**。

### 改法
- 删除 `SyncJobStatusGroup` 折叠组结构，改为单一**扁平列表**（复用 `SyncJobItem` 行）。
- **状态筛选**：直接点顶部 StatusPill 切换（`aria-pressed` + `aria-label`，再点取消）——药丸**兼任"计数 + 筛选"**，不另设下拉（评审去重，见 §8）。
- **分页（page/limit）**：上一页 / 下一页 + 每页条数（5/10/20/50）+ 跳页输入框，显示 `共 N 条 · 第 X / Y 页`，样式对齐事件流。保留默认轮询（pending/running/failed 5s）。
- **StatusPill 汇总行保留**（一眼看各状态量，并兼作筛选入口）。
- **视觉打磨**：列表 + 分页条整体对齐 `OpenVikingEventStream`；§4/§3 的 meta 行、错误归因、两个 Pill 在新布局下排版正确（CSS 见 §8）。

### 边界
按负责人要求做**完整 page/limit 分页 + 跳页**（与事件流一致），为此 m10 **包含一处后端改动**：`/admin/openviking/sync_jobs` 列表端点 + `OpenVikingSyncService.list_jobs` 由 cursor keyset 改为 offset 分页（返回 `{items, total, page, limit}`，并修了原 `total=当前页条数` 旧 bug），同步更新集成测试。其余仍为前端。

### 验收
- 列表无折叠组；状态筛选 + 上一页/下一页可用；StatusPill 汇总仍在；视觉与事件流一致、整洁。

---

## 8. 复检发现与返工（2026-05-30 首轮提交后）

开发首轮提交 vitest/lint/tsc 全绿，但复检发现**验证纪律缺口**与两处 CSS 问题——`vitest 绿 ≠ 跑起来对`，UX 里程碑必须亲眼验。代码本体（A1–A4）质量合格，以下为返工项：

1. **CSS·新类无样式**：新增的 `.settings-openviking-job-meta`（jobMetaLine 那行）在 `globals.css` **无对应规则**，当前裸渲染。补样式（字号/颜色/间距，与行内 `small` 协调）。
2. **CSS·死规则**：被删除的 `.settings-openviking-status-only`（`globals.css:3848`）已无引用，删掉。
3. **A5 新布局视觉打磨**：两个 Pill、meta 行、错误归因、筛选/分页条在页面上确认整洁好看。

上述 3 项已落地（`.settings-openviking-job-meta` 补样式、死规则 `.settings-openviking-status-only` 已删）。

### 2026-05-31 UI 评审优化（经 ui-ux-pro-max 评审）已落地
- **删冗余筛选**：原 A5 既有可点 StatusPill 又有状态下拉，二者重复 → 删下拉，药丸兼任筛选（+`aria-pressed`/`aria-label`）。
- **合并重复空态**：counts 全 0 时两处"暂无同步任务"会同时渲染（潜在多匹配 bug）→ 合并为一处。
- **错误去重**：已知错误行内提示去掉"（原因：原文）"，原文归"详情"；未知错误仍兜底显示原文不丢信息。
- **状态徽标位置与事件流一致**：保持在「详情」按钮右侧（曾试前置，按负责人要求回退对齐 `EventItem`）。
- 验证：前端 vitest 253 全过、tsc/eslint clean；E3 live e2e 改用 `data-status` 后真实浏览器重跑通过（14s）。

### DoD 收紧（写死，今后所有 UX 改动适用）
- **必须在运行中的页面亲眼验证**：造一条 `failed` + 一条 `cancelled` 同步任务，确认重试按钮、计数、归因、降噪、A5 列表/筛选/分页都正确渲染，再报"完成"。`vitest 绿` 只是 code-complete，不是 done。
- 诊断运行态问题先 `ps` / `ss` 看实际进程，不靠猜（首轮把 vite dev 误判为 prebuilt dist）。

---

## 9. 影响面 / 涉及文件

- `frontend/src/components/settings/OpenVikingDashboard.tsx`：`SyncJobItem`、`OpenVikingSyncJobsCard`（StatusPill 兼筛选）、`SYNC_STATUS_LABELS` / 状态文案与建议映射；**A5**：删 `SyncJobStatusGroup` 折叠组、改扁平列表 + StatusPill 筛选 + page/limit 分页（跳页）。
- `frontend/src/lib/api-openviking.ts` / `frontend/src/types/api.ts`：`listOpenVikingSyncJobs` 由 `cursor` 改 `page`；响应类型 `next_cursor` → `{page, limit}`。
- `frontend/src/styles/globals.css`：补 `.settings-openviking-job-meta` 样式、删死规则 `.settings-openviking-status-only`、StatusPill 可点筛选样式。
- `frontend/tests/openviking-dashboard.test.tsx`：cancelled 重试、`attempts`/`next_retry_at`、状态文案、A5 翻页/筛选/page 重置/错误分支+fallback/空态单测。
- `frontend/e2e/openviking-dashboard-management-live.spec.ts`：E3 改用 `data-status="failed"` 断言（原"状态 failed"行已被 A4 删除），真实浏览器重跑通过。
- **后端（A5 分页改动）**：`src/codeask/api/openviking_status.py`（列表端点 cursor→`page`/`limit`，返回 `{total, page, limit}`）、`src/codeask/rag/openviking/sync.py`（`list_jobs` offset 分页 + 真 `total`，删 cursor 编解码）、`tests/integration/test_openviking_admin_api.py`（page 分页 + 超末页空页用例）。retry/删除接口原已支持 cancelled、未动；批量"重试失败"不纳入 cancelled。

---

## 10. 决策记录（2026-05-30 已定）

1. **分批**：第一批 §2 + §3（真 bug + 信息缺口），第二批 §4–§6（体验对齐），第三批 §7（A5 交互改造）。
2. **"重试失败"批量不纳入 cancelled**：保持只重试 `failed`，cancelled 靠 §2 单条按钮覆盖，避免批量唤醒已放弃任务刷屏。后端 `openviking_status.py:227` 不动。
3. **A5 并入 m10**：列表改"StatusPill 筛选 + page/limit 分页（含跳页）"对齐事件流并视觉打磨。按负责人要求做**完整分页**，故 **m10 含一处后端改动**（sync_jobs 列表 cursor→page，见 §9）。状态徽标位置与事件流 `EventItem` 一致（详情按钮右侧）。开发**重写**列表区。
4. **分工**：由新开发实现 + 自测，架构（Claude）做 review / 最终验收。m10 含一处分页后端改动（§9）；DoD 收紧——UX 改动必须在运行页面亲眼验证（造 failed/cancelled 数据）后才算完成（§8）。

---

## 11. 验收清单（汇总）

- [x] cancelled 任务行有可用重试按钮，点击后回到调度（§2）
- [x] failed / cancelled 文案与计数可区分；StatusPill 拆为独立"失败"+"已停止重试"两个 Pill（§2）
- [x] `statusOutcome` 对 cancelled 返回 `"error"`，Badge 颜色与终态语义一致（§2）
- [x] failed 行显示重试次数 + 下次重试时间（绝对本地化时间，非 `formatSeconds`）；cancelled 显示已停止（§3）
- [x] 状态文案三处统一中文、单一来源（§4）
- [x] cancelled / 常见失败给出人话归因 + 建议，未知错误不丢信息（§4）
- [x] 无进度时不再显示冗余 `ETA —` / `状态` 行（§5）
- [x] 行带 `data-status`，e2e 解耦（§6）
- [x] **A5**：列表无折叠组，StatusPill 筛选（aria-pressed）+ page/limit 分页（上下页 + 每页 + 跳页）可用，汇总保留，视觉与事件流一致整洁（§7）
- [x] **A5 后端**：`sync_jobs` 列表 page/offset 分页、真 `total`、超末页空页；集成测试覆盖（§9）
- [x] **CSS**：`.settings-openviking-job-meta` 有样式（非裸渲染）；死规则 `.settings-openviking-status-only` 已删（§8）
- [x] **UI 评审优化**：删冗余下拉、合并空态、错误去重、徽标位置对齐事件流（§8）
- [x] **亲眼验证**：E3 live e2e 在真实浏览器覆盖 failed→重试路径（通过）；负责人页面实看并迭代了徽标位置/提示（§8 DoD）
- [ ] 前端 vitest / e2e 全绿，tsc / eslint clean
