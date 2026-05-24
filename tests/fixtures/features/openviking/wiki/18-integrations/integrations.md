# 18 集成 (openviking/integrations)

## 1. 模块概览

`openviking/integrations/` 提供 LangChain 和 LangGraph 的深度集成，使开发者可以在 LangChain 生态中直接使用 OpenViking 的上下文存储和检索能力。

---

## 2. LangChain 集成 (integrations/langchain/)

### 2.1 客户端 (client.py)

```python
def ensure_client(*, url=None, api_key=None, account=None, user=None, 
                  agent_id=None, timeout=60.0, client_class=SyncOpenViking,
                  **kwargs):
    """确保客户端已初始化 (惰性连接)"""
    # 1. 检查全局 _client 是否已存在
    # 2. 否则创建 SyncOpenViking 或 SyncHTTPClient
    # 3. 调用 initialize()
    # 4. 缓存并返回

def call_openviking(client, operation, **kwargs) -> Any:
    """统一的 OpenViking 调用接口"""
    # 动态分派到客户端方法
    # operation: "find", "read", "ls", "add_resource", ...
```

### 2.2 检索器 (retrievers.py)

```python
class OpenVikingRetriever(BaseRetriever):
    """LangChain 兼容的 BaseRetriever 实现"""
    
    # 20 个配置字段:
    url: str                       # OpenViking 服务器 URL
    api_key: Optional[str]
    account: Optional[str]
    target_uri: str = "viking://resources/"
    search_mode: str = "find"      # find / search
    content_mode: str = "auto"     # abstract / overview / read / auto
    limit: int = 10
    score_threshold: float = 0.0
    session_id: Optional[str]      # search 模式使用
    
    def _get_relevant_documents(query, *, run_manager) -> List[Document]:
        """
        1. 调用 OpenViking find/search
        2. 遍历结果项
        3. 根据 content_mode 读取内容
        4. 返回 LangChain Document 列表
        """
    
    def _content_for_item(client, item) -> str:
        """根据 content_mode 决定返回哪层内容"""
        # auto: L2 → L1 → L0
        # read: 直接读取 L2
        # abstract: L0 摘要
        # overview: L1 概览
```

### 2.3 工具 (tools.py)

```python
def create_openviking_tools(
    url=None, api_key=None, account=None,
    profile="retrieval",        # retrieval / agent / admin
    tool_names=None,             # 可选过滤
    allow_forget=False,
) -> List[StructuredTool]:
    """为 Agent 创建 LangChain 工具集"""
    
    # 工具清单:
    # viking_find(query, target_uri, limit, min_score)
    # viking_search(query, target_uri, session_id, limit, min_score)
    # viking_browse(uri, recursive, pattern)
    # viking_read(uris, max_chars, content_mode)
    # viking_grep(uri, pattern, case_insensitive, node_limit)
    # viking_store(messages, session_id, commit)
    # viking_archive_search(session_id, query, archive_id, token_budget)
    # viking_archive_expand(session_id, archive_id, max_chars)
    # viking_add_resource(path, to, parent, reason, instruction)
    # viking_add_skill(data, wait, timeout)
    # viking_health()
    # viking_forget(uri, recursive)  # 仅 allow_forget=True
    
    # Profile 过滤:
    # retrieval: find, search, browse, read, grep, health
    # agent: + store, add_resource, add_skill
    # admin: + forget
```

### 2.4 存储 (store.py)

