# OpenCode Agent Backend 系统设计

> 版本：v1.0.4
> 状态：Draft
> 关联：[交互流程规格](../specs/opencode-interaction-flow.md) | [产品契约](../prd/opencode-backend.md)

---

## 1. 模块边界

### 1.1 新增模块

opencode 兼容代码放在 `src/codeask/agent/` 下，但必须作为独立兼容模块开发，不抽取通用 Agent backend 层。

> 命名建议使用 `opencode_compat`，避免 `opencode_compact` 与上下文压缩 compaction 混淆。如果最终确定使用 `opencode_compact` 拼写，只改目录名，不改变模块边界。

```text
src/codeask/agent/opencode_compat/
├── __init__.py
├── backend.py                  # OpenCodeCompat 主入口，连接 sessions/workspace/process/http/events
├── sessions.py                 # opencode 会话绑定、状态、恢复
├── config.py                   # opencode.json + AGENTS.md 生成
├── profiles.py                 # 少量 provider profile；不做 provider profile 缓存
├── process.py                  # opencode shared server 生命周期
├── http.py                     # opencode HTTP API 客户端
├── events.py                   # opencode 原始事件归档与前端事件映射
├── workspace.py                # 会话 workspace、Wiki 链接、附件目录
├── worktrees.py                # 调用现有 WorktreeManager，并把 worktree 暴露到 workspace
└── mcp/
    ├── __init__.py
    ├── server.py               # opencode 专用 MCP Server (StreamableHTTP transport)
    ├── auth.py                 # MCP Bearer token 校验
    └── tools/
        ├── __init__.py
        ├── get_feature_info.py
        ├── prepare_worktree.py
        ├── bind_session_features.py
        ├── list_session_attachments.py
        └── read_session_attachment.py
```

边界约束：

- 不新增 `AgentBackend Protocol`、`backend_router` 或跨 agent 的公共 backend 抽象。
- 不复用旧 `src/codeask/agent/chat_runtime/` 的 tool registry、prompt、上下文组装和阶段机。
- opencode MCP tools 在 `opencode_compat/mcp/tools/` 内独立实现；可以调用 CodeAsk 平台服务和已有基础设施，但不包装旧 Agent tools。
- 未来如果接入 Claude Code、ACP 或其它 agent 工具，应新增独立目录，例如 `src/codeask/agent/claude_code_compat/`，不与 `opencode_compat` 互相复用内部代码。

### 1.2 修改模块

| 现有文件 | 变更 |
|---------|------|
| `src/codeask/api/sessions.py` | 新增 `agent_backend` 选择逻辑 |
| `src/codeask/sessions/messages.py` | 对 v1.0.4 新会话调用 `opencode_compat`；不经过通用 backend router |
| `src/codeask/app.py` | 注册 MCP HTTP endpoint、生命周期 hook |
| `src/codeask/settings.py` | 新增 `open_code_port_range`、`open_code_idle_timeout` |
| `src/codeask/db/models/session.py` | 新增 `ExternalAgentSession` model |
| `frontend/src/features/sessions/` | 重新适配 opencode 事件流和 Agent 行动轨迹展示 |
| `alembic/versions/` | 新增 migration: external_agent_sessions 表 |

### 1.3 不改动模块

- `src/codeask/agent/chat_runtime/` — 保留为历史兼容代码，v1.0.4 新会话不回退使用
- `src/codeask/agent/stages/` — 保留，不新增引用
- `src/codeask/agent/tools.py` / `tool_models.py` — 保留为旧 runtime 内部实现，不作为 opencode MCP 工具来源
- `src/codeask/agent/opencode_compat/` 内部不得反向依赖上述旧 runtime 模块

### 1.4 前端改动边界

v1.0.4 不增加用户可见的 Agent Backend 选择项，但前端必须改动会话页：

- Agent 行动轨迹按 opencode 原始事件重新设计，不沿用旧 CodeAsk Agent 阶段链路。
- 工具卡片支持展开完整参数、输出摘要、错误详情、耗时和 backend 标识。
- MCP 工具和 opencode 内置工具统一展示，但保留来源区分。
- 失败提示必须使用居中弹窗；成功提示使用低密度居中浮层。
- 会话切换、页面切换和停止生成时，不允许出现标题变了但消息/轨迹仍停留在旧会话的状态。

### 1.5 模块实现确认

v1.0.4 实现前先固定每个模块的职责和验收边界，避免开发过程中重新引入旧 Agent runtime 或抽象公共 backend。

