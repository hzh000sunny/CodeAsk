# v1.0.5 收口验收清单

> 版本：v1.0.5
> 状态：Completed
> 关联：[PRD](../prd/rag-knowledge.md) · [设计](../design/openviking-integration.md) · [Phase 0](./phase-0-spike.md) · [Phase 1](./phase-1-sync-adapter.md) · [Phase 2](./phase-2-opencode-integration.md) · [DEVELOPMENT_ACCEPTANCE](../../DEVELOPMENT_ACCEPTANCE.md)

---

## 0. 验收原则（重申）

- 不能只看后端单测通过，也不能只看前端能渲染；必须覆盖模型实际看到的上下文、工具调用、证据回填、降级语义和真实用户路径
- 涉及 LLM / Agent / RAG / 工具调用必须有 live E2E 通道（默认跳过，显式环境变量开启）
- 升级路径必须在真实数据备份上跑过一次
- OpenViking 与 Ollama 的依赖关系必须有明确失败语义，不允许"前端看上去能用，但后端实际不可用"

---

## 1. OpenViking 集成边界

- [x] `docs/v1.0.5/specs/openviking-agpl-review.md` 状态 = Recorded（已完成）
- [ ] CodeAsk README / INSTALL 包含 OpenViking 引用与许可证披露
- [ ] CodeAsk 仓库未拷贝 OpenViking 源码（grep 验证）
- [x] OpenViking 作为 CodeAsk 声明依赖随 `uv sync` 安装；运行期通过 `openviking_bin` 直接拉起独立 `openviking-server` 子进程，不再使用 `uvx` 在线解析依赖；业务代码不 `import openviking`
- [ ] 没有任何文件 `import openviking` 作为业务代码（grep 验证）

---

## 2. Phase 0 spike

- [x] `phase-0-spike.md` §10 实验记录已填
- [x] OpenViking 版本（0.3.17）与 embedding 模型（bge-m3）已锁定并写入 PRD / SDD
- [ ] 召回基线（relevance@5）：测试方法已固化 in §7；实际跑分推到 Phase 2 live E2E（依赖完整 fixture 索引）
- [ ] §8 退出条件全部满足（含 Phase 2 推迟项确认）

---

## 3. Phase 1 同步适配器

v1.0.5 按交付里程碑 M1–M5 分段验收（M1–M5 跨 Phase 1/Phase 2 两个工作域，阶梯见 [phase-1 §1](./phase-1-sync-adapter.md)）。本节（§3）覆盖落在 Phase 1 工作域的里程碑：**M1** = §3.1–§3.5 + §3.2.1/§3.2.2（边界与本地自测）；**M3 native 隔离** = §3.9；**M4 FTS5 删除 + UI 搜索兜底** = §3.6 + §3.8；**M5 写路径 hook** = §3.7。**M2（opencode 接入）的验收在 §4（Phase 2）。** 交付顺序 M1→M2→M3→M4→M5，M4 必须在 M3 之后。

### 3.1 模块与表

- [x] `src/codeask/rag/openviking/` 模块全部就位（含 `dashboard.py` / `tuning.py`）
- [x] `src/codeask/api/` 三个 router 就位：`openviking_status.py` / `openviking_admin.py` / `openviking_tuning.py`
- [x] alembic head 包含 4 张表：`openviking_sync_jobs` / `openviking_embedding_settings` / `openviking_tuning_settings` / `openviking_dashboard_events`
- [x] OpenViking server startup / keepalive / shutdown 行为符合 SDD §5
- [x] `openviking_embedding_settings` 表存在；首次启动时按 settings 默认值填入一行
- [x] `openviking_dashboard_events` 表存在；启动 sweep / hook / 模型切换全部写入对应 event_type

