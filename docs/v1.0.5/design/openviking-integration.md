# OpenViking Integration 系统设计

> 版本：v1.0.5
> 状态：Draft
> 关联：[产品契约](../prd/rag-knowledge.md) | [Phase 0 spike](../plans/phase-0-spike.md) | [集成边界声明](../specs/openviking-agpl-review.md)

---

## 1. 模块边界

### 1.1 新增模块

```text
src/codeask/rag/
└── openviking/
    ├── __init__.py
    ├── config.py           # ov.conf 生成；从 CodeAsk settings + DB 派生
    ├── process.py          # OpenViking server 生命周期（参考 opencode_compat/process.py）
    ├── client.py           # OpenViking HTTP / MCP 客户端封装
    ├── sync.py             # 同步引擎；wiki / report / repo 增量同步 + progress sweep + ETA
    ├── uri.py              # CodeAsk 主数据 ↔ viking:// URI 映射
    ├── models.py           # OpenVikingSyncJob / OpenVikingEmbeddingSetting /
    │                       # OpenVikingTuningSetting / OpenVikingDashboardEvent
    ├── dashboard.py        # emit_event；事件流写入封装
    ├── health.py           # 健康检查、版本探测、Ollama 健康联动、模型可用性探测
    ├── tuning.py           # 主机识别 / 推荐预设 / Ollama systemd snippet 生成 / 实测探测
    └── README.md           # 模块边界说明
```

```text
src/codeask/api/
├── openviking_status.py    # GET /status / /sync_jobs / /events + 手动操作（详见 Phase 1 §7.1-§7.1.3）
├── openviking_admin.py     # admin embedding 模型管理（list / set / rebuild，详见 Phase 1 §7.2）
└── openviking_tuning.py    # admin tuning API（详见 Phase 1 §7.1.4）
```

```text
alembic/versions/
└── XXXX_openviking_v1_0_5.py   # 单 migration 建 4 张表：
                                # openviking_sync_jobs (§3.1)
                                # openviking_embedding_settings (§3.3)
                                # openviking_tuning_settings (§3.4)
                                # openviking_dashboard_events (§13.1)
```

### 1.2 修改模块

| 现有文件 | 变更 |
|---|---|
| `src/codeask/app.py` | 启动阶段拉起 OpenViking server；注册 keepalive 与同步定时任务；新增 `app.state.openviking_*` |
| `src/codeask/agent/opencode_compat/config.py` | 在 `opencode.json` 的 `mcp` 中加入 OpenViking remote MCP endpoint 与 token |
| `src/codeask/agent/opencode_compat/context.py` | `build_dynamic_codeask_context` 加入 OpenViking 资源布局与使用原则段落 |
| `src/codeask/agent/opencode_compat/prompts.py` | `AGENTS.md` 与 system prompt 增加 RAG 使用原则 |
| `src/codeask/wiki/` 相关 hook | Wiki 节点变更后写入同步队列 |
| `src/codeask/sessions/report_generation.py` 及报告 verify hook | 报告生命周期变更后写入同步队列 |
| `src/codeask/code_index/cloner.py` & `worktree.py` | 代码仓 ready / 更新后写入同步队列 |
| `src/codeask/settings.py` | 新增 OpenViking / Ollama 配置项 |
| `frontend/src/components/settings/...` | admin 设置页新增 OpenViking 仪表盘组件（详见 §13.4） |
| `frontend/src/components/session/action-trace/...` | 新增 OpenViking 工具事件展示 |

### 1.3 不动模块

- `src/codeask/agent/opencode_compat/` 内部不反向依赖 `src/codeask/rag/openviking/`；OpenViking 模块通过 app.state 暴露 client/sync，让 opencode_compat 间接拿到
- `src/codeask/wiki/native_search.py`、`wiki/search.py`、FTS5 / n-gram 索引保留作为兜底；v1.0.5 不删除
- `src/codeask/agent/chat_runtime/`、`agent/orchestrator.py` 不动；v1.0.4 已经只在回退路径使用

### 1.4 边界约束

- `rag/openviking/` 不抽通用 RAG backend Protocol。如果未来引入 AnythingLLM 或其它后端，新增独立目录如 `rag/anythingllm_compat/`，不与 OpenViking 模块复用内部代码
- 不让 OpenViking 直接读写 CodeAsk DB；CodeAsk 主数据永远经由 CodeAsk 后端
- 不让 OpenViking 直接读取宿主机绝对路径；所有同步路径通过 sync.py 受控转发，并在导入元数据中只保留 CodeAsk 相对路径

---

## 2. 数据流

### 2.1 写入侧（CodeAsk → OpenViking）

```text
Wiki / 报告 / 仓库变更
  ↓
CodeAsk 写入 openviking_sync_jobs（status=pending）
  ↓
APScheduler 定时任务 / 即时触发
  ↓
sync.py 取出任务
  ↓
  ├─ Wiki: 从 wiki_workspace/current/<feature_slug>/... 准备本地路径
  ├─ 报告: 从 wiki_workspace verified / drafts 派生
  └─ 仓库: 从 $CODEASK_DATA_DIR/repos/<repo_id>/... 派生
  ↓
client.py 调 OpenViking add_resource (SDK / REST)
  ↓
等待 OpenViking 索引任务完成或登记 task_id 异步追踪
  ↓
回写 openviking_sync_jobs（status=indexed / failed + viking_uri + error）
```

