# 06 存储层 (openviking/storage)

## 1. 模块概览

存储层是 OpenViking 最复杂的子系统，包含虚拟文件系统、向量数据库引擎、消息队列管道、分布式锁、导入导出和健康监控。

| 子模块 | 用途 | 核心文件 |
|---|---|---|
| VikingFS | 虚拟文件系统抽象 | `viking_fs.py`, `content_write.py` |
| Vectordb | 向量数据库 | `vectordb/`, `vectordb_adapters/`, `viking_vector_index_backend.py` |
| QueueFS | 语义处理管道 | `queuefs/` |
| OVPack | 导出/导入/备份/恢复 | `ovpack/` |
| Transaction | 分布式锁 + 崩溃恢复 | `transaction/` |
| Observers | 健康监控 | `observers/` |

---

## 2. VikingFS - 虚拟文件系统

### 2.1 核心类: VikingFS

```python
class VikingFS:
    """基于 AGFS 客户端的虚拟文件系统抽象"""
    
    # 文件操作
    async def read(uri, offset=0, limit=-1) -> str
    async def write(uri, content, mode) -> Dict       # mode: create/replace/append
    async def mkdir(uri, description=None) -> None
    async def rm(uri, recursive=False) -> None         # 含向量清理
    async def mv(from_uri, to_uri) -> None             # cp + rm
    async def stat(uri) -> Dict                        # 含向量计数
    async def exists(uri) -> bool
    async def glob(pattern, uri) -> Dict
    async def grep(uri, pattern, case_insensitive, node_limit, exclude_uri, level_limit) -> Dict
    
    # 层次化内容
    async def tree(uri, output, abs_limit, show_all_hidden, node_limit) -> List[Dict]
    async def abstract(uri) -> str                     # L0 摘要
    async def overview(uri) -> str                     # L1 概览
    
    # 语义搜索
    async def find(query, target_uri, ...) -> List     # 通过 HierarchicalRetriever
    async def search(query, target_uri, ...) -> List   # 通过 IntentAnalyzer
    
    # 关系
    async def link(from_uri, to_uris, reason) -> None
    async def unlink(from_uri, to_uri) -> None
    async def get_relations(uri) -> List
```

### 2.2 单例模式

```python
_viking_fs: Optional[VikingFS] = None

def init_viking_fs(agfs_client, ...) -> VikingFS
def get_viking_fs() -> VikingFS        # 未初始化时返回 NullVikingFS
```

### 2.3 内容写入协调器 (ContentWriteCoordinator)

```python
class ContentWriteCoordinator:
    """协调文件写入操作: 加锁 + 语义刷新 + 记忆序列化 + 等待完成"""
    
    async def create(uri, content, ...)  # 创建新文件
    async def replace(uri, content, ...) # 替换文件
    async def append(uri, content, ...)  # 追加文件
    
    # 内部方法:
    async def _create_and_write(...)
    async def _write_in_place(...)
    async def _write_direct_with_refresh(...)
    async def _write_memory_with_refresh(...)
    async def _rollback_direct_write(...)
```

---

## 3. 向量数据库引擎 (vectordb/)

### 3.1 架构层次

```
VikingVectorIndexBackend (多租户外观)
    └── _SingleAccountBackend (每租户)
        └── CollectionAdapter (抽象)
            ├── LocalCollectionAdapter    → LocalCollection + PersistCollection
            ├── HttpCollectionAdapter     → HttpCollection (远程服务)
            ├── VolcengineCollectionAdapter → VolcengineCollection (火山引擎)
            └── VikingDBPrivateCollectionAdapter → VikingDBCollection (私有部署)
```

### 3.2 集合系统

#### ICollection 抽象 (collection/collection.py)

```python
class ICollection(ABC):
    # 数据操作
    async def upsert_data(data_list) -> UpsertDataResult
    async def fetch_data(ids) -> FetchDataInCollectionResult
    async def delete_data(ids) -> None
    async def delete_all_data() -> None
    
    # 搜索
    async def search_by_vector(vector, limit, filters) -> SearchResult
    async def search_by_keywords(text, limit, filters) -> SearchResult
    async def search_by_id(id, limit, filters) -> SearchResult
    async def search_by_multimodal(texts, limit, filters) -> SearchResult
    async def search_by_random(limit, filters) -> SearchResult
    async def search_by_scalar(filters, order_by, limit) -> SearchResult
    
    # 索引管理
    async def create_index(meta) -> IIndex
    async def get_index() -> IIndex
    async def drop_index() -> None
    
    # 聚合
    async def aggregate_data(filters) -> AggregateResult
```