### 3.2 进程与同步
- [x] admin 设置页可见 OpenViking 仪表盘核心卡片：Health / SyncJobs / EventStream / Tuning / Metrics
- [x] admin 切换 embedding 模型 → 写入新行 + previous_setting_id + 重新生成 ov.conf + 重启 server + 触发全量重建
- [ ] 切换期间召回质量下降但 opencode 会话不中断；重建完成后召回恢复
- [x] 切换、重建、失败、回退都写审计日志
- [ ] rebuild / 批量同步类任务的 `sync_jobs.progress` 由 `progress_sweep` 任务自动更新；admin 卡片仅在有真实 `total/indexed/eta_seconds` 时显示进度条 + ETA，单资源 `add_text_resource` 不显示假进度
- [x] M8 修复：OpenViking SyncJobs API 支持全表 summary、按状态过滤、cursor keyset 分页与 `display_name`；前端按 failed / pending / running / indexed 分组展示，避免 indexed 大列表按窗口混排
- [x] M8 修复：OpenViking 事件流改为完整分页；默认每页 5 条，每页只展示当前页事件行，底部显示总条数 / 当前页 / 总页数，支持选择每页条数和输入页码跳转，不再跨页追加、不再用 `×N` 聚合 chip 隐藏事件；历史页暂停实时轮询，回到第 1 页恢复实时刷新
- [x] M8 修复：运行指标卡不再使用 stub；throughput 来自 5 分钟内 `last_indexed_at` 聚合，breaker trips 来自 dashboard events，latency p95 / samples 来自 `OpenVikingClient` 请求耗时 recorder
- [x] M8 修复：dashboard live e2e fixture 增加 `afterEach` 自清；一次性脚本 `scripts/cleanup_openviking_e2e_fixture.sql` 已清理本地真实库 `e2e_unknown` sync job 残留
- [x] M8 修复：OpenViking 看板所有按钮均接入全局反馈；成功操作显示居中低密度 toast，失败操作显示居中错误弹窗，覆盖复制、分页、展开/收起、重试、重建、调优和 Ollama 验证；所有会修改后端状态的按钮必须先弹出页面内居中确认框，禁止使用浏览器原生 `window.confirm`
- [x] M8 修复（§⑥ 事件行人话化）：事件标题用中文标签映射（未命中回退原始枚举），描述为人话模板而非 `key=value` dump，badge 中文化；warning/error 行的错误原因（`error/detail/message/reason`）必须排在描述最前且永不被截断（回归 `scheduled_refresh_summary` 把 `error` slice 掉的 bug）
- [x] M8 修复（§⑥ 事件详情）：每条事件行提供"详情 / 收起详情"入口，展开后显示事件 id、原始 event_type、来源、source_id、sync_job_id、triggered_by、created_at 与 payload JSON，避免"查看事件详情"没有入口
- [x] M8 修复（§⑥ 可操作性）：warning/error 行显示"建议：…"文案；`sync_job_failed` 行有"重试该任务"按钮（调 `retrySyncJob(sync_job_id)`），`scheduled_refresh_summary`(error) 有"立即重新同步"按钮，`manual_rebuild_index`(error) 有"重试重建"按钮；按钮复用既有 feedback / 居中确认，禁止 `window.confirm`
- [x] M8 修复（§⑥ 后端补 emit）：同步任务失败时 `sync.py` `mark_failed` 补发 `sync_job_failed` 事件，带 `error`/`attempts`/`sync_job_id`/资源可读名；`status="cancelled"`（放弃重试）→ `outcome="error"`，仍会重试 → `outcome="warning"`；使索引失败能出现在事件流
- [x] M8 修复（§⑦ 补遗-1）：`sync_job_failed` 收敛为每个失败资源最多 2 条——cancelled 发 error；否则 attempts==1 发 warning；中间重试（attempts>1 且 failed）不发；避免 flaky 资源刷满默认"重点事件"视图
- [x] M8 修复（§⑦ 补遗-2）：事件行建议按钮（重试该任务 / 立即重新同步 / 重试重建）成功 toast 只弹一次——去掉 onConfirm 乐观提示，仅保留 mutation onSuccess
- [x] M8 修复（§⑦ 补遗-3）：后端 no-op 调参守卫与前端 `valuesEqual` 对齐——比较前两侧 `.strip()`，带首尾空格的语义相同值不再落库 / 发 `tuning_change`
- [x] Wiki / 报告 / 仓库变更 hook 全部接入；启动 backfill 与定时 sweep 行为正确
- [x] kill OpenViking server 后重启：admin 仪表盘自动出现 `openviking_restart_detected` 事件，sync_jobs 进度从中断点续传，不重置
- [x] kill Ollama 后重启：仪表盘出现 `ollama_recovery` 事件，sync_jobs 在 1–2 分钟内追上
- [x] 编辑 Wiki / 新增 verified 报告 / 单仓库同步完成 → 仪表盘事件流出现对应 `wiki_doc_changed` / `report_status_changed` / `repo_synced` 事件；批量 / hourly repo refresh 只写一条 `repo_refresh_summary`，不刷 per-repo success 洪流
- [x] 24h scheduled_refresh 触发后产生 `scheduled_refresh_summary` 事件
- [x] admin 手动触发"单源重同步 / 全量重建 / 失败重试"三个动作走通；事件流出现 `manual_resync` / `manual_retry` 事件
- [x] events 接口分页可用；每 event_type 保留策略生效（默认 2000 条）
- [x] 事件流默认视图只展示重点事件；`repo_synced` success、`manual_retry_failed count=0`、`tuning_change` success / no-op 调参等噪声不进入默认看板，管理员可切换"全部事件"排查原始记录
- [x] 会话事件流返回前端前不泄露宿主机绝对路径（沿用 v1.0.4 会话 trace 出口脱敏）；admin OpenViking 诊断接口例外，需显示完整路径便于运维定位
- [ ] 失败重试与 cancelled 转换符合 SDD §9（指数退避 30s / 2m / 10m / 1h / 6h）
  - [x] 单次 `add_text_resource` 失败后任务进入 `failed`，`attempts=1`，`next_retry_at≈30s`
  - [x] `next_retry_at` 到期后 `run_pending_jobs` 会重新尝试 failed 任务
  - [x] 连续失败 5 次后任务进入 `cancelled`，`next_retry_at=None`