### 2.2 读取侧（opencode 会话内）

```text
opencode 发起 MCP 调用
  ├─ /api/agent-mcp/{session_id}/...  (CodeAsk MCP, v1.0.4)
  └─ http://127.0.0.1:1933/mcp        (OpenViking MCP, v1.0.5 新增)
       Authorization: Bearer <openviking_token>
  ↓
OpenViking 直接返回结果（find/search/read/grep/glob）
  ↓
opencode 把结果作为上下文消化
  ↓
（如需源码证据）opencode 调 CodeAsk MCP codeask_prepare_worktree
  ↓
opencode 用原生 read/grep/glob 读 session workspace 相对路径
```

CodeAsk 不在 opencode 流式响应中代理 OpenViking 调用；OpenViking 工具事件通过 opencode 原始事件流以 `tool.running / tool.completed` 形式回来，再由 `agent/opencode_compat/events.py` 归一化展示。

---

## 3. 数据模型

### 3.1 `OpenVikingSyncJob`

```python
class OpenVikingSyncJob(Base, TimestampMixin):
    __tablename__ = "openviking_sync_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    source_type: Mapped[str] = mapped_column(String(32))   # wiki_doc / wiki_dir / report / repo / feature_readme / global_index
    source_id: Mapped[str] = mapped_column(String(128))    # CodeAsk 主数据 ID
    feature_slug: Mapped[str | None] = mapped_column(String(128), nullable=True)
    viking_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16))        # pending / running / indexed / failed / cancelled
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(128), nullable=True)  # OpenViking 异步任务 id
    progress: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 由后台 sweep 任务从 OpenViking GET /api/v1/tasks/<task_id> 拉取后回写
```

`progress` JSON schema：

```json
{
  "total_chunks": int,          // 总 chunk 数；切完 parser 阶段后才精确
  "indexed_chunks": int,        // 已 embed 入库
  "failed_chunks": int,         // embedding 失败
  "requeue_count": int,         // 重新入队次数
  "throughput_chunks_per_sec": float,  // 最近 N 个 chunk 的 EMA 吞吐
  "last_chunk_latency_ms": float,      // 上一个 chunk 的实际耗时
  "eta_seconds": int | null,    // CodeAsk 上层算出的剩余时间；< 10 chunk 完成时为 null
  "last_updated_at": str,       // ISO8601；sweep 任务每次回写时刷新
  "files": {                    // 可选；OpenViking task 返回的 per-file 信息
    "total": int,
    "processed": int,
    "processed_names": [str, ...]  // 最多保留最近 10 个
  }
}
```

唯一约束：`(source_type, source_id)` 同时只允许一条非终态记录。

参考 anything-llm `DocumentSyncQueue` 设计：`maxRepeatFailures` 由 settings 控制；失败超过阈值标记 `cancelled` 并发审计事件。

### 3.2 不新增的字段

不在 `llm_configs` 上加任何 OpenViking 字段；不在 `sessions` 上加 OpenViking session 映射（OpenViking session 在 client.py 内部按 CodeAsk session_id 派生，不持久化）。

### 3.3 `OpenVikingEmbeddingSetting`

embedding 模型是 admin 运行时可切换配置，落 DB 而不只是 settings：

```python
class OpenVikingEmbeddingSetting(Base, TimestampMixin):
    __tablename__ = "openviking_embedding_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(32))         # 当前固定 "ollama"
    base_url: Mapped[str] = mapped_column(String(256))
    model: Mapped[str] = mapped_column(String(128))
    dimension: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_concurrent: Mapped[int] = mapped_column(Integer, default=1)
    # OpenViking 顶层 embedding.max_concurrent；客户端 asyncio.Semaphore 限流
    # 推荐：ollama=1（CPU 单 worker），cloud provider=5-10，自托管 GPU 服务=16-64
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    activated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)  # admin subject_id
    previous_setting_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rebuild_status: Mapped[str] = mapped_column(String(16), default="idle")
    # idle | rebuilding | completed | failed
    rebuild_progress: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 聚合所有 sync_jobs 在当前 rebuild 中的总进度：
    # {
    #   "total_sources": int, "indexed_sources": int, "failed_sources": int,
    #   "total_chunks": int, "indexed_chunks": int, "failed_chunks": int,
    #   "started_at": str, "estimated_completion_at": str | null
    # }
    # 注意：这是 rebuild 级别的聚合进度；单 sync_job 的精细进度走 §3.1 OpenVikingSyncJob.progress
```

只保留**当前一行**作为活跃配置（按 `activated_at` 取最新行）；历史行用于审计与回滚。`previous_setting_id` 指向上一个活跃行，便于切换失败回退。

settings 中的 `openviking_embed_*` 只用于**首次安装时填充 DB 默认值**；之后以 DB 为准。

### 3.4 `OpenVikingTuningSetting`

