# 07 模型 & 嵌入 (openviking/models)

## 1. 模块概览

`openviking/models/` 提供统一的 ML 模型接口层，支持多种 VLM 提供商、嵌入模型和重排序模型。

| 子模块 | 用途 |
|---|---|
| `vlm/` | 视觉语言模型 (6 种后端) |
| `embedder/` | 嵌入模型 (13 种提供商) |
| `rerank/` | 重排序模型 (4 种提供商) |

---

## 2. VLM 后端 (models/vlm/)

### 2.1 核心抽象

```python
@dataclass
class ToolCall:
    id: str
    name: str
    arguments: Dict[str, Any]

@dataclass
class VLMResponse:
    content: str
    tool_calls: List[ToolCall]
    finish_reason: str
    usage: Dict[str, int]               # {prompt_tokens, completion_tokens, total_tokens}
    reasoning_content: Optional[str]    # 推理模型的思考内容

class VLMBase(ABC):
    @abstractmethod
    async def get_completion(prompt, thinking, tools, tool_choice, messages) -> VLMResponse
    @abstractmethod
    async def get_completion_async(...) -> VLMResponse
    @abstractmethod
    async def get_vision_completion(prompt, images, thinking, ...) -> VLMResponse
    @abstractmethod
    async def get_vision_completion_async(...) -> VLMResponse
    
    # 公共方法:
    def _clean_response(content) -> str        # 移除 <think/> 标签
    def update_token_usage(model, provider, prompt, completion)
```

### 2.2 VLM 后端清单

| 后端 | 文件 | 提供商 | 特点 |
|---|---|---|---|
| `OpenAIVLM` | `openai_vlm.py` | OpenAI, Azure | 推理模型检测 (gpt-5/o1/o3/o4), reasoning_effort |
| `VolcEngineVLM` | `volcengine_vlm.py` | 火山引擎 | Ark SDK, thinking 模式, 30+ 图像格式支持 |
| `CodexVLM` | `codex_vlm.py` | OpenAI Codex | OAuth2 设备码认证, Responses API 适配 |
| `KimiVLM` | `kimi_vlm.py` | Kimi Coding | 订阅专用端点, User-Agent 设置 |
| `GLMVLM` | `glm_vlm.py` | 智谱 GLM | Coding Plan 端点 |
| `LiteLLMVLMProvider` | `litellm_vlm.py` | 100+ 提供商 | 自动检测 (gpt/claude/gemini...), 10 个预配置 |

### 2.3 VLMFactory

```python
class VLMFactory:
    @staticmethod
    def create(config) -> VLMBase:
        # volcengine → VolcEngineVLM
        # openai/azure → OpenAIVLM
        # openai-codex → CodexVLM
        # kimi → KimiVLM
        # glm → GLMVLM
        # litellm → LiteLLMVLMProvider
```

### 2.4 FailoverVLM - 故障转移

```python
class FailoverVLM(VLMBase):
    """主备 VLM 自动切换"""
    def __init__(primary: VLMBase, backup: VLMBase):
        self._switcher = PrimaryBackupSwitcher()
    
    # 所有调用通过 switcher 路由
    # 主 VLM 失败 → 自动切换到备 VLM
    # is_using_backup 属性检查当前状态
```

### 2.5 结构化 VLM 输出

```python
class StructuredVLM:
    """包装 VLM 进行 JSON Schema 约束输出"""
    
    async def complete_json(prompt, schema, thinking, tools) -> dict:
        # 1. 注入 JSON Schema 到 system prompt
        # 2. 调用 VLM
        # 3. parse_json_to_model() 容错解析
    
    async def complete_model(prompt, model_class, thinking, tools):
        # Pydantic 模型 → JSON Schema → VLM → 模型实例
```

### 2.6 TokenUsageTracker

```python
class TokenUsageTracker:
    """线程安全的 Token 使用追踪器"""
    def update(model_name, provider, prompt_tokens, completion_tokens)
    def get_model_usage(model_name) -> ModelTokenUsage
    def get_all_usage() -> Dict[str, ModelTokenUsage]
    def get_total_usage() -> TokenUsage
    def reset()
    @staticmethod
    def merge(*trackers) -> TokenUsageTracker
```

---

