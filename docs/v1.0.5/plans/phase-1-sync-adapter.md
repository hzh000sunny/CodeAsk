# Phase 1 — OpenViking Sync Adapter 实现

> 版本：v1.0.5
> 状态：Framework Draft（待 Phase 0 通过后细化）
> 关联：[PRD](../prd/rag-knowledge.md) · [设计](../design/openviking-integration.md) · [Phase 0](./phase-0-spike.md) · [Phase 2](./phase-2-opencode-integration.md)

---

## 0. 前置条件

进入 Phase 1 之前必须：

- Phase 0 实验记录通过退出条件（见 [`phase-0-spike.md`](./phase-0-spike.md) §8）
- 锁定 OpenViking 版本和 embedding 模型已写入 PRD / SDD
- OpenViking 集成边界声明已记录（不修改源码、不内嵌源码）

未达成上述条件不开 Phase 1 实现工单。

---

## 1. 范围

Phase 1 = 把 OpenViking 接入 CodeAsk 后端，把 Wiki UI 搜索框改成"OpenViking 优先 + ILIKE 兜底"，把 Wiki 写路径 hook 进 OpenViking 增量同步；**不接入 opencode 主链路**。同时一次性清理 FTS5 与 `agent_backend=native` legacy 代码。

包含：

- 新增 `src/codeask/rag/openviking/` 兼容模块（参考 SDD §1.1）
- 新增 4 张表 + 一条 alembic migration（详见 §3）
- 新增一条 alembic migration drop FTS5 三张虚表（详见 §3）
- 启动 OpenViking server 进程管理 + keepalive
- Wiki 写路径 hook（PRD §3.3 触发器表 / SDD §6.2）：上传 / publish / rollback / Report verify / 软删 → enqueue
- **草稿与 unverified Report 不入队**（SDD §6.3 过滤规则）
- 同步引擎执行 add-resource / 索引追踪 / 失败重试
- `/api/wiki/search` 改写为 **OpenViking 优先 + `NativeWikiSearchService` (SQL ILIKE) 兜底**（详见 §9）
- 删除 FTS5 链路代码（详见 §9 第 11-14 步）
- 删除 `agent_backend=native` legacy 路径（详见 §9 第 15-17 步）
- admin 诊断接口 `GET /api/admin/openviking/status`
- admin 设置页 OpenViking 仪表盘（详见 §7）
- 后端单元 / 集成测试

不包含：

- 不在 opencode 会话注入 OpenViking 资源提示（Phase 2）
- 不在 `opencode.json` 加 OpenViking MCP（Phase 2）
- 不暴露 OpenViking 工具事件到前端行动轨迹（Phase 2）
- 不接入 Claude Code backend

Phase 1 完成后：

- Wiki UI 搜索框：OpenViking 可用即语义优先，不可用即 ILIKE 兜底，前端零改动
- opencode 会话：行为与 v1.0.4 相同（用 `workspace/wiki` symlink + native grep）；Phase 2 才注入 OpenViking
- FTS5 索引、native chat_runtime 路径已从代码库完全清除

---

## 2. 模块清单

按 SDD §1.1 实施：

```text
src/codeask/rag/openviking/
├── __init__.py
├── config.py
├── process.py
├── client.py
├── sync.py            # 含 progress sweep + EMA throughput + ETA
├── uri.py
├── models.py          # 4 张表的 SQLAlchemy 模型
├── dashboard.py       # emit_event；事件流写入
├── health.py
├── tuning.py          # 主机识别 / 推荐预设 / Ollama snippet / 实测探测
└── README.md
```

`src/codeask/api/` 新增 3 个 router 模块：`openviking_status.py` / `openviking_admin.py` / `openviking_tuning.py`（详见 §7）。

每个文件的职责、关键接口、最低测试在 Phase 1 实现阶段按 SDD §1.1 / §3 / §5 / §6 / §13 章节展开；本计划 §7-§9 列出 API 表面、事件流入口与实施顺序。

---

## 3. 数据库

v1.0.5 新增 2 条 alembic migration，按顺序执行：

### 3.1 新增 4 张表