### 3.2.1 M1 边界回归（Superseded）

M1 阶段的瞬时护栏已被后续里程碑有意推翻：§3.6 已接入 OpenViking-first UI 搜索，§3.8 已删除 FTS5，§3.9 已迁移 native backend，§3.7 已接入写路径 hook。该小节只保留历史口径，不能再作为当前版本回归失败判断。

- [x] Superseded by §3.6：`api/wiki/search.py` 已改为 OpenViking-first + SQL ILIKE 兜底
- [x] Superseded by §3.8：`src/codeask/wiki/{search,indexer,tokenizer}.py` 已删除，FTS5 drop migration 已新增
- [x] Superseded by §3.9：native Agent 已迁入 `agent/native_backend/` 并从请求链路下线
- [x] Superseded by §3.7：Wiki publish / rollback / Report verify 已写入 `openviking_sync_jobs`

### 3.2.2 M1 本地自测记录（2026-05-25）

- [x] Ollama `/api/tags` 已确认存在 `bge-m3:latest`
- [x] `openviking-server 0.3.17` 已通过 `uv sync` 安装到 CodeAsk `.venv`，并由 `uv run openviking-server --help` 验证；运行期不再依赖 `uvx --from ...`
- [x] CodeAsk 启动后 admin status API surfacing OpenViking `/health`，返回 healthy 与实测版本 `0.3.17`
- [x] CodeAsk admin status API surfacing Ollama `/api/tags`，返回 `bge-m3:latest` 可用状态与模型列表
- [x] Admin API 手动 enqueue 一条 Markdown 文档，并通过 `run_pending` 同步到 OpenViking，任务状态更新为 `indexed`
- [x] Lifespan 注册 OpenViking keepalive 与 `openviking_sync_pending` 后台任务，pending 同步任务按 `openviking_sync_workers` 批量执行
- [x] Admin status 在 OpenViking 不可达 / 健康探测失败时仍返回 degraded，不向普通用户路径抛错
- [x] Admin status 的 `config_file` / `workspace_path` / `log_file` / `last_error` 以及 health / Ollama / sync job / rebuild 清理错误保留宿主机绝对路径；这是 admin-only 诊断页，便于直接定位配置、工作目录、日志和失败源
- [x] 真实浏览器打开 `#/settings?page=openviking`，刷新后仍保持在 OpenViking 设置页
- [x] OpenViking 仪表盘前端显示真实 `CODEASK_DATA_DIR/openviking/` 下的完整绝对诊断路径；会话页 Agent 行动轨迹仍按路径脱敏规则展示相对路径
- [x] 新增并通过 `frontend/e2e/openviking-dashboard-live.spec.ts` 真实浏览器 e2e（需 `CODEASK_RUN_LIVE_OPENVIKING_E2E=1` 显式开启）
- [x] 新增并通过 `frontend/e2e/openviking-dashboard-management-live.spec.ts` 真实浏览器管理交互 e2e：E3 / E5 / E6 / E8 / E9 / E10 / E12 覆盖，E2 / E4 / E7 以破坏性隔离用例 `test.skip` 占位
- [x] OpenViking 仪表盘前端显示 OpenViking health、Ollama / 模型 readiness、Embedding 模型与可用模型列表
- [x] OpenViking SyncJobs 卡片不再按 status 伪造进度；只读取真实 `job.progress`，缺失时只显示任务状态，不展示空进度条 / `进度 ?`
- [x] OpenViking SyncJobs 卡片不再显示不可读主键作为主标题；wiki_doc / report 使用后端解析的 `display_name`，未知来源才回落到 source_type/source_id
- [x] OpenViking EventStream 卡片优先显示 `payload.name` / `payload.title` / `feature_slug+relative_path`，避免 `repo · <hex-id>` 这类不可读摘要成为主信息
- [x] OpenViking 看板 UI 已按 1440 / 1280 / 390 三档真实浏览器截图复核：Health + Embedding 分离，SyncJobs 全宽，EventStream + Metrics 同行，Tuning 全宽；移动端设置二级导航为横向紧凑 tabs，不再占半屏空白
- [x] 本轮 live E2E 后已清理真实库测试污染：`e2e_unknown` / `mgmt-retry-*` / `m1_smoke_*` 在 `openviking_sync_jobs` 与 `openviking_dashboard_events` 中残留计数均为 0
- [x] M1 边界回归测试覆盖：未改 Wiki 搜索、未删 FTS5、未迁 native Agent、未接 Wiki 写路径 hook
- [x] 新增 OpenViking Python 模块 pyright 子集为 `0 errors`
- [x] 全项目 `pyright src/codeask evals` 已清零；历史遗留类型债已在 M4 阶段处理，不能再按 M1 旧口径误报为遗留

