# M6 — 同步完整性、仪表盘事件与 Ollama 实测验证

> 版本：v1.0.5
> 状态：Completed
> 关联：[acceptance §3.2/§3.4/§3.7/§5](./acceptance-checklist.md) · [phase-1](./phase-1-sync-adapter.md) · [m5-write-path-hooks](./m5-write-path-hooks.md)
> 来源：2026-05-27 全量回归发现 B1–B4 验收项引用的功能在 src 中未实现（grep 实证：相关 event_type / scheduler job 不存在）。

> **release 复核说明（2026-06-03）**：本文的 B1/B2 是 M6 当时基于逐篇 `wiki_doc` / `report` 同步的完整性补丁。M11/M12 后当前实现已经收敛为 `wiki_feature` 目录级 sweep：枚举 active feature 的 published Wiki 文档，按 feature 汇总 hash 后导入 `knowledge-base/`；Report 只做 `problem-reports/` 文件投影，不再进入 OpenViking；定时 sweep 还会对账远端 stale wiki feature 并入队 delete。下方旧的 `wiki_doc_changed` / `report_status_changed` 事件名作为历史记录保留，当前 UI 主要看到 `wiki_feature_changed` / `report_projection_changed`。

---

## 0. 背景与范围

2026-05-27 对真实库做完整回归，确认以下 acceptance 项对应的功能**未实现**（均 grep 实证、且 acceptance 中本就 `[ ]`）：

- §3.2 line57/58 崩溃恢复事件、line59 内容变更命名事件、line60 定时刷新事件
- §3.4 line119 Ollama 实测验证事件
- §5 "升级部署…首次 sweep 自动补齐"（实测升级后 `openviking_sync_jobs=0`，已有 45 wiki/6 reports 不自动入队）

本 plan 把这四块（B1–B4）转成开发可执行任务。2026-05-27 已完成实现与测试补齐：启动 backfill / scheduled refresh、命名内容事件、OpenViking 重启与 Ollama 恢复事件、Ollama 并发轻量验证端点与前端按钮均已落地。

**已实现、无需动**的部分：写路径 hook 入队（M5）、keepalive 自动重启机制（已验证：杀 OpenViking 后 ~30s 重生、主进程不受影响）、tuning 读写/回滚/预设、`verify_ollama_recommend` 纯函数。

### 锁定决策（2026-05-27 负责人拍板）
- **B1**：启动一次性 backfill + 每 `scheduled_refresh_hours` 全量重扫；带"已同步且 hash 未变则跳过"的幂等护栏。
- **B4**：轻量探测——查 Ollama 实际并发（`/api/ps` 或其运行配置）与期望比对，不做真实并发压测。

---

## B1. 同步完整性：启动 backfill + 24h scheduled_refresh

**目标**：升级/重启后已有内容自动进 OpenViking；每 24h 补偿性全量重扫。满足 §5 自动补齐、§3.2 line60、§3.7 line163。

### B1-1 sweep 函数（新增）
- 位置：`src/codeask/rag/openviking/sync.py`（`OpenVikingSyncService` 新方法 `sweep_all(*, triggered_by) -> dict[str,int]`），或新建 `sweep.py` 复用 service。
- 枚举：所有 `WikiDocument`（**排除 draft、排除已软删 deleted_at 非空**）+ 所有 `Report`（**仅 `verified=true`**）。复用 M4 反查口径：`source_type=wiki_doc` / `source_id=str(WikiDocument.id)`；`source_type=report` / `source_id=str(Report.id)`。
- **幂等护栏**：对每条算当前正文 markdown sha；仅当 ①无对应 `openviking_sync_jobs` 行，或 ②已有行 `source_hash != 当前 hash`，或 ③已有行 `status != 'indexed'` 时才 `enqueue(operation=upsert)`。已 indexed 且 hash 未变则跳过（避免全量重 embedding 打爆 Ollama）。
- 返回 `{scanned, enqueued, skipped}`，过程 best-effort（单条失败不中断整轮）。