| 表 | schema 见 | 用途 |
|---|---|---|
| `openviking_sync_jobs` | SDD §3.1 | 同步任务状态机 + progress 字段 |
| `openviking_embedding_settings` | SDD §3.3 | 当前激活 embedding 配置 + 切换历史 |
| `openviking_tuning_settings` | SDD §3.4 | append-only 调优记录 |
| `openviking_dashboard_events` | SDD §13.1 | append-only 事件流 |

文件：`alembic/versions/XXXX_openviking_v1_0_5_tables.py`

### 3.2 DROP FTS5 虚表

```python
def upgrade():
    op.execute("DROP TABLE IF EXISTS docs_fts")
    op.execute("DROP TABLE IF EXISTS docs_ngram_fts")
    op.execute("DROP TABLE IF EXISTS reports_fts")

def downgrade():
    raise NotImplementedError("v1.0.5 不支持 downgrade 到 FTS5")
```

文件：`alembic/versions/YYYY_drop_fts5_tables.py`（在 3.1 之后）

`document_chunks` 物理表暂留（含 legacy 上传文档历史，不再读写）；`documents` 表保留（仍由 `LegacyWikiSyncService` 用作上传桥接）。

### 3.3 升级路径验证

- 临时数据库跑一次（空库）
- v1.0.4 数据备份跑一次（含真实 wiki / report 数据，验证 FTS5 drop 不破坏其它表）
- 验证写入 acceptance-checklist

---

## 4. 启动与生命周期

`src/codeask/app.py` 生命周期内增加：

- `app.state.openviking_process` —— OpenViking server 管理
- APScheduler 任务：
  - `openviking_keepalive`：每 `openviking_keepalive_interval_seconds` 拉起
  - `openviking_sync`：每 `openviking_sync_interval_seconds` 取 pending job 执行
- 关停时优雅终止 OpenViking 进程

参考 v1.0.4 `_ensure_opencode_server`。Ollama 进程不归 CodeAsk 管。

---

## 5. 同步触发点（hook 清单）

| 事件 | hook 位置 | 写入 source_type |
|---|---|---|
| Wiki 节点保存（create / update / publish） | `src/codeask/wiki/...` 写操作 commit 后 | `wiki_doc` |
| Wiki 目录变化（move / rename / soft-delete） | 同上 | `wiki_dir` |
| Feature 创建 / 重命名 / 归档 | `src/codeask/api/features.py` | `feature_readme` + `global_index` |
| 报告 verify / unverify / delete | `src/codeask/wiki/reports.py` 或 `sessions/report_generation.py` 完成处 | `report` + `global_index` |
| 仓库 `ready` / 同步完成 / 删除 | `src/codeask/code_index/cloner.py` | `repo` + `global_index` |
| OpenViking 启动后首次 sweep | `app.py` startup | 扫描全量主数据，未在 jobs 中的写入 pending |

所有 hook 必须在 DB 事务 commit 后再 enqueue，避免脏写。

---

## 6. 错误处理

按 SDD §9 实现：

- failed → 指数退避：30s / 2m / 10m / 1h / 6h
- 超过 `openviking_sync_max_repeat_failures` 标 `cancelled`，写审计事件
- OpenViking server 健康检查失败时整体暂停同步，admin 面板可见

---

## 7. admin 诊断与运行时配置

### 7.1 状态接口

新增 `src/codeask/api/openviking_status.py`：

