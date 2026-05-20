# 02 核心包 (openviking/core)

## 1. 模块概览

`openviking/core/` 定义了 OpenViking 的核心概念和基础数据结构，是整个系统的基石。

| 文件 | 用途 |
|---|---|
| `context.py` | Context / ContextType / ContextLevel 核心数据类型 |
| `directories.py` | 虚拟目录体系 (RBAC 三层结构) |
| `namespace.py` | 命名空间隔离策略 (user/agent 空间) |
| `uri_validation.py` | Viking URI 验证与路径安全 |
| `building_tree.py` | 资源解析树到 VikingFS 的映射结构 |
| `skill_loader.py` | 技能 (SKILL.md) 加载与验证 |
| `path_variables.py` | 路径变量提供者 (日期/时间) |
| `mcp_converter.py` | MCP 协议工具 ↔ OpenViking 技能转换 |

---

## 2. context.py - 核心上下文类型

### 2.1 ContextLevel 枚举

```python
class ContextLevel(IntEnum):
    L0_ABSTRACT = 0    # 一句话摘要 (~100 tokens)
    L1_OVERVIEW = 1    # 核心信息概览 (~2k tokens)
    L2_DETAIL = 2      # 完整原始数据
```

### 2.2 ContextType 枚举

```python
class ContextType(str, Enum):
    RESOURCE = "resource"  # 项目文档/仓库/网页等
    MEMORY = "memory"      # 用户偏好/Agent 经验
    SKILL = "skill"        # Agent 技能定义
    SESSION = "session"    # 会话存档
```

### 2.3 Context 数据类

核心数据模型，用于在 VikingFS 中表示一个上下文节点：

| 字段 | 类型 | 说明 |
|---|---|---|
| `uri` | `str` | Viking URI (如 `viking://resources/my_project/docs/api.md`) |
| `context_type` | `ContextType` | 上下文分类 |
| `level` | `ContextLevel` | L0/L1/L2 分级 |
| `content` | `str` | 文本内容 |
| `abstract` | `str` | L0 摘要 |
| `overview` | `str` | L1 概览 |
| `name` | `str` | 显示名称 |
| `description` | `Optional[str]` | 描述 |
| `tags` | `List[str]` | 标签列表 |
| `account_id` | `Optional[str]` | 租户 ID |
| `owner_user_id` | `Optional[str]` | 属主用户 ID |
| `owner_agent_id` | `Optional[str]` | 属主 Agent ID |
| `active_count` | `int` | 活跃度计数 (影响热度评分) |
| `created_at` | `Optional[str]` | 创建时间 |
| `updated_at` | `Optional[str]` | 更新时间 |
| `source_session` | `Optional[str]` | 来源会话 ID |
| `language` | `Optional[str]` | 语言 (en/zh/ja/ko...) |
| `extra` | `Dict[str, Any]` | 扩展元数据 |

### 2.4 Vectorize 数据类

嵌入处理配置：

| 字段 | 说明 |
|---|---|
| `dense` | 是否生成密集向量 |
| `sparse` | 是否生成稀疏向量 |
| `model` | 指定嵌入模型 (可选) |

---

## 3. directories.py - 虚拟目录体系

### 3.1 三层 RBAC 虚拟目录结构

```
viking://
├── resources/        # 全局共享资源 (所有用户可见)
│   ├── {project}/
│   │   ├── docs/
│   │   └── src/
│   └── ...
├── user/             # 用户私有空间 (按 user_id 隔离)
│   └── {user_id}/
│       ├── memories/
│       │   ├── profile.md
│       │   ├── preferences/
│       │   └── ...
│       └── privacy/
└── agent/            # Agent 私有空间 (按 agent_id 隔离)
    └── {agent_id}/
        ├── skills/
        ├── memories/
        │   ├── trajectories/
        │   └── experiences/
        └── instructions/
```

### 3.2 根目录常量

```python
ROOT_RESOURCES = "viking://resources"
ROOT_USER = "viking://user"
ROOT_AGENT = "viking://agent"
ROOT_SESSION = "viking://session"
ROOT_SYSTEM = "viking://local/_system"
```

### 3.3 特殊系统目录

| URI | 用途 |
|---|---|
| `viking://local/_system/` | 内部系统文件 |
| `viking://local/_system/redo/` | 崩溃恢复 RedoLog |
| `viking://local/_system/locks/` | 分布式锁文件 |
| `viking://resources/.watch_tasks.json` | 资源监控任务 |

---

## 4. namespace.py - 命名空间隔离

### 4.1 核心函数

| 函数 | 用途 |
|---|---|
| `canonical_user_root(user_id)` | 用户空间根: `viking://user/{user_id}` |
| `canonical_agent_root(agent_id)` | Agent 空间根: `viking://agent/{agent_id}` |
| `to_user_space(uri, user_id)` | 将 URI 映射到用户空间 |
| `to_agent_space(uri, agent_id)` | 将 URI 映射到 Agent 空间 |
| `user_space_fragment(user_id)` | `user/{user_id}` 片段 |
| `agent_space_fragment(agent_id)` | `agent/{agent_id}` 片段 |