参数调优是 admin 频繁动作（PRD §10.4），不适合塞进 `OpenVikingEmbeddingSetting`（那张表语义是"当前 embedding 配置"，每次切 model 才新建一行）。单独建调优表：

```python
class OpenVikingTuningSetting(Base, TimestampMixin):
    __tablename__ = "openviking_tuning_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(16))
    # "openviking" | "ollama_recommend" | "codeask"
    key: Mapped[str] = mapped_column(String(64))
    # openviking: embedding.max_concurrent / embedding.circuit_breaker.failure_threshold /
    #             embedding.circuit_breaker.reset_timeout / embedding.max_retries /
    #             embedding.max_input_tokens
    # ollama_recommend: num_parallel / num_thread
    # codeask: sync_workers / progress_sweep_interval_seconds / scheduled_refresh_hours
    value: Mapped[str] = mapped_column(String(256))  # 统一存字符串；读取时按 key 强类型解析
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    activated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    previous_value: Mapped[str | None] = mapped_column(String(256), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # admin 在 UI 可填一段调整原因，便于以后回看
```

**Append-only 设计**：每次写新行；按 `(scope, key)` 取 `id` 最大（或 `activated_at` 最新）的一行为当前生效配置。历史行保留，便于回滚和审计；不加唯一约束。

`ollama_recommend` scope 的行**只是 CodeAsk 提供给 admin 的建议值**，不代表 Ollama 实际生效值；admin 是否真的改 systemd 由仪表盘探测当前 Ollama 行为反推。

### 3.5 不在第一版引入的

- 多模型并存（同时跑两套 embedding，切流量做 A/B）
- 切换时增量重建（只对受新模型影响的 chunk 重嵌入）
- per-feature 选不同 embedding 模型

这些都留给后续版本；v1.0.5 全量重建简单可审计。

---

## 4. URI 映射规则

`rag/openviking/uri.py` 维护双向映射。

| CodeAsk 主数据 | OpenViking URI |
|---|---|
| Feature `<feature_slug>` | `viking://resources/codeask/features/<feature_slug>/README.md` |
| Wiki 节点（feature_slug + 相对路径 `<rel>`） | `viking://resources/codeask/features/<feature_slug>/knowledge-base/<rel>` |
| Verified 报告 `<report_id>` | `viking://resources/codeask/features/<feature_slug>/problem-reports/verified/<filename>.md` |
| Draft 报告 `<report_id>` | `viking://resources/codeask/features/<feature_slug>/problem-reports/drafts/<filename>.md` |
| 仓库 `<repo_slug>` | `viking://resources/codeask/repos/<repo_slug>/` |
| 全局特性目录 | `viking://resources/codeask/global/feature-index.md` |
| 全局仓库目录 | `viking://resources/codeask/global/repo-index.md` |
| 全局报告索引 | `viking://resources/codeask/global/report-index.md` |

规则：

- `<feature_slug>` 取 `features.slug`；slug 缺失退化为 `feature_<id>`
- 文件名按 CodeAsk Wiki 节点的展示名做安全转义；保留 `.assets/` 相对引用
- 报告文件名前缀使用强制日期：`YYYY-MM-DD-<slugified-title>.md`，符合 `docs/rules/problem-report.md`
- slug 重命名触发：旧 URI 写入 `tombstone` 同步任务 → 调用 OpenViking 删除 → 新 URI 写入 `pending` 同步任务

---

## 5. OpenViking server 生命周期

### 5.1 启动

```python
# src/codeask/app.py 生命周期内
if settings.rag_backend == "openviking":
    app.state.openviking_process = OpenVikingProcessManager(
        bin=settings.openviking_bin,
        config_path=Path(settings.data_dir) / "openviking" / "ov.conf",
        port=settings.openviking_port,
        host=settings.openviking_host,
        log_dir=Path(settings.data_dir) / "openviking" / "logs",
    )
    app.state.openviking_process.ensure_server()
    scheduler.add_job(
        app.state.openviking_process.keepalive,
        "interval",
        seconds=settings.openviking_keepalive_interval_seconds,
        id="openviking_keepalive",
    )
    scheduler.add_job(
        run_pending_sync_jobs,
        "interval",
        seconds=settings.openviking_sync_interval_seconds,
        id="openviking_sync",
    )
```

参考 v1.0.4 `_ensure_opencode_server`：best-effort 拉起，进程退出由 keepalive 重启。Ollama 进程 **不归 CodeAsk 管**；CodeAsk 只在健康检查时探测 Ollama URL 是否可达。

### 5.2 健康检查

`health.py` 提供：

- `openviking_health()` → 调用 OpenViking `/health` 与 MCP `health`
- `ollama_health()` → 探测 `<base_url>/api/tags` 或 `/api/ps`
- `version_probe()` → 启动时记录 `openviking-server --version`；与 `settings.openviking_verified_version` 比对，不匹配只写 warning

### 5.3 关停

CodeAsk 进程退出时调用 `process.shutdown()`；优雅终止超时使用 `openviking_graceful_shutdown_seconds`。OpenViking 写盘的索引数据保留在 `$CODEASK_DATA_DIR/openviking/workspace`，下次启动可恢复。