```python
GET /api/admin/openviking/status
→ {
  "running": bool,
  "pid": int|null,
  "port": int|null,
  "version": str|null,
  "verified_version": str,
  "uptime_seconds": int,
  "workspace": {
    "path": str,
    "total_vectors": int,
    "total_documents": int,
    "disk_usage_bytes": int
  },
  "embedding": {
    "provider": str,
    "base_url": str,
    "model": str,
    "dimension": int|null,
    "max_concurrent": int,
    "activated_at": str,
    "activated_by": str|null,
    "rebuild_status": "idle" | "rebuilding" | "completed" | "failed",
    "rebuild_progress": {                       // 见 SDD §3.1 progress schema
      "total_chunks": int,
      "indexed_chunks": int,
      "failed_chunks": int,
      "throughput_chunks_per_sec": float,
      "eta_seconds": int|null,
      "last_updated_at": str
    } | null,
    "ollama_healthy": bool,
    "ollama_models_available": list[str],       // 当前 ollama /api/tags 返回的可用模型
    "ollama_num_parallel": int|null,            // 探测得到的并发能力（推断；不一定能拿到）
    "ollama_recommended_num_parallel": int      // CodeAsk 推荐值
  },
  "queue": {
    "pending": int,
    "running": int,
    "failed": int,
    "cancelled": int
  },
  "metrics_5min": {
    "throughput_chunks_per_sec": float,         // EMA 全局
    "avg_embed_latency_ms": float,
    "circuit_breaker_trips": int,
    "completed_jobs": int,
    "failed_jobs": int
  },
  "last_health_at": str,
  "last_error": str|null,
  "log_file": str
}
```

### 7.1.1 sync_jobs 列表接口

```python
GET /api/admin/openviking/sync_jobs?status=running|pending|failed&limit=50
→ {
  "items": [
    {
      "id": str,
      "source_type": str,
      "source_id": str,
      "feature_slug": str|null,
      "viking_uri": str|null,
      "status": str,
      "attempts": int,
      "next_retry_at": str|null,
      "last_synced_at": str|null,
      "last_indexed_at": str|null,
      "error": str|null,
      "task_id": str|null,
      "progress": {                              // 见 SDD §3.1
        "total_chunks": int,
        "indexed_chunks": int,
        "failed_chunks": int,
        "throughput_chunks_per_sec": float,
        "eta_seconds": int|null,
        "last_updated_at": str,
        "files": {"total": int, "processed": int, "processed_names": [str]}
      } | null,
      "created_at": str,
      "updated_at": str
    }
  ],
  "total": int
}
```

### 7.1.2 事件流接口

```python
GET /api/admin/openviking/events?event_type=...&source_type=...&limit=100&before_id=...
→ {
  "items": [
    {
      "id": int,
      "event_type": str,
      "source_type": str|null,
      "source_id": str|null,
      "sync_job_id": str|null,
      "triggered_by": str|null,
      "payload": dict,
      "outcome": "info" | "success" | "warning" | "error",
      "created_at": str
    }
  ],
  "next_before_id": int|null   // 翻页用
}
```

### 7.1.3 手动操作接口

```python
POST /api/admin/openviking/sync_jobs/{job_id}/retry      # 单 job 重试
POST /api/admin/openviking/sync_jobs/retry_failed         # 批量重试 failed 任务
POST /api/admin/openviking/resync                         # 全量重同步；body: {source_type?, feature_slug?}
POST /api/admin/openviking/rebuild_index                  # 不切模型，清空 vectordb 后全量重建
```

每个写操作都生成 `openviking_dashboard_events` 一条记录，`triggered_by` = 当前 admin subject_id。

### 7.1.4 调优接口

新增 `src/codeask/api/openviking_tuning.py`（SDD §13.6.2）：

```python
GET  /api/admin/openviking/tuning
→ {
  "scopes": {
    "openviking": [
      {"key": "embedding.max_concurrent", "value": "1", "type": "int", "default": 1,
       "recommended": 2, "previous_value": null, "activated_at": "...", "activated_by": "..."},
      ...
    ],
    "ollama_recommend": [...],
    "codeask": [...]
  },
  "preset": "small_machine" | "medium_server" | "large_server" | "gpu_host" | "cloud_embedding"
}

GET  /api/admin/openviking/tuning/preset
→ {
  "detected_host": {
    "cpu_count": int, "ram_gb": int, "gpu": bool, "embedding_provider": str
  },
  "preset_id": str,
  "preset_values": {
    "openviking.embedding.max_concurrent": int,
    "codeask.sync_workers": int,
    "ollama_recommend.num_parallel": int,
    "ollama_recommend.num_thread": int
  }
}

POST /api/admin/openviking/tuning
body: {"changes": [{"scope": str, "key": str, "value": str, "notes": str|null}, ...]}
→ 202 Accepted
   {"applied": [...], "rejected": [...], "estimated_downtime_seconds": int, "tuning_event_ids": [int]}

POST /api/admin/openviking/tuning/rollback
body: {"scope": str, "key": str}
→ 202 Accepted

POST /api/admin/openviking/tuning/apply_preset
body: {"preset_id": str}                       # 只应用 openviking + codeask scope
→ 202 Accepted

GET  /api/admin/openviking/tuning/history?scope=...&key=...&limit=50
→ {
  "items": [{
    "scope": str, "key": str, "value": str, "activated_at": str,
    "activated_by": str|null, "notes": str|null,
    "previous_value": str|null
  }, ...]
}

GET  /api/admin/openviking/tuning/ollama_snippet
→ {"snippet": str, "current_recommended": {"num_parallel": int, "num_thread": int}}
```