## 3. 嵌入模型 (models/embedder/)

### 3.1 抽象层次

```
EmbedderBase (ABC)                      统一接口
├── DenseEmbedderBase                   密集向量 (get_dimension)
├── SparseEmbedderBase                  稀疏向量
├── HybridEmbedderBase                  混合向量 (密集 + 稀疏)
└── CompositeHybridEmbedder             组合 DenseEmbedder + SparseEmbedder
```

### 3.2 EmbedResult

```python
@dataclass
class EmbedResult:
    dense_vector: Optional[List[float]]
    sparse_vector: Optional[Dict[str, float]]
    
    @property
    def is_dense() -> bool
    @property
    def is_sparse() -> bool
    @property
    def is_hybrid() -> bool    # 同时有密集和稀疏
```

### 3.3 嵌入器清单

| 嵌入器 | 提供商 | 类型 | 特点 |
|---|---|---|---|
| `OpenAIDenseEmbedder` | OpenAI / Azure | 密集 | 自动维度检测, 客户端截断, 非对称参数 |
| `VolcengineDenseEmbedder` | 火山引擎 | 密集 | 文本 + 多模态模式 |
| `VolcengineSparseEmbedder` | 火山引擎 | 稀疏 | 多模态端点 |
| `VolcengineHybridEmbedder` | 火山引擎 | 混合 | 单次 API 调用 |
| `JinaDenseEmbedder` | Jina AI | 密集 | 非对称任务嵌入, Matryoshka 降维, late_chunking |
| `CohereDenseEmbedder` | Cohere | 密集 | API v2, 最多 96 批量, 服务端降维 |
| `VoyageDenseEmbedder` | Voyage AI | 密集 | OpenAI 兼容 API |
| `DashScopeDenseEmbedder` | 阿里云灵积 | 密集 | 文本 + 多模态双模式 |
| `MiniMaxDenseEmbedder` | MiniMax | 密集 | HTTP API, 自动维度检测 |
| `GeminiDenseEmbedder` | Google | 密集 | MRL 降维 (1-3072), 任务类型区分 |
| `LiteLLMDenseEmbedder` | LiteLLM | 密集 | 多提供者路由, 模型格式 "provider/model" |
| `VikingDBDenseEmbedder` | VikingDB | 密集 | Signature V4 认证 |
| `VikingDBSparseEmbedder` | VikingDB | 稀疏 | 多格式稀疏向量 |
| `VikingDBHybridEmbedder` | VikingDB | 混合 | 密集 + 稀疏 |
| `LocalDenseEmbedder` | 本地 | 密集 | llama-cpp-python, GGUF 模型, HuggingFace 下载 |

### 3.4 嵌入兼容函数

```python
async def embed_compat(embedder, text, is_query=False) -> EmbedResult
async def embed_batch_compat(embedder, texts, is_query=False) -> List[EmbedResult]
def truncate_and_normalize(embedding, dimension) -> List[float]
async def exponential_backoff_retry(func, max_retries=3, base_delay=1.0)
```

---

## 4. 重排序模型 (models/rerank/)

### 4.1 抽象

```python
class RerankBase(ABC):
    async def rerank_batch(query, documents) -> List[Dict]:
        # 返回: [{index, score}, ...]
    
    def update_token_usage(model_name, provider, response_data, query, documents):
        # 从 meta.billed_units 提取 token 使用量
```

### 4.2 重排序器清单

| 重排序器 | 提供商 | 特点 |
|---|---|---|
| `RerankClient` | Volcengine (VikingDB) | Signature V4 认证, 可路由到 Cohere/LiteLLM/OpenAI |
| `CohereRerankClient` | Cohere | Rerank v3.5, httpx |
| `LiteLLMRerankClient` | LiteLLM | litellm.rerank(), 按索引排序 |
| `OpenAIRerankClient` | OpenAI 兼容 | Bearer 认证 POST, DashScope 等 |

### 4.3 多提供者路由

```python
class RerankClient:
    @staticmethod
    def from_config(config):
        # 根据配置自动选择:
        # cohere → CohereRerankClient
        # litellm → LiteLLMRerankClient
        # openai → OpenAIRerankClient
        # volcengine/vikingdb → RerankClient (默认)
```
