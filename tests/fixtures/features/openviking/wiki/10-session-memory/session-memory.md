# 10 会话 & 记忆 (openviking/session)

## 1. 模块概览

`openviking/session/` 实现了 Agent 会话生命周期管理、长期记忆提取、记忆去重、以及 Working Memory v2 系统。

| 文件 | 用途 |
|---|---|
| `session.py` | 会话核心: 消息管理, 两阶段提交, 存档, Working Memory v2 |
| `compressor.py` | 会话压缩器 v1: 8 类记忆提取 + LLM 去重 |
| `compressor_v2.py` | 会话压缩器 v2: 记忆模板化系统 (ReAct 编排) |
| `memory_extractor.py` | 记忆提取器: LLM → 8 类候选记忆 |
| `memory_deduplicator.py` | 记忆去重器: 向量预过滤 + LLM 决策 |
| `memory_archiver.py` | 冷热分离: 低热度记忆归档 |
| `tool_skill_utils.py` | 工具/技能名称校准与统计 |
| `memory/` | 记忆模板化系统 v2 |

---

## 2. Session 核心 (session.py)

### 2.1 数据模型

```python
@dataclass
class SessionMeta:
    session_id: str
    created_at: str          # ISO 时间戳
    updated_at: str
    participants: List[str]  # [user:alice, agent:bot1]
    message_count: int
    commit_count: int
    memories_extracted: Dict[str, int]  # 按类别计数
    llm_token_usage: Dict[str, int]
    embedding_token_usage: Dict[str, int]
    # WMv2 字段:
    pending_tokens: int       # 待处理 token 数
    keep_recent_count: int    # 保留的最近消息数

@dataclass
class Usage:
    uri: str
    type: str                 # context / skill
    contribution: str         # 贡献描述
    input: str                # 输入
    output: str               # 输出
    success: bool
    timestamp: str
```

### 2.2 Session 类

```python
class Session:
    # 构造
    def __init__(viking_fs, vikingdb_manager, session_compressor, user, ctx, session_id)
    
    # 加载/持久化
    async def load()                    # 读取 messages.jsonl + history/ + .meta.json
    async def exists() -> bool
    async def ensure_exists()
    
    # 消息管理
    async def add_message(role, parts, role_id, created_at) -> Message
        # 1. 追加 Message 到内存列表
        # 2. 更新 SessionStats
        # 3. 维护 WMv2 pending_tokens (滑动窗口)
        # 4. 持久化到 messages.jsonl
    
    async def update_tool_part(message_id, tool_id, output, status)
        # 更新 ToolPart.output/status 并持久化
    
    # 上下文/技能使用记录
    async def used(contexts, skill)
    
    # 提交 (两阶段)
    async def commit_async(keep_recent_count=0) -> Dict
        """
        Phase 1 (分布式锁下):
          1. 分割消息: 保留 keep_recent_count 条最近消息
          2. 将旧消息归档到 archive_{commit_count}/messages.jsonl
          3. 保留尾部消息到 messages.jsonl
          4. 生成 Working Memory v2 (.overview.md)
        
        Phase 2 (后台任务):
          1. 调用 compressor.extract_long_term_memories()
          2. 写入 relations
          3. 写入 memory_diff.json
          4. 更新 active_count
          5. redo-log 恢复
        """
```

### 2.3 Working Memory v2

```python
WM_SEVEN_SECTIONS = [
    "Session Title",          # 会话标题
    "Current State",          # 当前状态
    "Task & Goals",           # 任务与目标
    "Key Facts & Decisions",  # 关键事实与决策
    "Files & Context",        # 文件与上下文
    "Errors & Corrections",   # 错误与修正
    "Open Issues",            # 待解决问题
]

# 更新策略:
# 首次提交: 纯 LLM 完成生成 7 部分结构化文档
# 后续提交: 使用 update_working_memory 工具
#   - KEEP: 保留该部分
#   - UPDATE: 修改该部分
#   - APPEND: 追加内容到该部分
```

---