**调参应用实现**（SDD §13.6.3）：

```python
async def apply_tuning(changes: list[TuningChange], admin_id: str):
    # 1. 校验 changes（key 合法、value 在范围内）
    invalid = [c for c in changes if not is_valid(c)]
    if invalid:
        return rejected_response(invalid)

    # 2. 写 DB（append-only OpenVikingTuningSetting）+ emit_event
    for change in changes:
        await tuning_repo.append(change, admin_id=admin_id, previous=...)
        await dashboard.emit_event(
            event_type="tuning_change",
            scope=change.scope, key=change.key,
            triggered_by=admin_id,
            payload={
                "value_before": change.previous_value,
                "value_after": change.value,
                "notes": change.notes,
            },
            outcome="info",
        )

    # 3. 按 scope restart 相应进程
    if any(c.scope == "openviking" for c in changes):
        await regenerate_ov_conf()
        await process.restart_openviking()    # ~30s
    if any(c.scope == "codeask" for c in changes):
        await scheduler.reload_jobs()         # 秒级

    scope_set = {c.scope for c in changes}
    return accepted_response(estimated_downtime=30 if "openviking" in scope_set else 5)
```

不做异步 baseline snapshot；admin 通过仪表盘 metrics 卡片自然观察改后状态。

**主机识别 / 推荐预设算法**：

```python
def detect_preset() -> tuple[str, dict]:
    cpu_count = os.cpu_count() or 4
    ram_gb = psutil.virtual_memory().total // (1024**3)
    has_gpu = detect_gpu()                         # lspci / nvidia-smi
    provider = read_setting("embedding.provider")  # ollama / openai / volcengine / ...

    if provider != "ollama":
        return "cloud_embedding", PRESET_CLOUD
    if has_gpu:
        return "gpu_host", PRESET_GPU
    if cpu_count >= 64:
        return "large_server", PRESET_LARGE
    if cpu_count >= 32:
        return "medium_server", PRESET_MEDIUM
    if cpu_count >= 16:
        return "small_server", PRESET_SMALL
    return "small_machine", PRESET_TINY
```

**Ollama 实际配置探测**（SDD §13.6.6）：

```python
async def verify_ollama_recommend(expected_num_parallel: int):
    """
    1. 向 Ollama 同时发 expected_num_parallel + 2 个并发 embed
    2. 测每个的 wall time
    3. 如果前 expected_num_parallel 个 latency 接近、之后的 latency 明显递增
       → NUM_PARALLEL 生效
       否则 → 没生效（admin 忘了 restart 或 daemon-reload）
    4. emit_event("ollama_settings_verified", outcome=...)
    """
```

### 7.2 Embedding 模型管理接口

新增 `src/codeask/api/openviking_admin.py`：

```python
GET  /api/admin/openviking/embedding             # 当前激活配置
GET  /api/admin/openviking/embedding/candidates  # 列 ollama /api/tags + 历史模型
POST /api/admin/openviking/embedding             # 切换；body: {model: str, base_url?: str, dimension?: int}
                                                 # 返回 202 + new setting + rebuild_status=rebuilding
GET  /api/admin/openviking/embedding/history     # 历史切换审计
POST /api/admin/openviking/embedding/rebuild     # 不切模型，重新跑一次全量重建（修复异常）
```

切换流程（POST 入口）：

