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

本文（Phase 1 = sync adapter 工作域）覆盖交付里程碑 **M1 / M3 / M4 / M5**；opencode 接入是 **M2**，落在 [phase-2 文档](./phase-2-opencode-integration.md)。当前实现的是 **M1**：只把 OpenViking 作为独立增强后端接入 CodeAsk（建表、进程管理、健康检查、手动同步、admin API 和仪表盘骨架）。**M1 不改 opencode 主链路、不删 FTS5、不搬 native Agent、不接 Wiki 写路径 hook。**

> 术语：**Phase** 是工作域 / 文档分组（Phase 1 = sync adapter，Phase 2 = opencode 接入）；**M1–M5** 是跨这两个工作域的**交付里程碑阶梯**。

v1.0.5 交付里程碑阶梯（按交付顺序）：

| 里程碑 | 范围 | 所属文档 | 前置依赖 |
|---|---|---|---|
| M1 | OpenViking 核心适配器 + 手动同步 + admin 仪表盘 | 本文（Phase 1） | 无（当前实施范围） |
| M2 | opencode 主链路接入 OpenViking MCP（动态上下文 / MCP 只读工具 / 行动轨迹） | [phase-2 文档](./phase-2-opencode-integration.md) | M1 |
| M3 | native Agent 隔离（搬入 `native_backend/` + `reports.py` 解耦 FTS5） | 本文（Phase 1） | M1 |
| M4 | FTS5 删除 + Wiki UI 搜索 OpenViking-first/ILIKE 兜底 | 本文（Phase 1） | **M3**（`reports.py` 必须先从 `WikiSearchService` 解耦） |
| M5 | Wiki / Report / Repo 写路径 hook（发布/verify/ready 后增量 enqueue） | 本文（Phase 1） | M1 |

交付顺序 **M1 → M2 → M3 → M4 → M5**。硬依赖只有两条：①一切在 M1 之后；②**M4 必须在 M3 之后**。M2 与 M3/M5 代码区不重叠，理论上 M1 之后可并行；但定调为**先 M2 交付 opencode 价值，再做 M3/M4 的破坏性清理**（降低清理期风险）。

M1 的验收标准是：OpenViking 不可用时 CodeAsk 仍能以 v1.0.4 行为启动和运行；OpenViking 可用时 admin 能看到健康、队列、事件和调优信息；后端能手动 enqueue 并跑通至少一条同步任务。

2026-05-25 M1 实现记录：

- `src/codeask/rag/openviking/` 已落地配置生成、进程管理、HTTP client、同步队列、URI、health、dashboard event 模块。
- Alembic `0030` 已新增 4 张 OpenViking 表：sync jobs、embedding settings、tuning settings、dashboard events。
- 后端启动会 best-effort 拉起 OpenViking 0.3.17；OpenViking 不可用只进入 admin degraded 状态，不阻塞普通路径。
- APScheduler 已注册 OpenViking keepalive 与 pending sync 后台任务；M1 的后台同步只消费已入队任务，不主动扫描 Wiki / Report 写路径。
- Admin API 已覆盖 status、sync_jobs、events、embedding、tuning 与手动 enqueue/run_pending。
- 前端设置页已新增 OpenViking 仪表盘，路由 `#/settings?page=openviking` 刷新保持在当前页面。
- M1 边界保持：未接 opencode 主链路，未删 FTS5，未迁 native Agent，未接 Wiki 写路径 hook。
- 实测发现 OpenViking 0.3.17 响应使用 `{status, result}` envelope，client 已按 envelope 解包；`vlm.enabled` 会被 0.3.17 拒绝，M1 不生成 VLM 配置。

包含：

- 新增 `src/codeask/rag/openviking/` 兼容模块（参考 SDD §1.1）
- 新增 4 张表 + 一条 alembic migration（详见 §3）
- 启动 OpenViking server 进程管理 + keepalive
- 同步引擎执行手动 enqueue / add-resource / 索引追踪 / 失败重试
- admin 诊断接口 `GET /api/admin/openviking/status`
- admin 设置页 OpenViking 仪表盘（详见 §7）
- 后端单元 / 集成测试

不包含：

