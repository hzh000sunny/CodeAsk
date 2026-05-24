# 17 Python CLI (openviking_cli)

## 1. 模块概览

`openviking_cli/` 提供 OpenViking 的 Python CLI 工具集, 包括服务器启动、交互式设置向导、HTTP 客户端和分层配置管理。

**入口点** (pyproject.toml):
```toml
[project.scripts]
ov = "openviking_cli.rust_cli:main"           # → Rust CLI (实际二进制)
openviking = "openviking_cli.rust_cli:main"   # → Rust CLI (别名)
openviking-server = "openviking_cli.server_bootstrap:main"  # → Python 服务器
vikingbot = "vikingbot.cli.commands:app"       # → VikingBot CLI
```

---

## 2. 服务器引导 (server_bootstrap.py)

```python
def main():
    """openviking-server 命令入口"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=1933)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--with-bot", action="store_true")
    parser.add_argument("--without-bot", action="store_true")
    parser.add_argument("--with-console", action="store_true")
    parser.add_argument("--init", action="store_true")     # 初始化模式
    parser.add_argument("--doctor", action="store_true")    # 诊断模式
    
    # init 模式: 运行 setup_wizard → 生成 ov.conf
    # doctor 模式: 验证配置 + 检查依赖
    # 服务器模式: 加载配置 → 创建 FastAPI app → uvicorn.run()
```

---

## 3. 设置向导 (setup_wizard.py)

```python
def run_setup_wizard():
    """交互式设置向导, 生成 ov.conf 配置"""
    
    # 流程:
    # 1. 检测 Ollama 是否安装
    # 2. 选择 VLM 提供商:
    #    - Volcengine (火山引擎 Doubao)
    #    - OpenAI (官方 API)
    #    - OpenAI Codex (OAuth)
    #    - Kimi Coding (订阅)
    #    - GLM Coding Plan (订阅)
    #    - LiteLLM (多提供商)
    #    - Ollama (本地模型)
    # 3. 配置 API Key / Base URL
    # 4. 选择嵌入模型提供商
    # 5. 设置存储路径
    # 6. 写入 ~/.openviking/ov.conf
```

---

## 4. 诊断工具 (doctor.py)

```python
def run_doctor():
    """诊断命令, 验证环境是否就绪"""
    
    # 检查项:
    # - 配置文件存在 & 格式有效
    # - Python 版本 (>= 3.10)
    # - 嵌入提供商连通性 (API Key 验证)
    # - VLM 提供商连通性
    # - 磁盘空间 (存储路径)
    # - Codex OAuth 状态 (如适用)
    
    # 输出: [PASS] / [FAIL] / [WARN] 带详细消息
```

---

## 5. HTTP 客户端 (client/)

### 5.1 抽象基类

```python
class BaseClient(ABC):
    """所有客户端的抽象基类"""
    
    # 抽象方法 (40+ 个):
    @abstractmethod
    async def initialize()
    @abstractmethod
    async def close()
    @abstractmethod
    async def add_resource(path, to, parent, ...) -> Dict
    @abstractmethod
    async def ls(uri, ...) -> List
    @abstractmethod
    async def read(uri, ...) -> str
    @abstractmethod
    async def find(query, target_uri, ...) -> Any
    # ... 等
```

### 5.2 AsyncHTTPClient

```python
class AsyncHTTPClient(BaseClient):
    """异步 HTTP 客户端"""
    
    def __init__(url, api_key=None, account=None, user=None, 
                 agent_id=None, timeout=60.0, extra_headers=None):
        self._http = httpx.AsyncClient(
            base_url=url,
            timeout=timeout,
            headers={
                "Content-Type": "application/json",
                "X-API-Key": api_key,
                "X-OpenViking-Account": account,
                "X-OpenViking-User": user,
                "X-OpenViking-Agent": agent_id,
                **(extra_headers or {}),
            }
        )
    
    # 实现全部 BaseClient 方法 (每个方法 → HTTP 请求)
```

### 5.3 SyncHTTPClient

```python
class SyncHTTPClient:
    """同步 HTTP 客户端, 包装 AsyncHTTPClient"""
    # 所有方法为同步版本
    # 内部使用 asyncio.run() 或 run_async()
```

---

## 6. 分层配置管理 (utils/config/)

### 6.1 配置类清单

