# v1.0.5 收口验收清单

> 版本：v1.0.5
> 状态：Draft
> 关联：[PRD](../prd/rag-knowledge.md) · [设计](../design/openviking-integration.md) · [Phase 0](./phase-0-spike.md) · [Phase 1](./phase-1-sync-adapter.md) · [Phase 2](./phase-2-opencode-integration.md) · [DEVELOPMENT_ACCEPTANCE](../../DEVELOPMENT_ACCEPTANCE.md)

---

## 0. 验收原则（重申）

- 不能只看后端单测通过，也不能只看前端能渲染；必须覆盖模型实际看到的上下文、工具调用、证据回填、降级语义和真实用户路径
- 涉及 LLM / Agent / RAG / 工具调用必须有 live E2E 通道（默认跳过，显式环境变量开启）
- 升级路径必须在真实数据备份上跑过一次
- OpenViking 与 Ollama 的依赖关系必须有明确失败语义，不允许"前端看上去能用，但后端实际不可用"

---

## 1. OpenViking 集成边界

- [ ] `specs/openviking-agpl-review.md` 状态 = Recorded（已完成）
- [ ] CodeAsk README / INSTALL 包含 OpenViking 引用与许可证披露
- [ ] CodeAsk 仓库未拷贝 OpenViking 源码（grep 验证）
- [ ] `pyproject.toml` 把 OpenViking 放在 optional-dependencies
- [ ] 没有任何文件 `import openviking` 作为业务代码（grep 验证）

---

## 2. Phase 0 spike

- [x] `phase-0-spike.md` §10 实验记录已填
- [x] OpenViking 版本（0.3.17）与 embedding 模型（bge-m3）已锁定并写入 PRD / SDD
- [ ] 召回基线（relevance@5）：测试方法已固化 in §7；实际跑分推到 Phase 2 live E2E（依赖完整 fixture 索引）
- [ ] §8 退出条件全部满足（含 Phase 2 推迟项确认）

---

## 3. Phase 1 同步适配器

### 3.1 模块与表

- [ ] `src/codeask/rag/openviking/` 模块全部就位（含 `dashboard.py` / `tuning.py`）
- [ ] `src/codeask/api/` 三个 router 就位：`openviking_status.py` / `openviking_admin.py` / `openviking_tuning.py`
- [ ] alembic head 包含 4 张表：`openviking_sync_jobs` / `openviking_embedding_settings` / `openviking_tuning_settings` / `openviking_dashboard_events`
- [ ] OpenViking server startup / keepalive / shutdown 行为符合 SDD §5
- [ ] `openviking_embedding_settings` 表存在；首次启动时按 settings 默认值填入一行
- [ ] `openviking_dashboard_events` 表存在；启动 sweep / hook / 模型切换全部写入对应 event_type

### 3.2 进程与同步
- [ ] admin 设置页可见 OpenViking 仪表盘三个核心卡片：Health / SyncJobs / EventStream
- [ ] admin 切换 embedding 模型 → 写入新行 + previous_setting_id + 重新生成 ov.conf + 重启 server + 触发全量重建
- [ ] 切换期间召回质量下降但 opencode 会话不中断；重建完成后召回恢复
- [ ] 切换、重建、失败、回退都写审计日志
- [ ] sync_jobs.progress 由 `progress_sweep` 任务每 5 s 自动更新；admin 卡片显示进度条 + ETA（EMA 算法，详见 SDD §6.1）
- [ ] Wiki / 报告 / 仓库变更 hook 全部接入；启动 sweep 行为正确
- [ ] kill OpenViking server 后重启：admin 仪表盘自动出现 `openviking_restart_detected` 事件，sync_jobs 进度从中断点续传，不重置
- [ ] kill Ollama 后重启：仪表盘出现 `ollama_recovery` 事件，sync_jobs 在 1–2 分钟内追上
- [ ] 编辑 Wiki / 新增 verified 报告 / 仓库同步完成 → 仪表盘事件流出现对应 `wiki_doc_changed` / `report_status_changed` / `repo_synced` 事件
- [ ] 24h scheduled_refresh 触发后产生 `scheduled_refresh_summary` 事件
- [ ] admin 手动触发"单源重同步 / 全量重建 / 失败重试"三个动作走通；事件流出现 `manual_resync` / `manual_retry` 事件
- [ ] events 接口分页可用；每 event_type 保留策略生效（默认 2000 条）
- [ ] events 接口返回不泄露宿主机绝对路径（沿用 v1.0.4 出口脱敏）
- [ ] 失败重试与 cancelled 转换符合 SDD §9（指数退避 30s / 2m / 10m / 1h / 6h）

### 3.3 Embedding 模型管理

