# 16 C++ 向量引擎 (src/)

## 1. 模块概览

`src/` 包含 C++ 实现的向量数据库引擎，以 Python abi3 扩展模块形式提供 (支持 Python 3.10+ 稳定 ABI)。

| 文件 | 用途 |
|---|---|
| `CMakeLists.txt` | CMake 构建系统 (C++17, Python abi3) |
| `abi3_engine_backend.cpp` | Python 扩展模块 (~1593 行, 26 个方法) |
| `abi3_x86_caps.cpp` | x86 CPU 特性检测 (SSE3/AVX2/AVX512) |

**引擎源代码** (未在文件列表中, 但从 CMake 引用推断):
- `index/` — HNSW 向量索引实现
- `store/` — KV 存储 (PersistStore, VolatileStore, BytesRow)
- `common/` — 共享工具 (log_utils)

---

## 2. 构建系统 (CMakeLists.txt)

### 2.1 配置变量

```cmake
# x86 变体 (多版本编译)
set(OV_X86_BUILD_VARIANTS "sse3;avx2;avx512")

# Python 扩展后缀
set(OV_PY_EXT_SUFFIX ".so")

# 依赖
find_package(Python3 REQUIRED COMPONENTS Development)
find_package(Threads REQUIRED)
# LevelDB: leveldb-1.23 (自带)
# spdlog: spdlog-1.14.1 (自带)
# krl: ARM only (自带)
```

### 2.2 构建目标

```
engine_common (静态库)
├── log_utils.cpp
├── bytes_row.cpp
├── persist_store.cpp
└── volatile_store.cpp

engine_index_{variant} (静态库, 每变体)
└── index/*.cpp

_x86_{variant} (Python 扩展, 每变体)
└── abi3_engine_backend.cpp + engine_common + engine_index_{variant}

_x86_caps (Python 扩展, CPU 检测)
└── abi3_x86_caps.cpp
```

### 2.3 编译选项

```cmake
# SSE3:  -msse3
# AVX2:  -mavx2 -mfma -mbmi2
# AVX512: -mavx512f -mavx512dq -mavx512bw -mavx512vl

# ARM: 单变体 _native + krl 链接
```

---

## 3. abi3_engine_backend.cpp - Python 扩展

### 3.1 Handle 管理

```cpp
// Capsule-based 句柄传递:
// - SchemaHandle { shared_ptr<Schema> }
// - BytesRowHandle { shared_ptr<Schema>, shared_ptr<BytesRow> }
// - IndexEngine (raw ptr)
// - KVStore (raw ptr)

// 命名 Capsule:
constexpr auto kIndexCapsuleName = "OpenViking.IndexEngine";
constexpr auto kStoreCapsuleName = "OpenViking.KVStore";
constexpr auto kSchemaCapsuleName = "OpenViking.Schema";
constexpr auto kBytesRowCapsuleName = "OpenViking.BytesRow";

// 类型化析构函数 (schema/bytes_row/index/store)
```

### 3.2 类型转换

```cpp
// Python → C++:
py_to_string(obj, out, allow_bytes) -> bool;
py_to_uint64(obj, out) -> bool;
py_to_uint32(obj, out) -> bool;
py_to_float(obj, out) -> bool;
py_to_int64(obj, out) -> bool;
py_to_bool(obj, out) -> bool;
py_to_float_vector(obj, out) -> bool;
py_to_string_vector(obj, out) -> bool;
py_to_int64_vector(obj, out) -> bool;
py_to_field_value(obj, field_type, out) -> bool;

// C++ → Python:
value_to_py(value, field_type) -> PyObject*;
float_vector_to_py(vec) -> PyObject*;
string_vector_to_py(vec) -> PyObject*;
uint64_vector_to_py(vec) -> PyObject*;

// FieldType 映射:
py_to_field_type(obj, out) -> bool;
// 0→INT64, 1→UINT64, 2→FLOAT32, 3→STRING
// 4→BINARY, 5→BOOLEAN, 6→LIST_INT64, 7→LIST_STRING, 8→LIST_FLOAT32
```

### 3.3 GIL 管理

```cpp
void call_without_gil(std::function<void()> func) {
    PyThreadState* state = PyEval_SaveThread();
    func();
    PyEval_RestoreThread(state);
}
// 所有阻塞操作释放 GIL
```

### 3.4 模块方法 (26 个)

#### Schema 操作
```python
_new_schema(field_infos: list) -> capsule
    # 从字段类型/名称列表创建 Schema
_schema_get_total_byte_length(capsule) -> int
```

