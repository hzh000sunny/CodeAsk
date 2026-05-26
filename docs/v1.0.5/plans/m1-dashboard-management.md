# M1 看板管理层补齐 — OpenViking Admin Dashboard

> 版本：v1.0.5
> 状态：待开发（M1 §7 管理层在前后端均为真空，本文是补齐工单）
> 关联：[Phase 1 §7](./phase-1-sync-adapter.md) · [验收 §3.2/§3.3/§3.4](./acceptance-checklist.md) · [设计 SDD §13.4/§13.6](../design/openviking-integration.md)

## 0. 背景与问题

M1 的 OpenViking admin 看板**只交付了只读状态展示**，规格里整个**管理/交互层（参数调整、模型切换、手动同步操作）在前后端都没实现**。验收时被发现：看板组件未按 §13.4 五卡拆分、布局未对齐、所有参数不可调。acceptance §3.2/§3.3/§3.4 的勾选项至今全空，那才是真实状态——之前不应被当作"已签收"。

本文把缺口整理成可交付工单：后端写端点 + 支撑模块、前端五卡 + 交互控件 + 布局，并为**每个前端 UI 配对 e2e 用例**。

## 1. 现状清点（基于真实代码）

| 区域 | 现状 | 文件 |
|---|---|---|
| 后端 status | `enqueue` / `run_pending` / `list sync_jobs` / `list events` / `status`（只读 + 两个手动同步原子） | `api/openviking_status.py` |
| 后端 tuning | **仅** `GET tuning` + 默认播种；`_detect_preset` 只看 CPU、无 GPU/provider、无预设值、无 recommended | `api/openviking_tuning.py` |
| 后端 embedding | **仅** `GET embedding` + 默认播种 | `api/openviking_admin.py` |
| 后端 tuning 支撑模块 | **整个文件不存在**（plan §2 列的主机识别/预设/snippet/探测从未建） | `rag/openviking/tuning.py`（缺） |
| 后端进程编排 | 仅 `ensure_server` / `shutdown` / `describe`，**无** `restart` / `regenerate_ov_conf` 编排 | `rag/openviking/process.py` |
| 前端 | 单文件 5 个**只读** `surface` 段；无卡片网格 | `components/settings/OpenVikingDashboard.tsx` |
| 前端 api | **仅 5 个 GET**（status/jobs/events/embedding/tuning），无任何 mutation | `lib/api-openviking.ts` |
| 前端 e2e | 仅 1 个只读 smoke | `frontend/e2e/openviking-dashboard-live.spec.ts` |

---

## 2. 后端 checklist

### A1 — 新建 `rag/openviking/tuning.py` 支撑模块（SDD §13.6）

- [ ] `detect_preset() -> (preset_id, preset_values)`：CPU + RAM + GPU（lspci/nvidia-smi）+ embedding provider 综合判定（替换 router 内只看 CPU 的 `_detect_preset`）
- [ ] 各预设 `PRESET_*`（`small_machine/small_server/medium_server/large_server/gpu_host/cloud_embedding`）的 `preset_values` + 每个 key 的 `recommended`
- [ ] `ollama_snippet(num_parallel, num_thread) -> str`（systemd override 片段）
- [ ] `verify_ollama_recommend(expected_num_parallel)`：实测并发探测（§13.6.6），发 `ollama_settings_verified` 事件
- [ ] 单测：不同 CPU/GPU/provider 取值正确；snippet 文本正确

### A2 — tuning 写端点（`api/openviking_tuning.py`，§7.1.4）

- [ ] `POST /admin/openviking/tuning`：校验 key/范围 → append-only 写 `OpenVikingTuningSetting`（`previous_value`）→ 每条发 `tuning_change` 事件 → openviking scope 走 restart、codeask scope 走 scheduler reload；返回 `{applied, rejected, estimated_downtime_seconds}`
- [ ] 极端值（如 `max_concurrent=10000`）被 schema 拒绝，`outcome=error`，不应用
- [ ] `POST /admin/openviking/tuning/rollback`（相同写+重启流程，`notes="rollback"`）
- [ ] `POST /admin/openviking/tuning/apply_preset`（只动 openviking + codeask scope）
- [ ] `GET /admin/openviking/tuning/history?scope&key&limit`
- [ ] `GET /admin/openviking/tuning/preset`（detected_host + preset_values）
- [ ] `GET /admin/openviking/tuning/ollama_snippet`
- [ ] GET tuning 响应补 `recommended` / `previous_value`（当前缺 recommended）

### A3 — embedding 管理端点（`api/openviking_admin.py`，§7.2）