#### LocalCollection - 本地实现

- `VolatileCollection`: 内存索引 (测试用)
- `PersistCollection`: 磁盘持久化 (JSON 文件 + delta replay 恢复)

#### HttpCollection - HTTP 远程客户端

通过 HTTP API 调用远程 VikingDB 服务，支持 20+ API 端点。

### 3.3 索引系统 (index/)

#### IIndex 抽象

```python
class IIndex(ABC):
    async def upsert_data(delta_list) -> None
    async def delete_data(delta_list) -> None
    async def search(query_vector, limit, filters, sparse_raw_terms, sparse_values) -> Tuple[List[int], List[float]]
    async def aggregate(filters) -> Dict
    async def get_meta_data() -> Dict
    async def close() / drop()
```

#### PersistentIndex

- 版本化快照: `versions/` 目录 + `.write_done` 标记
- 恢复: 加载最新版本
- 清理: 移除旧版本

### 3.4 C++ 引擎后端 (vectordb/engine/)

#### 引擎变体选择

```python
# 优先级: 环境变量 OV_ENGINE_VARIANT / 自动检测
# x86: x86_sse3 → x86_avx2 → x86_avx512
# ARM: _native
# 回退: 纯 Python 实现 (_python_api.py)
```

#### abi3 桥接 (engine/_python_api.py)

```python
# build_abi3_exports() 构建:
# - Schema: 字段元数据管理 (FieldMeta, FieldType)
# - BytesRow: 二进制行序列化 (固定区 + 可变区)
# - IndexEngine: HNSW 向量索引 (search, add_data, delete_data, dump)
# - PersistStore: LevelDB 持久化 KV 存储
# - VolatileStore: 内存 KV 存储
```

**FieldType 枚举**: INT64, UINT64, FLOAT32, STRING, BINARY, BOOLEAN, LIST_INT64, LIST_STRING, LIST_FLOAT32

### 3.5 元数据系统 (meta/)

- `CollectionMeta`: 集合元数据 (主键, 字段定义, 向量化配置, 维度)
- `IndexMeta`: 索引元数据 (向量索引类型, 距离度量, 量化, HNSW 参数, 稀疏配置)

### 3.6 存储引擎 (store/)

- `StoreManager`: 三表管理 (Candidates C, Delta D, TTL T)
  - `add_cands_data()`: 写入候选 + 生成 delta
  - `delete_data()`: 删除候选 + 记录 delta
  - `fetch_cands_data()`: 按标签读取
  - `get_delta_data_after_ts()`: 增量重放
  - `expire_data()`: TTL 过期处理

---

## 4. QueueFS - 语义处理管道

### 4.1 管道流程

```
文件写入
    │
    ▼
SemanticQueue.coalesce()  ← 合并相同 URIs 的消息
    │
    ▼
SemanticProcessor.on_dequeue()
    │
    ├── 记忆目录 → _process_memory_directory()
    └── 资源/技能目录 → SemanticDagExecutor
                            │
                            ├── 文件摘要 (并行)
                            ├── 概览生成 (子节点完成后)
                            ├── 差异检测 (增量模式)
                            └── 嵌入消息生成
                                │
                                ▼
                            EmbeddingQueue
                                │
                                ▼
                            TextEmbeddingHandler
                                │
                                ▼
                            VikingVectorIndexBackend
```

### 4.2 关键类

#### NamedQueue

```python
class NamedQueue:
    """基于 AGFS 的命名队列, 至少一次投递语义"""
    async def enqueue(data) -> str
    async def dequeue() -> Tuple[str, Any]    # 标记 processing
    async def ack(msg_id)                     # 确认完成
    async def requeue(msg_id)                 # 重新入队
    async def peek() -> Optional[Tuple]
    def size() -> int
```

#### SemanticQueue

```python
class SemanticQueue(NamedQueue):
    """支持合并去重的语义队列"""
    # 45 秒窗口内相同 coalesce_key 的记忆写入自动去重
    # 合并: 递增版本号, is_semantic_coalesce_stale() 检查过期
```

#### SemanticDagExecutor

```python
class SemanticDagExecutor:
    """事件驱动的延迟调度 DAG 执行器"""
    # - 文件摘要并行处理
    # - 概览在子节点全部完成后生成
    # - 增量模式: 比较文件大小/内容检测变化
    # - 生命周期锁刷新循环
```

#### QueueManager