### 5.4 ov.conf 生成

`config.py.build_ov_conf(settings)` 生成（首次启动或配置 hash 变化时重写）：

```json
{
  "storage": {
    "workspace": "<CODEASK_DATA_DIR>/openviking/workspace",
    "vectordb": {"name": "context", "backend": "local"},
    "agfs": {"backend": "local"}
  },
  "server": {
    "host": "127.0.0.1",
    "port": 1933,
    "auth_mode": "trusted",
    "cors_origins": ["http://127.0.0.1:5173"],
    "temp_upload": {"default_mode": "local"}
  },
  "embedding": {
    "dense": {
      "provider": "ollama",
      "api_base": "<current OpenVikingEmbeddingSetting.base_url>/v1",
      "model": "<current OpenVikingEmbeddingSetting.model>",
      "dimension": "<current OpenVikingEmbeddingSetting.dimension>",
      "input": "text"
    },
    "text_source": "content_only",
    "max_input_tokens": "<tuning: embedding.max_input_tokens, default 4096>",
    "max_concurrent": "<tuning: embedding.max_concurrent, default 1 for ollama>",
    "max_retries": "<tuning: embedding.max_retries, default 3>",
    "circuit_breaker": {
      "failure_threshold": "<tuning: embedding.circuit_breaker.failure_threshold, default 5>",
      "reset_timeout": "<tuning: embedding.circuit_breaker.reset_timeout, default 60>"
    }
  },
  "auto_generate_l0": false,
  "auto_generate_l1": false,
  "vlm": {"enabled": false}
}
```

可调字段（用 `<tuning: ...>` 标记）由 `OpenVikingTuningSetting` 表当前生效行决定（详见 §3.4 + §13.6）。其它字段固定。

ov.conf 重写时机：

- 首次启动 server（DB 未空）
- 切换 embedding model
- 任何 `scope=openviking` 的 tuning 变更
- 重写后必须 restart server（OpenViking 不支持 reload）

---

## 6. 同步引擎

`sync.py` 暴露：

- `enqueue(source_type, source_id, **meta)` —— 写 `openviking_sync_jobs(status=pending)`，由 hook / 后台 sweep 调用
- `run_pending_jobs(limit=N)` —— APScheduler 调用，按 `status=pending` + `next_retry_at <= now` 取任务
- `force_resync(source_type, source_id)` —— admin 手动触发

执行顺序（每个 job）：

1. 标 `running`、`attempts += 1`
2. 从 CodeAsk 主数据派生本地路径或文本
3. 调 `client.add_resource(path, parent=..., reason=..., instruction=...)`，**走 OpenViking HTTP REST**（`POST /api/v1/resources`），不调 `ov` CLI
4. 若 OpenViking 返回异步 `task_id`，记录到 `sync_jobs.task_id`，由后台 sweep（§6.1）跟踪
5. 等待索引完成 → 写 `viking_uri`、`source_hash`、`last_indexed_at`，标 `indexed`
6. 失败 → 标 `failed`、记录 `error`、按指数退避更新 `next_retry_at`；超过 `maxRepeatFailures` 标 `cancelled`

> 注：CLI（`ov add-resource ...`）只用于 spike / 人工排查；CodeAsk 产品代码全部走 HTTP REST，避免依赖 `ov` 二进制 PATH。

并发：单进程内同步 worker 数受 `settings.openviking_sync_workers` 控制（建议默认 2）。

### 6.1 进度 sweep 与 ETA 计算

`sync.py` 暴露一个后台 sweep 任务，由 APScheduler 每 `settings.openviking_progress_sweep_interval_seconds`（默认 5 秒）触发：

```python
async def sweep_progress():
    """
    对所有 sync_jobs 状态为 running 的任务：
      1. 调 OpenViking GET /api/v1/tasks/<task_id> 拉最新进度
      2. 写回 sync_jobs.progress
      3. 推算 EMA throughput 与 ETA
      4. 发事件到事件流（详见 §13.2）
    """
```

**EMA 吞吐算法**：

```python
# alpha 默认 0.3
new_chunk_count = current.indexed_chunks - previous.indexed_chunks
elapsed_sec = (now - previous.last_updated_at).total_seconds()
instant_throughput = new_chunk_count / max(elapsed_sec, 1e-3)

# 第一次没有历史时直接用 instant；之后做 EMA
if previous.throughput_chunks_per_sec is None:
    throughput = instant_throughput
else:
    throughput = alpha * instant_throughput + (1 - alpha) * previous.throughput_chunks_per_sec
```

**ETA 计算**：

```python
# 至少需要 10 个 chunk 已完成才给 ETA；否则用 phase-0 实测基线（3 s/chunk）作为冷启动
MIN_SAMPLES = 10
COLD_START_CHUNK_SEC = 3.0

remaining = max(0, total_chunks - indexed_chunks)
if indexed_chunks < MIN_SAMPLES or throughput < 0.01:
    eta_seconds = int(remaining * COLD_START_CHUNK_SEC)  # 标记 source="cold_start"
else:
    eta_seconds = int(remaining / throughput)            # 标记 source="ema"
```

**总 chunk 数的确定时机**：