### 3.3 Embedding 模型管理

2026-05-26 补齐：Embedding 模型管理已从只读展示扩展为 admin 可切换 / rebuild / 查看候选与历史。破坏性 live 用例需要在隔离数据目录复核，避免清空当前生产式 OpenViking 索引。

- [x] 当前 embedding 配置可读；首次启动按 settings 默认值填入一行
- [x] 候选模型来自 Ollama `/api/tags` + 历史配置
- [x] admin 切换模型会写新 `OpenVikingEmbeddingSetting`、保留 `previous_setting_id`、写 `audit_log`、发 `embedding_model_switched`
- [x] admin 切换模型 / rebuild 会将 sync_jobs 置 pending，并 best-effort 清理 `viking://resources/codeask`
- [ ] 切模型 / rebuild 的真实 live E2E 需隔离数据目录执行并验证召回恢复

### 3.4 调优面板

2026-05-26 补齐：Tuning 面板已支持配置读取、推荐值、写入、预设、OpenViking 重启与基础前端交互。Ollama 实测并发探测与 APScheduler interval 重排仍保留为后续增强。

- [x] `openviking_tuning_settings` 表首次启动填入默认值；推荐值由主机识别预设计算
- [x] 仪表盘 OpenVikingTuningCard 显示三个 scope 的当前值、推荐值、写入按钮与套用预设入口
- [x] M8 修复：调优面板取消"偏离推荐 / 已对齐"分流展示；三个 scope 均默认折叠，summary 右侧显式展示"展开参数 / 收起参数"动作和 chevron，hover / focus 有视觉反馈；展开后统一以 `参数 | 自定义值 | 推荐值 | 操作` 四列布局展示全部参数，并保留参数描述、影响说明与推荐值；操作列仅展示"应用"，不再展示对齐推荐与回滚按钮
- [x] 调优面板按钮交互接入全局反馈：点击应用时若值未变更则提示无需应用；若值已变更则先弹出页面内居中确认框，确认后才提交并显示成功 toast；套用预设也先走页面内居中确认框；复制 snippet、验证 Ollama 设置均有成功 toast；接口失败时弹出全局错误对话框并保留卡片内联错误
- [x] admin 改 `openviking.embedding.max_concurrent` → 写 DB → 重写 ov.conf → restart OpenViking → 返回预计中断时长
- [x] admin 改 `codeask.sync_workers` → 秒级生效；不重启 OpenViking
- [x] 改任一参数后事件流出现一条 `tuning_change` 事件，含 scope / key / value_before / value_after / notes / triggered_by；若新值与当前值一致，不写 tuning setting、不写 audit、不写 `tuning_change`
- [x] 一次应用推荐预设 → 多个参数一次性改完；不影响 ollama_recommend
- [x] Ollama systemd snippet 接口返回正确的 NUM_PARALLEL / NUM_THREAD；admin 可点击"验证 Ollama 设置"，CodeAsk 轻量探测实际并发并写入 `ollama_settings_verified`（success / warning）
- [x] 极端值（如 `codeask.sync_workers=10000`）被后端拒绝；事件 outcome=error；前端卡片显示 rejected 原因；不应用

### 3.5 边界与质量

- [ ] 会话页 Agent 行动轨迹只显示 opencode 调 OpenViking MCP 的工具事件，不显示后台同步事件
- [x] admin 诊断接口与卡片可读；显示宿主机绝对路径，路径脱敏只约束会话事件流和普通用户可见链路
- [x] 后端 pytest 全量通过；不引入 ruff / pyright 新红
- [ ] 真实数据备份升级回归通过

### 3.6 Wiki UI 搜索框（OpenViking 优先 + ILIKE 兜底）