- 不在 opencode 会话注入 OpenViking 资源提示（M2 / phase-2 文档）
- 不在 `opencode.json` 加 OpenViking MCP（M2 / phase-2 文档）
- 不暴露 OpenViking 工具事件到前端行动轨迹（M2 / phase-2 文档）
- 不改 `/api/wiki/search`（M4）
- 不接 Wiki / Report / Repo 写路径 hook（M5）
- 不删除 FTS5（M4）
- 不隔离 native Agent（M3）
- 不接入 Claude Code backend

Phase 1 完成后：

- OpenViking server 可由 CodeAsk 后端 best-effort 拉起；失败只进入 admin degraded 状态，不阻断普通用户路径
- admin 可查看 OpenViking 健康、同步任务、事件流、embedding/tuning 当前配置
- 手动 enqueue / resync 能创建并推进 sync job；未接 hook 前不会自动把 Wiki 写路径变更同步进去
- opencode 会话、Wiki UI 搜索、FTS5、native Agent 行为与 v1.0.4 保持一致

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

M1 新增 1 条 alembic migration：

### 3.1 新增 4 张表

| 表 | schema 见 | 用途 |
|---|---|---|
| `openviking_sync_jobs` | SDD §3.1 | 同步任务状态机 + progress 字段 |
| `openviking_embedding_settings` | SDD §3.3 | 当前激活 embedding 配置 + 切换历史 |
| `openviking_tuning_settings` | SDD §3.4 | append-only 调优记录 |
| `openviking_dashboard_events` | SDD §13.1 | append-only 事件流 |

文件：`alembic/versions/XXXX_openviking_v1_0_5_tables.py`

### 3.2 DROP FTS5 虚表（M4，不在 M1 实施）

```python
def upgrade():
    op.execute("DROP TABLE IF EXISTS docs_fts")
    op.execute("DROP TABLE IF EXISTS docs_ngram_fts")
    op.execute("DROP TABLE IF EXISTS reports_fts")

def downgrade():
    raise NotImplementedError("v1.0.5 不支持 downgrade 到 FTS5")
```

文件：`alembic/versions/YYYY_drop_fts5_tables.py`（在 M4 实施，必须在 M3 native 隔离之后）

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

## 5. 同步触发点（hook 清单，M5 实施）

M1 不接任何写路径 hook，只提供手动 enqueue / resync 入口和后台 worker。下表是 M5 的目标清单，保留在本文中用于后续里程碑衔接：

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

M1 OpenViking 接入 + 仪表盘（步骤 1-11）：

1. settings + alembic migration（4 张表：`openviking_sync_jobs` / `openviking_embedding_settings` / `openviking_tuning_settings` / `openviking_dashboard_events`）+ 空 module（编译通过）
2. process + health（启停 + 探测 + Ollama `/api/tags` 模型列表，纯单元）
3. client（HTTP + MCP 调用真实 server，集成）
4. uri + sync（无 hook 触发，手动 enqueue 跑一次）
5. `dashboard.emit_event` + sync_job 状态转移时调用
6. 手动 resync / enqueue API（只允许 admin；写入 sync_jobs 并发事件，不触碰 Wiki 写路径）
7. APScheduler 任务（keepalive / sync / **progress_sweep** / scheduled_refresh / event_retention / metrics_5min_rollup）
8. admin status API + sync_jobs API + events API + 手动操作 API
9. **tuning API** + 主机识别 / 推荐预设算法 / Ollama 实测探测（不做 before/after snapshot）
10. 前端：OpenVikingHealthCard + OpenVikingSyncJobsCard + OpenVikingEventStream + OpenVikingTuningCard（最小可用版本）
11. 前端：OpenVikingMetricsCard（可后置到 Phase 2）

M3 自研 Agent 隔离（步骤 12-14，搬迁不删除，**必须在删 FTS5 之前**，详见 SDD §1.6；不在 M1 实施）：

> 排期约束：FTS5 删除会移除 `WikiSearchService`，而 native 的 `tools/reports.py` 仍 import 它；必须先把 native 搬走并把 `reports.py` 解耦，否则中间态 import 不了。