- [ ] `POST /admin/openviking/embedding`（切模型）：校验 admin → 探 Ollama `/api/tags` → 写新 `OpenVikingEmbeddingSetting`（`previous_setting_id`）→ 重生成 ov.conf + 重启 → 所有 sync_jobs 置 pending + 清向量库 → `rebuild_status=rebuilding`；返回 202；发 `embedding_model_switched` + 写 `audit_log`
- [ ] `GET /admin/openviking/embedding/candidates`（Ollama `/api/tags` + 历史模型）
- [ ] `POST /admin/openviking/embedding/rebuild`（不切模型，全量重建）
- [ ] `GET /admin/openviking/embedding/history`

### A4 — 手动同步操作（`api/openviking_status.py`，§7.1.3）

- [ ] `POST /admin/openviking/sync_jobs/{id}/retry`（单 job，发 `manual_retry`）
- [ ] `POST /admin/openviking/sync_jobs/retry_failed`（批量 failed）
- [ ] `POST /admin/openviking/resync`（body `{source_type?, feature_slug?}`，发 `manual_resync`）
- [ ] `POST /admin/openviking/rebuild_index`（清向量库后全量重建）
- [ ] 每个写操作 `triggered_by` = admin subject_id，发对应事件

### A5 — 进程 / 配置编排（支撑 A2/A3 重启）

- [ ] `regenerate_ov_conf()`（核对 `config.py` 现有生成函数能否复用，避免重写）
- [ ] `restart_openviking()` = `shutdown()` + `ensure_server()` 编排（当前仅有两个原子方法）
- [ ] codeask scope 改动走 scheduler reload（秒级，不重启 server）

---

## 3. 前端 checklist

### B1 — `lib/api-openviking.ts` 补 mutation（当前仅 5 GET）+ `types/api.ts` 类型

- [ ] tuning：`applyTuning` / `rollbackTuning` / `applyTuningPreset` / `getTuningPreset` / `getTuningHistory` / `getOllamaSnippet`
- [ ] embedding：`switchEmbeddingModel` / `listEmbeddingCandidates` / `rebuildEmbedding` / `getEmbeddingHistory`
- [ ] sync：`retrySyncJob` / `retryFailedSyncJobs` / `resyncOpenViking` / `rebuildOpenVikingIndex`

### B2 — 按 §13.4 拆五卡 + 交互控件（当前是单文件只读段）

- [ ] **OpenVikingHealthCard**：进程/健康/Ollama 状态 + **Embedding 切换入口**（候选模型下拉 + 确认弹窗，提示切模型会触发清库重建）
- [ ] **OpenVikingSyncJobsCard**：每条 job **进度条 + ETA**（当前仅状态徽章）+ **单条重试按钮**；卡级 **resync / rebuild_index** 操作
- [ ] **OpenVikingEventStream**：**分页 + 按 outcome / event_type 过滤**（当前平铺无分页）；按 outcome 着色
- [ ] **OpenVikingTuningCard**：三 scope 参数**可编辑**（输入/下拉）+ 推荐值并排 + **应用 / 回滚** + **套用预设** + 主机识别展示 + **Ollama systemd snippet 复制按钮**（当前全只读 `Metric`）
- [ ] **OpenVikingMetricsCard**（可后置）：throughput / latency / circuit breaker trips
- [ ] 破坏性操作（切模型 / rebuild）二次确认；写操作成功后乐观刷新 + 失败 toast

### B3 — 布局对齐

- [ ] 用卡片网格替换扁平 `settings-stack` 堆叠（"组件未对齐"问题）；响应式；loading / empty / error 三态统一

---

## 4. e2e 用例（每个前端 UI 一一对应）

> 统一约定（沿用 `frontend/e2e/openviking-dashboard-live.spec.ts`）：新建 `frontend/e2e/openviking-dashboard-management-live.spec.ts`；`const ENABLED = process.env.CODEASK_RUN_LIVE_OPENVIKING_E2E === "1"`；`test.skip(!ENABLED, ...)`；`test.describe.configure({ timeout: 180_000 })`；每个用例先 admin 登录（`/#/login` → 填 用户名/密码 → 点 登录）再 `goto /#/settings?page=openviking`。破坏性用例（切模型/rebuild）跑完需把状态复原或在隔离的 e2e 数据目录运行。