```python
class OpenVikingStore(BaseStore):
    """LangGraph BaseStore 实现, 基于 OpenViking 内容存储"""
    
    # URI 结构:
    # 数据: viking://user/memories/langgraph_store/data/{ns}/{key}.json
    # 索引: viking://user/memories/langgraph_store/index/{ns}/{key}.md
    
    def __init__(root_uri="viking://user/memories/langgraph_store", index=True):
        ...
    
    def batch(ops) -> List[Any]:
        """批量处理 GetOp / PutOp / SearchOp / ListNamespacesOp"""
    
    def get(namespace, key) -> Item:
        """读取 JSON 记录, 返回 Item(namespace, key, value, created_at, updated_at)"""
    
    def put(namespace, key, value, index, *, ttl) -> None:
        """写入数据记录 + 可选索引文档"""
    
    def delete(namespace, key) -> None:
        """删除数据和索引记录"""
    
    def search(namespace_prefix, *, query, filter, limit, offset) -> List[SearchItem]:
        """语义搜索 (find) 或列出 + 过滤"""
    
    def list_namespaces(*, prefix, suffix, max_depth, limit, offset) -> List[tuple]:
        """通过 glob 列出命名空间"""
```

### 2.5 上下文后端 (context.py)

```python
class OpenVikingContextBackend:
    """LangChain 上下文后端, 用于 Agent 上下文持久化"""
    # 存储/检索 Agent 的执行上下文
    # URI: viking://agent/{id}/contexts/{session_id}/
```

### 2.6 消息历史 (history.py)

```python
class OpenVikingMessageHistory(BaseChatMessageHistory):
    """LangChain 消息历史, 基于 OpenViking 会话存储"""
    # 实现 add_message / clear / messages
    # 通过 Session.add_message() 存储
```

### 2.7 中间件 (middleware.py)

```python
class OpenVikingMiddleware:
    """LangGraph 中间件, 自动将 Agent 状态持久化到 OpenViking"""
    # 拦截 Agent 执行步骤
    # 记录: 消息历史, 工具调用, 状态变更
```

### 2.8 测试客户端 (testing.py)

```python
class InMemoryOpenVikingClient:
    """确定性内存客户端, 用于 CI 测试和示例"""
    
    # 内部状态:
    records: Dict[str, str]       # URI → 内容
    sessions: Dict                # 会话
    archives: Dict                # 存档
    
    # 查找: 基于文本标记匹配 (确定性)
    # 搜索: 会话内上下文搜索
    # 所有操作完全内存, 无外部依赖
    
    def find(query, target_uri, limit, score_threshold) -> List:
        """基于标记的确定性搜索"""
        # tokens = set(query.lower().split())
        # score = |matching tokens| / |query tokens|
    
    def commit_session(session_id) -> Dict:
        """创建存档 + 记录文件"""
```

---

## 3. LangGraph 集成

### 3.1 Agent (langgraph/agent/)

```python
# quick_app.py / live_app.py
# 使用 OpenVikingStore 进行 Agent 状态持久化
# 使用 OpenVikingRetriever 进行上下文检索
```

### 3.2 中间件 (langgraph/middleware/)

```python
# quick_app.py
# 展示 OpenVikingMiddleware 的基本用法
# 自动在 Agent 执行步骤间持久化状态
```

### 3.3 消息历史 (langchain/message-history/)

```python
# quick_app.py
# 展示 OpenVikingMessageHistory 的基本用法
```

### 3.4 RAG (langchain/rag/)

```python
# quick_app.py
# 展示 OpenViking 作为 RAG 后端的完整流程
# 1. add_resource 摄入文档
# 2. OpenVikingRetriever 检索上下文
# 3. LLM 生成答案
```

---

## 4. 使用示例

```python
from openviking.integrations.langchain import (
    create_openviking_tools,
    OpenVikingRetriever,
    OpenVikingStore,
    InMemoryOpenVikingClient,
)

# 创建 Agent 工具集
tools = create_openviking_tools(
    url="http://localhost:1933",
    profile="agent",
)

# 创建检索器
retriever = OpenVikingRetriever(
    url="http://localhost:1933",
    target_uri="viking://resources/myproject/",
    search_mode="find",
    limit=5,
)

# 创建 LangGraph Store
store = OpenVikingStore(
    root_uri="viking://user/memories/langgraph_store",
)
```
