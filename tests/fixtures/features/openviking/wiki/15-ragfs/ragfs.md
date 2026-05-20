# 15 RAGFS 虚拟文件系统 (crates/ragfs)

## 1. 模块概览

`crates/ragfs/` 是一个 Rust 库 + 二进制 crate, 实现了**插件式虚拟文件系统** (Aggregated File System for AI Agents)。它是 OpenViking 存储层的底层引擎。

**组成**:
- `ragfs` 库 (lib.rs): 核心抽象 + 插件系统
- `ragfs-server` 二进制: HTTP REST API 服务器
- `ragfs-shell` 二进制: 交互式 Shell (待实现)
- `ragfs-python` crate: Python 绑定 (PyO3)

---

## 2. 核心抽象 (core/)

### 2.1 FileSystem Trait

```rust
#[async_trait]
pub trait FileSystem: Send + Sync {
    async fn create(&self, path: &str) -> Result<()>;
    async fn mkdir(&self, path: &str, mode: u32) -> Result<()>;
    async fn remove(&self, path: &str) -> Result<()>;
    async fn remove_all(&self, path: &str) -> Result<()>;
    async fn read(&self, path: &str, offset: u64, size: i64) -> Result<Vec<u8>>;
    async fn write(&self, path: &str, data: &[u8], offset: u64, flags: WriteFlag) -> Result<u64>;
    async fn read_dir(&self, path: &str) -> Result<Vec<FileInfo>>;
    async fn stat(&self, path: &str) -> Result<FileInfo>;
    async fn rename(&self, old: &str, new: &str) -> Result<()>;
    async fn chmod(&self, path: &str, mode: u32) -> Result<()>;
    
    // 默认实现:
    async fn truncate(&self, path: &str, size: u64) -> Result<()>;
    async fn exists(&self, path: &str) -> Result<bool>;
    async fn grep(&self, path, pattern, recursive, case_insensitive, 
                  stream, node_limit, exclude_path, level_limit) -> Result<GrepResult>;
}
```

### 2.2 WriteFlag

```rust
enum WriteFlag {
    Create,      // 创建新文件 (已存在则失败)
    Append,      // 追加到文件末尾
    Truncate,    // 截断后写入
    None,        // 覆盖 (默认)
}
```

### 2.3 核心数据类型

```rust
struct FileInfo {
    name: String,
    size: u64,
    mode: u32,
    mod_time: SystemTime,
    is_dir: bool,
}

struct GrepResult {
    matches: Vec<GrepMatch>,
    count: usize,
}

struct GrepMatch {
    file: String,
    line: u64,
    content: String,
}

struct PluginConfig {
    name: String,
    mount_path: String,
    params: HashMap<String, ConfigValue>,
}

enum ConfigValue {
    String(String),
    Int(i64),
    Bool(bool),
    StringList(Vec<String>),
}
```

---

## 3. MountableFS - 挂载路由器

```rust
struct MountableFS {
    // radix_trie::Trie<String, MountInfo> 用于路径路由
    // HashMap<String, Arc<dyn ServicePlugin>> 用于插件管理
}

impl MountableFS {
    fn register_plugin(&mut self, plugin: Arc<dyn ServicePlugin>);
    async fn mount(&self, config: PluginConfig) -> Result<()>;
    async fn unmount(&self, path: &str) -> Result<()>;
    fn list_mounts(&self) -> Vec<MountInfo>;
    fn find_mount(&self, path: &str) -> Option<(String, &MountInfo)>;
    // find_mount 使用最长前缀匹配 (radix trie)
}

impl FileSystem for MountableFS {
    // 每个操作都委托给 find_mount 找到的挂载点
    // 跨挂载 rename 返回 InvalidOperation
    // grep 处理 exclude_path 的跨挂载解析
}
```

---

## 4. 内置插件

### 4.1 MemFS (memfs/mod.rs, 656 行)

```rust
struct MemFileSystem {
    entries: Arc<RwLock<HashMap<String, FileEntry>>>,
}
// 完全内存文件系统
// 创建/写入前检查父目录存在
// rename 递归处理子项
// 无配置参数
```

### 4.2 KVFS (kvfs/mod.rs, 566 行)

```rust
struct KVFileSystem {
    store: Arc<RwLock<HashMap<String, KVEntry>>>,
}
// 键值存储风格文件系统
// 路径作为键, 前缀匹配列出
// 无配置参数
```

### 4.3 LocalFS (localfs/mod.rs, 1273 行)

```rust
struct LocalFileSystem {
    base_path: PathBuf,
    has_rg: bool,  // ripgrep 是否可用
}
// 挂载本地目录
// 配置: local_dir (必填)
// grep 双路径:
//   1. 快速路径: 外部 rg --json (解析 JSON 行, 处理退出码 0/1/2)
//   2. 回退路径: grep-regex + ignore::WalkBuilder
// 最大文件大小: 5MB
// 使用 --no-ignore-parent 避免父 .gitignore
```

### 4.4 QueueFS (queuefs/mod.rs, 1029 行)

```rust
// 基于文件系统的消息队列
// 每个队列 6 个控制文件:
//   enqueue (0o222), dequeue (0o444), peek (0o444),
//   size (0o444), clear (0o222), ack (0o222)

struct QueueFileSystem {
    backend: Arc<Mutex<Box<dyn QueueBackend>>>,
}

// 后端: Memory / SQLite (WAL 模式)
// SQLite: 至少一次投递 + 过期恢复 + Go 格式兼容
```

