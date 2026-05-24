# 03 服务器 & API (openviking/server)

## 1. 模块概览

`openviking/server/` 实现了基于 FastAPI 的 HTTP 服务器，提供完整的 REST API、认证体系和 MCP 端点。

| 文件/目录 | 用途 |
|---|---|
| `app.py` | FastAPI 应用工厂 + 生命周期管理 |
| `bootstrap.py` | 服务器启动入口 (`openviking-server`) |
| `config.py` | 服务器配置模型 (Host/Port/CORS/Workers) |
| `auth.py` | API Key + Bearer Token 认证中间件 |
| `identity.py` | 请求上下文 (RequestContext) 与身份模型 |
| `dependencies.py` | FastAPI 依赖注入 |
| `models.py` | 请求/响应 Pydantic 模型 |
| `responses.py` | 标准化 API 响应格式 |
| `error_mapping.py` | 异常 → HTTP 错误码映射 |
| `body_dump_middleware.py` | 请求体转储 (调试) |
| `local_input_guard.py` | 本地输入安全检查 |
| `telemetry.py` | 服务器遥测集成 |
| `temp_upload_store.py` | 临时上传文件存储 |
| `mcp_endpoint.py` | MCP (Model Context Protocol) 端点 |
| `routers/` | 15 个路由模块 |
| `api_keys/` | API Key 管理 (legacy + new) |
| `oauth/` | OAuth2 认证流 |

---

## 2. app.py - 应用工厂

### 2.1 ServerConfig

```python
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 1933
    workers: int = 1
    cors_origins: List[str] = ["*"]
    enable_admin: bool = False
    enable_bot: bool = False
    enable_console: bool = False
    log_level: str = "info"
```

### 2.2 应用创建

```python
def create_app(config, service, viking_db, queue_manager, ...) -> FastAPI:
    # 1. 初始化所有单例 (VikingFS, LockManager, QueueManager...)
    # 2. 注册中间件 (CORS, 认证, 遥测, 请求日志)
    # 3. 挂载所有路由模块
    # 4. 配置生命周期处理器 (startup/shutdown)
    # 5. 可选: 挂载 VikingBot 网关, Web 控制台
```

### 2.3 生命周期

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup:
    # - 初始化 VikingFS
    # - 启动 QueueManager 守护线程
    # - 恢复 RedoLog 中的崩溃任务
    # - 启动 WatchScheduler
    # - 启动指标采集
    
    yield
    
    # Shutdown:
    # - 停止 QueueManager (5s 排空超时)
    # - 刷新指标
    # - 关闭 VikingDB 连接
    # - 等待活跃请求完成
```

---

## 3. 路由体系 (routers/)

### 3.1 路由模块一览

| 路由文件 | API 前缀 | 核心端点 |
|---|---|---|
| `resources.py` | `/api/v1/resources` | POST add_resource, POST add_skill, GET/POST reindex, POST build_index, POST summarize |
| `filesystem.py` | `/api/v1/fs` | GET ls/tree/stat, POST mkdir/write, DELETE rm, POST mv, GET read/abstract/overview |
| `search.py` | `/api/v1/search` | POST find, POST search |
| `content.py` | `/api/v1/content` | GET read, POST grep, POST glob |
| `sessions.py` | `/api/v1/sessions` | CRUD sessions, POST messages, POST commit, GET context/archive |
| `admin.py` | `/api/v1/admin` | Accounts CRUD, Users CRUD, Agents, Roles, API Keys |
| `system.py` | `/api/v1/system` | GET status, GET health, POST wait, GET/POST consistency |
| `metrics.py` | `/api/v1/metrics` | Prometheus /metrics 端点 |
| `observer.py` | `/api/v1/observer` | GET observer state for all components |
| `relations.py` | `/api/v1/relations` | GET list, POST link, DELETE unlink |
| `tasks.py` | `/api/v1/tasks` | GET task status, GET list |
| `pack.py` | `/api/v1/pack` | POST export/backup/import/restore |
| `bot.py` | `/api/v1/bot` | VikingBot 网关代理 |
| `console.py` | `/console/api/v1` | Web 控制台 BFF 端点 |
| `debug.py` | `/api/v1/debug` | 调试端点 |
| `webdav.py` | `/api/v1/webdav` | WebDAV 协议支持 |
| `stats.py` | `/api/v1/stats` | 统计聚合端点 |
| `privacy_configs.py` | `/api/v1/privacy` | 隐私配置 CRUD |

### 3.2 资源路由 (resources.py)

```
POST /api/v1/resources
  添加资源: {path, to, parent, reason, instruction, wait, timeout, build_index, summarize, watch_interval}
  → {task_id, uri, status}