| 模块 | 职责 | 关键接口 / 数据 | 不做什么 | 最低测试 |
|---|---|---|---|---|
| `opencode_compat/__init__.py` | 暴露模块公共入口 | `OpenCodeCompat`, `create_opencode_compat(...)` | 不提供通用 backend registry | import smoke |
| `backend.py` | 串联 sessions、workspace、config、process、http、events，提供 `initialize_session/run_turn/cleanup_session/ensure_running` | `OpenCodeCompat`, `OpenCodeTurnContext` | 不实现通用 AgentBackend；不回退 native runtime | app lifespan + fake opencode 完整 run 集成 |
| `sessions.py` | 管理 CodeAsk session 与 opencode session/workspace 的绑定 | `ExternalAgentSession`, `get_by_session_id`, `upsert`, `mark_running`, `mark_error` | 不保存 opencode message 正文全文；正文仍由会话 turn 管理 | DB CRUD、恢复、删除级联 |
| `workspace.py` | 创建会话 workspace、附件目录、Wiki symlink，恢复被删 symlink | `prepare_workspace(session_id)`, `ensure_wiki_link`, `resolve_workspace_path` | 不复制整份 Wiki；不直接管理 git worktree | symlink 创建、删除恢复、路径越界拒绝 |
| `config.py` | 生成 workspace 级 `opencode.json` 和 `AGENTS.md` | provider 配置、MCP remote 配置、permission 配置、模型上下文提示 | 不从 URL / 模型名猜协议；不写 provider 缓存 | JSON schema 快照、OpenAI/Anthropic profile 生成 |
| `profiles.py` | 根据 CodeAsk LLM 协议选择少量已验证 profile | `openai-compatible`, `anthropic-compatible-v1-bearer`, `anthropic-default` | 不做厂商特判；不做成功 profile 持久化缓存 | 9 条真实配置映射回归、未知协议失败 |
| `process.py` | 管理一个 shared `opencode serve` 常驻进程 | `ensure_server`, `restart`, `shutdown`, `healthcheck` | 不为每个会话默认起进程；per-session 只作为排障模式 | 端口分配、健康检查、换端口恢复 |
| `http.py` | 封装 opencode HTTP API | `POST /session`, `POST /session/:id/prompt_async`, `GET /session/:id/message`, `/global/event`, `abort/revert` | 不按 REST 直觉拼 `/messages` | fake server 集成 + 路径快照 |
| `events.py` | 归档 opencode 原始事件并映射前端事件 | raw JSONL、normalized event、tool/reasoning/status/error | 不复用旧 `scope_detection` 阶段事件 | event mapper 单测、sync 折叠、高频去噪 |
| `worktrees.py` | 调用现有 `WorktreeManager` 准备 session worktree 并暴露到 workspace | repo id/name、commit/branch、workspace relative link | 不重写 git worktree 管理；不复制仓库 | 真实 repo worktree smoke + 清理 |
| `mcp/server.py` | 提供 opencode remote MCP StreamableHTTP endpoint | initialize、tools/list、tools/call | 不单独起 MCP 进程；复用 FastAPI | MCP initialize/list/call 集成 |
| `mcp/auth.py` | 校验每个会话 MCP Bearer token | token/session/workspace 绑定 | 不接受无 token 调用 | token 正反例、跨会话拒绝 |
| `mcp/tools/*` | 提供 opencode 专用 CodeAsk 平台工具 | 特性信息、仓库准备、附件、绑定特性 | 不包装旧 Agent tools；不提供 Wiki/报告检索读取封装；不做业务语义判断 | 每个 tool handler 单测 + MCP 集成 |
| `frontend/src/features/sessions/*` | 展示 opencode 流式文本、行动轨迹、状态、错误和会话数据 | normalized opencode events、message snapshot、context metrics | 不展示旧 Agent 阶段流；不隐藏失败 | Vitest + Playwright E2E |

---

## 2. opencode 兼容入口

```python
from collections.abc import AsyncIterator

class OpenCodeTurnContext:
    session_id: str
    turn_id: str
    user_message: str
    history: list[SessionMessage]
    attachments: list[AttachmentInfo]
    conversation_summary: str | None
    tool_action_summary: dict[str, Any] | None
    subject_id: str | None
    features: list[FeatureInfo]          # 活跃特性列表
    feature_repos: dict[int, list[RepoInfo]]  # 特性->仓库映射
    repositories: list[RepoInfo]         # 用户可访问仓库列表，用于显式仓库请求
    bound_features: list[int]            # 会话已绑定特性
    wiki_workspace_path: str             # wiki 目录绝对路径
    codeask_mcp_token: str               # MCP 认证 token

class OpenCodeCompat:
    async def initialize_session(self, session_id: str, llm_config: LLMConfig) -> ExternalAgentSession: ...
    async def run_turn(self, ctx: OpenCodeTurnContext) -> AsyncIterator[ChatRuntimeEvent]: ...
    async def cleanup_session(self, session_id: str) -> None: ...
    async def ensure_running(self, session_id: str) -> ExternalAgentSession: ...
```

v1.0.4 不建立通用 AgentBackend 抽象。`OpenCodeCompat` 是 opencode 专用入口，只服务 `src/codeask/agent/opencode_compat/`。选择失败应返回明确错误，不静默回退 native runtime。

---

