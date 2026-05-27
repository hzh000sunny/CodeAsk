# M1 看板管理层补齐 — OpenViking Admin Dashboard

> 版本：v1.0.5
> 状态：已实现管理闭环并补齐非破坏性交互 live E2E（2026-05-26）；破坏性 live 用例仍需在隔离数据目录单独验收
> 关联：[Phase 1 §7](./phase-1-sync-adapter.md) · [验收 §3.2/§3.3/§3.4](./acceptance-checklist.md) · [设计 SDD §13.4/§13.6](../design/openviking-integration.md)

## 0. 背景与问题

M1 的 OpenViking admin 看板**只交付了只读状态展示**，规格里整个**管理/交互层（参数调整、模型切换、手动同步操作）在前后端都没实现**。验收时被发现：看板组件未按 §13.4 五卡拆分、布局未对齐、所有参数不可调。acceptance §3.2/§3.3/§3.4 的勾选项至今全空，那才是真实状态——之前不应被当作"已签收"。

本文把缺口整理成可交付工单：后端写端点 + 支撑模块、前端五卡 + 交互控件 + 布局，并为**每个前端 UI 配对 e2e 用例**。

## 1. 现状清点（整改前，基于真实代码）

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

## 1.1 2026-05-26 实现记录

- 后端已补 `src/codeask/rag/openviking/tuning.py`，包含主机预设识别、推荐参数、Ollama systemd snippet 与可插拔验证 helper。
- 后端已补 tuning 写端点、rollback、apply preset、history、snippet；每条应用/拒绝都会写 `openviking_dashboard_events` 与 `audit_log`。
- 后端已补 embedding candidates、switch、rebuild、history；切模型/重建会重写配置、重启 OpenViking、将现有 sync jobs 置 pending，并 best-effort 清理 `viking://resources/codeask`。
- 后端已补单 job retry、retry failed、resync、rebuild index；写操作都会记录 `triggered_by`、dashboard event 与 audit log。
- 前端已从只读堆叠改为职责分离的网格：Health、Embedding、SyncJobs、EventStream、Tuning、Metrics；补齐 mutation API、过滤、分页、预设/snippet/回滚入口。
- 复审后已修正前端真实性问题：SyncJobs 进度条只读取真实 `job.progress.total/indexed/eta_seconds`；普通单资源任务无增量进度时只显示状态，不再显示 `进度 ?` / 空进度条；Metrics 未采集时显示"未采集"，不再写死 `0/-`；所有管理写操作会在卡片内显示请求异常或后端 `rejected` 原因，不再静默失败。
- 已通过真实浏览器 smoke：`CODEASK_RUN_LIVE_OPENVIKING_E2E=1 ... e2e/openviking-dashboard-live.spec.ts`，验证五卡可见、刷新保持 `?page=openviking`、admin 诊断页显示完整宿主机路径。
- 已新增真实浏览器管理交互 E2E：`frontend/e2e/openviking-dashboard-management-live.spec.ts`，覆盖 E3 / E5 / E6 / E8 / E9 / E10 / E12；E2 / E4 / E7 以 `test.skip` 明确标注为破坏性隔离用例。
- 已补真实浏览器三档视觉复核：1440 / 1280 / 390 宽度下 OpenViking 看板无主要溢出；移动端设置二级导航改为横向紧凑 tabs，避免遮挡或挤压看板内容。
- 已清理本轮 live E2E 写入真实库的 `e2e_unknown` / `mgmt-retry-*` / `m1_smoke_*` 测试数据，`openviking_sync_jobs` 与 `openviking_dashboard_events` 对应残留计数均为 0。
- 尚未在共享真实数据目录执行破坏性 live 用例（切 embedding 模型、rebuild index、openviking scope 调参重启）。这些用例需要隔离数据目录或专门复原脚本，避免清空当前 OpenViking 索引。

---

## 2. 后端 checklist

### A1 — 新建 `rag/openviking/tuning.py` 支撑模块（SDD §13.6）