```python
class QueueManager:
    """管理 EmbeddedQueue + SemanticQueue 守护线程"""
    # std_queues: {EMBEDDING, SEMANTIC}
    # 并发控制: asyncio.Semaphore
    # 优雅关闭: 5s 排空超时
```

---

## 5. OVPack - 导出导入

### 5.1 格式 (v2)

```
{name}.ovpack  (ZIP 文件)
├── manifest.json              # 根清单
├── content/                   # 文件内容
│   ├── resources/
│   └── user/
├── index/                     # 索引记录 (JSONL)
│   └── index.jsonl
└── vectors/                   # 密集向量快照 (二进制)
    └── dense.bin
```

### 5.2 操作

```python
# 导出: 生成 ZIP + manifest + index + vectors
async def export_ovpack(uri, to, include_vectors=True) -> str

# 备份: 仅导出 public scopes
async def backup_ovpack(to, include_vectors=True) -> str

# 导入: 读取 ZIP, 验证 manifest, 写入文件 + 向量
async def import_ovpack(file_path, parent, on_conflict, vector_mode) -> str

# 恢复: 从备份恢复
async def restore_ovpack(file_path, on_conflict, vector_mode) -> str
```

### 5.3 作用域常量

```python
PUBLIC_SCOPES = (resources, user, agent, session)
IMPORTABLE_SCOPES
NON_VECTOR_SCOPES = {session}
```

---

## 6. Transaction - 分布式锁与崩溃恢复

### 6.1 锁系统

#### PathLockEngine (path_lock.py)

```python
class PathLockEngine:
    """基于文件系统的分布式锁"""
    
    # 锁文件:
    # 目录级: .path.ovlock          (TREE 锁)
    # 文件级: .exact.ovlock.{name}.{sha1}  (EXACT 锁)
    
    # Fencing Token:
    # {owner_id}:{timestamp_ns}:{E|T}
    # E = EXACT, T = TREE
    
    # 三种锁模式:
    async def acquire_exact(path) -> None      # 精确文件锁
    async def acquire_tree(path) -> None       # 目录树锁
    async def acquire_mv(src, dst) -> None     # 移动锁 (src TREE + dst EXACT)
    
    # 过期检测: 300s 默认
    # 活锁防护: (timestamp, owner_id) 字典序比较
    # 锁刷新: 重写时间戳
```

#### LockManager (lock_manager.py)

```python
class LockManager:
    """全局锁管理器单例"""
    
    async def acquire_exact_path(path) -> LockHandle
    async def acquire_tree(path) -> LockHandle
    async def acquire_tree_batch(paths) -> LockHandle    # 长度→字典序, 防死锁
    async def acquire_mv(src, dst) -> LockHandle
    async def refresh_lock(handle) -> None
    async def release(handle) -> None
    
    # 后台过期清理: 60s 间隔
    # RedoLog 恢复: _recover_pending_redo(), _redo_session_memory()
```

#### LockContext (lock_context.py)

```python
class LockContext:
    """异步上下文管理器, 支持 tree/exact/mv 模式"""
    async def __aenter__() -> LockHandle
    async def __aexit__()              # 失败时释放已获取的路径
```

### 6.2 RedoLog (redo_log.py)

```python
class RedoLog:
    """基于 AGFS 标记文件的崩溃恢复"""
    # 目录: viking://local/_system/redo/
    async def write_pending(task_id, info) -> None
    async def mark_done(task_id) -> None
    async def list_pending() -> List[str]
    async def read(task_id) -> Dict
    
    # 启动时恢复:
    # _recover_pending_redo() → 重放 session_memory 操作
```

---

## 7. Observers - 健康监控

### 7.1 BaseObserver 抽象

```python
class BaseObserver(ABC):
    async def get_status_table() -> str    # 格式化状态表格
    async def is_healthy() -> bool          # 健康检查
    async def has_errors() -> bool          # 是否有错误
```

### 7.2 观察者清单

| 观察者 | 监控对象 | 不健康条件 |
|---|---|---|
| `FilesystemObserver` | RAGFS 操作统计 | - |
| `LockObserver` | 活跃锁句柄 | 挂起锁 > 600s |
| `ModelsObserver` | VLM/Embedding/Rerank token 使用 | - |
| `QueueObserver` | 队列待处理/进行中/错误 | 大量错误堆积 |
| `RetrievalObserver` | 检索查询/结果/延迟 | 零结果率 > 50% |
| `VikingDBObserver` | 集合向量/索引计数 | 集合不可用 |