OpenViking 在 parse 阶段切完所有文件后才知道精确 chunk 数。这之前 `progress.total_chunks` 取 OpenViking task `meta.total_processable`（文件数）的粗估，admin 卡片标记 "estimating..."。Parse 完成后 sweep 自动切换到精确总数。

### 6.2 增量同步触发器

`sync.py.enqueue()` 由下列 hook 调用（详见 Phase 1 §5）：

| 触发事件 | 写入 | 在事件流中显示为 |
|---|---|---|
| Wiki 节点 create/update/publish | `source_type=wiki_doc` | `wiki_doc_changed` |
| Wiki 目录 move/rename/delete | `source_type=wiki_dir` | `wiki_dir_changed` |
| 报告 verified/unverified/deleted | `source_type=report` | `report_status_changed` |
| 仓库 ready/refresh 完成 | `source_type=repo` | `repo_synced` |
| 特性创建/重命名/归档 | `source_type=feature_readme` + `global_index` | `feature_changed` |
| APScheduler 周期 sweep（默认 24h） | 对存在但 sync_hash 不匹配的对象 | `scheduled_refresh` |
| admin UI 手动重同步 | 单对象 / 单特性 / 全量 | `manual_resync` |
| CodeAsk 启动时对齐 | 缺失对象补 enqueue | `startup_sweep` |
| 模型切换 | 全量 reset → enqueue | `embedding_model_switched` |

定时增量 sweep（`scheduled_refresh`）的实现：

- APScheduler 每 24h（可配）跑一次
- 对每个 source 对象计算 `source_hash`（基于内容 hash + mtime）
- 与 `sync_jobs.source_hash` 比对；变化的写入新 pending job
- 跑完一轮发 `scheduled_refresh_summary` 事件（新增多少 / 跳过多少 / 失败多少）

---

## 7. MCP 接入

### 7.1 opencode.json 配置

`opencode_compat/config.py` 在 `mcp` 段加：

```json
{
  "mcp": {
    "codeask": {
      "type": "remote",
      "url": "http://127.0.0.1:8000/api/agent-mcp/<session_id>",
      "headers": {"Authorization": "Bearer <session_token>"}
    },
    "openviking": {
      "type": "remote",
      "url": "http://127.0.0.1:1933/mcp",
      "headers": {"Authorization": "Bearer <openviking_token>"}
    }
  }
}
```

OpenViking token 由 CodeAsk 从 `ov.conf.server.api_key` 或 trusted-mode 注入 header 派生。第一版若使用 `auth_mode=trusted`，可不需要 Bearer，但建议固定一个本机 token 以便审计。

### 7.2 工具白名单

通过 opencode `tool.allowed` 或 `permission.tool.*` 限定 OpenViking 工具可用集：

```text
openviking_find / openviking_search / openviking_read /
openviking_list / openviking_grep / openviking_glob / openviking_health
```

`add_resource / remember / forget` 不出现在白名单。

---

## 8. 动态上下文增强

`build_dynamic_codeask_context`（v1.0.4 已有）追加一段：

```md
## Knowledge Retrieval Layer (v1.0.5)

CodeAsk derived knowledge is indexed in OpenViking under:
- viking://resources/codeask/features/<feature_slug>/knowledge-base/   (wiki)
- viking://resources/codeask/features/<feature_slug>/problem-reports/  (verified strong; drafts weak)
- viking://resources/codeask/repos/<repo_slug>/                        (code repos)
- viking://resources/codeask/global/                                   (indices)

Tool usage principles:
1. Prefer OpenViking find/search to locate candidate Wiki, reports, or code paths.
2. Use grep/glob for exact-text or filename matching when symbols or strings are known.
3. OpenViking read(uri) returns OpenViking-managed content (abstract/overview/L2). It is not a substitute for real source code.
4. Before reading real repository files, call CodeAsk MCP codeask_prepare_worktree.
5. After the worktree is ready, use opencode native read/grep/glob on workspace-relative paths.
6. Verified reports are strong evidence; draft reports are weak background only.
7. Never claim a historical report matches the current issue unless symptoms, error, scenario, and root cause align tightly.
```

提示保持原则导向；不固化"先 Wiki 后代码"等顺序。

---

## 9. 错误处理矩阵