| # | 前端 UI | e2e 用例（标题 + 关键断言） |
|---|---|---|
| E1 | 五卡布局 | `renders five aligned OpenViking cards`：Health / Embedding / SyncJobs / EventStream / Tuning 五张卡 heading 均可见；断言卡片容器使用网格类（非纯堆叠）；reload 后仍在 `?page=openviking` |
| E2 | HealthCard · Embedding 切换 | `admin can switch embedding model with confirm + rebuild`：打开候选下拉（来自 `/embedding/candidates`）→ 选另一模型 → **出现二次确认弹窗**（提示清库重建）→ 确认 → `rebuild_status` 变 `rebuilding`；事件流出现 `embedding_model_switched`；取消路径不触发切换 |
| E3 | SyncJobsCard · 进度/重试 | `sync job shows progress + ETA and can be retried`：列表项含进度条与 ETA 文案；对一条 failed job 点"重试" → 该 job 状态从 `failed` 回到 `pending`/`running`；事件流出现 `manual_retry` |
| E4 | SyncJobsCard · resync/rebuild | `admin can trigger resync and rebuild index`：点卡级 resync → 出现 `manual_resync` 事件；rebuild_index 二次确认后触发，`rebuild_status=rebuilding` |
| E5 | EventStream · 分页/过滤 | `event stream filters by outcome and paginates`：按 `outcome=error` 过滤后列表只剩 error 项；翻页加载更多；不同 outcome 着色 class 存在 |
| E6 | TuningCard · 应用 | `admin can edit and apply a codeask-scope param`：改 `codeask.sync_workers` → 应用 → 出现一条 `tuning_change`（含 value_before/after）；codeask scope **秒级生效不重启**；非法极端值被拒并提示 |
| E7 | TuningCard · openviking 应用+重启 | `applying openviking-scope param restarts server`：改 `openviking.embedding.max_concurrent` → 应用 → 提示 ~30s 中断 → 重启后 Health 卡恢复 running，metrics 刷新到新值 |
| E8 | TuningCard · 回滚 | `admin can rollback a tuning change`：对刚改的 key 回滚 → 值恢复上一版；事件流出现 `tuning_change` `notes="rollback"` |
| E9 | TuningCard · 套用预设 | `apply recommended preset updates multiple params`：点"套用预设" → 多个 openviking+codeask 参数一次性变为预设值；不动 ollama_recommend |
| E10 | TuningCard · Ollama snippet | `ollama systemd snippet is shown and copyable`：snippet 文本含 `NUM_PARALLEL` / `NUM_THREAD`；复制按钮可点 |
| E11 | 路径脱敏（回归） | `management views never leak host paths`：在所有卡操作后 `body.innerText` 不含 `/home/hzh`、`/home/codeask`、`/tmp/`（沿用现有断言） |
| E12 | 未授权拒绝 | `non-admin cannot access management actions`：非 admin 用户访问看板/调用写操作被拒（403 / 不渲染控件） |

> E2/E4/E7 是破坏性（清库重建 / 重启），建议在专用 e2e 数据目录或 `test.describe.serial` 内按"改→验证→复原"组织，避免污染后续用例。

---

## 5. 后端单测 / 集成

- [ ] A2/A3/A4 每个端点单测：成功、校验拒绝、`triggered_by`、对应事件写入、`audit_log`（embedding 切换）
- [ ] tuning apply：openviking scope 触发 `restart_openviking`、codeask scope 走 reload（用 fake/mock 断言调用）
- [ ] embedding 切换状态机：sync_jobs 置 pending + `rebuild_status` 流转
- [ ] A1 tuning 模块单测见 A1
- [ ] events 分页/过滤后端契约（前端 E5 依赖）

---

## 6. 验收（含真实前端核对——这次的教训）

- [ ] acceptance §3.2 / §3.3 / §3.4 全部勾项可验证为真（这些框至今全空）
- [ ] **真实浏览器**核对：五卡可见且对齐、参数可改并生效、切模型有确认 + rebuild 进度、回滚/预设/snippet 可用
- [ ] §4 的 E1–E12 e2e 全绿（`CODEASK_RUN_LIVE_OPENVIKING_E2E=1`）
- [ ] pyright `src/codeask evals` = 0；pytest 绿；ruff 绿；前端 tsc + vitest 绿
- [ ] 操作视图不泄露宿主机绝对路径

---

## 7. 排序与风险

1. **A5（restart + ov.conf 编排）先做** —— A2/A3 的前置。
2. A1 tuning 支撑模块 → A2 tuning 写端点 → B1 api → OpenVikingTuningCard（E6–E10）。
3. A3 embedding 管理 → HealthCard 切换（E2）：**破坏性（清库重建）**，前端必须二次确认。
4. A4 手动同步 → SyncJobsCard（E3/E4）。
5. EventStream 分页/过滤（E5）、布局对齐（E1）、Metrics（可后置）。

整体是 M1 真空，工作量不小，按上面分批，每批"后端端点 + 前端控件 + 对应 e2e"成组交付、组内绿了再走。