12. 新建 `src/codeask/agent/native_backend/`，把 native-only 模块整体搬入（`orchestrator.py` / `wiki_tools.py` / `tools.py` / `tool_schemas.py` / `tool_delegates.py` / `tool_models.py` / `state.py` / `prompts.py`（顶层 native prompts，**非** `opencode_compat/prompts.py`）/ `code_tools.py` / `answer_links.py` / `stages/` / `chat_runtime/{runtime,loop,retrieval,prompt,compaction,tool_executor,tool_registry,tool_contracts}.py` / `chat_runtime/tools/`）；`chat_runtime/events.py` + `chat_runtime/context.py` + 顶层 `sse.py`（`SSEMultiplexer`）+ `trace.py`（`AgentTraceLogger`）留原位作共享层（opencode 路径引用，**不搬**）；改写所有内部 import 路径；写 `native_backend/README.md`（复活指引：RAG 接 OpenViking 不回退 FTS5）
13. 解耦 FTS5（**自包含方案**）：`native_backend/chat_runtime/tools/reports.py` 删除 `from codeask.wiki.search import ReportSearchHit, WikiSearchService`，改为在 `native_backend` 内部自写最小 ILIKE report 搜索 + 本地 report-hit dataclass（沿用原字段保证 `asdict` 输出契约；复刻 `verified=1`/feature 过滤、metadata 取 `commit_sha`、子串 snippet）；**不**复用、**不**扩展共享的 `wiki/native_search.py:NativeWikiSearchService`（活主链路零改动；允许少量重复 SQL）。仅为保活，非目标方案
14. 下线请求链路：
    - `app.py` 移除 native 构造与注入（`AgentWikiToolService` / `AgentCodeSearchService` / `ToolRegistry.bootstrap` / `AgentOrchestrator` / `chat_tool_registry` + 各 `register_*_tools` / `ChatRuntime`），删 `app.state.{tool_registry,agent_orchestrator,chat_runtime}`；**保留** `trace_logger` 与 `worktree_manager`（opencode 仍用）；scheduler 只剩 opencode_keepalive / opencode_session_idle_cleanup
    - `sessions/messages.py`：`stream_agent_response` 收敛为只走 opencode（删 `agent_backend` 判断 + native `ChatRuntime` fall-through 整段）；删除已无调用方的 `stream_legacy_orchestrator_response`；保留 `SSEMultiplexer` import
    - `api/sessions.py`：删 `agent_backend != "opencode"` 分支，`== "opencode"` 简化恒真
    - `settings.py` 收敛 `agent_backend: Literal["opencode"]`
    - 新增冒烟测试 `tests/unit/test_native_backend_importable.py`；原 native 测试迁入 `tests/native_backend/` 标 legacy（保留逻辑，不删；共享层 `tests/unit/chat_runtime/test_events.py` 留原位）

M4 FTS5 链路清除（步骤 15-17，须在 native 解耦之后；不在 M1 实施）。纪律同 M3：**先切断所有活消费者 → 再删模块/虚表 → 再上新搜索路径**，每步独立可跑、可回滚。

> 真实改面比 SDD 初稿大：`WikiSearchService` / `WikiIndexer` 的活消费者不止 `documents_compat.py`，还包括 `api/reports.py` 与 `wiki/reports.py:ReportService`；`tokenizer.py` 的 `tokenize` 还被 `path_resolver.py` 用（非 FTS5）。详见 SDD §1.5 消费者表。

15. **（D1）切断 FTS5 写/读的活消费者** —— 做完后无任何活代码引用 `WikiSearchService`/`WikiIndexer`，模块成孤儿但 app 仍绿：
    - `api/documents_compat.py`：上传 `upload_document` 移除 `DocumentChunker.chunk_file` + `DocumentChunk` 写入 + `indexer.index_chunk`（含 `tokenized_text`/`ngram_text`），保留 `Document` 写入与 `LegacyWikiSyncService` 桥接（**OpenViking 入队不在此处加，挪到 M5 step20**）；删 `GET /documents/search` 端点；`delete_document` 移除 `unindex_chunks_for_document`
    - `wiki/reports.py:ReportService`：移除 verify / unverify / reject 上所有 `self._indexer.index_report/unindex_report` 调用 + 构造里的 `_indexer`（这三处是仅有的调用点，`create_draft`/`update_draft` 无）
    - `api/reports.py`：删 `GET /reports/search` 端点（无产品消费者；前端仅 action-trace 标签引用同名 native 工具，非 REST 调用）；`delete_report` 移除 `unindex_report`
    - 调整/删除打 `/documents/search`、`/reports/search` 的后端测试