## 3. 数据模型

### 3.1 ExternalAgentSession (SQLAlchemy)

```python
class ExternalAgentSession(Base, TimestampMixin):
    __tablename__ = "external_agent_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    backend_type: Mapped[str] = mapped_column(String(32), nullable=False)
    external_session_key: Mapped[str] = mapped_column(String(128), nullable=False)
    session_dir: Mapped[str] = mapped_column(String(512), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=True)
    pid: Mapped[int] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="starting")
    config_hash: Mapped[str] = mapped_column(String(64), nullable=True)
    config_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    session: Mapped[Session] = relationship("Session", back_populates="external_agent")
```

### 3.2 Alembic Migration

```python
# alembic/versions/XXXX_external_agent_sessions.py

def upgrade():
    op.create_table(
        "external_agent_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(64), sa.ForeignKey("sessions.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("backend_type", sa.String(32), nullable=False),
        sa.Column("external_session_key", sa.String(128), nullable=False),
        sa.Column("session_dir", sa.String(512), nullable=False),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("pid", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="starting"),
        sa.Column("config_hash", sa.String(64), nullable=True),
        sa.Column("config_json", sa.JSON(), nullable=True),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
```

---

## 4. Wiki 文件工作区

### 4.1 持久化目录

CodeAsk 维护一个持久化 Wiki 文件工作区，供所有 opencode 会话通过文件系统读取：

```text
<CODEASK_DATA_DIR>/wiki_workspace/current/
├── _manifest.json
├── <feature-name-or-slug>/
│   ├── index.md
│   ├── <wiki-dir>/
│   ├── <wiki-doc>.md
│   └── <wiki-doc>.assets/
└── ...
```

`WikiWorkspaceExporter` 负责从 CodeAsk Wiki 数据模型导出该目录：

- 特性是一级目录。
- 特性下的目录和文档结构与当前特性 Wiki 树一致。
- Markdown 文件名优先使用用户可见标题；必要时做文件系统安全转义。
- 静态资源保持 Markdown 中可用的相对路径，例如 `Untitled.assets/image.png`。
- 每个特性目录生成 `index.md`，汇总该特性的 Wiki 入口、描述和目录树。
- 根目录生成 `_manifest.json`，记录 feature_id、feature_name、wiki_node_id、title、relative_path、updated_at。
- 导出动作由 Wiki 写入、删除、排序、导入完成等事件触发；会话创建时只读取现有工作区，不做全量导出。

### 4.2 会话挂载

会话 workspace 中的 Wiki 路径固定为：

```text
<session_dir>/workspace/wiki
```

挂载策略按优先级：

| 策略 | 说明 |
|---|---|
| symlink | 默认策略，创建 `workspace/wiki -> <CODEASK_DATA_DIR>/wiki_workspace/current`，无额外空间、准备时间最低 |
| bind mount | 可选策略，适合需要更强路径隔离的部署环境 |

不采用：

- 每会话复制整份 Wiki。
- 目录硬链接。Linux 通常不允许普通目录硬链接；如需近似快照，应后续单独设计 hardlink farm，但不作为 v1.0.4 第一版目标。

### 4.3 一致性规则

- v1.0.4 默认使用 live view：会话看到的是当前持久化 Wiki 工作区。
- 如果用户在 opencode 调查期间修改 Wiki，新读到的内容可能反映最新版本；这符合第一版产品取舍。
- Phase 0 已验证：删除 `workspace/wiki` symlink 不会删除真实 Wiki 工作区；后续 `opencode_compat/workspace.py` 可重新创建 symlink 恢复入口。
- 后续如需要会话级快照，可在 `wiki_workspace/snapshots/<snapshot_id>/` 增加只读快照，但不能影响第一版零复制目标。

---

## 5. OpenCodeCompat 核心流程

### 5.1 initialize_session (阶段 0)

```python
class OpenCodeCompat:
    async def initialize_session(self, session_id: str, llm_config: LLMConfig) -> ExternalAgentSession:
        # 1. 创建会话数据目录
        session_dir = await self._dir_mgr.create(session_id)

        # 2. 挂载 wiki 目录 (默认 symlink；可配置 bind mount)
        await self._dir_mgr.mount_wiki(session_dir / "workspace" / "wiki")

        # 3. 生成 opencode.json
        config = self._config_gen.generate(session_id, llm_config)
        await self._config_gen.write(session_dir / "config" / "opencode.json", config)

        # 4. 生成 AGENTS.md
        agents_md = self._config_gen.generate_agents_md(session_id)
        await self._config_gen.write(session_dir / "workspace" / "AGENTS.md", agents_md)

        # 5. 生成 MCP token
        mcp_token = secrets.token_urlsafe(32)
        await self._mcp_auth.store(session_id, mcp_token)

        # 6. 分配端口
        port = self._port_allocator.allocate()

        # 7. 确保 shared opencode server 常驻进程可用
        server = await self._process.ensure_server()

        # 8. 在当前 workspace 下创建 opencode session
        opencode_sid = await self._http.create_session(
            server.base_url,
            directory=str(session_dir / "workspace"),
        )

        # 9. 写入 DB
        ext_session = ExternalAgentSession(
            session_id=session_id,
            backend_type="opencode",
            external_session_key=opencode_sid,
            session_dir=str(session_dir),
            port=server.port,
            pid=server.pid,
            status="active",
            config_hash=self._compute_config_hash(session_id, llm_config),
            config_json=config,
        )
        await self._store.save(ext_session)
        return ext_session
```

