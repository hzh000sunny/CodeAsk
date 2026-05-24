# 04 服务层 (openviking/service)

## 1. 模块概览

`openviking/service/` 实现了业务逻辑服务层，是所有操作的核心编排层。

| 文件 | 类 | 说明 |
|---|---|---|
| `core.py` | `OpenVikingService` | 主服务入口, 组合所有子服务 |
| `resource_service.py` | `ResourceService` | 资源添加/索引/摘要/监控 |
| `fs_service.py` | `FSService` | 文件系统操作编排 |
| `search_service.py` | `SearchService` | 搜索/查找编排 |
| `session_service.py` | `SessionService` | 会话生命周期管理 |
| `relation_service.py` | `RelationService` | 关系链接管理 |
| `pack_service.py` | `PackService` | 导出/导入/备份/恢复 |
| `task_tracker.py` | `TaskTracker` | 异步任务追踪 |
| `task_store.py` | `TaskStore` | 任务持久化 |
| `reindex_executor.py` | `ReindexExecutor` | 重索引执行器 |
| `debug_service.py` | `DebugService` | 调试/观察者服务 |

---

## 2. OpenVikingService - 主服务

```python
class OpenVikingService:
    """将所有子服务组合为统一入口"""
    
    def __init__(config, vikingdb, viking_fs, queue_manager, ...):
        self.resources = ResourceService(...)
        self.fs = FSService(...)
        self.search = SearchService(...)
        self.sessions = SessionService(...)
        self.relations = RelationService(...)
        self.pack = PackService(...)
        self.debug = DebugService(...)
        self.task_tracker = TaskTracker(...)
    
    async def initialize()
    async def close()
```

---

## 3. ResourceService - 资源服务

```python
class ResourceService:
    """资源摄入与管理"""
    
    async def add_resource(
        path, to=None, parent=None,
        reason=None, instruction=None,
        wait=False, timeout=None,
        build_index=False, summarize=False,
        telemetry=None, watch_interval=None
    ) -> Dict:
        """
        1. DataAccessor.access(source) → LocalResource (临时文件)
        2. ParserRegistry.parse(temp_path) → ParseResult (文档树)
        3. TreeBuilder.finalize(parse_result) → BuildingTree (URI 映射)
        4. 写入 VikingFS + 入队 SemanticQueue
        5. 可选: 等待处理完成 (wait=True)
        6. 可选: 构建索引/生成摘要
        7. 可选: 注册 WatchTask (watch_interval)
        """
    
    async def add_skill(data, wait, timeout) -> Dict:
        """添加技能定义到 viking://agent/{id}/skills/"""
    
    async def reindex(uri, mode, wait) -> Dict:
        """重索引: summary/index/all"""
    
    async def build_index(resource_uris) -> Dict:
        """为指定资源构建向量索引"""
    
    async def summarize(resource_uris) -> Dict:
        """为指定资源生成摘要"""
```

---

## 4. FSService - 文件系统服务

```python
class FSService:
    """文件系统操作编排 (含加密/向量/关系)"""
    
    async def ls(uri, simple, recursive, output, abs_limit, show_all_hidden) -> List
        # 列表视图或完整视图
    
    async def tree(uri, output, abs_limit, show_all_hidden, node_limit) -> List[Dict]
        # 递归树视图, 含 L0 abstract
    
    async def stat(uri) -> Dict
        # 文件信息 + 向量计数
    
    async def mkdir(uri, description) -> None
        # 创建目录 (含多租户隔离)
    
    async def rm(uri, recursive) -> None
        # 删除 + 向量清理 + 级联选项
    
    async def mv(from_uri, to_uri) -> None
        # 移动/重命名 (cp + rm)
    
    async def read(uri, offset, limit) -> str
        # 读取 + 解密 (如已加密)
    
    async def write(uri, content, mode, wait, timeout, telemetry) -> Dict
        # 写入 + 加密 (如启用) + 语义入队
    
    async def abstract(uri) -> str
        # L0 摘要读取
    
    async def overview(uri) -> str
        # L1 概览读取
    
    async def grep(uri, pattern, case_insensitive, node_limit, exclude_uri, level_limit) -> Dict
        # 正则搜索 + 加密回退
    
    async def glob(pattern, uri) -> Dict
        # Glob 模式匹配
```

---

## 5. SearchService - 搜索服务