- [x] `detect_preset() -> (preset_id, preset_values)`：CPU + RAM + GPU（lspci/nvidia-smi）+ embedding provider 综合判定（替换 router 内只看 CPU 的 `_detect_preset`）
- [x] 各预设 `PRESET_*`（`small_machine/small_server/medium_server/large_server/gpu_host/cloud_embedding`）的 `preset_values` + 每个 key 的 `recommended`
- [x] `ollama_snippet(num_parallel, num_thread) -> str`（systemd override 片段）
- [ ] `verify_ollama_recommend(expected_num_parallel)`：当前已提供可插拔 helper；真实并发探测与 `ollama_settings_verified` 事件仍需单独接入 UI/后台探测
- [x] 单测：不同 CPU/GPU/provider 取值正确；snippet 文本正确

### A2 — tuning 写端点（`api/openviking_tuning.py`，§7.1.4）

- [x] `POST /admin/openviking/tuning`：校验 key/范围 → append-only 写 `OpenVikingTuningSetting`（`previous_value`）→ 每条发 `tuning_change` 事件 → openviking scope 走 restart、codeask scope 走运行时 reload；返回 `{applied, rejected, estimated_downtime_seconds}`
- [x] 极端值（如 `max_concurrent=10000`）被 schema 拒绝，`outcome=error`，不应用
- [x] `POST /admin/openviking/tuning/rollback`（相同写+重启流程，`notes="rollback"`）
- [x] `POST /admin/openviking/tuning/apply_preset`（只动 openviking + codeask scope）
- [x] `GET /admin/openviking/tuning/history?scope&key&limit`
- [x] `GET /admin/openviking/tuning/preset`（detected_host + preset_values）
- [x] `GET /admin/openviking/tuning/ollama_snippet`
- [x] GET tuning 响应补 `recommended` / `previous_value`（当前缺 recommended）

### A3 — embedding 管理端点（`api/openviking_admin.py`，§7.2）

- [x] `POST /admin/openviking/embedding`（切模型）：校验 admin → 探 Ollama `/api/tags` → 写新 `OpenVikingEmbeddingSetting`（`previous_setting_id`）→ 重生成 ov.conf + 重启 → 所有 sync_jobs 置 pending + 清向量库 → `rebuild_status=rebuilding`；返回 202；发 `embedding_model_switched` + 写 `audit_log`
- [x] `GET /admin/openviking/embedding/candidates`（Ollama `/api/tags` + 历史模型）
- [x] `POST /admin/openviking/embedding/rebuild`（不切模型，全量重建）
- [x] `GET /admin/openviking/embedding/history`

### A4 — 手动同步操作（`api/openviking_status.py`，§7.1.3）

- [x] `POST /admin/openviking/sync_jobs/{id}/retry`（单 job，发 `manual_retry`）
- [x] `POST /admin/openviking/sync_jobs/retry_failed`（批量 failed）
- [x] `POST /admin/openviking/resync`（body `{source_type?, feature_slug?}`，发 `manual_resync`）
- [x] `POST /admin/openviking/rebuild_index`（清向量库后全量重建）
- [x] 每个写操作 `triggered_by` = admin subject_id，发对应事件

### A5 — 进程 / 配置编排（支撑 A2/A3 重启）

- [x] `regenerate_ov_conf()`（核对 `config.py` 现有生成函数能否复用，避免重写）
- [x] `restart_openviking()` = `shutdown()` + `ensure_server()` 编排（当前仅有两个原子方法）
- [ ] codeask scope 改动已秒级更新运行时 settings；APScheduler interval 重排尚未完整实现（当前 `sync_workers` 立即生效，interval 类参数保留后续补齐）

---

## 3. 前端 checklist

### B1 — `lib/api-openviking.ts` 补 mutation（当前仅 5 GET）+ `types/api.ts` 类型

- [x] tuning：`applyTuning` / `rollbackTuning` / `applyTuningPreset` / `getTuningPreset` / `getTuningHistory` / `getOllamaSnippet`
- [x] embedding：`switchEmbeddingModel` / `listEmbeddingCandidates` / `rebuildEmbedding` / `getEmbeddingHistory`
- [x] sync：`retrySyncJob` / `retryFailedSyncJobs` / `resyncOpenViking` / `rebuildOpenVikingIndex`

### B2 — 按 §13.4 拆五卡 + 交互控件（当前是单文件只读段）