### 5.2 run (阶段 1-2)

```python
async def run_turn(self, ctx: OpenCodeTurnContext) -> AsyncIterator[ChatRuntimeEvent]:
    ext_session = await self._store.get(ctx.session_id)
    await self.ensure_running(ctx.session_id)

    # 1. 组装 system context
    system_context = await self._assemble_context(ctx)

    # 2. 通过 prompt_async 发送消息到 opencode，所有请求都带 directory
    await self._http.prompt_async(
        base_url=ext_session.server_url,
        session_key=ext_session.external_session_key,
        directory=ext_session.workspace_dir,
        system=system_context,
        text=ctx.user_message,
    )

    # 3. 消费 /global/event，并按 directory + sessionID 归属
    async for sse_event in self._events.consume_global(ext_session.server_url):
        codeask_event = self._events.map(sse_event, ext_session)
        yield codeask_event

        # 更新 last_active_at
        await self._store.touch(ext_session.id)
```

### 5.3 ensure_running (阶段 5)

```python
async def ensure_running(self, session_id: str) -> ExternalAgentSession:
    ext_session = await self._store.get(session_id)

    # 检查进程是否存活
    if self._proc_mgr.is_alive(ext_session.pid):
        return ext_session

    # 获取最新 LLM 配置
    llm_config = await self._llm_gateway.get_session_config(session_id)
    new_hash = self._compute_config_hash(session_id, llm_config)

    # 配置变更 → 重新生成 opencode.json
    if new_hash != ext_session.config_hash:
        await self._config_gen.write(
            Path(ext_session.session_dir) / "config" / "opencode.json",
            self._config_gen.generate(session_id, llm_config),
        )
        ext_session.config_hash = new_hash

    # 重新启动进程
    port = self._port_allocator.allocate()
    proc, port = await self._proc_mgr.start(
        session_id, Path(ext_session.session_dir), llm_config, port
    )

    # 验证 opencode session 仍存在
    exists = await self._http.get_session(port, ext_session.external_session_key)
    if not exists:
        # 极端情况：SQLite 文件被删，重建 session
        ext_session.external_session_key = await self._http.create_session(port, ...)

    ext_session.port = port
    ext_session.pid = proc.pid
    ext_session.status = "active"
    await self._store.save(ext_session)
    return ext_session
```

---

## 6. opencode server 形态

v1.0.4 需要通过 Phase 0 spike 验证 opencode server 的真实运行模型后再最终定稿。`specs/opencode-1.14.48-phase0-spike.md` 已确认 opencode 1.14.48 的 HTTP server、`prompt_async`、`/global/event`、MCP local、SQLite 恢复、shared server 三会话并发、shared server 多 workspace provider 配置隔离以及 shared server 多 workspace remote MCP endpoint/token 隔离可用。ACP 已做探索性验证，但当前版本暂不考虑；`abort + revert` 深度回滚作为遗留增强项，不阻塞主功能。

| 方案 | 说明 | 优点 | 风险 |
|---|---|---|---|
| 每会话一个 opencode server 进程 | 每个 CodeAsk session 启动独立 `opencode serve`，独立 HOME/config/SQLite/workspace | 隔离最强、API key 和上下文不串、排障简单 | 资源占用高，需进程上限和空闲清理 |
| 共享 opencode server，多 opencode session | 一个 server 承载多个 opencode session，CodeAsk 为每个会话准备独立 workspace，并在 workspace 内写入独立 `opencode.json` | 资源占用低、启动快；已实测不同 workspace 可读取不同 provider、MCP 配置和 MCP token，三会话并发 smoke 通过 | 仍需验证长期运行资源回收和更高并发稳定性 |

Phase 0 实测已经证明 shared server 可以同时承载多个 session，并且可以按 `directory` 读取不同 workspace 下的 `opencode.json`。provider 配置、MCP 配置、MCP token 和工具列表均已验证可按 workspace 隔离。因此 v1.0.4 后续实现应优先按 shared server 方向设计，但保留 per-session server 作为排障/回退模式。

必须验证的问题：