### 4.5 SQLFS (sqlfs/mod.rs)

```rust
struct SQLFileSystem {
    backend: Arc<RwLock<Box<dyn DatabaseBackend>>>,
    cache: ListDirCache,  // LRU 缓存
}
// 数据库后端: SQLite (rusqlite) / MySQL (sqlx)
// 配置: driver, dsn, table_prefix, max_file_size, cache_enabled
```

### 4.6 S3FS (s3fs/mod.rs, 860 行, feature-gated)

```rust
struct S3FileSystem {
    client: Arc<S3Client>,
    dir_cache: S3ListDirCache,  // LRU + TTL
    stat_cache: S3StatCache,    // LRU + TTL
}
// 16 个配置参数
// 三种目录标记模式: empty / nonempty / none
// 特殊字符编码: !HH 格式
// 批量删除
```

### 4.7 ServerInfoFS (serverinfofs/mod.rs)

```rust
// 只读虚拟文件系统
// 文件:
//   version    → 版本字符串
//   uptime     → 运行时间 (JSON)
//   server_info → 服务器信息 (JSON)
//   stats      → 统计信息 (JSON)
//   README.md  → 帮助文本
```

---

## 5. 统计系统 (core/stats.rs)

```rust
enum FsOperation { Create, Mkdir, Remove, RemoveAll, Read, Write, 
                   ReadDir, Stat, Rename, Chmod, Truncate, Exists, 
                   Grep, EnsureParentDirs }

struct OperationStats { count, total_time_us, min_time_us, max_time_us }
struct FilesystemStats { operations: HashMap<FsOperation, OperationStats> }
struct StatsCollector { stats: Arc<RwLock<FilesystemStats>> }
struct OperationTimer { collector, op, start }  // RAII 计时器

struct StatsWrappedFS {  // 装饰器模式
    inner: Box<dyn FileSystem>,
    stats: Arc<StatsCollector>,
}
// 每个操作自动计时
```

---

## 6. HTTP 服务器 (server/)

### 6.1 架构

```
axum 0.7 HTTP Server
├── TraceLayer (INFO)
├── CorsLayer::permissive()
└── Router (/api/v1)
    ├── GET    /files              → read_file
    ├── PUT    /files              → write_file
    ├── POST   /files              → create_file
    ├── DELETE /files              → delete_file
    ├── GET    /stat               → stat_file
    ├── GET    /directories        → list_directory
    ├── POST   /directories        → create_directory
    ├── POST   /directories/ensure-parent → ensure_parent_dirs
    ├── GET    /mounts             → list_mounts
    ├── POST   /mount              → mount_filesystem
    ├── POST   /unmount            → unmount_filesystem
    ├── POST   /grep               → grep_content
    ├── GET    /stats              → get_stats
    └── GET    /health             → health_check
```

### 6.2 AppState

```rust
struct AppState {
    fs: Arc<MountableFS>,
}
```

### 6.3 动态挂载

```json
POST /api/v1/mount
{
  "plugin": "s3fs",
  "path": "/data",
  "params": {
    "bucket": "my-bucket",
    "region": "us-east-1",
    "endpoint": "https://s3.amazonaws.com"
  }
}
```

---

## 7. Python 绑定 (ragfs-python)

```rust
// PyO3 模块: ragfs_python
#[pyclass]
struct RAGFSBindingClient {
    fs: Arc<MountableFS>,
    rt: tokio::runtime::Runtime,
}

#[pymethods]
impl RAGFSBindingClient {
    #[new]
    fn __new__(config_path: Option<&str>) -> Self;
    
    // 注册所有内置插件: MemFS, KVFS, QueueFS, SQLFS, LocalFS, ServerInfoFS, S3FS
    
    // 文件操作 (PyO3 返回类型):
    fn ls(&self, path: &str) -> PyResult<Py<PyList>>;       // PyDict 格式
    fn read(&self, path: &str, offset: u64, size: i64) -> PyResult<Py<PyBytes>>;
    fn cat(&self, path: &str) -> PyResult<Py<PyBytes>>;     // read 别名
    fn write(&self, path: &str, data: &[u8]) -> PyResult<String>;
    fn create(&self, path: &str) -> PyResult<()>;
    fn mkdir(&self, path: &str, mode: &str) -> PyResult<()>;
    fn rm(&self, path: &str, recursive: bool) -> PyResult<()>;
    fn stat(&self, path: &str) -> PyResult<Py<PyDict>>;
    fn mv(&self, old: &str, new: &str) -> PyResult<()>;
    
    // 挂载管理:
    fn mounts(&self) -> PyResult<Py<PyList>>;
    fn mount(&self, fstype: &str, path: &str, config: Option<&PyDict>) -> PyResult<()>;
    fn unmount(&self, path: &str) -> PyResult<()>;
    
    // 搜索:
    fn grep(&self, path, pattern, recursive, case_insensitive, 
            stream, node_limit, exclude_path, level_limit) -> PyResult<Py<PyDict>>;
    
    // 统计:
    fn get_stats(&self, path: Option<&str>) -> PyResult<Py<PyDict>>;
    fn health(&self) -> PyResult<HashMap<String, String>>;
}

// 异常映射: ragfs Error → openviking.pyagfs.* 异常
fn to_py_err(e: Error) -> PyErr; {
    // NotFound → AGFSNotFoundError
    // AlreadyExists → AGFSAlreadyExistsError
    // PermissionDenied → AGFSPermissionDeniedError
    // ...
}
```