1. 校验 admin 身份
2. 探测 Ollama `/api/tags` 验证模型存在；如果不存在但 admin 显式确认，写入但 `rebuild_status=pending_pull`
3. 写 `OpenVikingEmbeddingSetting` 新行，`previous_setting_id` 指向旧行
4. 重新生成 `ov.conf` → 重启 OpenViking server（沿用 process.py 的 restart 流程）
5. 把所有 `openviking_sync_jobs` 标 `pending`；清除 OpenViking workspace 向量数据
6. APScheduler 同步任务开始全量重建；进度写 `rebuild_progress`
7. 完成 → `rebuild_status=completed`；记录审计

前端 OpenViking 仪表盘的完整组件清单见 SDD §13.4；本节只列 Phase 1 需要先实现的最小可用版本：

- `OpenVikingHealthCard.tsx`（必须）：进程状态 + Embedding 当前配置 + 切换 model 入口
- `OpenVikingSyncJobsCard.tsx`（必须）：进行中 / 等待 / 失败任务列表，每条带进度条 + ETA + 手动重试
- `OpenVikingEventStream.tsx`（必须）：事件流，按 outcome 着色；`tuning_change` 单条事件按时间倒序展示
- `OpenVikingTuningCard.tsx`（必须）：参数调优面板（SDD §13.6.1）；含主机识别 + 推荐预设 + 三个 scope 的参数列表 + 回滚 + Ollama systemd snippet
- `OpenVikingMetricsCard.tsx`（可后置到 Phase 2）：throughput / latency / breaker trips

切换 / 重建 / 手动操作沿用 v1.0.3 admin 权限通道；事件全部写入 `openviking_dashboard_events`；重要审计动作（embedding_model_switched / manual_resync）同时写入 `audit_log`。

### 7.3 仪表盘事件流实现

新增 `src/codeask/rag/openviking/dashboard.py`（SDD §13.2）：

```python
async def emit_event(session, *, event_type, source_type=None, source_id=None,
                    sync_job_id=None, triggered_by=None, payload=None, outcome="info")
```

调用入口清单（按 Phase 1 实施顺序）：

| 触发点 | 调用 emit_event 时机 |
|---|---|
| `sync.py.enqueue()` | 写入新 pending job 后；event_type 按 PRD §10.2 表查 |
| `sync.py.run_pending_jobs()` | job 转 running 时；job 完成 (`sync_job_completed`) 或失败 (`sync_job_failed`) |
| `process.py.keepalive()` | 检测到 OpenViking pid 变化 → `openviking_restart_detected` |
| `health.py.ollama_health()` | 探测到 Ollama 从 unhealthy → healthy → `ollama_recovery`；反向 → `ollama_lost` |
| `app.py` startup hook | 启动 sweep 完成 → `startup_sweep` 含 `payload={discovered_jobs: int, ...}` |
| `app.py` startup sync_jobs reconcile | `running` 状态 job 重新拉 task → `codeask_restart_sweep` |
| `openviking_admin.py` model 切换接口 | `embedding_model_switched` 含 `payload={from, to, dimension_changed: bool}` |
| `openviking_admin.py` 手动重同步接口 | `manual_resync` 含 `payload={scope, count}` |
| APScheduler 24h sweep | 每轮跑完 → `scheduled_refresh_summary` 含 `payload={added, skipped, failed}` |
| sweep 进度任务发现 circuit breaker 异常 | `circuit_breaker_tripped` / `circuit_breaker_recovered`（OpenViking 不直接暴露这个状态，需要从 server log pattern 或失败模式推断） |

事件写入**不抛异常给业务调用方**；失败只 log，避免 dashboard 写入故障影响主同步链路。

### 7.4 后台 sweep 任务清单

`app.py` 注册的 APScheduler 任务（除 Phase 1 §4 已列出的）：

| 任务 | 间隔 | 函数 |
|---|---|---|
| `openviking_progress_sweep` | 5 s | `sync.sweep_progress()` 拉 OpenViking task 状态回写 sync_jobs.progress；推 EMA throughput |
| `openviking_scheduled_refresh` | 24 h | `sync.scheduled_refresh()` 对所有 source 对象计算 hash + 入队变化的 |
| `openviking_event_retention` | 24 h | 裁剪 `openviking_dashboard_events` 表，每 event_type 保留最近 N 条 |
| `openviking_metrics_5min_rollup` | 1 min | 聚合最近 5 分钟 throughput / latency / breaker trips 到 status 接口可读的内存缓存 |