POST /api/v1/resources/skills
  添加技能: {data, wait, timeout}
  → {task_id, uri, status}

POST /api/v1/resources/reindex
  重索引: {uri, mode (summary/index/all), wait}

POST /api/v1/resources/build_index
  构建索引: {resource_uris: [...]}

POST /api/v1/resources/summarize
  生成摘要: {resource_uris: [...]}
```

### 3.3 文件系统路由 (filesystem.py)

```
GET  /api/v1/fs/ls?uri=viking://resources/&simple=true&recursive=false
GET  /api/v1/fs/tree?uri=...&node_limit=100
GET  /api/v1/fs/stat?uri=...
GET  /api/v1/fs/read?uri=...&offset=0&limit=-1
GET  /api/v1/fs/abstract?uri=...
GET  /api/v1/fs/overview?uri=...
POST /api/v1/fs/mkdir  {uri, description}
POST /api/v1/fs/write  {uri, content, mode (create/replace/append), wait, timeout}
POST /api/v1/fs/mv     {from, to}
DELETE /api/v1/fs?uri=...&recursive=false
```

### 3.4 搜索路由 (search.py)

```
POST /api/v1/search/find
  {query, target_uri, limit, score_threshold, filter, since, until, time_field, level}
  → {results: [{uri, score, context_type, level, abstract, overview, content}]}

POST /api/v1/search/search
  {query, target_uri, session_id, limit, score_threshold, filter, ...}
  → 结合会话上下文的增强搜索
```

### 3.5 会话路由 (sessions.py)

```
POST   /api/v1/sessions             创建会话: {session_id}
GET    /api/v1/sessions             列出会话
GET    /api/v1/sessions/{id}        获取会话详情
DELETE /api/v1/sessions/{id}        删除会话
POST   /api/v1/sessions/{id}/messages    添加消息
POST   /api/v1/sessions/{id}/commit      提交会话 (触发记忆提取)
GET    /api/v1/sessions/{id}/context      获取汇编上下文
GET    /api/v1/sessions/{id}/archive/{aid} 获取存档
GET    /api/v1/tasks/{task_id}            获取提交任务状态
```

---

## 4. auth.py - 认证体系

### 4.1 API Key 认证

```python
class APIKeyAuth:
    """验证 X-API-Key 或 Authorization: Bearer 头部"""
    
    # 支持两种密钥类型:
    # - root API key: 完全管理权限
    # - user API key:  限定用户/Agent 作用域
    
    # 认证中间件:
    # 1. 提取密钥 (Header / Query / Cookie)
    # 2. 查询密钥存储 (LegacyKeyStore 或 NewKeyStore)
    # 3. 验证账号/用户/Agent 权限
    # 4. 构建 RequestContext 注入请求
```

### 4.2 OAuth2 认证

```python
# OAuth2 授权码流程 + PKCE:
# GET  /api/v1/auth/oauth/authorize    → 重定向到 IdP
# POST /api/v1/auth/oauth/token        → 交换授权码获取 Token
# POST /api/v1/auth/oauth/refresh      → 刷新 Token
# GET  /api/v1/auth/oauth/userinfo     → 获取用户信息