- [x] **spike 前置**：已确认 OpenViking 查询走 REST 还是 MCP，记录端点 / 入参 / 响应结构 + 一次成功样本（`find_or_search` 在 M2 前不存在，须 spike 落地）
- [x] `OpenVikingClient` 新增查询方法（复用 trusted headers / `trust_env=False`），有单测覆盖正常命中与异常
- [x] OpenViking 健康有命中 → 命中走 OpenViking；事件流可见 `openviking_search_hit`（统计）
- [x] OpenViking 健康 0 命中 → 自动回退 SQL ILIKE；前端不区分来源；事件流可见 `openviking_search_miss`
- [x] OpenViking 不可达 / 异常 → 自动回退 SQL ILIKE；不弹窗；admin 仪表盘 Health 卡显示 degraded
- [x] 分组（current_feature / other_current_features / history_features / current_feature_reports）在两条路径下行为一致
- [x] 前端 `frontend/src/lib/wiki/api.ts` 无改动，证明后端是无缝替换
- [x] OpenViking 长期不可用时连续搜索多次：仪表盘事件流不被搜索失败刷屏（去重 / 速率限制生效）

### 3.7 Wiki / Report 写路径 hook（M5，详见 [m5-write-path-hooks.md](./m5-write-path-hooks.md)）

引擎底座（M5-0，D1 + D2）：

- [x] delete spike 已记录 OpenViking 删除/移除资源端点（端点 / 入参 / 响应 / 成功样本）
- [x] `OpenVikingClient.delete_resource` 已加（复用 trusted headers / `trust_env=False`），单测覆盖正常 + 异常
- [x] `enqueue` 支持 `operation=upsert|delete`（存 `progress`，无新迁移）
- [x] `run_pending_jobs` / `_resource_from_job` 按 `source_type`+`source_id` **现查最新正文**（upsert）或调 `delete_resource`（tombstone）；保留 manual 内联兼容路径
- [x] 正文不内联进 `progress`；**快速二次发布索引到最新正文**（验证去重不再导致 staleness）

hook 接入（D3：均在 API 端点 `session.commit()` 之后，enqueue 失败只 log 不阻塞主写路径）：

- [x] `POST /api/documents` 上传 → sync_jobs 新增 pending，`source_type=wiki_doc`、`source_id=str(WikiDocument.id)`（hook 在上传端点 commit 后，非 `sync_legacy_markdown_document` 内部）
- [x] `backfill_feature_content` 全量回填也入队（其调用方 commit 后逐个，不漏 backfill 路径）
- [x] `POST /api/wiki/documents/{node_id}/publish`：sync_jobs 新增一条；`source_hash` 与新版本 markdown sha 对齐
- [x] `POST /api/wiki/documents/{node_id}/versions/{version_id}/rollback`：sync_jobs 入队
- [x] `PUT /api/wiki/documents/{node_id}/draft` + `DELETE .../draft`：**sync_jobs 不增加新行**
- [x] WikiNode 软删（tree 删除 / legacy 软删）→ tombstone job（`operation=delete`）；恢复（`deleted_at=None`）→ 重新 upsert；子树批量删除逐个 doc 入队
- [x] Report `verified=false → true` → upsert，`source_type=report`、`source_id=str(Report.id)`
- [x] Report `verified=true → false`（unverify / reject）+ delete report → tombstone
- [x] Report 在 `verified=false` 状态下编辑 → **sync_jobs 不增加新行**
- [x] Report 在 `verified=true` 状态下编辑（且 hash 不同）→ upsert（当前产品禁止 verified 状态直接编辑，已核对无需新增 hook）
- [ ] 导入会话软删（`imports/session_service.py`）后置，不在 M5 范围
- [x] scheduled_refresh 24h sweep 也遵守上述过滤：扫描时跳过 drafts 与 unverified reports
- [x] OpenViking / delete 端点不可用时主写路径仍 2xx；tombstone job 走退避重试

服务层发布路径覆盖（步骤 20c，F1 补齐——验收发现 D3 端点 hook 漏掉内部调 `publish_document` 的服务层）：

- [x] `WikiDocumentService.publish_document` / `rollback_to_version` 在 commit 前向 `session.info` 打标已发布 document id（中性，不 import rag.openviking）
- [x] `drain_wiki_document_syncs` helper 在端点 commit 后取标入队 upsert，best-effort 容错
- [x] 晋级会话附件（`POST /wiki/promotions/session-attachment`）→ 入队 `wiki_doc`
- [x] 导入 resolve / bulk-resolve / retry(item+session) / apply_job → 各自端点 commit 后入队所发布文档（额外覆盖 upload 完成即 materialize 的路径）
- [x] publish / rollback 端点统一改走 drain（不再各自显式 enqueue，避免双机制/重复）
- [x] 集成测试覆盖：晋级 + 至少一条导入发布路径产出 pending `wiki_doc` job