```python
class SearchService:
    """搜索与检索编排"""
    
    async def find(query, target_uri, limit, score_threshold, filter, ...) -> QueryResult:
        """通过 HierarchicalRetriever 进行语义搜索"""
    
    async def search(query, target_uri, session_id, ...) -> QueryResult:
        """通过 IntentAnalyzer 进行会话感知搜索"""
        # 1. 如果提供 session_id: 获取会话对象
        # 2. IntentAnalyzer.analyze() → QueryPlan
        # 3. HierarchicalRetriever.retrieve() → QueryResult
```

---

## 6. SessionService - 会话服务

```python
class SessionService:
    """会话生命周期管理"""
    
    async def create(session_id, telemetry) -> Dict
        # 1. 初始化用户/代理目录
        # 2. 创建 Session 对象
        # 3. 返回 {session_id, user}
    
    async def get(session_id) -> Dict
        # 加载会话 + 元数据
    
    async def sessions() -> List
        # 列出所有会话
    
    async def delete(session_id) -> None
        # 删除会话
    
    async def add_message(session_id, role, content, parts, ...) -> Dict
        # 添加消息到会话
    
    async def commit(session_id, telemetry) -> Dict
        # 触发两阶段提交 (存档 + 记忆提取)
    
    async def get_commit_task(task_id) -> Optional[Dict]
        # 查询提交任务状态
```

---

## 7. RelationService - 关系服务

```python
class RelationService:
    """上下文关系管理"""
    
    async def relations(uri) -> List
        # 获取 URI 的所有关联
    
    async def link(from_uri, to_uris, reason) -> None
        # 创建双向链接 (from ↔ to)
        # 支持关联原因描述
    
    async def unlink(from_uri, to_uri) -> None
        # 移除链接
```

---

## 8. PackService - 打包服务

```python
class PackService:
    """OVPack 导出/导入"""
    
    async def export_ovpack(uri, to, include_vectors) -> str
        # 1. 构建 manifest (文件系统 + 向量)
        # 2. 生成 index records
        # 3. 可选: 导出密集向量快照
        # 4. 打包为 ZIP
    
    async def backup_ovpack(to, include_vectors) -> str
        # 仅导出 public scopes
    
    async def import_ovpack(file_path, parent, on_conflict, vector_mode) -> str
        # 1. 读取 ZIP, 验证 manifest
        # 2. 解析根 URI
        # 3. 写入文件到 VikingFS
        # 4. 可选: 恢复向量或入队向量化
    
    async def restore_ovpack(file_path, on_conflict, vector_mode) -> str
        # 从备份恢复
```

---

## 9. TaskTracker & TaskStore

```python
class TaskTracker:
    """异步任务追踪器单例"""
    async def register(task_id, task_type) -> None
    async def update(task_id, status, progress, result) -> None
    async def get(task_id) -> Optional[Dict]
    async def list(status_filter, task_type_filter) -> List
    async def wait(task_id, timeout) -> Dict

class TaskStore:
    """任务持久化存储"""
    # 任务状态: pending → running → completed/failed
    # 持久化到 {workspace}/tasks/
```

---

## 10. DebugService

```python
class DebugService:
    """调试与观察者服务"""
    
    @property
    def observer() -> SystemObserver:
        """聚合所有组件观察者的系统观察器"""
        # 提供 system(), is_healthy() 方法
        # 聚合: Filesystem/Lock/Models/Queue/Retrieval/VikingDB 观察者
```

---

## 11. ReindexExecutor

```python
class ReindexExecutor:
    """重索引执行器"""
    
    async def execute(uri, mode) -> Dict:
        """
        mode:
          - summary:  重新生成 L0/L1 (Abstract/Overview)
          - index:    重新生成向量嵌入
          - all:      summary + index
        """
```

---

## 12. 服务间依赖图

```
OpenVikingService
├── ResourceService
│   ├── DataAccessor (parse/accessors)
│   ├── ParserRegistry (parse)
│   ├── TreeBuilder (parse)
│   ├── VikingFS (storage)
│   └── QueueManager (storage/queuefs)
├── FSService
│   ├── VikingFS (storage)
│   ├── FileEncryptor (crypto)
│   └── ContentWriteCoordinator (storage)
├── SearchService
│   ├── HierarchicalRetriever (retrieve)
│   ├── IntentAnalyzer (retrieve)
│   └── SessionService
├── SessionService
│   ├── Session (session)
│   ├── SessionCompressor (session)
│   └── TaskTracker
├── RelationService → VikingFS
├── PackService
│   ├── VikingFS
│   └── VikingVectorIndexBackend (storage)
├── DebugService → All Observers
└── TaskTracker → TaskStore
```
