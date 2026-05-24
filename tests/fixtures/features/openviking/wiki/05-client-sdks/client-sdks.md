# 05 客户端 SDK (openviking/client)

## 1. 模块概览

`openviking/client/` 和顶级客户端文件提供多种客户端接入方式，支持嵌入式(进程内)、HTTP、同步、异步四种模式。

| 文件 | 类 | 说明 |
|---|---|---|
| `client/local.py` | `LocalClient` | 进程内直接调用 (最快) |
| `client/session.py` | `Session` | 面向对象会话包装器 |
| `async_client.py` | `AsyncOpenViking` | 异步嵌入式单例客户端 |
| `sync_client.py` | `SyncOpenViking` | 同步外观 (包装 AsyncOpenViking) |
| `client.py` | - | 统一导出 (4 种客户端) |

HTTP 模式客户端由 `openviking_cli/client/` 提供:
| `openviking_cli/client/http.py` | `AsyncHTTPClient` | 异步 HTTP 客户端 |
| `openviking_cli/client/sync_http.py` | `SyncHTTPClient` | 同步 HTTP 客户端 |

---

## 2. AsyncOpenViking - 异步嵌入式客户端

```python
class AsyncOpenViking:
    """异步嵌入式模式, 线程安全单例 (双重检查锁定)"""
    
    _instance: Optional[AsyncOpenViking] = None
    _lock: threading.Lock
    
    def __init__(path=None, **kwargs):
        self._client = LocalClient(path=path)
        self.user = UserIdentifier.the_default_user()
    
    async def initialize()          # 惰性初始化
    async def close()
    @classmethod async def reset()  # 重置单例 (测试用)
    
    # 会话操作
    def session(session_id, must_exist=False) -> Session
    async def create_session(session_id, telemetry) -> Dict
    async def list_sessions() -> List
    async def get_session(session_id, auto_create=False) -> Dict
    async def get_session_context(session_id, token_budget) -> Dict
    async def delete_session(session_id)
    async def add_message(session_id, role, content, parts, ...) -> Dict
    async def commit_session(session_id, telemetry) -> Dict
    async def get_task(task_id) -> Optional[Dict]
    
    # 文件系统操作
    async def ls(uri, **kwargs) -> List
    async def tree(uri, **kwargs) -> Dict
    async def mkdir(uri, description) -> None
    async def stat(uri) -> Dict
    async def rm(uri, recursive) -> None
    async def mv(from_uri, to_uri) -> None
    async def abstract(uri) -> str
    async def overview(uri) -> str
    async def read(uri, offset=0, limit=-1) -> str
    async def write(uri, content, mode, wait, timeout, telemetry) -> Dict
    async def grep(uri, pattern, ...) -> Dict
    async def glob(pattern, uri) -> Dict
    
    # 搜索
    async def find(query, target_uri, limit, score_threshold, filter, ...)
    async def search(query, target_uri, session, session_id, ...)
    
    # 资源
    async def add_resource(path, to, parent, ...) -> Dict
    async def add_skill(data, wait, timeout, telemetry) -> Dict
    async def reindex(uri, mode, wait) -> Dict
    async def wait_processed(timeout) -> Dict
    async def build_index(resource_uris) -> Dict
    async def summarize(resource_uris) -> Dict
    
    # 关系
    async def relations(uri) -> List[Dict]
    async def link(from_uri, uris, reason) -> None
    async def unlink(from_uri, uri) -> None
    
    # 打包
    async def export_ovpack(uri, to, include_vectors) -> str
    async def backup_ovpack(to, include_vectors) -> str
    async def import_ovpack(file_path, parent, on_conflict, vector_mode) -> str
    async def restore_ovpack(file_path, on_conflict, vector_mode) -> str
    
    # 系统
    async def check_consistency(uri) -> Dict
    def get_status() -> SystemStatus
    def is_healthy() -> bool
    @property def observer() -> Any
    
    # 高级访问
    @property def _service() -> OpenVikingService
```

---

## 3. SyncOpenViking - 同步外观

```python
class SyncOpenViking:
    """同步外观, 使用 run_async() 桥接所有异步方法"""
    
    def __init__(**kwargs):
        self._async = AsyncOpenViking(**kwargs)
    
    # 所有方法与 AsyncOpenViking 名称相同但为同步版本
    # 内部调用 run_async(self._async.method(...))
    
    def initialize()           # 同步
    def session(session_id)    # 同步
    def add_resource(...)      # 同步
    def find(...)              # 同步
    # ... (全部 30+ 个方法)
```

---

## 4. LocalClient - 进程内客户端