### 4.2 隔离策略

```python
# 配置驱动的隔离选项
memory.isolate_user_scope_by_agent     # 用户记忆按 Agent 隔离
memory.isolate_agent_scope_by_user     # Agent 记忆按用户隔离
memory.enable_role_id_memory_isolate  # 基于会话参与者角色 ID 隔离
```

### 4.3 命名空间策略

`NamespacePolicy` 控制 URI 在不同隔离模式下的路由:
- 单租户模式: 所有 URI 共享同一空间
- 多租户模式: 通过 `account_id` 前缀隔离租户
- 角色隔离模式: 根据消息的 `role_id` (如 `user:alice`, `agent:bot1`) 路由到不同子空间

---

## 5. uri_validation.py - URI 验证

### 5.1 VikingURI 类

```python
class VikingURI:
    SCHEME = "viking"
    
    @staticmethod
    def parse(uri: str) -> ParsedURI:
        # 解析 viking://resources/my_project/docs/api.md
        # → (scope="resources", path=["my_project", "docs", "api.md"])
    
    @staticmethod
    def validate(uri: str) -> bool:
        # 验证格式: viking://{scope}/{path}
    
    @staticmethod
    def is_valid_scope(scope: str) -> bool:
        # 有效范围: resources, user, agent, session, local
```

### 5.2 路径安全函数

| 函数 | 用途 |
|---|---|
| `validate_path_segment(name)` | 拒绝特殊字符 (不能含 /, \0) |
| `sanitize_name(name)` | 清理文件名 (替换非法字符) |
| `is_safe_uri(uri)` | 检查路径遍历攻击 |
| `validate_rel_path(rel_path)` | 验证相对路径安全 |

---

## 6. building_tree.py - 构建树映射

### 6.1 BuildingTree 数据类

解析后的文件树到 VikingFS 的中间表示：

```python
@dataclass
class BuildingTree:
    root_uri: str                    # 根 URI
    source_path: str                 # 原始来源路径
    nodes: List[BuildingNode]        # 节点列表
    temp_dir: Optional[str]          # 临时目录
    source_format: str               # 来源格式 (git, url, local...)
```

### 6.2 BuildingNode

```python
@dataclass
class BuildingNode:
    rel_path: str                    # 相对路径
    target_uri: str                  # 目标 Viking URI
    is_dir: bool                     # 是否为目录
    content_path: Optional[str]      # 内容文件路径 (临时)
    meta: Dict[str, Any]             # 元数据
```

---

## 7. skill_loader.py - 技能加载

### 7.1 技能格式

技能文件遵循 `SKILL.md` 规范，使用 YAML frontmatter:

```markdown
---
name: search_code
description: Search and analyze code in repositories
tools:
  - grep
  - read
parameters:
  pattern:
    type: string
    description: Search pattern
---
# search_code

## Description
...
```

### 7.2 SkillLoader 类

| 方法 | 用途 |
|---|---|
| `load_skill(uri)` | 从 VikingFS 加载并解析 SKILL.md |
| `load_skills_from_dir(uri)` | 扫描目录加载所有技能 |
| `validate_skill(skill_dict)` | 验证技能定义完整性 |
| `list_skills()` | 列出所有已加载技能 |
| `get_skill(name)` | 按名称获取技能 |
| `skill_to_tool_schema(skill)` | 将技能转换为 LLM tool schema |

### 7.3 技能类型

| 类型 | 说明 |
|---|---|
| `system` | 系统内置技能 |
| `user` | 用户自定义技能 |
| `agent` | Agent 作用域技能 |

---

## 8. path_variables.py - 路径变量

### 8.1 变量提供者

```python
class CalendarVariableProvider:
    """提供日期/时间相关的路径变量"""
    # {year}, {month}, {day}, {hour}, {minute}
    # 示例: viking://resources/images/{year}/{month}/{day}/
    #     → viking://resources/images/2026/05/19/
```

### 8.2 变量模式

| 变量 | 示例值 |
|---|---|
| `{year}` | `2026` |
| `{month}` | `05` |
| `{day}` | `19` |
| `{hour}` | `14` |
| `{minute}` | `30` |
| `{user_id}` | `alice_abc123` |
| `{agent_id}` | `bot_xyz789` |
| `{account_id}` | `acct_001` |

---

## 9. mcp_converter.py - MCP 协议转换

### 9.1 功能

将 Model Context Protocol (MCP) 工具定义转换为 OpenViking 技能格式，使外部 MCP 服务可以被 OpenViking Agent 使用。

### 9.2 核心函数

| 函数 | 用途 |
|---|---|
| `mcp_tool_to_skill(tool_def)` | MCP Tool → SKILL.md 格式 |
| `mcp_tools_to_skills(tools)` | 批量转换 |
| `skill_to_mcp_endpoint(skill)` | 反向: 技能 → MCP 端点描述 |

### 9.3 转换映射

| MCP 字段 | SKILL.md 字段 |
|---|---|
| `name` | `name` |
| `description` | `description` |
| `inputSchema.properties` | `parameters` |
| `inputSchema.required` | `required` 标记 |