- 一个 opencode server 是否可以同时服务多个 session：已通过三会话并发 smoke。
- 多 session 是否能使用不同 LLM 配置和不同 MCP token：已通过 workspace 级 provider 与 remote MCP token 隔离测试。
- server 级 HOME/config 是否会导致认证、provider、MCP 或历史上下文串用：当前 Phase 0 未发现串用；长期运行和更高并发仍需在实现阶段 E2E 观察。
- `prompt_async` 与 `/global/event` 是否比同步 `/message` + `/event` 更适合 CodeAsk。
- `abort + revert` 是否按 session 隔离。此项列入遗留增强，不作为主功能硬前置。
- CodeAsk HTTP client 必须使用 opencode 1.14.48 的真实消息路径：消息列表是 `GET /session/:sessionID/message`，单条消息是 `GET /session/:sessionID/message/:messageID`，不是 `/messages`。

当前实测倾向：

- 主路径使用 `prompt_async` + `/global/event`。
- `opencode run --format json` 可用于 CLI smoke，但不适合作为 CodeAsk 集成主验证路径；真实集成以 HTTP event + SQLite/session API 为准。
- remote MCP 主路径已验证：`opencode.json` 的 `mcp.<name>.url` 指向 MCP 根路径即可，headers 会透传，opencode 会优先尝试 StreamableHTTP，并可完成 `tools/list` 与 `tools/call`。
- shared server 重启恢复已验证：同一数据目录和 workspace 下，重启后可读取原 session message，并继续第二轮 prompt。实现不应假设重启必须复用旧端口，端口可重新分配并更新会话记录。
- ACP 可行但当前版本暂不考虑，因为它通过 JSON-RPC over stdio 暴露 ACP update，事件语义与 opencode HTTP 原始事件不同。

---

## 7. MCP Server 实现

### 7.1 Transport

CodeAsk 在 FastAPI 中新增 MCP endpoint，实现 StreamableHTTP transport：

```python
# src/codeask/agent/opencode_compat/mcp/server.py

from mcp.server.lowlevel import Server
from mcp.server.streamable_http import StreamableHTTPServerTransport
from fastapi import Request, Response

router = APIRouter(prefix="/api/agent-mcp")

@router.post("/{session_id}/message")
async def mcp_message(session_id: str, request: Request):
    """StreamableHTTP POST endpoint"""
    transport = get_or_create_transport(session_id)
    return await transport.handle_request(request)

@router.get("/{session_id}/message")
async def mcp_sse(session_id: str, request: Request):
    """StreamableHTTP SSE endpoint (fallback)"""
    transport = get_or_create_transport(session_id)
    return await transport.handle_request(request)
```

### 7.2 Authentication

```python
async def mcp_auth(request: Request, session_id: str):
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401)
    token = auth_header[7:]
    expected = await mcp_token_store.get(session_id)
    if token != expected:
        raise HTTPException(status_code=403)
```

### 7.3 Tool Registration

```python
mcp_server = Server("codeask-agent-mcp")

@mcp_server.list_tools()
async def list_tools():
    return [
        Tool(name="list_features", description="...", inputSchema={...}),
        Tool(name="get_feature_info", description="...", inputSchema={...}),
        Tool(name="list_feature_repos", description="...", inputSchema={...}),
        Tool(name="prepare_worktree", description="...", inputSchema={...}),
        Tool(name="bind_session_features", description="...", inputSchema={...}),
        Tool(name="list_session_attachments", description="...", inputSchema={...}),
        Tool(name="read_session_attachment", description="...", inputSchema={...}),
    ]

@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict, context: RequestContext):
    session_id = context.session_id  # 从 URL 路径解析
    handler = tool_registry.get(name)
    return await handler(session_id, arguments)
```

### 7.4 MCP Tool 契约

MCP 工具不复用旧 CodeAsk Agent 工具实现，应按 opencode MCP 调用习惯重新实现。所有参数必须使用 JSON object，字段名稳定、简单、可被模型直接构造。

#### list_features

功能：列出当前用户可见的活跃特性，供模型判断问题边界。

输入：

```json
{
  "query": "可选，按名称/slug/描述模糊过滤",
  "limit": 50
}
```

输出：

```json
{
  "features": [
    {
      "feature_id": 1,
      "name": "小米",
      "slug": "xiaomi",
      "description": "小米病历与治疗记录",
      "wiki_path": "./wiki/小米/index.md",
      "repo_count": 0
    }
  ]
}
```

#### get_feature_info

功能：读取单个特性详情、Wiki 入口和仓库绑定。

输入：

```json
{
  "feature_id": 1,
  "slug": "可选，feature_id 不存在时使用",
  "name": "可选，feature_id/slug 不存在时使用"
}
```

输出：

```json
{
  "feature_id": 1,
  "name": "小米",
  "slug": "xiaomi",
  "description": "...",
  "wiki_path": "./wiki/小米/index.md",
  "repos": [
    {
      "repo_id": "repo_abc",
      "name": "payment-service",
      "default_ref": "main",
      "description": "..."
    }
  ]
}
```

#### list_feature_repos