- [x] **OpenVikingHealthCard**：进程/健康/Ollama 状态 + admin 绝对路径只读展示与复制
- [x] **OpenVikingEmbeddingCard**：从 Health 拆出，候选模型下拉 + 切换 / 重建入口（确认弹窗提示清库重建）
- [x] **OpenVikingSyncJobsCard**：默认折叠 indexed、分页、状态计数、失败重试；只有真实 `job.progress` 存在时显示进度条 + ETA，无增量进度时只显示状态
- [x] **OpenVikingEventStream**：**分页 + 按 outcome / event_type 过滤**；每条显示时间、payload 摘要、outcome 状态，同类型连续事件折叠聚合
- [x] **OpenVikingTuningCard**：按 scope 分组，窄输入框，推荐值并排，短按钮文案 **应用 / 回滚**，每个 key 显示影响说明，支持套用预设与 **Ollama systemd snippet 复制按钮**
- [x] **OpenVikingMetricsCard**：只显示 throughput / latency / breaker trips 等运行指标；队列计数归 SyncJobs 卡，未采集时明确显示"未采集"，不再使用假 0/`-`
- [x] 写操作成功后刷新；失败时在当前卡片展示局部错误 / rejected 原因；破坏性操作（切模型 / rebuild）二次确认已落地。全局 toast / 中央弹窗可后续统一，但不再阻塞本看板的错误可见性。

### B3 — 布局对齐

- [x] 用卡片网格替换扁平 `settings-stack` 堆叠（"组件未对齐"问题）；响应式；loading / empty / error 三态统一

---

## 4. e2e 用例（每个前端 UI 一一对应）

> 统一约定（沿用 `frontend/e2e/openviking-dashboard-live.spec.ts`）：新建 `frontend/e2e/openviking-dashboard-management-live.spec.ts`；`const ENABLED = process.env.CODEASK_RUN_LIVE_OPENVIKING_E2E === "1"`；`test.skip(!ENABLED, ...)`；`test.describe.configure({ timeout: 180_000 })`；每个用例先 admin 登录（`/#/login` → 填 用户名/密码 → 点 登录）再 `goto /#/settings?page=openviking`。破坏性用例（切模型/rebuild）跑完需把状态复原或在隔离的 e2e 数据目录运行。

| # | 前端 UI | e2e 用例（标题 + 关键断言） | 当前状态 |
|---|---|---|---|
| E1 | 五卡布局 | `admin OpenViking dashboard survives reload and exposes diagnostic paths`：Health / SyncJobs / EventStream / Tuning / Metrics heading 均可见；reload 后仍在 `?page=openviking` | 已覆盖：`openviking-dashboard-live.spec.ts` |
| E2 | HealthCard · Embedding 切换 | `embedding model switch is destructive and reserved for isolated data dirs`：切模型会清库重建，因此只保留占位，需隔离数据目录跑 | 已占位 skip：破坏性 |
| E3 | SyncJobsCard · 状态/重试 | `sync job shows real progress and can be retried from the UI`：列表项只在有真实 `job.progress` 时显示进度条；无 progress 的 failed job 显示状态；点"重试"后状态回到 pending，事件流出现 `manual_retry` | 已覆盖：`openviking-dashboard-management-live.spec.ts` |
| E4 | SyncJobsCard · resync/rebuild | `resync and rebuild index are destructive and reserved for isolated data dirs`：rebuild 会清向量库，因此只保留占位，需隔离数据目录跑 | 已占位 skip：破坏性 |
| E5 | EventStream · 分页/过滤 | `event stream filters by outcome and paginates`：制造多条 `manual_retry_failed` 事件，按 `outcome=info` 和 `event_type=manual_retry_failed` 过滤，加载更多后条数增长 | 已覆盖：`openviking-dashboard-management-live.spec.ts` |
| E6 | TuningCard · 应用 | `tuning rejects invalid values, applies valid values, then rolls back`：非法 `10000` 显示 rejected 原因且不落库；合法 `codeask.sync_workers` 落库生效 | 已覆盖：`openviking-dashboard-management-live.spec.ts` |
| E7 | TuningCard · openviking 应用+重启 | `openviking-scope tuning restart is reserved for isolated data dirs`：openviking scope 调参会重启后端 RAG 服务，因此只保留占位，需隔离数据目录跑 | 已占位 skip：破坏性 |
| E8 | TuningCard · 回滚 | 同 E6：合法变更后点击回滚，值恢复上一版 | 已覆盖：`openviking-dashboard-management-live.spec.ts` |
| E9 | TuningCard · 套用预设 | `preset action applies recommended values without touching Ollama recommendations`：等待真实 preset 加载后确认套用，验证 codeask / openviking 推荐值生效，`ollama_recommend` 不变，并做 best-effort 还原 | 已覆盖：`openviking-dashboard-management-live.spec.ts` |
| E10 | TuningCard · Ollama snippet | `Ollama systemd snippet is visible and copyable`：snippet 文本含 `OLLAMA_NUM_PARALLEL` / `OLLAMA_NUM_THREAD`，复制按钮写入剪贴板 | 已覆盖：`openviking-dashboard-management-live.spec.ts` |
| E11 | admin 诊断路径（回归） | `admin OpenViking dashboard survives reload and exposes diagnostic paths`：admin-only 看板展示完整 `/.codeask/openviking/` 路径，便于定位配置、工作目录和日志；会话 trace 的路径脱敏仍由会话侧用例覆盖 | 已覆盖：`openviking-dashboard-live.spec.ts` |
| E12 | 未授权拒绝 | `anonymous users cannot access management mutations`：匿名调用 `POST /api/admin/openviking/tuning` 返回 403 | 已覆盖：`openviking-dashboard-management-live.spec.ts` |