| 场景 | 处理 | 用户可见 |
|---|---|---|
| OpenViking bin 不存在 | 标记 backend unavailable | 居中弹窗：知识检索后端不可用 |
| OpenViking 启动超时 | 重试一次；再失败标记 unavailable | 同上 |
| Ollama 未启动 / 模型未拉取 | OpenViking 启动后 embedding 调用失败 → 同步任务 failed | 居中弹窗：embedding 服务不可用 |
| OpenViking server 崩溃 | keepalive 重启 + 当前轮工具调用返回 error | 行动轨迹错误事件 |
| 同步任务超阈值失败 | 标 cancelled；admin 面板可重置 | admin 面板可见 |
| OpenViking 版本与已验证不一致 | 启动 warning；可配置阻止启动 | admin 可见 |
| MCP token 不一致 | 拒绝调用；审计 | 行动轨迹错误事件 |
| 资源不存在（read/list） | OpenViking 返回 not_found；模型自行处理 | 行动轨迹错误事件 |
| 集成边界承诺被破坏（修改 OpenViking 源码 / 内嵌源码 / SaaS 化） | 触发 specs/openviking-agpl-review.md §4 回访；阻止该改动合入 | 项目负责人可见 |
| OpenViking server 重启（手动 / 崩溃 / keepalive 拉起） | OpenViking 持久化队列（QueueFS + RedoLog）保证未完成 SemanticMsg 不丢；启动时自动恢复；in-flight 少数 chunk 重新入队；sync_jobs.progress 由 sweep 自动追上 | 仪表盘事件 `openviking_restart_detected` + 进度从中断点继续，不重置 |
| Ollama 进程重启 | OpenViking 端进度完全保留；in-flight HTTP connection reset 由 OpenViking re-enqueue；可能触发 circuit breaker 60 s 等待 | 仪表盘事件 `ollama_recovery`；卡片显示"恢复中" |
| CodeAsk 进程重启 | OpenViking 独立运行，sync_jobs `running` 状态保留；CodeAsk 重启后 sweep 自动对齐 | 仪表盘事件 `codeask_restart_sweep`；几秒内进度续传 |
| 改 embedding 模型 / dimension | 必须清 vectordb collection 并全量重建（详见 §3.3）；旧 sync_jobs 全部置 pending；新 rebuild_status=rebuilding | 仪表盘明示 "rebuilding in progress"；ETA 单独标识 |

---

## 10. 配置项

`src/codeask/settings.py` 新增：

```python
class Settings:
    # RAG backend 总开关（v1.0.5 默认 openviking；none 则退回 v1.0.4 文件检索）
    rag_backend: str = "openviking"   # openviking | none

    # OpenViking 进程
    openviking_bin: str = "openviking-server"
    openviking_host: str = "127.0.0.1"
    openviking_port: int = 1933
    openviking_keepalive_interval_seconds: int = 30
    openviking_startup_timeout_seconds: int = 30
    openviking_graceful_shutdown_seconds: int = 5
    openviking_verified_version: str | None = "0.3.17"

    # 同步与定时
    openviking_sync_workers: int = 2
    openviking_sync_interval_seconds: int = 60
    openviking_sync_max_repeat_failures: int = 5
    openviking_progress_sweep_interval_seconds: int = 5
    openviking_scheduled_refresh_hours: int = 24

    # 事件流保留
    openviking_event_retention_count: int = 2000
    openviking_event_retention_sweep_interval_hours: int = 24

    # MCP
    openviking_mcp_token: str | None = None        # 留 None 自动生成

    # Embedding（首次安装时填 OpenVikingEmbeddingSetting 表的默认值；之后以 DB 为准）
    openviking_embed_provider: str = "ollama"
    openviking_embed_base_url: str = "http://127.0.0.1:11434"
    openviking_embed_model: str = "bge-m3"
    openviking_embed_dimension: int = 1024

    # 数据目录
    openviking_data_dir: str = "{CODEASK_DATA_DIR}/openviking"
```

**Settings vs DB 配置的边界**：

| 配置项 | 来源 | 修改后何时生效 |
|---|---|---|
| `rag_backend` / `openviking_bin` / `openviking_host` / `openviking_port` / `openviking_data_dir` / `openviking_*_interval_seconds` / `openviking_event_retention_*` | settings | 重启 CodeAsk 进程；不走 DB |
| `openviking_embed_*` | settings = **首次安装填 DB 默认值** | 首次启动；之后 **DB 中 OpenVikingEmbeddingSetting 才是事实** |
| `embedding.max_concurrent` / `circuit_breaker` / `max_retries` / `max_input_tokens` | DB `OpenVikingTuningSetting` | admin UI 改完自动 restart OpenViking |
| Ollama `NUM_PARALLEL` / `NUM_THREAD` | systemd unit（CodeAsk 不直接管） | admin 自己改 systemd + `daemon-reload` + `restart ollama` |

---

## 11. 测试策略

| 层次 | 内容 | 工具 |
|---|---|---|
| 单元 | URI 映射、配置生成、同步状态机、错误分类 | pytest |
| 集成 | OpenViking client / sync / MCP 直接调用真实 server | pytest + 真实 openviking-server |
| Phase 0 spike | 真实 OpenViking + Ollama + 三类真实样本（Wiki / report / repo） | pytest + shell |
| 端到端 | 真实 opencode + 真实 LLM + 真实 OpenViking 完整调查链路 | Playwright live E2E |
| 安全 | MCP token 校验、路径遍历、宿主机绝对路径过滤 | pytest |
| 升级 | 旧 v1.0.4 数据库 → v1.0.5 schema；OpenViking 工作区从空到首次构建 | pytest + 临时数据目录 |

---

## 12. 待 Phase 0 后回填

下列字段在 Phase 0 spike 结束后需更新：

- 锁定 OpenViking 版本（`openviking_verified_version`）
- 锁定 embedding 模型（`openviking_embed_model`）
- 单 Wiki / 单仓库同步耗时基线
- 召回质量基线（min / mean / max score；零召回率）
- 是否需要 VLM
- 集成边界声明回访（指向 `specs/openviking-agpl-review.md`）