---

## 8. 测试矩阵

| 层次 | 用例 |
|---|---|
| 单元 | URI 映射往返；`ov.conf` 生成；同步状态机；指数退避；EMA throughput；ETA 冷启动 vs ema 切换；dashboard.emit_event 不抛异常 |
| 集成 | 真实 openviking-server（spike 锁定版本）；fake Ollama；端到端同步 1 个文档 + 1 个仓库；sync_jobs.progress 由 sweep 自动更新 |
| 升级 | v1.0.4 数据库 → alembic head（含 `openviking_sync_jobs` / `openviking_embedding_settings` / `openviking_dashboard_events`）；首次 sweep 行为；OpenViking 工作区从空到非空 |
| 安全 | trusted-mode header 注入；MCP bearer token；路径遍历拒绝；admin 接口未授权拒绝；events 接口不泄露宿主机绝对路径 |
| 性能 | spike 锁定模型下，Wiki 单文件同步耗时；100 个 wiki 节点同步总耗时；progress sweep 在 100+ 个 job 下的开销 |
| 故障 | OpenViking 进程 kill → keepalive 拉回；Ollama 关闭 → 队列正确退避；**kill OpenViking server 后重启，sync_jobs.progress 从中断点续传**；CodeAsk 进程重启后对齐 running 状态 |
| 事件 | emit_event 写入不阻塞主链路；事件流分页 + 过滤；每 event_type 保留策略生效；事件 outcome 着色对应正确 |
| 仪表盘 | status 接口字段齐全；sync_jobs 列表分页 + 状态过滤；events 接口分页；手动操作幂等；rebuild 中 admin 卡片显示进度与 ETA |
| 调优 | `OpenVikingTuningSetting` append-only 写入；改 openviking scope 触发 ov.conf 重写 + restart；改 codeask scope 秒级生效；每次变更只发一条 `tuning_change` 事件（不做自动对比）；回滚走相同流程；preset 算法在不同 CPU 核数 / GPU 主机下取值正确；Ollama systemd snippet 生成正确；探测 NUM_PARALLEL 实际是否生效 |

详细 case 写到 `acceptance-checklist.md`。

---

## 9. 实施顺序（建议工单切分）

OpenViking 接入 + 仪表盘（步骤 1-11）：

1. settings + alembic migration（4 张表：`openviking_sync_jobs` / `openviking_embedding_settings` / `openviking_tuning_settings` / `openviking_dashboard_events`）+ 空 module（编译通过）
2. process + health（启停 + 探测 + Ollama `/api/tags` 模型列表，纯单元）
3. client（HTTP + MCP 调用真实 server，集成）
4. uri + sync（无 hook 触发，手动 enqueue 跑一次）
5. `dashboard.emit_event` + sync_job 状态转移时调用
6. hooks（接入 wiki / report / repo 变更点，含 emit_event；按 SDD §6.2 触发器表 / §6.3 过滤规则——草稿与 unverified Report 不入队）
7. APScheduler 任务（keepalive / sync / **progress_sweep** / scheduled_refresh / event_retention / metrics_5min_rollup）
8. admin status API + sync_jobs API + events API + 手动操作 API
9. **tuning API** + 主机识别 / 推荐预设算法 / Ollama 实测探测（不做 before/after snapshot）
10. 前端：OpenVikingHealthCard + OpenVikingSyncJobsCard + OpenVikingEventStream + OpenVikingTuningCard（最小可用版本）
11. 前端：OpenVikingMetricsCard（可后置到 Phase 2）

Wiki UI 搜索框 OpenViking-first + ILIKE 兜底（步骤 12-13）：

12. `api/wiki/search.py` 改写：OpenViking healthy 时调 `client.find_or_search(q, scope, filter=feature_uri, limit)`；失败（异常 / 不可达）或 0 命中即 fallthrough 到 `NativeWikiSearchService`；URI → feature_id 反查保留原 `_group_for_hit` 分组；前端零改动
13. 集成测试：OpenViking 健康有命中 / OpenViking 健康 0 命中 / OpenViking 不可达 / OpenViking 异常——四种 case 验证兜底正确