功能：列出某个特性关联仓库；如果用户显式指定仓库但特性未确认，也可以用 `query` 搜索用户可访问仓库。

输入：

```json
{
  "feature_id": 1,
  "query": "可选，仓库名/描述过滤",
  "limit": 20
}
```

输出：

```json
{
  "repos": [
    {
      "repo_id": "repo_abc",
      "name": "payment-service",
      "default_ref": "main",
      "feature_ids": [1]
    }
  ]
}
```

#### prepare_worktree

功能：为指定仓库准备只读 worktree。模型可基于特性仓库绑定调用，也可在用户显式指定仓库时调用。

实现策略：复用现有 `codeask.code_index.worktree.WorktreeManager`，从 `<CODEASK_DATA_DIR>/repos/<repo_id>/bare` 创建 session-scoped worktree，再由 `opencode_compat/worktrees.py` 暴露到当前 opencode workspace 下。Phase 0 已用真实 repo `e35077cf009f4fdc` 验证 `ensure_worktree` 创建和 `destroy_worktree` 清理可行。

输入：

```json
{
  "repo_id": "repo_abc",
  "repo_name": "可选，repo_id 不存在时使用",
  "ref": "可选，默认使用仓库 default_ref",
  "reason": "模型为什么需要读取该仓库"
}
```

输出：

```json
{
  "path": "./payment-service/",
  "repo_id": "repo_abc",
  "repo_name": "payment-service",
  "ref": "main",
  "commit": "abc123def456",
  "readonly": true
}
```

#### bind_session_features

功能：模型确认会话涉及一个或多个特性后写入绑定。绑定不是代码检索的前置条件，可在多轮对话后发生。

输入：

```json
{
  "feature_ids": [1, 2],
  "reason": "为什么这些特性与当前会话相关"
}
```

输出：

```json
{
  "bound": [1, 2],
  "features": [
    {"feature_id": 1, "name": "小米", "slug": "xiaomi"}
  ]
}
```

#### list_session_attachments

功能：列出当前会话附件元数据和可读路径。

输入：

```json
{
  "query": "可选，按文件名/别名/描述过滤",
  "limit": 20
}
```

输出：

```json
{
  "attachments": [
    {
      "attachment_id": "att_123",
      "filename": "error.log",
      "display_name": "客户端日志",
      "description": "...",
      "path": "./attachments/error.log",
      "size": 12345,
      "mime_type": "text/plain"
    }
  ]
}
```

#### read_session_attachment

功能：读取无法直接用 opencode read 工具处理的附件文本内容或元数据；普通文本附件也可以直接 read `./attachments/`。

输入：

```json
{
  "attachment_id": "att_123",
  "max_chars": 12000
}
```

输出：

```json
{
  "attachment_id": "att_123",
  "filename": "error.log",
  "content": "...",
  "truncated": false
}
```

#### Wiki 与问题报告文件目录

opencode 运行时不提供独立的问题报告搜索/读取 MCP 工具。CodeAsk 将 Wiki 和问题报告导出到会话 workspace 的 `./wiki/<feature_slug>/` 下，由 opencode 使用自身的 `glob`、`grep`、`read` 工具访问。

每个特性目录结构固定为：

```text
./wiki/<feature_slug>/
├── README.md
├── knowledge-base/
│   └── *.md
└── problem-reports/
    ├── verified/
    │   └── *.md
    └── drafts/
        └── *.md
```

使用规则：

- `knowledge-base/` 是主知识库，回答特性知识时优先读取。
- `problem-reports/verified/` 是已验证问题定位报告，只作为参考证据；只有报错、场景、根因完全一致时，才能认为是同一个问题。
- `problem-reports/drafts/` 是草稿报告，只能作为弱背景，不能直接作为结论。
- 模型如果需要查报告，应先用 `glob/grep` 在 `./wiki/<feature_slug>/problem-reports/` 中定位，再用 `read` 读取具体 Markdown 文件。

---

## 8. opencode 事件流映射

v1.0.4 前端不沿用旧 CodeAsk Agent 阶段流。后端应尽量保留 opencode 原始事件语义，同时输出 CodeAsk 前端可稳定消费的结构：

```text
opencode raw SSE
  -> raw archive (stream.jsonl + DB event snapshot)
  -> normalized frontend event
  -> Agent 行动轨迹 UI
```

规范化事件类型建议：

| 类型 | 来源 | 前端用途 |
|---|---|---|
| `opencode_status` | session.status | busy/idle/retry/aborted |
| `opencode_text_delta` | message.part.delta | 聊天气泡流式文本 |
| `opencode_message_updated` | message.updated | 更新完整消息 parts |
| `opencode_tool_call` | tool part running | 行动轨迹工具开始 |
| `opencode_tool_result` | tool part completed/error | 行动轨迹工具结果 |
| `opencode_mcp_call` | MCP tool running | CodeAsk 平台工具开始 |
| `opencode_mcp_result` | MCP tool completed/error | CodeAsk 平台工具结果 |
| `opencode_error` | session.error / HTTP error | 居中弹窗错误 |
| `opencode_done` | idle + final response | 本轮完成 |