---

## 13. Admin 仪表盘契约

PRD §10 规定 admin 必须能感知 OpenViking 的所有后台活动。本节定义 SDD 层的实现契约。

### 13.1 数据模型

新增 `openviking_dashboard_events` 表，append-only 事件流：

```python
class OpenVikingDashboardEvent(Base):
    __tablename__ = "openviking_dashboard_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # wiki_doc_changed / wiki_dir_changed / report_status_changed / repo_synced /
    # feature_changed / scheduled_refresh / scheduled_refresh_summary /
    # manual_resync / manual_retry / startup_sweep /
    # embedding_model_switched / openviking_restart_detected /
    # openviking_restart_completed / ollama_recovery / ollama_lost /
    # ollama_settings_verified / codeask_restart_sweep /
    # circuit_breaker_tripped / circuit_breaker_recovered /
    # sync_job_completed / sync_job_failed / sync_job_cancelled /
    # tuning_change
    source_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sync_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    triggered_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # admin subject_id / "scheduler" / "startup" / "hook"
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # event-specific fields: error message, chunk count delta, duration, etc.
    outcome: Mapped[str] = mapped_column(String(16), nullable=False, default="info")
    # info / success / warning / error
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
```

索引：`(created_at DESC)`、`(event_type)`、`(source_type, source_id)`。

保留策略：每事件类型保留最近 N 条（默认 N=2000），超出按 `created_at` 升序裁剪；后台 24h 跑一次。审计层重要事件（embedding_model_switched / manual_resync）已经在 `audit_log` 表，不重复保留。

### 13.2 事件写入入口

由 `sync.py` / `process.py` / `health.py` / `config.py` 等模块写入：

```python
# src/codeask/rag/openviking/dashboard.py
async def emit_event(
    session: AsyncSession,
    *,
    event_type: str,
    source_type: str | None = None,
    source_id: str | None = None,
    sync_job_id: str | None = None,
    triggered_by: str | None = None,
    payload: dict | None = None,
    outcome: str = "info",
) -> None:
    """统一事件写入；不抛异常给调用方，失败只 log。"""
```

调用规则：

- sync_jobs 状态机每次转移调一次（进入 running / 完成 / 失败 / 取消）
- sweep 任务发现 OpenViking server 重启（pid 变化）调一次
- health.py 检测 Ollama 不可用 / 恢复各调一次
- 模型切换、手动重同步各调一次
- 不在每个 chunk 完成时调（噪声）；chunk 级进度通过 `sync_jobs.progress` 拉

### 13.3 API 端点

仪表盘读取走 `src/codeask/api/openviking_status.py` 提供的三个端点（详见 Phase 1 §7）：

```text
GET /api/admin/openviking/status               # 全局健康 + 当前 embedding 配置
GET /api/admin/openviking/sync_jobs?status=...  # sync_jobs 当前状态 + progress
GET /api/admin/openviking/events?limit=...      # 事件流分页
```

仪表盘默认每 5 s 轮询 `status` + `sync_jobs`；`events` 按用户进入页面或下拉刷新触发。

### 13.4 前端组件（详见 Phase 2）

`frontend/src/components/settings/openviking/` 新增：

| 组件 | 职责 |
|---|---|
| `OpenVikingDashboard.tsx` | 顶层容器；并列状态卡片 + 任务卡片 + 事件流 |
| `OpenVikingHealthCard.tsx` | OpenViking + Ollama 健康；当前 embedding 配置；切换 model 入口 |
| `OpenVikingSyncJobsCard.tsx` | 进行中 / 等待 / 失败任务列表；ETA；手动重试入口 |
| `OpenVikingEventStream.tsx` | 时间倒序事件流；按 event_type 筛选；error/warning 高亮 |
| `OpenVikingMetricsCard.tsx` | 最近 5 分钟 throughput / avg latency / breaker trips |

视觉沿用 v1.0.4 opencode 卡片样式；失败提示沿用 v1.0.3 ui-feedback 规则（居中弹窗）。

### 13.5 配置项

仪表盘相关的 settings 字段（progress sweep / scheduled refresh / event retention）已统一并入 §10 配置项表。

### 13.6 调优面板

PRD §10.4 / §10.5 规定 admin 必须能通过仪表盘**调参数 + 看效果**。SDD 实现：

#### 13.6.1 前端组件

新增 `OpenVikingTuningCard.tsx`：

- 顶部显示当前主机识别结果（CPU 核数 / GPU / OpenViking 模式）+ 推荐预设（PRD §10.5.4 表查的那一行）
- 参数列表（按 scope 分组）：
  - **OpenViking 端**：每项一行，左侧当前值，右侧输入框 + 应用按钮
  - **Ollama 端**：当前推断值 + 推荐值 + "复制 systemd snippet" 按钮
  - **CodeAsk 端**：同 OpenViking，但应用是秒级生效