### B1-2 启动 backfill
- 位置：`src/codeask/app.py` lifespan，`if settings.openviking_enabled:` 块内（约 234 行后，keepalive/sync_pending 注册附近）。
- 行为：启动时**异步**触发一次 `sweep_all(triggered_by="startup_backfill")`（用 `asyncio.create_task` 或丢进 scheduler 立即执行，**不阻塞 startup**）。幂等护栏保证重复启动不重复入队。

### B1-3 scheduled_refresh 定时任务（新增 scheduler job）
- 位置：`src/codeask/app.py` lifespan，与现有 `scheduler.add_job(openviking_keepalive/openviking_sync_pending)` 同处（约 236–261）。
- `scheduler.add_job(..., "interval", seconds=settings.openviking_scheduled_refresh_hours*3600, id="openviking_scheduled_refresh", coalesce=True, max_instances=1)`，回调跑 `sweep_all(triggered_by="scheduled_refresh")`，结束后 `emit_event(event_type="scheduled_refresh_summary", outcome="success", payload={scanned,enqueued,skipped})`。
- 同步删除调优 UI 上 `scheduled_refresh_hours` 行的旧占位标注（`frontend/src/components/settings/OpenVikingDashboard.tsx`），改为生效说明。

### B1 测试
- 单测/集成：sweep 入队全部非 draft wiki + verified report；跳过 draft 与 unverified report；二次跑幂等（hash 未变 → enqueued=0）；hash 变更 → 重新入队。
- 升级回归集成：模拟升级后首启（无 OV 表→迁移→backfill），断言 `openviking_sync_jobs` 被填充、`scheduled_refresh_summary` 事件落库。
- e2e：调优卡 `scheduled_refresh_hours` 不再显示旧占位标注。

### B1 完成记录（2026-05-27）
- `OpenVikingSyncService.sweep_all(triggered_by=...)` 已实现：枚举非删除且已发布 Wiki、已验证报告，按 `source_hash` 做幂等护栏。
- `app.py` lifespan 已接启动异步 backfill；APScheduler 已接 `openviking_scheduled_refresh`，按 `openviking_scheduled_refresh_hours` 周期执行并发送 `scheduled_refresh_summary`。
- 调优 UI 已将 `scheduled_refresh_hours` 文案从旧占位标注改为"定时任务生效"。
- 测试覆盖：发布 Wiki / 已验证报告入队，draft / unverified 跳过，hash 未变跳过，hash 变更重新入队。

---

## B2. 命名内容事件 wiki_doc_changed / report_status_changed / repo_synced

**目标**：§3.2 line59——内容变更时事件流出现对应命名事件（当前只有通用 `sync_job_enqueued`）。

- 位置：写路径 hook `src/codeask/rag/openviking/hooks.py`（`drain_wiki_document_syncs` 与 report hook 入队点），以及仓库同步完成点。
- 在每个 hook 入队后调用 `emit_event`：
  - wiki 文档发布/回滚/上传/软删/恢复 → `wiki_doc_changed`（payload：doc id、operation upsert|delete、hash）
  - Report verify/unverify/reject/删除 → `report_status_changed`（payload：report id、verified 前后、operation）
  - 仓库同步完成 → `repo_synced`（payload：repo/feature、计数）
- **去重**：确认现有 `sync_job_enqueued` 事件来源（e2e 渲染中可见），命名事件应**取代**该路径上的通用事件，或明确二者语义分工，避免一次变更两条事件刷屏（M4 已有去重/限流要求 §3.6 line138，沿用）。

### B2 测试
- 集成：发布 wiki → `wiki_doc_changed`；verify report → `report_status_changed`；仓库同步 → `repo_synced`；draft/unverified 编辑**不**产生事件（沿用 §3.7 过滤）。
- e2e：事件流类型过滤里出现这三类。