## 3. 记忆提取器 (memory_extractor.py)

### 3.1 8 类记忆

```python
class MemoryCategory(Enum):
    PROFILE = "profile"        # 用户画像 (姓名, 角色, 背景)
    PREFERENCES = "preferences"  # 偏好 (代码风格, 语言, 格式)
    ENTITIES = "entities"      # 实体 (人名, 项目名, API)
    EVENTS = "events"          # 事件 (时间线, 里程碑)
    CASES = "cases"            # 案例 (问题→方案→结果)
    PATTERNS = "patterns"      # 模式 (重复行为, 工作流)
    TOOLS = "tools"            # 工具使用经验
    SKILLS = "skills"          # 技能使用经验
```

### 3.2 提取流程

```python
class MemoryExtractor:
    CATEGORY_DIRS = {
        PROFILE: "memories/profile.md",
        PREFERENCES: "memories/preferences/",
        ENTITIES: "memories/entities/",
        EVENTS: "memories/events/",
        CASES: "memories/cases/",
        PATTERNS: "memories/patterns/",
        TOOLS: "memories/tools/",
        SKILLS: "memories/skills/",
    }
    
    async def extract(context, user, session_id) -> List[CandidateMemory]:
        # 1. 格式化会话消息
        # 2. 检测输出语言 (Unicode 范围检测)
        # 3. LLM 调用提取候选记忆
        # 4. 规范化 JSON 响应
        # 5. 工具/技能候选: 与 ToolPart 校准
        # 6. 创建 CandidateMemory / ToolSkillCandidateMemory
```

### 3.3 工具/技能记忆特殊处理

```python
# 工具记忆内容结构:
"""
# {tool_name}

## 工具描述
{static_description}

## 调用统计
- 总调用次数: N
- 成功率: X%
- 平均耗时: Yms
- 平均 Token: Z

## 使用指南
{merged_guidelines}

## 最佳场景
{best_for}
...
"""

# 统计累加 (Python):
# - total_calls, success_count, avg_time, avg_tokens
# - 从现有记忆解析旧统计, 与新统计合并
```

---

## 4. 记忆去重器 (memory_deduplicator.py)

### 4.1 两步去重

```python
class MemoryDeduplicator:
    async def deduplicate(candidate, ctx) -> DedupResult:
        # Step 1: 向量预过滤
        # - 生成候选记忆的嵌入向量
        # - 在向量存储中搜索相似记忆 (阈值过滤)
        # - 包含批次内记忆 (跨候选去重)
        
        # Step 2: LLM 决策
        # - 渲染 compression.dedup_decision 提示词
        # - 对每个相似记忆决策: MERGE / DELETE
        # - 对候选记忆决策: SKIP / CREATE / NONE
```

### 4.2 决策枚举

```python
class DedupDecision(Enum):
    SKIP = "skip"      # 跳过, 不创建
    CREATE = "create"  # 创建新记忆
    NONE = "none"      # 不创建候选, 仅处理已有记忆

class MemoryActionDecision(Enum):
    MERGE = "merge"    # 合并到已有记忆
    DELETE = "delete"  # 删除已有记忆
```

---

## 5. 记忆模板化系统 v2 (memory/)

### 5.1 YAML Schema 定义

```yaml
# memory/templates/preferences.yaml
memory_type: preferences
description: User preferences and habits
directory: preferences
filename_template: "{{ name }}.md"
operation_mode: upsert
fields:
  - name: name
    field_type: STRING
    description: Unique name identifier
    merge_op: IMMUTABLE
  - name: content
    field_type: STRING
    description: Preference details
    merge_op: PATCH
  - name: category
    field_type: STRING
    description: Preference category
    merge_op: REPLACE
```

### 5.2 ExtractLoop - ReAct 编排器