（合并入上方"admin 切换 embedding 模型..."项，无独立 checkbox）

### 3.4 调优面板

- [ ] `openviking_tuning_settings` 表首次启动按主机识别结果填入推荐预设默认值
- [ ] 仪表盘 OpenVikingTuningCard 显示三个 scope 的当前值、推荐值、回滚按钮
- [ ] admin 改 `openviking.embedding.max_concurrent` → 写 DB → 重写 ov.conf → restart OpenViking → ~30 s 服务中断 → 仪表盘 metrics 卡片自然刷新到改后数据
- [ ] admin 改 `codeask.sync_workers` → 秒级生效；不重启 OpenViking
- [ ] 改任一参数后事件流出现一条 `tuning_change` 事件，含 scope / key / value_before / value_after / notes / triggered_by
- [ ] 回滚动作正确恢复上一版值；事件流出现 `tuning_change` outcome=info notes="rollback"
- [ ] 一次应用推荐预设 → 多个参数一次性改完；不影响 ollama_recommend
- [ ] Ollama systemd snippet 接口返回正确的 NUM_PARALLEL / NUM_THREAD；admin 自己改 systemd 并 restart 后，CodeAsk 探测出 NUM_PARALLEL 实际生效，事件流 `ollama_settings_verified` outcome=success
- [ ] 极端值（如 max_concurrent=10000）被后端 schema 拒绝；事件 outcome=error；不应用

### 3.5 边界与质量

- [ ] 会话页 Agent 行动轨迹只显示 opencode 调 OpenViking MCP 的工具事件，不显示后台同步事件
- [ ] admin 诊断接口与卡片可读；不显示宿主机绝对路径
- [ ] 后端 pytest 全量通过；不引入 ruff / pyright 新红
- [ ] 真实数据备份升级回归通过

### 3.6 Wiki UI 搜索框（OpenViking 优先 + ILIKE 兜底）

- [ ] OpenViking 健康有命中 → 命中走 OpenViking；事件流可见 `openviking_search_hit`（统计）
- [ ] OpenViking 健康 0 命中 → 自动回退 SQL ILIKE；前端不区分来源；事件流可见 `openviking_search_miss`
- [ ] OpenViking 不可达 / 异常 → 自动回退 SQL ILIKE；不弹窗；admin 仪表盘 Health 卡显示 degraded
- [ ] 分组（current_feature / other_current_features / history_features / current_feature_reports）在两条路径下行为一致
- [ ] 前端 `frontend/src/lib/wiki/api.ts` 无改动，证明后端是无缝替换
- [ ] OpenViking 长期不可用时连续搜索多次：仪表盘事件流不被搜索失败刷屏（去重 / 速率限制生效）

### 3.7 Wiki 写路径 hook（同步过滤规则）

- [ ] `POST /api/documents` 上传 Markdown / PDF / 文本：sync_jobs 表新增一条 pending，`source_type=wiki_doc`
- [ ] `POST /api/wiki/documents/{node_id}/publish`：sync_jobs 表新增一条；`source_hash` 与新版本 markdown sha 对齐
- [ ] `POST /api/wiki/documents/{node_id}/rollback`：sync_jobs 入队
- [ ] `PUT /api/wiki/documents/{node_id}/draft` + `DELETE .../draft`：**sync_jobs 表不增加新行**
- [ ] WikiNode 软删 → sync_jobs 入队 `tombstone=true`；OpenViking 资源被 `forget`
- [ ] Report `verified=false → true` → sync_jobs 入队 `source_type=report`
- [ ] Report `verified=true → false` → sync_jobs 入队 `source_type=report, tombstone=true`
- [ ] Report 在 `verified=false` 状态下编辑 → **sync_jobs 不增加新行**
- [ ] Report 在 `verified=true` 状态下编辑（且 hash 不同）→ sync_jobs 入队
- [ ] scheduled_refresh 24h sweep 也遵守上述过滤：扫描时跳过 drafts 与 unverified reports

### 3.8 FTS5 删除

- [ ] alembic head 之后：`docs_fts` / `docs_ngram_fts` / `reports_fts` 三张虚表不存在
- [ ] `find src/codeask/wiki -name "search.py" -o -name "indexer.py" -o -name "tokenizer.py"` 无输出
- [ ] `wiki/chunker.py` 不再 import `tokenizer`，`ParsedChunk` 不含 `tokenized_text` / `ngram_text` 字段
- [ ] `grep -rn "docs_fts\|docs_ngram_fts\|reports_fts\|WikiIndexer\|WikiSearchService" src/codeask/ alembic/versions/` 仅出现在新增的 DROP migration 文件中

### 3.9 自研 Agent 隔离（保留不删）