### B2 完成记录（2026-05-27）
- hook 路径通过 `emit_enqueue_event=False` 避免重复发送通用 `sync_job_enqueued`，改由 `emit_named_change_event` 发送业务命名事件。
- Wiki 文档相关 hook 发送 `wiki_doc_changed`；报告状态相关 hook 发送 `report_status_changed`；代码仓同步完成发送 `repo_synced`。
- 集成测试覆盖 Wiki 发布、promote、import、legacy backfill、删除、恢复，以及报告 verify / unverify / delete 事件。

---

## B3. 崩溃/恢复事件 openviking_restart_detected / ollama_recovery

**目标**：§3.2 line57/58。机制（keepalive 重启、jobs 持久化续传）已具备，**只缺事件落库**。

### B3-1 openviking_restart_detected
- 位置：`src/codeask/app.py:_ensure_openviking_server`（keepalive 回调，:430）。
- 在闭包里维护上一次 handle 状态（pid/running），当 `ensure_server()` 检测到进程曾 down、本次重新拉起（pid 变化/从无到有）时 `emit_event(event_type="openviking_restart_detected", outcome="warning", payload={old_pid,new_pid,reason})`。需把 `session_factory` 传进 keepalive 闭包。
- 续传：`run_pending_jobs` 本就读 DB 中 pending/failed，重启后自动续跑、**不重置进度**（已验证 jobs 持久化）；加一条集成测试断言重启后 job 状态/进度不被清零即可。

### B3-2 ollama_recovery
- 位置：新增或并入一个周期任务，用 `check_ollama_models`（现有 ollama 健康探针）跟踪健康态；unhealthy→healthy 跃迁时 `emit_event(event_type="ollama_recovery", outcome="success")`。
- 可并入 `openviking_sync_pending` 或单独 interval job；状态用一个小 dict 跨周期保存（同 B3-1 思路）。

### B3 测试
- 集成/live：杀 OpenViking → 轮询事件流出现 `openviking_restart_detected`，且既有 sync_jobs 进度未重置。
- 集成：mock ollama 健康 down→up → `ollama_recovery`。

### B3 完成记录（2026-05-27）
- `_ensure_openviking_server` 已跟踪上一次进程句柄；keepalive 检测到非启动场景 pid 变化时发送 `openviking_restart_detected`。
- 新增 Ollama 健康周期检查，unhealthy → healthy 时发送 `ollama_recovery`。
- 单测覆盖 restart 事件、Ollama recovery 事件，以及重启后 sync job 进度不被重置。

---

## B4. ollama_settings_verified — 轻量探测

**目标**：§3.4 line119。复用 `tuning.py:252 verify_ollama_recommend(expected_num_parallel, probe)`。

- 新增 admin 端点：`POST /api/admin/openviking/tuning/ollama_verify`（`src/codeask/api/openviking_tuning.py`，`require_admin`）。
  - 从 tuning 读 `ollama_recommend.num_parallel` 期望值。
  - 提供**轻量 probe**：查 Ollama 实际并发——优先 `GET {ollama_base_url}/api/ps`（看运行模型/并发）或 Ollama 暴露的运行配置；拿到 observed_parallel。
  - 调 `verify_ollama_recommend(expected_num_parallel=期望, probe=轻量probe)`，`emit_event(event_type="ollama_settings_verified", outcome="success" if verified else "warning", payload={expected, observed})`，返回结果。
- 前端：`OpenVikingDashboard.tsx` 在 Ollama systemd snippet 区（约 803 行）加"验证"按钮，调上面端点，展示 observed vs expected + outcome。

### B4 测试
- 集成：mock probe 返回 ≥expected → outcome=success + 事件；< expected → warning + 事件。
- e2e（新 UI 必须有用例）：management spec 加——点"验证"按钮 → 出现结果文案 + 事件流 `ollama_settings_verified`。