#### BytesRow 操作
```python
_new_bytes_row(schema_capsule) -> capsule
_bytes_row_serialize(capsule, values: dict) -> bytes
_bytes_row_serialize_batch(capsule, batch_values: list) -> bytes
_bytes_row_deserialize(capsule, data: bytes) -> dict
_bytes_row_deserialize_field(capsule, data: bytes, field_name: str) -> Any
```

#### IndexEngine 操作
```python
_new_index_engine(dimension, index_type, metric_type, ...) -> capsule
_index_engine_add_data(capsule, keys: list, vectors: list, fields: list) -> None
_index_engine_delete_data(capsule, keys: list) -> None
_index_engine_search(capsule, query: list, k: int, params: dict) -> (labels, scores)
_index_engine_dump(capsule, path: str) -> None
_index_engine_get_state(capsule) -> (update_timestamp, element_count)
```

#### KVStore 操作
```python
_new_persist_store(path: str, options: dict) -> capsule
_new_volatile_store() -> capsule
_store_exec_op(capsule, op_type: int, args: dict) -> None
_store_get_data(capsule, keys: list) -> list
_store_put_data(capsule, keys: list, values: list) -> None
_store_delete_data(capsule, keys: list) -> None
_store_clear_data(capsule) -> None
_store_seek_range(capsule, start_key: str, end_key: str) -> list
```

#### 日志
```python
_init_logging(log_dir: str, level: str) -> None
```

### 3.5 模块常量

```python
# 模块属性:
_ENGINE_BACKEND_API = "abi3-v1"
```

---

## 4. abi3_x86_caps.cpp - CPU 特性检测

### 4.1 检测函数

```cpp
struct CpuFeatures {
    bool sse3, avx, avx2, avx512f, avx512dq, avx512bw, avx512vl;
};

CpuFeatures detect_cpu_features() {
    // CPUID Leaf 1: 检查 SSE3 + OSXSAVE + AVX
    // XCR0: 检查 AVX OS 支持
    // CPUID Leaf 7: 检查 AVX2 + AVX512 特性
    // XCR0: 检查 AVX512 OS 支持 (OPMASK + ZMM + SSE)
    // 非 x86: 返回空特性
}
```

### 4.2 Python 接口

```python
import _x86_caps
_x86_caps.get_supported_variants() -> List[str]
# 返回: ["x86_sse3", "x86_avx2", "x86_avx512"]
# (仅返回 CPU 支持的变体)
```

---

## 5. 引擎变体选择

```python
# openviking/storage/vectordb/engine/__init__.py

def _select_variant() -> str:
    """
    优先级:
    1. OV_ENGINE_VARIANT 环境变量
    2. 自动检测:
       - x86: 导入 _x86_caps → 选择最佳变体
         (avx512 > avx2 > sse3)
       - ARM: _native
    3. 回退: 纯 Python (_python_api.py)
    """

def _load_backend() -> module:
    """
    加载对应变体的 .abi3.so 文件
    - 优先 abi3 变体 (稳定 ABI)
    - 回退到平台特定 (.cpython-*.so)
    """
```

---

## 6. 纯 Python 回退 (_python_api.py)

当 C++ 引擎不可用时, 使用纯 Python 实现:

```python
class _PySchema:
    """Python 实现的 Schema"""
    # struct 格式: 小端字节序, 固定区 + 可变区

class _PyBytesRow:
    """Python 实现的 BytesRow 序列化"""
    # 与 C++ 实现二进制兼容

def build_abi3_exports():
    """构建 abi3-v1 API 兼容的导出"""
    # 创建 Schema/BytesRow/IndexEngine/PersistStore/VolatileStore
    # 包装器, 委托给 C++ 句柄或纯 Python 实现
```

---

## 7. 关键架构特征

- **abi3 稳定 ABI**: 一次编译, 兼容 Python 3.10-3.14+ (无需为每个 Python 版本重新编译)
- **CPU 多变体编译**: x86 上编译 SSE3/AVX2/AVX512 三个版本, 运行时自动选择最优
- **Capsule 句柄模式**: 使用 PyCapsule 在 Python 和 C++ 之间传递不透明指针, 自动内存管理
- **GIL 释放**: 所有阻塞操作 (搜索/持久化) 通过 `PyEval_SaveThread` 释放 GIL
- **LevelDB 持久化**: PersistStore 基于 LevelDB 实现持久化 KV 存储
- **RocksDB 兼容**: StoreEngineProxy 在启动时清理过期的 RocksDB LOCK 文件