# 支持的提供商:
# - Google, GitHub, GitLab, Microsoft, ...
# - 自定义 OAuth2 提供商
```

### 4.3 OTP 认证

```python
# 一次性密码 (OTP) 认证:
# POST /api/v1/auth/otp
#   {email} → 发送 OTP 到邮箱
# POST /api/v1/auth/otp/verify
#   {email, otp} → 验证并返回临时 API Key
```

---

## 5. identity.py - 请求上下文

### 5.1 RequestContext

```python
@dataclass
class RequestContext:
    """注入到每个请求的上下文对象"""
    user: UserIdentity           # 用户标识 (user_id, agent_id, account_id)
    role: Role                   # ROOT / ADMIN / USER
    request_id: str              # 请求追踪 ID
    telemetry: Optional[TelemetryContext]  # 遥测上下文
    agent_ids: List[str]         # 关联的 Agent ID 列表
    
    # 派生属性:
    # - is_root: 是否为 ROOT 角色
    # - is_admin: 是否为 ADMIN 角色
    # - account_id: 租户 ID
```

### 5.2 Role 枚举

```python
class Role(str, Enum):
    ROOT = "root"        # 超级管理员 (跨租户)
    ADMIN = "admin"      # 租户管理员
    USER = "user"        # 普通用户
```

### 5.3 UserIdentity

```python
@dataclass
class UserIdentity:
    user_id: str         # 用户 ID
    agent_id: str        # Agent ID
    account_id: str      # 租户 ID
    role: Role           # 角色
```

---

## 6. mcp_endpoint.py - MCP 端点

### 6.1 MCP 协议支持

```python
# Model Context Protocol 端点:
# POST /mcp
#   Header: Mcp-Session-Id: <session_id>
#   Body: JSON-RPC 2.0 消息

# 支持的 MCP 方法:
# - tools/list:      列出可用的 OpenViking 工具
# - tools/call:      调用指定的 OpenViking 工具
# - resources/list:  列出可访问的资源
# - resources/read:  读取资源内容
# - prompts/list:    列出提示词模板
# - prompts/get:     获取特定提示词
```

### 6.2 MCP 工具映射

OpenViking 操作通过 MCP 暴露为工具:
- `ov_search` → `tools/call`
- `ov_browse` → `tools/call`
- `ov_read` → `tools/call`
- `ov_write` → `tools/call`
- `ov_add_resource` → `tools/call`
- ...

---

## 7. error_mapping.py - 错误映射

| 异常类 | HTTP 状态码 | 说明 |
|---|---|---|
| `NotFoundError` | 404 | URI 不存在 |
| `ConflictError` | 409 | URI 已存在 |
| `PermissionDeniedError` | 403 | 权限不足 |
| `ValidationError` | 422 | 参数验证失败 |
| `StorageException` | 500 | 存储层错误 |
| `LockError` | 423 | 资源被锁定 |
| `EncryptionError` | 500 | 加密/解密失败 |
| `CollectionNotFoundError` | 404 | 向量集合不存在 |
| `EmbeddingConfigurationError` | 500 | 嵌入配置错误 |

---

## 8. 标准化响应格式

```json
{
  "status": "success",
  "data": { ... },
  "meta": {
    "request_id": "req_xxx",
    "time_cost_ms": 42.5
  }
}

// 错误:
{
  "status": "error",
  "error": {
    "code": "NOT_FOUND",
    "message": "URI not found: viking://resources/xxx",
    "details": {}
  }
}
```

---

## 9. console/ - Web 控制台

### 9.1 控制台代理架构

```
浏览器 → console:8020 → 代理 → OpenViking:1933
         (静态文件)    (BFF)
```

### 9.2 ConsoleConfig

```python
@dataclass
class ConsoleConfig:
    host: str = "127.0.0.1"
    port: int = 8020
    openviking_base_url: str = "http://127.0.0.1:1933"
    write_enabled: bool = False       # 是否允许写操作
    request_timeout_sec: float = 30.0
    cors_origins: List[str] = ["*"]
```

### 9.3 运行时能力

```python
# GET /console/api/v1/runtime/capabilities
{
  "write_enabled": true,
  "allowed_modules": ["fs.read", "search.find", "fs.write", "admin.write", ...],
  "dangerous_actions": ["fs.mkdir", "fs.mv", "fs.rm", "admin.create_account", ...]
}
```

### 9.4 安全门控

- 路径遍历防护: 拒绝 `..` 和绝对路径
- 写入门控: `write_enabled=False` 时返回 403
- 参数验证: 所有路径参数过滤特殊字符