### 3.8 FTS5 删除

- [x] alembic head 之后：`docs_fts` / `docs_ngram_fts` / `reports_fts` 三张虚表不存在
- [x] `find src/codeask/wiki -name "search.py" -o -name "indexer.py" -o -name "tokenizer.py"` 无输出
- [x] `wiki/chunker.py` 不再 import `tokenizer`，`ParsedChunk` 不含 `tokenized_text` / `ngram_text` 字段
- [x] `tokenize` 已迁出 tokenizer.py：`grep -rn "from codeask.wiki.tokenizer\|wiki\.tokenizer" src/codeask` 无输出；`/api/wiki/resolve`（`path_resolver` 路径模糊匹配）仍正常工作
- [x] `wiki/reports.py:ReportService` 无 `WikiIndexer` 引用：verify / unverify / reject 不再写 FTS5（这三处是仅有的 indexer 调用点）
- [x] `api/reports.py` 已删 `GET /reports/search` 端点、无 `WikiIndexer` 引用；`api/documents_compat.py` 已删 `GET /documents/search`、上传与 delete 路径无 `WikiIndexer`
- [x] 旧 `WikiIndexer` / FTS `WikiSearchService` 活代码已删除；`docs_fts` / `docs_ngram_fts` / `reports_fts` 仅保留在新增 DROP migration 与验收测试断言中。注：`NativeWikiSearchService` 是 SQL ILIKE 兜底服务，名称包含 `WikiSearchService` 子串，不属于已删除的 FTS 服务。

### 3.9 自研 Agent 隔离（保留不删）

- [x] `src/codeask/agent/native_backend/` 存在，包含 orchestrator / wiki_tools / tools / tool_schemas / tool_delegates / tool_models / state / prompts / code_tools / answer_links / stages / chat_runtime（runtime 系列 + tools/）
- [x] `src/codeask/agent/native_backend/README.md` 存在，写明"冻结参考、不在请求链路、复活时 RAG 接 OpenViking 不回退 FTS5"
- [x] `chat_runtime/events.py` + `chat_runtime/context.py` 仍在 `agent/chat_runtime/` 原位（共享类型层）
- [x] 顶层 `agent/sse.py`（`SSEMultiplexer`）+ `agent/trace.py`（`AgentTraceLogger`）仍在 `agent/` 原位（共享层，opencode 路径引用，未误搬入 native_backend）
- [x] `reports.py` 解耦走自包含方案：`grep -rn "search_reports\|ReportSearchHit" src/codeask/wiki/native_search.py` 无输出（report 搜索未渗入活的共享服务）
- [x] `python -c "import codeask.agent.native_backend.orchestrator"` 成功（模块未 bitrot）
- [x] 冒烟测试 `tests/unit/test_native_backend_importable.py` 通过：import 关键模块 + 用 fake 依赖构造 `AgentOrchestrator`
- [x] `native_backend` 内无 FTS5 依赖：`grep -rn "WikiSearchService\|wiki\.(search|indexer|tokenizer)" src/codeask/agent/native_backend/` 无输出
- [x] `native_backend` **不在请求链路**：`grep -rn "native_backend" src/codeask/app.py src/codeask/api/ src/codeask/sessions/` 无输出
- [x] `settings.agent_backend` 为 `Literal["opencode"]`；运行时无法选到 native
- [x] `grep -rn "agent_backend.*native" src/codeask/` 仅出现在 native_backend 内部 / 测试 / 注释，不出现在请求路径接线

### 3.10 M4 阶段二 pyright strict 清债（详见 [m4-phase-2-pyright-cleanup.md](./m4-phase-2-pyright-cleanup.md)）

- [x] `uv run pyright src/codeask evals` = **0 errors**
- [x] `.github/workflows/backend.yml` 的 Pyright step 仍是硬 gate（未加 `continue-on-error`）
- [x] `pyproject.toml [tool.pyright]` 的 `strict` 范围未被收窄；`native_backend` 仍在 `exclude`（唯一例外）
- [x] 全量 `pytest` 绿、ruff check / format 绿、前端 tsc / vitest 不受影响
- [x] diff 抽查无"假绿"：无新增 `# type: ignore`、未全局禁用任何 `reportXxx` 规则、无静默逻辑变更（纯类型修复）
- [x] 分批推进，每批退出条件（该批 pyright 0 + pytest 绿 + ruff 绿）均满足