16. **（D2）删模块 + 瘦身 chunker**：
    - **先迁 `tokenize`**：把 `tokenizer.py:tokenize` 挪到 `path_resolver.py`（或新建 `wiki/text_utils.py`）并改 `path_resolver.py` 的 import；`to_ngrams` 不迁（FTS5 专用）
    - 删 `wiki/search.py` / `wiki/indexer.py` / `wiki/tokenizer.py`
    - 瘦身 `wiki/chunker.py`（删 tokenizer import、删 `ParsedChunk.tokenized_text`/`ngram_text` 字段及 `_build` 两处赋值；保留 `heading_path`/`raw_text`/`normalized_text`/`signals_json`，`NativeWikiSearchService._best_heading_path` 要用）
    - 删 `tests/integration/test_wiki_search.py` 及其它直测 FTS5 的单测
    - 注：`document_chunks` 表保留（历史数据，删后不再读写），其 NOT NULL 的 `tokenized_text`/`ngram_text` 列无害，**不需要** migration 动它
17. **（D2）alembic drop migration**：`revision = "0031"`、`down_revision = "0030"`（本仓用短数字 revision id，当前 head 是 `0030`，非文件名），drop `docs_fts` / `docs_ngram_fts` / `reports_fts`；`downgrade` raise `NotImplementedError`（详见 §3.2）

M4 Wiki UI 搜索框 OpenViking-first + ILIKE 兜底（步骤 18-19；不在 M1 实施）：

18. **（D3）先 spike 再开工** —— OpenViking 查询侧 client 方法不存在，且查询走 REST 还是 MCP 未验证（M2 只验过 MCP `find`）：
    - **18a 半天 spike**：对运行中的 OpenViking server 实打查询，产出「查询接口（REST `/api/v1/...` 还是 MCP）+ 端点路径 + 入参（scope/filter/limit）+ 响应结构 + 一次成功样本」。这是 M4 唯一真实未知，不出结论后续全是返工
    - **18b 加 client 查询方法**：spike 确认后给 `OpenVikingClient` 加查询方法（如 `async def search(...)`），复用现有 `_client()`（trusted headers + `trust_env=False`）
    - **18c 改写 `api/wiki/search.py`**：OpenViking healthy（复用 M1/M2 已有健康判断，**不新开 /health 探针**）→ 调 client 查询；异常 / 不可达 / 0 命中 → fallthrough 到现有 `NativeWikiSearchService`；URI → feature_id 反查保留原 `_group_for_hit` 分组；命中发 `openviking_search_hit`、0 命中发 `openviking_search_miss`，长期不可用要去重/限速防刷屏；前端零改动（`frontend/src/lib/wiki/api.ts` 不动）
19. 集成测试：OpenViking 健康有命中 / 健康 0 命中 / 不可达 / 异常——四种 case 验证兜底正确，断言分组在两条路径下一致

> M4 拆两阶段：步骤 15-19 是**阶段一**（删 FTS5 + UI 搜索），已交付（commit `ec1414e`）。**阶段二**是把 `src/codeask` 历史 pyright strict 债清零、让 pyright gate 恢复硬约束，独立 commit、按目录分批，详见 [m4-phase-2-pyright-cleanup.md](./m4-phase-2-pyright-cleanup.md)、验收 acceptance §3.10。

2026-05-26 M4 阶段一实现记录：