> E2/E4/E7 是破坏性（清库重建 / 重启），建议在专用 e2e 数据目录或 `test.describe.serial` 内按"改→验证→复原"组织，避免污染后续用例。

---

## 5. 后端单测 / 集成

- [x] A2/A3/A4 关键端点单测：成功、校验拒绝、`triggered_by`、对应事件写入、`audit_log`（tuning / embedding / manual rebuild）
- [x] tuning apply：openviking scope 触发 `restart_openviking`、codeask scope 走运行时 reload（用 fake/mock 断言调用）
- [x] embedding 切换状态机：sync_jobs 置 pending + `rebuild_status` 流转
- [x] A1 tuning 模块单测见 A1
- [x] events 分页/过滤后端契约已由 API 参数与前端单测覆盖；后续可补更细的后端分页边界测试

---

## 6. 验收（含真实前端核对——这次的教训）

- [ ] acceptance §3.2 / §3.3 / §3.4：已完成管理面非破坏性路径；Ollama 实测探测、APScheduler interval 重排、E2/E4/E7 破坏性 live 用例仍待隔离验收
- [x] **真实浏览器**核对：五卡可见且对齐、刷新保持 OpenViking 页、admin 诊断路径完整可读；1440 / 1280 / 390 三档宽度已截图复核
- [x] §4 的 E1/E3/E5/E6/E8/E9/E10/E11/E12 已有真实浏览器 e2e 覆盖
- [ ] §4 的 E2/E4/E7 已有 `test.skip` 占位；需隔离数据目录执行切模型 / rebuild / openviking scope 重启
- [x] pyright `src/codeask evals` = 0；pytest 绿；ruff 绿；前端 tsc + vitest + eslint 绿（2026-05-26 全量回归通过）
- [x] admin 操作视图显示完整宿主机绝对路径；路径脱敏只约束会话事件流

---

## 7. 排序与风险

1. **A5（restart + ov.conf 编排）先做** —— A2/A3 的前置。
2. A1 tuning 支撑模块 → A2 tuning 写端点 → B1 api → OpenVikingTuningCard（E6–E10）。
3. A3 embedding 管理 → HealthCard 切换（E2）：**破坏性（清库重建）**，前端必须二次确认。
4. A4 手动同步 → SyncJobsCard（E3/E4）。
5. EventStream 分页/过滤（E5）、布局对齐（E1）、Metrics（可后置）。

整体是 M1 真空，工作量不小，按上面分批，每批"后端端点 + 前端控件 + 对应 e2e"成组交付、组内绿了再走。