---

## 4. Phase 2 opencode 接入

- [x] M2.0 spike 完成：确认 OpenViking MCP endpoint 为 `http://127.0.0.1:1933/mcp`，transport 为 streamable HTTP，CodeAsk 管理的 trusted 模式使用 `X-OpenViking-*` 身份头
- [x] M2.0 spike 完成：真实 `tools/list` 返回 `find/search/read/list/remember/add_resource/grep/glob/forget/health`，并已记录一次 `health` 与 `find` 成功调用样本
- [x] M2.0 spike 完成：确认 opencode remote MCP 工具名为 `openviking_<tool>` 前缀形式，例如 `openviking_find`
- [x] M2.0 spike 完成：确认 opencode 1.14.48 可通过 `permission` 对 `openviking_remember` / `openviking_add_resource` / `openviking_forget` 做 per-tool deny；M2.2 采用 permission deny，不先做 proxy
- [x] `opencode.json` 中加入 OpenViking remote MCP，工具白名单按 PRD §6.2 限定（单测覆盖 `oauth:false`、trusted headers、3 个写工具 deny）
- [x] 动态上下文与系统提示包含 RAG 使用原则；OpenViking degraded 时不注入 OpenViking 上下文段
- [x] 前端 action-trace 展示 OpenViking 工具事件，路径脱敏正常；详情展示 `viking://` URI、score、耗时
- [x] OpenViking 失败语义按 SDD §9 / PRD §8 落地：不健康时 `opencode.json` 与动态上下文均不注入 OpenViking，用户路径 graceful degrade；admin 仪表盘 Health 卡显示 degraded
- [x] OpenViking 不可用时 opencode 仍可完成会话（基于 `workspace/wiki/` symlink + native grep/read 检索 Markdown），已由 degraded fallback live E2E 复核
- [x] 全局 LLM 池在坏 provider 先失败时可继续轮转，不会因为同 workspace 重写 `opencode.json` 导致 opencode 无响应
- [x] opencode 的 user text part 不会被误判为 assistant 正文输出；provider error 发生在真正正文前时仍允许全局池轮转
- [x] `CODEASK_RUN_LIVE_OPENVIKING_E2E=1` 跑通 `frontend/e2e/openviking-rag-live.spec.ts`：Wiki 语义召回、源码桥接、OpenViking degraded fallback、写工具未执行。该 spec 已改为"模型自主决策优先"：不再强制正向工具调用链，只保留回答正确性、写工具拒绝、degraded 时不调用 `openviking_*` 等边界断言。
- [x] `CODEASK_RUN_LIVE_AGENT_E2E=1` 跑通 `frontend/e2e/admin-agent-source-live.spec.ts`：源码问答以答案正确性为硬判据；仓库 / 文件检查工具仅在实际调用时记录采样，不强制模型必须调用。
- [x] 每轮会话只复用 `initialize_session` 的 OpenViking 可用性判断；动态上下文构建不再二次 `/health` 探针，避免 degraded health timeout 路径叠加延迟
- [x] 新增 OpenViking Python 模块 `pyright` 子集为 `0 errors`；`opencode_compat` 旧目录在严格模式下仍有历史类型债，不能在 M2 验收报告中误报为全目录 pyright 通过
- [ ] 真实库 9 条 LLM 配置全量 smoke：2026-05-25 复核为 4 条 DeepSeek 通过、5 条火山配置返回 `InvalidSubscription`，需要修复外部账号订阅 / 权限后复跑

### 4.1 M7 会话控制与多代码仓上下文

- [x] opencode 单轮绝对墙钟超时从 600s 调整为 3600s；无进展超时从 30s 调整为 600s，仍保留两层守护。
- [x] no-progress / absolute-timeout 合成错误事件分别带 `no_progress_seconds` / `absolute_wait_seconds` 诊断字段，便于定位卡死类型。
- [x] Stop 语义从"回滚清空"调整为"截断保留"：用户 turn 保留，已发生 AgentTrace 保留，已生成 assistant partial 写入 agent turn；空内容也写入 stopped 占位。
- [x] `SessionTurn.stopped_at` 已通过 migration `0032` 增加并透出 API；前端会话气泡显示"已停止"chip，空 stopped 内容显示"用户在模型回复前停止了这一轮"。
- [x] Abort endpoint 不再删除 turn / trace；取消流中的迟到 agent turn 与迟到 tool_result 会被阻止写入，避免截断后上下文被旧轮次污染。
- [x] 动态上下文的最近会话片段会标注 stopped agent turn，下一轮模型能看到截断内容或停止占位。
- [x] opencode system prompt 明确：绑定特性有多个 ready repository 时，跨仓交互 / 端到端流程 / 组件边界问题应准备并检查全部相关 ready 仓，只有用户明确指定或问题明显单组件时才收敛到单仓。
- [x] 动态上下文 `Bound Features` 段为每个已绑定特性列出 `Linked ready repos: [repo_id:name, ...]`；只列 ready 仓，不把未 ready 仓作为可读证据。