- FTS5 活消费者已切断：`/api/documents` 上传不再 chunk / 写 `document_chunks` / 写 FTS5；`/documents/search` 与 `/reports/search` REST 端点删除；Report verify / unverify / reject / delete 不再触碰 `WikiIndexer`。
- FTS5 模块已删除：`wiki/search.py` / `wiki/indexer.py` / `wiki/tokenizer.py` 不再存在；`tokenize` 迁入 `wiki/text_utils.py` 供 `path_resolver.py` 继续使用；`wiki/chunker.py` 删除 `tokenized_text` / `ngram_text` 运行时字段。`document_chunks` 物理表及历史列保留，不再由上传路径写入。
- Alembic 新增 `0031` drop migration 删除三张旧虚表；历史 `0005` 迁移保留 revision 链但改为 no-op，避免新库安装再创建已废弃虚表。
- OpenViking 查询 spike 结论：使用 REST `POST /api/v1/search/find`，入参 `{query,target_uri,limit,score_threshold}`，trusted headers 仍为 `X-OpenViking-Account/User/Agent`；响应为 `{status:"ok", result:{resources:[{uri,score,context_type,level,abstract,overview}], total}}`。实测成功样本命中 `viking://resources/codeask/features/m4-spike/knowledge-base/m4-spike.md/m4-spike.md`，score `0.6444`。读取正文端点实测为 `GET /api/v1/content/read`，不是旧文档里的 `/api/v1/fs/read`。
- Wiki UI 搜索已改为 OpenViking-first：进程 running 且可查询时调用 `OpenVikingClient.find`；命中 URI 通过 `openviking_sync_jobs.viking_uri` 映射回 `WikiDocument` / `Report` 后复用原分组语义；0 命中、异常、未启动、无法映射都回退 `NativeWikiSearchService`；长期 unavailable 事件按 60s 限速，避免 dashboard 被刷屏。前端 `frontend/src/lib/wiki/api.ts` 未改。

M5 Wiki / Report 写路径 hook（步骤 20-22；不在 M1 实施）。**完整计划见 [m5-write-path-hooks.md](./m5-write-path-hooks.md)**，下列为概要。

四个已锁定决策（详见 m5 文档 §1）：① **D1 content 现查**——引擎按 `source_type`+`source_id` 现查正文，不内联快照（消除 `enqueue` 去重导致的 staleness）；② **D2 tombstone 净新增**——client 无删除方法、引擎只有 add，需 spike OpenViking 删除端点 + `client.delete_resource` + 引擎 `operation=upsert|delete`；③ **D3 hook 放 API 端点 commit 之后**（service 只 flush，commit 在 API 层；修正旧措辞"放进 `sync_legacy_markdown_document` 内"）；④ **D4 软删覆盖主路径**——tree 删除 + legacy 软删发 tombstone、恢复重新 upsert，导入会话软删后置。

- **M5-0（先做，最重）**：delete spike → `client.delete_resource` → `enqueue` 加 `operation` 形参（存 `progress`，免迁移）→ `run_pending_jobs`/`_resource_from_job` 改为现查正文（upsert）或调 delete（tombstone）。
20. publish（`api/wiki/documents.py:34`，commit `:40`）/ rollback（`api/wiki/versions.py:79`，commit `:85`）端点 commit 后 `enqueue(source_type="wiki_doc", source_id=str(document.id), …)`；`save_draft`/`delete_draft` 不入队。
20b. legacy `/documents` 上传（`documents_compat.py:43`，commit `:110`）+ `backfill_feature_content`（`wiki/sync/service.py:28`，调用方 commit 后逐个）入队，覆盖上传 + 全量回填；source_id 用同步出的 `WikiDocument.id`（与 M4 反查一致）。
21. Report verify 端点（`api/reports.py:96`，commit `:112`）`false→true` upsert；unverify/reject/delete report → tombstone；unverified 编辑不入队。
22. Wiki 节点软删（`tree/service.py:465` / `sync/service.py:149` 所属端点 commit 后）→ tombstone；恢复（`tree/service.py:517`）→ 重新 upsert。

source_type/source_id 与 M4 反查约定：`wiki_doc`→`WikiDocument.id`、`report`→`Report.id`（见 m5 文档 §2）。

收尾（每个里程碑合入前必做）：升级路径在真实数据备份上回归一次；勾选 acceptance-checklist 对应 Phase 1 子项。

每步独立可验证 + 可回滚。交付里程碑与本文步骤的对应：**M1 = 步骤 1-11**；**M3 = 步骤 12-14**（native 隔离）；**M4 = 步骤 15-19**（删 FTS5 + UI 搜索兜底）；**M5 = 步骤 20-22**（写路径 hook）。**M2（opencode 接入）不在本文，见 [phase-2 文档](./phase-2-opencode-integration.md)，排在 M1 之后交付。** 硬依赖：M4 必须在 M3 之后（步骤 12-14 把 `reports.py` 从 `WikiSearchService` 解耦后，步骤 15-17 才能删 FTS5）。

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