- "应用推荐预设"快捷按钮：一次性把整组参数填入（仅 OpenViking + CodeAsk，不动 Ollama）
- "回滚上一次变更"按钮：从 `OpenVikingTuningSetting` 取 `previous_value` 恢复
- 改完任一参数 → 弹出确认框（提示中断时长）→ 应用 → restart → 进度条等 30 s baseline 稳定

#### 13.6.2 调优 API

新增（详见 Phase 1 §7.1.4）：

```text
GET  /api/admin/openviking/tuning              # 当前所有 scope 的生效配置 + 推荐预设
GET  /api/admin/openviking/tuning/preset       # CodeAsk 自动识别的主机规格 + 推荐预设
POST /api/admin/openviking/tuning              # 改一个或多个参数
POST /api/admin/openviking/tuning/rollback     # 回滚某个 scope.key 到上一版
POST /api/admin/openviking/tuning/apply_preset # 一次应用推荐预设（不含 ollama_recommend）
GET  /api/admin/openviking/tuning/history?scope=...&key=...&limit=...   # 历史变更
GET  /api/admin/openviking/tuning/ollama_snippet  # 返回当前推荐的 systemd snippet 文本
```

#### 13.6.3 只展示当前事实数据

参数变更只发一条事件，记录改了什么；不做改前改后自动对比 snapshot（PRD §10.4）：

```text
admin POST /tuning  with {scope, key, value, notes?}
  ↓
emit_event(event_type="tuning_change",
           payload={
             scope, key,
             value_before, value_after,
             notes: str | null
           },
           outcome="info")
  ↓
写 DB → 重写 ov.conf（如 scope=openviking） → restart 相应进程
  ↓
返回 202
```

admin 通过观察仪表盘 `MetricsCard`（throughput / latency / breaker_trips，5 分钟滚动窗口）自然看到改后的状态。不需要后端跑 sleep + 异步 snapshot + 配对事件渲染。

如果未来确实需要趋势图，再补 `metrics_history` 时序表（PRD §10.3 已经声明历史趋势图不在第一版）。

#### 13.6.4 改 OpenViking 参数的 restart 流程

```python
async def apply_openviking_tuning(changes: list[TuningChange], admin_id: str):
    # 1. 校验：每条 change 都在合法 key 集合 + 取值范围内
    # 2. 写 DB（append-only 到 OpenVikingTuningSetting）
    # 3. 重新生成 ov.conf（读所有 scope=openviking 的最新 value）
    # 4. emit_event("tuning_change", payload={value_before, value_after, notes})
    # 5. process.restart()  # 关 + 起 OpenViking server
    # 6. 等 /health 通过 → emit_event("openviking_restart_completed")
    # 返回 202 + 估计中断时长
```

不破坏已有索引（不动 vectordb collection）。

#### 13.6.5 改 CodeAsk 参数

```python
async def apply_codeask_tuning(changes, admin_id):
    # 1. 校验
    # 2. 写 DB
    # 3. emit_event("tuning_change", payload={value_before, value_after, notes})
    # 4. 重启 APScheduler 相关 job（不重启进程）
    # 秒级生效；不需要等 health
```

#### 13.6.6 Ollama 端推荐值（不直接改）

```python
async def get_ollama_snippet() -> str:
    setting = read_latest(scope="ollama_recommend")
    return f"""
    # Add to /etc/systemd/system/ollama.service via:
    #   sudo systemctl edit ollama
    [Service]
    Environment="OLLAMA_NUM_PARALLEL={setting.num_parallel}"
    Environment="OLLAMA_NUM_THREAD={setting.num_thread}"

    # Then:
    #   sudo systemctl daemon-reload
    #   sudo systemctl restart ollama
    """
```

admin 应用后，**仪表盘自动探测**新值是否生效：

- 调 `GET /api/ps`（Ollama）观察当前 loaded model 的 context / processor，间接验证 NUM_THREAD
- 给 Ollama 发 N 个并发 embed 请求看是否真有并发（实测 latency 不雪崩 = NUM_PARALLEL 生效）
- 探测结果写入 `openviking_dashboard_events` 的 `ollama_settings_verified` 事件，outcome 标记是否符合 admin 之前请求的值

如果探测发现 admin 改的 systemd 没生效（比如忘了 daemon-reload），事件 outcome=warning，仪表盘提示。

#### 13.6.7 安全与审计

- 所有 tuning API 走 admin 权限通道（v1.0.3）
- 每条变更同时写 `audit_log` 与 `openviking_dashboard_events`
- 单次 `POST /tuning` 可批量改多个参数，但每个 (scope, key) 独立成事件，便于回滚
- 极端值（如 `max_concurrent=1000`）走后端 schema 校验拒绝，事件 outcome=error

### 13.7 不在第一版做的（PRD §10.3 已声明）

- 实时 WebSocket 推送
- Prometheus / OTel exporter
- 历史趋势图（用 sync_jobs.progress 时序数据 + tuning history 后续可补）
- 多 OpenViking 实例聚合
- **自动调参**（CodeAsk 根据指标自动改参数；v1.0.5 只做"建议 + admin 手动应用"，不自动）
- **改前改后自动对比**（v1.0.5 只发单条 `tuning_change` 事件；admin 通过 metrics 卡片自然观察改后状态；折线图作为未来历史趋势能力可补）