```python
# src/codeask/agent/opencode_compat/events.py

class OpenCodeEventMapper:
    def map(self, sse_event: dict, *, backend: str) -> ChatRuntimeEvent:
        event_type = sse_event.get("type")

        if event_type == "message.part.delta":
            delta = sse_event.get("data", {}).get("text_delta", "")
            return ChatRuntimeEvent(type="text_delta", data={"delta": delta})

        elif event_type == "message.updated":
            return self._map_message_updated(sse_event, backend)

        elif event_type == "session.status":
            status = sse_event.get("data", {}).get("status")
            if status == "idle":
                return ChatRuntimeEvent(type="done", data={})
            # busy → 不发送事件给前端

        elif event_type == "session.error":
            return ChatRuntimeEvent(
                type="error",
                data={"message": sse_event.get("data", {}).get("error")}
            )

    def _map_message_updated(self, event: dict, backend: str) -> ChatRuntimeEvent:
        parts = event.get("data", {}).get("parts", [])
        for part in parts:
            if part.get("type") == "tool_call":
                return ChatRuntimeEvent(
                    type="tool_call",
                    data={
                        "tool_call_id": part["id"],
                        "tool_name": part["name"],
                        "arguments_summary": part.get("arguments", {}),
                        "reason": None,
                        "backend": backend,
                    }
                )
            elif part.get("type") == "tool_result":
                return ChatRuntimeEvent(
                    type="tool_result",
                    data={
                        "tool_call_id": part["tool_call_id"],
                        "tool_name": part.get("name", ""),
                        "ok": part.get("is_error", False) is False,
                        "summary": part.get("result", "")[:200],
                        "backend": backend,
                    }
                )
```

---

## 9. LLM 与 opencode 配置

v1.0.4 不建立通用后端路由。会话发送主路径在确认使用 v1.0.4 opencode runtime 时，直接调用 `src/codeask/agent/opencode_compat/`。如果 LLM 配置协议暂不支持 opencode，直接返回明确错误，不回退旧 native runtime。

### 9.1 LLM provider 映射要求

Phase 0 使用 CodeAsk DB 中 9 条真实 LLM 配置做 opencode provider smoke matrix，结论如下：

- `openai` / `openai_compatible` 使用 `@ai-sdk/openai-compatible` 可通过。
- DeepSeek 的 `anthropic` endpoint 使用 `@ai-sdk/anthropic` 可通过。
- 火山的 `anthropic` endpoint 在 `@ai-sdk/anthropic` 映射下失败，错误为 401，实际请求 URL 为 `.../api/coding/messages`，网关提示缺少或错误 Authorization。
- 进一步测试发现：`@ai-sdk/anthropic` + `baseURL=<用户配置URL>/v1` + `headers.Authorization=Bearer <api_key>` 在火山 Anthropic GLM、火山 Anthropic MiniMax、DeepSeek Anthropic、DeepSeek Anthropic Pro 上均通过。

因此 `opencode_compat/config.py` 不应把 provider 映射写成不可调整的简单分支。第一版至少需要：

- 生成配置时保留 provider npm/baseURL/header 的 profile 扩展点。
- 会话启动失败时给出清晰错误，不能只暴露底层 401。
- “记录每个 LLM 配置最近一次 opencode smoke 状态和成功 profile”列为遗留增强项；主功能阶段先固定使用当前已验证的少量 profile 打通流程。

推荐初版 profile：

| profile | 适用 | opencode provider |
|---|---|---|
| `openai-compatible` | OpenAI 协议和 OpenAI-compatible 协议 | `@ai-sdk/openai-compatible`，使用用户原始 `base_url` |
| `anthropic-compatible-v1-bearer` | Anthropic 协议默认优先候选；已在当前火山、DeepSeek 真实 Anthropic 配置中全部通过 | `@ai-sdk/anthropic`，`baseURL=<base_url>/v1`，`Authorization: Bearer <api_key>` |
| `anthropic-default` | 标准 Anthropic-compatible endpoint，仅作为 fallback 或显式兼容项 | `@ai-sdk/anthropic`，使用用户原始 `base_url` |

profile 的选择不应通过厂商名硬编码，也不应把候选列表做成大量枚举。v1.0.4 初版原则：

- 每个协议候选尽量保持 1 个，确有实测差异时最多保留 2 个。
- 候选优先级由真实配置 smoke matrix 决定，优先选择“当前测试全部通过”的 profile。
- 除非有新的真实失败样本和通用抽象名称，否则不新增 provider/vendor 专属 profile。
- provider profile 测试结果持久化暂不进入主功能第一阶段，作为遗留增强项；后续可在配置测试入口中记录最近一次 opencode smoke 状态和错误摘要。

---

## 10. 生命周期管理

