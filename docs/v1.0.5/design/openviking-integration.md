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
    ├── config.py           # ov.conf 生成；从 CodeAsk settings 派生
    ├── process.py          # OpenViking server 生命周期（参考 opencode_compat/process.py）
    ├── client.py           # OpenViking HTTP / MCP 客户端封装
    ├── sync.py             # 同步引擎；wiki / report / repo 增量同步
    ├── uri.py              # CodeAsk 主数据 ↔ viking:// URI 映射
    ├── models.py           # OpenVikingSyncJob 等 SQLAlchemy 模型
    ├── health.py           # 健康检查、版本探测、Ollama 健康联动
    └── README.md           # 模块边界说明
```

```text
src/codeask/api/
└── openviking_status.py    # GET /api/admin/openviking/status 诊断接口
```

```text
alembic/versions/
└── XXXX_openviking_sync_jobs.py
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
| `frontend/src/components/settings/...` | admin 设置页新增 OpenViking 状态卡片 |
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
```

唯一约束：`(source_type, source_id)` 同时只允许一条非终态记录。

参考 anything-llm `DocumentSyncQueue` 设计：`maxRepeatFailures` 由 settings 控制；失败超过阈值标记 `cancelled` 并发审计事件。

### 3.2 不新增的字段

不在 `llm_configs` 上加任何 OpenViking 字段；不在 `sessions` 上加 OpenViking session 映射（OpenViking session 在 client.py 内部按 CodeAsk session_id 派生，不持久化）。

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
  "embedder": {
    "provider": "ollama",
    "base_url": "http://127.0.0.1:11434",
    "model": "<settings.openviking_embed_model>",
    "dimension": null
  },
  "vlm": {"enabled": false}
}
```

---

## 6. 同步引擎

`sync.py` 暴露：

- `enqueue(source_type, source_id, **meta)` —— 写 `openviking_sync_jobs(status=pending)`，由 hook / 后台 sweep 调用
- `run_pending_jobs(limit=N)` —— APScheduler 调用，按 `status=pending` + `next_retry_at <= now` 取任务
- `force_resync(source_type, source_id)` —— admin 手动触发

执行顺序（每个 job）：

1. 标 `running`、`attempts += 1`
2. 从 CodeAsk 主数据派生本地路径或文本
3. 调 `client.add_resource(path, parent=..., reason=..., instruction=...)`
4. 若 OpenViking 返回异步 task_id，记录后由后台 sweep 跟踪
5. 等待索引完成 → 写 `viking_uri`、`source_hash`、`last_indexed_at`，标 `indexed`
6. 失败 → 标 `failed`、记录 `error`、按指数退避更新 `next_retry_at`；超过 `maxRepeatFailures` 标 `cancelled`

并发：单进程内同步 worker 数受 `settings.openviking_sync_workers` 控制（建议默认 2）。

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

---

## 10. 配置项

`src/codeask/settings.py` 新增：

```python
class Settings:
    # OpenViking 进程
    openviking_bin: str = "openviking-server"
    openviking_host: str = "127.0.0.1"
    openviking_port: int = 1933
    openviking_keepalive_interval_seconds: int = 30
    openviking_startup_timeout_seconds: int = 30
    openviking_graceful_shutdown_seconds: int = 5
    openviking_verified_version: str | None = "0.3.17"

    # 同步
    openviking_sync_workers: int = 2
    openviking_sync_interval_seconds: int = 60
    openviking_sync_max_repeat_failures: int = 5

    # MCP
    openviking_mcp_token: str | None = None        # 留 None 自动生成

    # Embedding
    openviking_embed_provider: str = "ollama"
    openviking_embed_base_url: str = "http://127.0.0.1:11434"
    openviking_embed_model: str = "bge-m3"          # Phase 0 实测后可改

    # 数据目录
    openviking_data_dir: str = "{CODEASK_DATA_DIR}/openviking"
```

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