```python
class ExtractLoop:
    """简化的 ReAct 编排器: 单次 LLM 调用 + 工具使用, 迭代至多 max_iterations 次"""
    
    async def run() -> Tuple[Optional[Any], List[Dict]]:
        # 0. Prefetch (预先读取已有记忆)
        # 1. 构建 System Message (含 JSON Schema)
        # 2. ReAct 循环:
        #    a. LLM 调用 (含工具定义)
        #    b. 如有工具调用 → 执行 → 注入结果 → 继续
        #    c. 如有结构化输出 → 检查未读文件 → 必要时重新获取
        #    d. 最后一次迭代 → 强制输出最终结果
        # 3. resolve_operations() → ResolvedOperations
```

### 5.3 合并操作 (merge_op/)

| MergeOp | 适用类型 | 行为 |
|---|---|---|
| `PATCH` | STRING | 搜索替换 (StrPatch) → 模糊匹配 → 全文替换回退 |
| `REPLACE` | 所有类型 | 完全替换现有值 |
| `SUM` | INT64, FLOAT32 | 累加数值 |
| `IMMUTABLE` | 所有类型 | 一旦设定不可更改 |

### 5.4 PATCH 搜索替换策略

```python
class MultiSearchReplaceDiffStrategy:
    """基于 RooCode 的多搜索替换策略"""
    
    # Diff 格式:
    # <<<<<<< SEARCH
    # 要查找的文本
    # =======
    # 替换为的文本
    # >>>>>>> REPLACE
    
    # 匹配策略:
    # 1. 精确子串匹配 (快速路径)
    # 2. 逐行模糊匹配 (Levenshtein 距离)
    # 3. 缩进保持
    # 4. 行号处理 (添加/剥离)
```

### 5.5 记忆更新器 (MemoryUpdater)

```python
class MemoryUpdater:
    async def apply_operations(operations, ctx, ...) -> MemoryUpdateResult:
        # 1. URI 补充 (generate_uri with Jinja2)
        # 2. 对每个 upsert:
        #    a. 读取已有内容 (或使用预取的)
        #    b. 按字段应用 MergeOp
        #    c. 保留系统管理的元数据 (source_trajectories)
        #    d. 序列化 (含 HTML 注释元数据)
        #    e. 写入 VikingFS
        # 3. 对每个 delete: rm
        # 4. 向量化已写入/已编辑的记忆
        # 5. 生成概览 (.overview.md)
```

### 5.6 Agent 记忆: 两阶段提取

```python
class AgentTrajectoryContextProvider:
    """Phase 1: 提取执行轨迹摘要"""
    # 严格的 JSON 输出: 一次会话 = 一个轨迹 (内部编号步骤)
    # 仅暴露 trajectories schema

class AgentExperienceContextProvider:
    """Phase 2: 将轨迹整合为经验"""
    # 输入: 轨迹 + 至多 5 个候选经验
    # 输出: 经验条目 (experience_name, content, supersedes)
    # 系统管理 source_trajectories (LLM 不输出此字段)
```

---

## 6. 记忆归档器 (memory_archiver.py)

```python
class MemoryArchiver:
    """冷热分离: 低热度记忆自动归档"""
    
    async def scan(scope_uri, ctx) -> List[ArchivalCandidate]:
        # 滚动向量索引查找 L2 记忆
        # 计算 hotness_score
        # 返回按分数升序的冷记忆候选
    
    async def archive(candidates, ctx) -> ArchivalResult:
        # 移动到 {parent}/_archive/{filename}
    
    async def restore(archived_uri, ctx) -> bool:
        # 移除 _archive/ 段还原
```

---

## 7. 会话压缩器 v1 vs v2

| 特性 | v1 (compressor.py) | v2 (compressor_v2.py) |
|---|---|---|
| 记忆分类 | 8 类固定 | YAML Schema 可扩展 |
| 编排方式 | 线性 LLM 调用 | ReAct 循环 + 工具 |
| 去重 | LLM 辅助 | 向量 + LLM |
| 合并策略 | MERGE/DELETE | PATCH/REPLACE/SUM/IMMUTABLE |
| Agent 记忆 | 不支持 | 两阶段提取 |
| 配置方式 | 硬编码 | YAML 模板驱动 |