- [ ] `src/codeask/agent/native_backend/` 存在，包含 orchestrator / wiki_tools / tools / tool_schemas / tool_delegates / code_tools / answer_links / stages / chat_runtime（runtime 系列 + tools/）
- [ ] `src/codeask/agent/native_backend/README.md` 存在，写明"冻结参考、不在请求链路、复活时 RAG 接 OpenViking 不回退 FTS5"
- [ ] `chat_runtime/events.py` + `chat_runtime/context.py` 仍在 `agent/chat_runtime/` 原位（共享类型层）
- [ ] `python -c "import codeask.agent.native_backend.orchestrator"` 成功（模块未 bitrot）
- [ ] 冒烟测试 `tests/unit/test_native_backend_importable.py` 通过：import 关键模块 + 用 fake 依赖构造 `AgentOrchestrator`
- [ ] `native_backend` 内无 FTS5 依赖：`grep -rn "WikiSearchService\|wiki.search\|wiki.indexer\|wiki.tokenizer" src/codeask/agent/native_backend/` 无输出
- [ ] `native_backend` **不在请求链路**：`grep -rn "native_backend" src/codeask/app.py src/codeask/api/ src/codeask/sessions/` 无输出
- [ ] `settings.agent_backend` 为 `Literal["opencode"]`；运行时无法选到 native
- [ ] `grep -rn "agent_backend.*native" src/codeask/` 仅出现在 native_backend 内部 / 测试 / 注释，不出现在请求路径接线

---

## 4. Phase 2 opencode 接入

- [ ] `opencode.json` 中加入 OpenViking remote MCP，工具白名单按 PRD §6.2 限定
- [ ] 动态上下文与 `AGENTS.md` 包含 RAG 使用原则
- [ ] 前端 action-trace 展示 OpenViking 工具事件，路径脱敏正常
- [ ] OpenViking 失败语义按 SDD §9 / PRD §8 落地：用户路径 graceful degrade（opencode 走 native `read/grep/glob`），admin 仪表盘 Health 卡显示 degraded；不向普通用户弹窗
- [ ] OpenViking 不可用时 opencode 仍可完成会话（基于 `workspace/wiki/` symlink + native grep 检索 Markdown）

---

## 5. 多环境 E2E 矩阵

| 环境 | 命令 / 范围 | 结论 |
|---|---|---|
| 临时空库 `start.sh` | 空数据目录 → OpenViking server 拉起、首次同步、admin 卡片可见 | TBD |
| 真实数据只读 | 连接真实数据备份 → admin 看到全量同步状态；不写 Wiki / 仓库 | TBD |
| 真实数据可写沙箱 | 在沙箱中触发 Wiki / 报告 / 仓库变更，验证增量同步 | TBD |
| 真实 LLM / opencode / OpenViking / Ollama live | `CODEASK_RUN_LIVE_OPENVIKING_E2E=1` 跑 Phase 2 §5 全部用例 | TBD |
| OpenViking 不可用降级 | 关停 OpenViking → 新会话立即弹错；恢复后会话可继续 | TBD |
| Ollama 不可用降级 | 关停 Ollama → 同步任务 failed；admin 卡片提示 embedding 不可用 | TBD |
| 升级部署 | `start.sh` 升级 v1.0.4 → v1.0.5；首次 sweep 自动补齐 | TBD |
| 长对话 | 真实 LLM 多轮、跨会话切换、刷新继续追问 | TBD |
| 特性源码调查 | OpenViking 召回代码候选 → `codeask_prepare_worktree` → opencode 读取真实文件 | TBD |

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

- [ ] PRD / SDD / Phase 0/1/2 / Acceptance / 集成边界声明 全部 status = Completed 或 Recorded
- [ ] `docs/README.md` 顶层指针更新为 v1.0.5
- [ ] v1.0.4 README 末尾追加"由 v1.0.5 接续"指引
- [ ] `future/rag-knowledge-pipeline.md` 加 superseded 提示，指向 v1.0.5
- [ ] `future/openviking-rag-research-2026-05-20.md` 加 superseded 提示，指向 v1.0.5 spike 结果

---

## 9. 风险声明（收口前确认）

- [ ] OpenViking 版本未来变更的升级路径有方案（升级后能重建索引）
- [ ] Ollama 模型变更不影响已有索引（或有重建脚本）
- [ ] 大代码仓导入失败有 admin 重试与诊断
- [ ] CodeAsk 主进程不再依赖任何 v1.0.5 spike 阶段的临时配置（`/tmp/codeask-v105-spike/...`）
- [ ] OpenViking 集成边界（不修改源码、不内嵌源码）与 docker 镜像策略已对外文档化