FTS5 链路清除（步骤 14-16）：

14. 改写 `api/documents_compat.py`：`POST /documents` 上传逻辑移除 `DocumentChunker.chunk_file` + `WikiIndexer.index_chunk`；保留 `Document` 写入与 `LegacyWikiSyncService` 桥接；新增 enqueue OpenViking sync 调用；删除 `GET /documents/search` 端点
15. 删除 `src/codeask/wiki/search.py` / `wiki/indexer.py` / `wiki/tokenizer.py`；瘦身 `wiki/chunker.py`（删 tokenizer import、删 `tokenized_text` / `ngram_text` 字段）；删除对应单元 / 集成测试 (`tests/integration/test_wiki_search.py`)
16. alembic migration drop `docs_fts` / `docs_ngram_fts` / `reports_fts`（详见 §3.2）

`agent_backend=native` legacy 路径清除（步骤 17-19）：

17. `src/codeask/app.py` 删除 native wiring：`AgentWikiToolService` / `ToolRegistry` / `AgentOrchestrator` / `chat_tool_registry` / 各 `register_*_tools` 构造与注入；`scheduler` 中只剩 opencode_keepalive / opencode_session_idle_cleanup
18. `src/codeask/sessions/messages.py:stream_agent_response` 删除 `if agent_backend != "opencode"` 分支；`api/sessions.py` 同理
19. 删除文件：`agent/orchestrator.py` / `agent/wiki_tools.py` / `agent/tools.py` / `agent/tool_schemas.py` / `agent/tool_delegates.py` / `agent/stages/` 整目录 / `agent/chat_runtime/{runtime,loop,retrieval,prompt,compaction,tool_executor,tool_registry,tool_contracts}.py` / `agent/chat_runtime/tools/` 整目录；保留 `chat_runtime/events.py` + `chat_runtime/context.py`；清理 `chat_runtime/__init__.py` 的 re-export；`settings.py` 收敛 `agent_backend: Literal["opencode"]`（或直接删除该字段并清理所有引用）；删除对应测试

Wiki 写路径 hook（步骤 20-22）：

20. `wiki/documents/service.py:publish_document` / `rollback_to_version` 完成后调 `rag.openviking.sync.enqueue(source_type="wiki_doc", source_id=document.id)`；`save_draft` / `delete_draft` 不调
21. `wiki/reports.py` + `api/reports.py` verify endpoint：`verified=false → true` 入队；`verified=true → false` 入队 tombstone；`verified=false` 状态下编辑不入队
22. wiki node 软删 hook（`WikiNode.deleted_at` 标记后）入队 tombstone

每步独立可验证 + 可回滚；建议按 11/13/16/19/22 为里程碑分别打 PR。
12. 升级路径在真实数据备份上的回归
13. acceptance-checklist 内 Phase 1 子项打勾

---

## 10. 退出条件

- 临时空库 `start.sh` 跑通；OpenViking server 自动拉起，sync 队列从空开始
- 真实数据备份升级路径完成；老数据无回归
- 全量 sweep 后所有现存 Feature / Wiki / verified 报告 / ready 仓库都在 OpenViking 中可见
- admin 诊断接口与卡片可读 / 可看 / 不显示宿主机绝对路径
- 仪表盘三个核心组件（Health / SyncJobs / EventStream）展示真实数据：当前 embedding 配置、进行中任务进度 + ETA、最近 100 条事件
- kill OpenViking server 后重启，仪表盘自动恢复显示进度，不需要 admin 手动刷新
- Ollama 重启后仪表盘出现 `ollama_recovery` 事件，sync_jobs 在 1–2 分钟内自动追上进度
- 手动重同步 / 重建 / 失败重试三个动作走通；事件流可见 `manual_resync` / `manual_retry` 等事件
- 后端测试矩阵通过；CI 不引入新红
- 不依赖 opencode 会话即可独立验证（手动调 OpenViking MCP / CLI 看到资源）

下一步进入 Phase 2。