| 文件 | 配置类 | 说明 |
|---|---|---|
| `open_viking_config.py` | `OpenVikingConfig` | 顶级服务器配置 |
| `storage_config.py` | `StorageConfig` | 存储路径 (workspace) |
| `log_config.py` | `LogConfig` | 日志级别/输出 |
| `embedding_config.py` | `EmbeddingConfig` | 嵌入模型配置 (dense, max_concurrent, text_source) |
| `vlm_config.py` | `VLMConfig` | VLM 模型配置 (provider, model, api_key, api_base) |
| `parser_config.py` | `ParserConfig` | 解析器配置 |
| `memory_config.py` | `MemoryConfig` | 记忆系统配置 (agent_memory_enabled, 隔离策略) |
| `retrieval_config.py` | `RetrievalConfig` | 检索配置 (alpha, threshold, hotness_alpha) |
| `rerank_config.py` | `RerankConfig` | 重排序配置 |
| `vectordb_config.py` | `VectordbConfig` | 向量数据库后端配置 |
| `transaction_config.py` | `TransactionConfig` | 事务锁配置 (lock_expire) |
| `telemetry_config.py` | `TelemetryConfig` | 遥测配置 |
| `encryption_config.py` | `EncryptionConfig` | 加密配置 |
| `oauth_config.py` | `OAuthConfig` | OAuth2 配置 |
| `agfs_config.py` | `AGFSConfig` | AGFS 服务器连接 |
| `prompts_config.py` | `PromptsConfig` | 提示词模板配置 |
| `ovcli_config.py` | `OVCLIConfig` | CLI 客户端配置 |
| `consts.py` | - | 常量定义 |

### 6.2 配置加载器

```python
class ConfigLoader:
    """从文件/环境变量加载配置"""
    
    @staticmethod
    def load(config_path=None) -> OpenVikingConfig:
        """
        1. 读取 JSON 配置文件
        2. 应用环境变量覆盖
        3. 验证配置完整性
        4. 返回类型化配置对象
        """
```

### 6.3 配置工具

```python
def get_openviking_config() -> OpenVikingConfig:
    """获取全局配置单例"""
    # 惰性加载, 缓存

def get_llm_config(prompt_id) -> dict:
    """获取提示词特定的 LLM 配置"""
    # 提示词可能覆盖默认 VLM 配置 (model, temperature, max_tokens...)
```

---

## 7. 其他工具

### 7.1 LLM 工具 (utils/llm.py)

```python
async def call_llm(prompt, model=None, temperature=None, ...) -> str:
    """统一的 LLM 调用接口"""

def parse_json_from_response(response) -> Optional[dict]:
    """从 LLM 响应中容错解析 JSON"""
    # 处理代码块、纯 JSON、有问题的引号
```

### 7.2 URI 工具 (utils/uri.py)

```python
class VikingURI:
    @staticmethod
    def parse(uri: str) -> Tuple[str, List[str]]:
        # viking://resources/proj/docs → ("resources", ["proj", "docs"])
    
    @staticmethod
    def build(scope: str, path: List[str]) -> str:
        # ("resources", ["proj", "docs"]) → "viking://resources/proj/docs"
    
    @staticmethod
    def validate(uri: str) -> bool:
        # 格式验证 + 路径遍历攻击检测
```

### 7.3 用户标识 (session/user_id.py)

```python
class UserIdentifier:
    @staticmethod
    def the_default_user() -> str:
        """获取当前系统用户标识"""
        # $USER 环境变量, 回退到 "default"
    
    @staticmethod
    def generate_agent_id(name) -> str:
        """生成 Agent ID (name + MD5 hash)"""
```

### 7.4 检索类型 (retrieve/types.py)

```python
@dataclass
class TypedQuery:
    query: str
    context_type: Optional[str]
    target_dirs: Optional[List[str]]
    level: Optional[int]

@dataclass
class QueryPlan:
    queries: List[TypedQuery]
    reasoning: str

@dataclass
class MatchedContext:
    uri: str
    score: float
    content: str
    abstract: Optional[str]
    context_type: str
    level: int
    relations: List[Dict]
```

### 7.5 异步工具 (utils/async_utils.py)

```python
def run_async(coro) -> Any:
    """在同步上下文中运行异步协程"""
    # 检测是否有运行中的事件循环
    # 有 → 创建新线程运行
    # 无 → asyncio.run()
```

### 7.6 下载器 (utils/downloader.py)

```python
async def download_file(url, dest_path, progress_callback=None):
    """带进度回调的文件下载器"""
```

### 7.7 提取器 (utils/extractor.py)

```python
async def extract_text_from_url(url) -> str:
    """从 URL 提取可读文本内容"""
    # 使用 readabilipy + markdownify
```