```python
class LocalClient(BaseClient):
    """通过直接服务调用实现 (无网络序列化), 最快模式"""
    
    def __init__(path=None, user=None):
        self._service = OpenVikingService(...)
        self._ctx = RequestContext(...)
    
    async def initialize()
    async def close()
    
    # 实现 BaseClient 的所有抽象方法
    # 每个方法直接调用 _service 层
    
    # 额外方法:
    @property
    def service() -> OpenVikingService     # 暴露底层服务
    async def _create_session_impl(session_id) -> Dict
    async def _add_message_impl(session_id, role, content, parts, ...) -> Dict
```

### 辅助函数

```python
def _to_jsonable(value) -> Any:
    """递归转换内部对象为 JSON 可序列化"""
    # 处理: to_dict(), list, dict, datetime...

def _resolve_search_filter(filter, since, until, time_field) -> Optional[Dict]:
    """合并时间过滤条件"""
```

---

## 5. HTTP 客户端

### 5.1 AsyncHTTPClient

```python
class AsyncHTTPClient(BaseClient):
    """异步 HTTP/HTTPS 客户端"""
    
    def __init__(url, api_key=None, account=None, user=None, agent_id=None, timeout=60.0):
        self._http = httpx.AsyncClient(base_url=url, timeout=timeout, headers={...})
    
    # 实现 BaseClient 的所有异步方法
    # 每个方法 → HTTP 请求
```

### 5.2 SyncHTTPClient

```python
class SyncHTTPClient:
    """同步 HTTP 客户端, 包装 AsyncHTTPClient"""
    # 所有方法为同步版本, 内部使用 run_async()
```

---

## 6. Session 对象

```python
class Session:
    """面向对象会话包装器, 委托给底层客户端"""
    
    def __init__(client, session_id, user)
    
    async def add_message(role, content=None, parts=None, created_at=None, role_id=None) -> Dict
        # Part 对象 → dataclasses.asdict → client.add_message()
    
    async def commit(telemetry=None) -> Dict
    async def commit_async(telemetry=None) -> Dict
    async def delete() -> None
    async def load() -> Dict
    async def get_session_context(token_budget=None) -> Dict
    async def get_archive(archive_id) -> Dict
```

---

## 7. 消息模型 (openviking/message/)

### 7.1 Part 类型

```python
@dataclass
class TextPart:
    text: str
    type: Literal["text"] = "text"

@dataclass
class ContextPart:
    type: Literal["context"] = "context"
    uri: str                          # Viking URI
    context_type: Literal["memory", "resource", "skill"] = "memory"
    abstract: str = ""                # L0 摘要 (提示注入用)

@dataclass
class ToolPart:
    type: Literal["tool"] = "tool"
    tool_id: str = ""                 # 工具调用/结果 ID
    tool_name: str = ""               # 工具名称
    tool_uri: str = ""                # 会话中工具的 URI
    skill_uri: str = ""               # 所属技能的 URI
    tool_input: Optional[dict] = None # 输入参数
    tool_output: str = ""             # 工具结果
    tool_status: str = "pending"      # pending|running|completed|error
    duration_ms: Optional[float] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None

Part = Union[TextPart, ContextPart, ToolPart]
```

### 7.2 Message

```python
@dataclass
class Message:
    id: str                           # 消息标识符
    role: Literal["user", "assistant"]
    parts: List[Part]
    role_id: Optional[str]            # 显式参与者 (user:alice, agent:bot1)
    created_at: str                   # ISO 时间戳
    
    @property
    def content -> str                # 快速访问第一个 TextPart
    @property
    def estimated_tokens -> int       # len/4 启发式估算
    
    def to_dict() -> dict             # JSONL 序列化
    @classmethod
    def from_dict(data) -> Message    # 反序列化 (含旧 content 字段兼容)
    
    # 便利构造器:
    @classmethod
    def create_user(content, msg_id=None, role_id=None) -> Message
    @classmethod
    def create_assistant(content, context_refs=None, tool_calls=None, ...) -> Message
    
    # Part 查询:
    def get_context_parts() -> List[ContextPart]
    def get_tool_parts() -> List[ToolPart]
    def find_tool_part(tool_id) -> Optional[ToolPart]
    
    def to_jsonl() -> str             # JSONL 行
```

---

## 8. 客户端选择指南

| 场景 | 推荐客户端 |
|---|---|
| Python 应用嵌入式使用 | `AsyncOpenViking` |
| 同步脚本/REPL | `SyncOpenViking` |
| 远程服务器连接 | `AsyncHTTPClient` / `SyncHTTPClient` |
| 单元测试 | `InMemoryOpenVikingClient` (integrations/langchain/testing.py) |
| 快速原型 | `SyncOpenViking` |
