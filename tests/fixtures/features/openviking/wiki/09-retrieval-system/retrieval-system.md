# 09 检索系统 (openviking/retrieve)

## 1. 模块概览

`openviking/retrieve/` 实现了 OpenViking 的核心检索能力——层次化目录递归检索、LLM 驱动的意图分析、以及记忆生命周期管理。

| 文件 | 类 | 说明 |
|---|---|---|
| `hierarchical_retriever.py` | `HierarchicalRetriever` | 层次化 BFS 递归检索 |
| `intent_analyzer.py` | `IntentAnalyzer` | LLM 意图分析 → 查询计划 |
| `memory_lifecycle.py` | - | 热度评分函数 |
| `retrieval_stats.py` | `RetrievalStatsCollector` | 线程安全检索统计 |

---

## 2. HierarchicalRetriever - 层次化检索器

### 2.1 核心算法

```python
class HierarchicalRetriever:
    """基于目录的层次化递归检索, 带重排序相关性评分"""
    
    async def retrieve(query, ctx, limit, mode, score_threshold, scope_dsl, level) -> QueryResult:
        """
        管道:
        1. 确定起始目录 (context_type → root URIs)
        2. 全局向量搜索 (top-K 候选)
        3. 合并起点 + 全局结果
        4. 递归搜索 (BFS 优先队列)
           - 搜索当前目录子项
           - 分数传播: final = α × child_score + (1-α) × parent_score
           - 收敛检测: 3 轮无变化 → 停止
        5. 转换为 MatchedContext (热度混合)
        """
```

### 2.2 常量

```python
MAX_CONVERGENCE_ROUNDS = 3   # 收敛检测轮数
MAX_RELATIONS = 5             # 最大关联上下文
GLOBAL_SEARCH_TOPK = 10       # 全局搜索结果数
LEVEL_URI_SUFFIX = {
    0: ".abstract.md",       # L0
    1: ".overview.md",       # L1
}
```

### 2.3 分数传播

```python
# alpha 权重 (默认可配置):
# child_contribution = alpha * child_score  (子节点自己的分数)
# parent_contribution = (1-alpha) * parent_score  (父目录的分数)
# final_score = child_contribution + parent_contribution
```

### 2.4 结果转换

```python
def _convert_to_matched_contexts(candidates, ctx) -> List[MatchedContext]:
    # 1. 语义分数 × 热度混合 (hotness_alpha 权重)
    # 2. 读取关联上下文 (relations, 最多 MAX_RELATIONS)
    # 3. L0/L1 级别: 追加 .abstract.md / .overview.md 后缀
```

### 2.5 搜索模式

```python
# find 模式: 全局搜索 (无会话上下文)
# search 模式: 会话感知搜索 (通过 IntentAnalyzer 生成查询计划)
```

---

## 3. IntentAnalyzer - 意图分析器

```python
class IntentAnalyzer:
    """LLM 驱动的查询意图分析 → 结构化查询计划"""
    
    async def analyze(
        compression_summary,   # 会话压缩摘要
        messages,              # 最近消息
        current_message,       # 当前用户消息
        context_type,          # 上下文类型
        target_abstract        # 目标摘要
    ) -> QueryPlan:
        """
        1. 构建上下文提示词
           - 压缩摘要 + 最近消息 + 当前消息
           - 渲染 retrieval.intent_analysis 提示词
        2. LLM 调用
        3. 解析 JSON → List[TypedQuery]
        4. 返回 QueryPlan (含类型化查询列表)
        """
```

### 3.1 TypedQuery

```python
@dataclass
class TypedQuery:
    query: str                         # 搜索查询文本
    context_type: Optional[str]        # memory / resource / skill
    target_dirs: Optional[List[str]]   # 目标目录 URI 列表
    level: Optional[int]               # 0/1/2 级别过滤
```

---

## 4. 记忆生命周期 (memory_lifecycle.py)

### 4.1 热度评分函数

```python
def hotness_score(active_count, updated_at, now, half_life_days=7.0) -> float:
    """
    score = sigmoid(log1p(active_count)) × exp(-decay × age_days)
    
    其中:
    - sigmoid(x) = 1 / (1 + e^(-x+1))  # 向右平移
    - decay = ln(2) / half_life_days   # 半衰期 7 天
    - age_days = (now - updated_at).days
    
    返回 0.0 当 updated_at 为 None
    """
```

### 4.2 应用场景

- 检索结果混合: `final_score = α × semantic_score + (1-α) × hotness_score`
- 记忆归档: `hotness_score < threshold` → 移动到 `_archive/`
- 向量搜索排序: 热度作为二级排序键

---

## 5. RetrievalStatsCollector - 检索统计

```python
class RetrievalStatsCollector:
    """线程安全的检索统计收集器单例"""
    
    def record_query(context_type, result_count, scores, latency_ms, rerank_used, rerank_fallback)
    
    def snapshot() -> RetrievalStats
    def reset()
    
    # RetrievalStats 包含:
    # - total_queries, total_results, zero_result_queries
    # - total_score_sum, max_score, min_score
    # - queries_by_type (按上下文类型)
    # - rerank_used, rerank_fallback
    # - avg_results_per_query, zero_result_rate, avg_score, avg_latency_ms
```

---

## 6. 检索流程完整示例

```
用户输入: "how do I configure authentication?"
    │
    ▼
IntentAnalyzer.analyze()
    → [
        TypedQuery(query="authentication configuration", 
                   context_type="resource", target_dirs=["viking://resources/myproject/"]),
        TypedQuery(query="auth setup steps",
                   context_type="memory", target_dirs=None)
      ]
    │
    ▼
HierarchicalRetriever.retrieve() × 2
    │
    对每个 TypedQuery:
    ├── _global_vector_search()  → top-10 候选
    ├── _merge_starting_points() → 过滤 L2, 重排序, 合并
    └── _recursive_search()
        ├── BFS 优先队列: [(-score, uri), ...]
        ├── 每轮: 搜索子项, 传播分数
        └── 3 轮收敛 → 停止
    │
    ▼
合并所有结果 → _convert_to_matched_contexts()
    → [MatchedContext(uri, score, content, abstract, relations), ...]
```