---

## 5. 多环境 E2E 矩阵

| 环境 | 命令 / 范围 | 结论 |
|---|---|---|
| 临时空库 `start.sh` | 空数据目录 → OpenViking server 拉起、首次同步、admin 卡片可见 | TBD |
| 真实数据只读 | 连接真实数据备份 → admin 看到全量同步状态；不写 Wiki / 仓库 | TBD |
| 真实数据可写沙箱 | 在沙箱中触发 Wiki / 报告 / 仓库变更，验证增量同步 | TBD |
| 真实 LLM / opencode / OpenViking / Ollama live | `CODEASK_RUN_LIVE_OPENVIKING_E2E=1` 跑 Phase 2 §5 全部用例 | Passed 2026-05-25：4/4 |
| 真实 LLM 配置 smoke | `CODEASK_LIVE_LLM_CONFIG_SMOKE=1` 跑数据库 9 条 LLM 配置 | Partial 2026-05-25：4 DeepSeek passed；5 火山 failed with `InvalidSubscription` |
| OpenViking 不可用降级 | OpenViking degraded → 会话不注入 OpenViking MCP / 上下文段，退回 workspace wiki native read/grep/glob | Passed 2026-05-25 |
| Ollama 不可用降级 | 关停 Ollama → 同步任务 failed；admin 卡片提示 embedding 不可用 | TBD |
| 升级部署 | `start.sh` 升级 v1.0.4 → v1.0.5；首次 sweep 自动补齐 | TBD |
| 长对话 | 真实 LLM 多轮、跨会话切换、刷新继续追问 | TBD |
| 特性源码调查 | 用户自然语言问源码问题；模型可自主选择 OpenViking / CodeAsk MCP / opencode 原生文件工具，硬判据为答案正确且不越界 | Passed 2026-05-28：`admin-agent-source-live` 1/1；`agent-feature-scoped-code-live` 3/3（含 AnythingLLM fixture 自动 git 初始化） |
| AnythingLLM fixture 可复现 | 删除 `references/anything-llm/.git` 后，Playwright globalSetup 自动初始化 git checkout，continuity / feature-scoped live 不再因缺 `.git` 自跳过 | Passed 2026-05-28 |

---

## 6. 连续会话验收

- [ ] 同一会话第二轮追问能看到 OpenViking 召回历史摘要
- [ ] 刷新后追问保持上一轮工具行动摘要
- [ ] 上一轮 OpenViking 工具结果摘要进入模型上下文（不是只显示在行动轨迹）
- [ ] 历史 turns 与 traces 都保存且按权限可读

---

## 7. 权限与隔离

- [ ] OpenViking MCP token 按会话校验；跨会话 token 拒绝
- [ ] OpenViking 工具事件返回前端前完成路径脱敏（沿用 v1.0.4 出口规则）
- [ ] OpenViking server 进程崩溃不影响 CodeAsk 主进程
- [ ] 未授权用户不能触发 admin OpenViking 操作

---

## 8. 文档收口

- [x] PRD / SDD / Phase 0 / Phase 1 / Acceptance / 集成边界声明全部 status = Completed 或 Recorded（Phase 2 已完成主链路接入，保留真实 LLM 配置外部订阅风险项）
- [x] `docs/README.md` 顶层指针更新为 v1.0.5
- [x] v1.0.4 README 末尾追加"由 v1.0.5 接续"指引
- [x] `future/rag-knowledge-pipeline.md` 加 superseded 提示，指向 v1.0.5
- [x] `future/openviking-rag-research-2026-05-20.md` 加 superseded 提示，指向 v1.0.5 spike 结果

---

## 9. 风险声明（收口前确认）

- [ ] OpenViking 版本未来变更的升级路径有方案（升级后能重建索引）
- [ ] Ollama 模型变更不影响已有索引（或有重建脚本）
- [ ] 大代码仓导入失败有 admin 重试与诊断
- [ ] CodeAsk 主进程不再依赖任何 v1.0.5 spike 阶段的临时配置（`/tmp/codeask-v105-spike/...`）
- [ ] OpenViking 集成边界（不修改源码、不内嵌源码）与 docker 镜像策略已对外文档化