### 10.1 启动时

```python
# src/codeask/app.py

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 初始化 opencode 独立兼容模块
    app.state.opencode_compat = OpenCodeCompat(...)

    # 初始化 MCP server
    app.state.mcp_server = create_mcp_server()

    # 启动 shared opencode server 管理和清理定时任务
    app.state.cleanup_task = asyncio.create_task(
        periodic_cleanup(interval=300)  # 每 5 分钟检查
    )

    yield

    # 关闭时清理 shared opencode 进程
    await opencode_backend.shutdown_all()
```

### 10.2 定时清理任务

```python
async def periodic_cleanup(interval: int = 300):
    while True:
        await asyncio.sleep(interval)
        idle_sessions = await _get_idle_sessions(timeout_minutes=30)
        for session in idle_sessions:
            await opencode_backend.cleanup_session_resources(session.session_id)
```

shared server 是常驻资源，不因为单个会话闲置而关闭。定时清理只处理会话级临时资源：worktree、过期附件临时文件、事件缓冲和已删除会话目录。shared server 只有在 CodeAsk 退出、健康检查失败或管理员显式重启时关闭。

### 10.3 会话删除时

```python
async def on_session_deleted(session_id: str):
    ext = await external_session_store.get(session_id)
    if ext:
        await opencode_backend.cleanup_session(session_id)
        # 删除整个会话数据目录
        shutil.rmtree(Path(ext.session_dir), ignore_errors=True)
        await external_session_store.delete(ext.id)
```

---

## 11. 测试策略

| 层次 | 内容 | 工具 |
|------|------|------|
| 单元测试 | MCP tool handlers、event mapper、config generator、port allocator | pytest + mock |
| 集成测试 | OpenCodeCompat 完整流程 (使用 fake opencode HTTP server) | pytest + httpx |
| Phase 0 spike | 真实 opencode 版本 + 临时目录验证 server/message/event/MCP/permission/Wiki/worktree 主路径 | pytest + shell/httpx |
| 端到端 | 真实 opencode + 真实 LLM 的完整调查链路 | Playwright live E2E |
| 安全测试 | Token 泄漏检测、路径遍历、会话隔离 | pytest |

### 11.1 Fake OpenCode HTTP Server

集成测试使用 fake opencode HTTP server 模拟：

```python
class FakeOpenCodeServer:
    """模拟 opencode HTTP API，用于集成测试"""
    def __init__(self, port: int):
        self.port = port
        self.sessions: dict[str, list[dict]] = {}
        self.event_queue: asyncio.Queue = asyncio.Queue()

    async def start(self): ...

    # 实现 POST /session, POST /session/:id/message, GET /event
```

---

## 12. 配置项

```python
# src/codeask/settings.py 新增

class Settings:
    # opencode 进程
    opencode_bin: str = "opencode"                    # opencode 可执行文件路径
    opencode_port_range: str = "4200-4299"            # 端口范围
    opencode_idle_timeout_minutes: int = 30           # 空闲超时
    opencode_startup_timeout_seconds: int = 15        # 启动超时
    opencode_graceful_shutdown_seconds: int = 5       # 优雅终止等待
    opencode_verified_version: str | None = None      # 已验证 opencode 版本
    opencode_server_mode: str = "shared"              # shared | per_session (per_session 作为排障/回退模式)

    # 会话数据目录
    agent_sessions_root: str = "{CODEASK_DATA_DIR}/agent_sessions"
    wiki_workspace_root: str = "{CODEASK_DATA_DIR}/wiki_workspace/current"
    wiki_mount_mode: str = "symlink"                  # symlink | bind_mount

    # MCP
    mcp_token_length: int = 32                        # MCP bearer token 长度
```

---

## 13. 错误处理矩阵

| 错误场景 | 处理方式 | 用户可见 |
|---------|---------|---------|
| opencode bin 不存在 | 标记 backend unavailable，写入错误日志 | 居中弹窗：Agent 执行引擎不可用，请检查 opencode 安装 |
| 端口范围内无可用端口 | 返回 `资源繁忙` 错误 | 提示稍后重试 |
| opencode 启动超时 | 杀死进程，重试一次；再失败返回错误 | 居中弹窗：Agent 启动超时 |
| opencode 版本不在已验证范围 | 允许启动但记录 warning；可配置为阻止启动 | 管理员可见 warning |
| opencode 进程崩溃 | 标记 status=error，下次 ensure_running 时重启；当前 turn 返回错误 | 居中弹窗：Agent 进程异常退出 |
| MCP tool 调用超时 | 返回 error result 给 opencode，模型自行处理 | 可能出现在回答质量中 |
| opencode session 丢失 | 重建 session，注入历史摘要 | 丢失本轮上下文，但历史 turns 可通过 CodeAsk 恢复 |
| opencode DB 文件损坏 | 删除旧 DB，重建 session | 相当于新会话，但 CodeAsk turns 保留 |