### B4 完成记录（2026-05-27）
- 新增 `POST /api/admin/openviking/tuning/ollama_verify`：读取 `ollama_recommend.num_parallel`，轻量探测 Ollama 运行并发，并发送 `ollama_settings_verified`。
- 默认 probe 读取 Ollama `/api/ps`；测试可通过 `app.state.ollama_parallel_probe` 注入稳定探针。
- 前端 snippet 区新增"验证 Ollama 设置"按钮，展示 expected / observed 与验证结果。
- 集成测试覆盖 success / warning 两种事件；管理页 live E2E 已补按钮与事件断言。

---

## 验收口径更新（实现后回填 acceptance-checklist）
- §3.2 line57/58/59/60 → 已勾 [x]，关联本 plan。
- §3.4 line119 → 已勾 [x]。
- §3.7 line163 scheduled_refresh 过滤 → 已勾 [x]。
- §5 "升级部署…首次 sweep 自动补齐" 行 → 由 backfill 覆盖，标 Passed。

### A2 / C1 收口记录（2026-05-28）

- `frontend/e2e/admin-agent-source-live.spec.ts` 已对齐 contextual-QA 契约：不再强制要求模型必须调用代码仓工具；硬性判据收敛为回答正确性与错误边界。若模型确实调用仓库 / 文件检查工具，测试会记录 `tools:*` 采样用于复盘，但不把"必须调工具"作为通过条件。
- `frontend/e2e/openviking-rag-live.spec.ts` 已放松正向工具链断言：Wiki 语义召回、源码桥接、degraded fallback 均以回答正确性和边界行为为主，不再强制 `openviking_* → codeask_prepare_worktree → grep/read` 三连。保留两类硬边界：OpenViking 写工具（`openviking_remember` / `openviking_add_resource` / `openviking_forget`）不得执行；OpenViking degraded 时不得调用 `openviking_*`。
- 已新增 Playwright `globalSetup`，在 live E2E 启动前对 `references/anything-llm` 做幂等 git checkout 初始化：目录存在但 `.git` 缺失时自动 `git init && git add -A && git commit`，避免 fresh checkout / CI / 其它环境中 continuity 与 feature-scoped AnythingLLM 场景自跳过。
- live 验证记录：
  - `CODEASK_RUN_LIVE_OPENVIKING_E2E=1 ... e2e/openviking-rag-live.spec.ts --reporter=line`：3/3 passed，运行时仅启用 `DeepSeek-OpenAI-Pro`，符合"DeepSeek-pro 跑 rag-live"要求。
  - `CODEASK_RUN_LIVE_AGENT_E2E=1 ... e2e/admin-agent-source-live.spec.ts --reporter=line`：1/1 passed。
  - `rm -rf references/anything-llm/.git` 后，`CODEASK_RUN_LIVE_AGENT_CONTINUITY_E2E=1 CODEASK_RUN_LIVE_FEATURE_SCOPED_CODE_E2E=1 ... agent-conversation-continuity-live + agent-feature-scoped-code-live --reporter=line`：3/3 passed，且 `.git` 被 globalSetup 自动恢复。

## 质量门禁（每项退出条件）
- `uv run pyright src/codeask evals` = 0；`uv run pytest -q` 绿；ruff check/format 绿。
- 前端 tsc/vitest/eslint(--max-warnings=0) 绿。
- 涉及 UI 的（B1 调优标注、B4 验证按钮）补 `CODEASK_RUN_LIVE_OPENVIKING_E2E=1` live e2e。

## 不在本 plan 范围
- 真实库测试污染清理（负责人另行安排）。
- C-1 dashboard e2e 硬编码路径断言修复、§1/§3.9/§8 文档口径——见回归修复清单 A/C/D 段，单独处理。
- 注：`dashboard.py:_redact_payload`（:60）会把事件 payload 里以 `/` 开头的字符串脱敏为 `[absolute-path-redacted]`。本 plan 新增事件 payload 不应放绝对路径；若后续需要 admin 看完整路径，再按 F-1 同口径单独评估，不在此扩范围。
