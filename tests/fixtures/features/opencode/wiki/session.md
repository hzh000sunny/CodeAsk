# Session 管理系统

## 概述

Session 是 Opencode 中的核心会话管理单元，代表用户与 AI 助手之间的一次完整对话。每个 Session 拥有独立的生命周期、消息历史、权限控制和事件溯源机制。系统采用 **Effect-TS** 作为依赖注入与副作用管理的核心框架，以 **Drizzle ORM + SQLite** 作为持久化存储，并通过 **事件溯源 (Event Sourcing)** 模式保证数据一致性与可追溯性。

---

## 数据模型

### 1. Info（Session 核心数据结构）

```typescript
// 文件: /home/hzh/wiki/opencode/packages/opencode/src/session/session.ts

interface Info {
  id: SessionID        // Snowflake 风格降序 ID，前缀 "ses_"
  slug: string         // 随机短标识符，用于 URL 友好引用
  projectID: ProjectID // 所属项目 ID
  workspaceID?: WorkspaceID  // 所属工作空间 ID（可选）
  directory: string    // 会话在文件系统中的绝对路径
  path?: string        // 相对于 worktree 的路径
  parentID?: SessionID // 父会话 ID（子会话场景）

  title: string        // 会话标题
  agent?: string       // 使用的 Agent 名称
  model?: {            // 使用的模型配置
    id: ModelID
    providerID: ProviderID
    variant?: string   // 模型变体
  }
  version: string      // 创建时的 Opencode 版本号
  summary?: {          // 会话摘要统计
    additions: number  // 新增行数
    deletions: number  // 删除行数
    files: number      // 涉及文件数
    diffs?: FileDiff[] // 文件差异详情
  }
  share?: {            // 分享配置
    url: string
  }
  permission?: Permission.Ruleset  // 权限规则集
  revert?: {           // 回退点（用于撤销操作）
    messageID: MessageID
    partID?: PartID
    snapshot?: string
    diff?: string
  }
  time: {
    created: number     // 创建时间戳
    updated: number     // 最后更新时间戳
    compacting?: number // 压缩时间戳
    archived?: number   // 归档时间戳
  }
}
```

### 2. 数据库表结构

系统使用三张核心表来存储 Session 及其消息数据：

```
┌─────────────────────────────────────────────────────────────────────┐
│                         session                                     │
├──────────────────┬──────────────────────────────────────────────────┤
│ id               │ TEXT PRIMARY KEY   → "ses_xxx"                   │
│ project_id       │ TEXT NOT NULL      → 外键 → project.id           │
│ workspace_id     │ TEXT               → 工作空间 ID                   │
│ parent_id        │ TEXT               → 自引用 → session.id          │
│ slug             │ TEXT NOT NULL      → URL 友好标识                  │
│ directory        │ TEXT NOT NULL      → 绝对路径                      │
│ path             │ TEXT               → 相对路径                      │
│ title            │ TEXT NOT NULL      → 标题                          │
│ version          │ TEXT NOT NULL      → Opencode 版本                │
│ agent            │ TEXT               → Agent 名称                   │
│ model            │ TEXT (JSON)        → { id, providerID, variant } │
│ share_url        │ TEXT               → 分享 URL                     │
│ summary_additions│ INTEGER            → 新增行数                      │
│ summary_deletions│ INTEGER            → 删除行数                      │
│ summary_files    │ INTEGER            → 涉及文件数                    │
│ summary_diffs    │ TEXT (JSON)        → FileDiff[]                  │
│ revert           │ TEXT (JSON)        → 回退点数据                    │
│ permission       │ TEXT (JSON)        → 权限规则集                    │
│ time_created     │ INTEGER            → 创建时间                      │
│ time_updated     │ INTEGER            → 更新时间                      │
│ time_compacting  │ INTEGER            → 压缩时间                      │
│ time_archived    │ INTEGER            → 归档时间 (NULL=未归档)        │
├──────────────────┴──────────────────────────────────────────────────┤
│ INDEX: session_project_idx     ON (project_id)                      │
│ INDEX: session_workspace_idx   ON (workspace_id)                    │
│ INDEX: session_parent_idx      ON (parent_id)                       │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                         message                                     │
├──────────────────┬──────────────────────────────────────────────────┤
│ id               │ TEXT PRIMARY KEY   → "msg_xxx"                   │
│ session_id       │ TEXT NOT NULL      → 外键 → session.id           │
│ time_created     │ INTEGER            → 创建时间                      │
│ time_updated     │ INTEGER            → 更新时间                      │
│ data             │ TEXT (JSON) NOT NULL → MessageV2.Info            │
├──────────────────┴──────────────────────────────────────────────────┤
│ INDEX: message_session_time_created_id_idx                          │
│        ON (session_id, time_created, id)                            │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                          part                                       │
├──────────────────┬──────────────────────────────────────────────────┤
│ id               │ TEXT PRIMARY KEY   → "prt_xxx"                   │
│ message_id       │ TEXT NOT NULL      → 外键 → message.id           │
│ session_id       │ TEXT NOT NULL      → 外键 → session.id           │
│ time_created     │ INTEGER            → 创建时间                      │
│ time_updated     │ INTEGER            → 更新时间                      │
│ data             │ TEXT (JSON) NOT NULL → MessageV2.Part            │
├──────────────────┴──────────────────────────────────────────────────┤
│ INDEX: part_message_id_id_idx ON (message_id, id)                   │
│ INDEX: part_session_idx        ON (session_id)                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 3. 实体关系图

```
┌──────────┐        ┌──────────┐        ┌──────────┐
│  Project  │◄───────│ Session  │────────│ Session  │  parent_id (自引用)
│          │        │          │        │ (parent) │
└──────────┘        └────┬─────┘        └──────────┘
                         │
                         │ 1:N
                         ▼
                   ┌──────────┐
                   │ Message  │
                   └────┬─────┘
                        │
                        │ 1:N
                        ▼
                   ┌──────────┐
                   │   Part   │
                   └──────────┘

Session  ←──  自引用 (parentID)  → 子会话 (Child Sessions)
Session  ←──  1:N  →  Message (会话消息)
Message  ←──  1:N  →  Part    (消息部件)
```

### 4. ID 生成策略

所有 ID 均采用 Snowflake 风格的单调生成策略：

| ID 类型 | 前缀 | 方向 | 示例格式 |
|---------|------|------|---------|
| SessionID | `ses_` | 降序 (descending) | `ses_<12位hex时间戳><14位base62随机>` |
| MessageID | `msg_` | 升序 (ascending) | `msg_<12位hex时间戳><14位base62随机>` |
| PartID | `prt_` | 升序 (ascending) | `prt_<12位hex时间戳><14位base62随机>` |

- **SessionID 采用降序**：使得最新的 Session 在数据库索引中排在前面，优化查询性能。
- **MessageID 和 PartID 采用升序**：保证消息和部件按时间自然排序。
- 所有 ID 均为 26 字符长度（不含前缀），由 `Identifier.create(prefix, direction)` 生成。

---

## Session 生命周期

### 创建 (Create)

```
用户请求
    │
    ▼
Session.create(input?)
    │
    ├── 获取实例上下文 (InstanceState.context)
    │    ├── ctx.directory
    │    └── sessionPath(worktree, cwd) → 计算相对路径
    │
    ├── 获取工作空间 ID (InstanceState.workspaceID)
    │
    ▼
createNext(...)  ←── 核心创建函数
    │
    ├── 生成 SessionID: SessionID.descending()
    ├── 生成 Slug: Slug.create()
    ├── 生成标题: input.title ?? createDefaultTitle(isChild)
    │    ├── 父会话: "New session - 2026-05-11T..."
    │    └── 子会话: "Child session - 2026-05-11T..."
    ├── 设置时间戳: created = updated = Date.now()
    │
    ├── 发布事件:
    │    ├── sync.run(Event.Created, { sessionID, info })
    │    │    └── 投影器将数据写入 session 表
    │    └── bus.publish(Event.Updated, { sessionID, info })
    │         └── 向后兼容的 bus 事件
    │
    └── 返回 Info 对象
```

默认标题格式：
- 父会话：`New session - <ISO 8601 timestamp>`（如 `New session - 2026-05-11T10:30:00.000Z`）
- 子会话：`Child session - <ISO 8601 timestamp>`

可以使用 `isDefaultTitle(title)` 判断标题是否为自动生成。

### 更新 (Update)

所有更新操作通过 `patch(sessionID, info)` 统一处理：

```
setTitle / setArchived / setPermission / setRevert / setSummary / touch
    │
    ▼
patch(sessionID, Partial<Info>)
    │
    ├── sync.run(Event.Updated, { sessionID, info })
    │    └── 投影器根据 info 中的字段更新 session 表
    │
    └── 自动发布 bus 事件通知订阅者
```

**各更新操作详解：**

| 操作 | 输入 | 更新字段 |
|------|------|---------|
| `setTitle` | `{ sessionID, title }` | `title` |
| `setArchived` | `{ sessionID, time? }` | `time.archived` |
| `setPermission` | `{ sessionID, permission }` | `permission`, `time.updated` |
| `setRevert` | `{ sessionID, revert?, summary? }` | `revert`, `summary`, `time.updated` |
| `clearRevert` | `sessionID` | `revert: null`, `time.updated` |
| `setSummary` | `{ sessionID, summary? }` | `summary`, `time.updated` |
| `touch` | `sessionID` | `time.updated` (仅更新最后修改时间) |

### 归档/取消归档 (Archive/Unarchive)

```
setArchived({ sessionID, time })
    │
    ├── time = undefined → 取消归档 (time.archived = null)
    │    └── 会话重新出现在活跃列表中
    │
    └── time = Date.now() → 归档
         └── 会话从默认查询中隐藏
              (listGlobal 默认过滤 time_archived IS NULL 的记录)
```

### Fork（派生）

```
fork({ sessionID, messageID? })
    │
    ├── 获取原始 Session
    ├── 生成派生标题: getForkedTitle(title)
    │    └── "My Session" → "My Session (fork #1)"
    │    └── "My Session (fork #1)" → "My Session (fork #2)"
    │
    ├── 创建新 Session (标���和路径与原会话相同)
    │
    ├── 复制消息:
    │    ├── 遍历原会话消息 (按时间升序)
    │    ├── 如果指定了 messageID: 只复制到该消息之前
    │    ├── 为每条消息创建新 ID (MessageID.ascending())
    │    ├── 建立 ID 映射表 (旧 ID → 新 ID)
    │    ├── 维护 assistant.parentID 的引用关系
    │    └── 为每个 Part 创建新 ID (PartID.ascending())
    │         └── 处理 compaction part 的 tail_start_id 映射
    │
    └── 返回新 Session 的 Info
```

### 删除 (Remove)

```
remove(sessionID)
    │
    ├── 获取 Session Info
    ├── 递归删除所有子会话 (children → remove)
    │
    ├── 发布删除事件:
    │    └── sync.run(Event.Deleted, { sessionID, info })
    │
    ├── 清理事件流:
    │    └── sync.remove(sessionID)
    │         └── 删除 EventSequenceTable 中的记录
    │         └── 删除 EventTable 中的记录
    │
    └── 级联删除:
         ├── session 表删除 → 级联删除所有 message
         ├── message 表删除 → 级联删除所有 part
         └── 外键约束 ON DELETE CASCADE 自动处理
```

**注意**：删除时会检查 InstanceState 是否存在。如果不存在（例如清理损坏的会话），会跳过事件发布步骤，确保清理操作总能执行。

---

## 事件溯源机制

### 事件定义

Session 系统定义了 5 种事件，其中前 3 种是同步事件（写入数据库），后 2 种是纯总线事件（仅通知）：

```
┌──────────────────────────────────────────────────────────────────┐
│                     Session Events                               │
├──────────────┬─────────┬──────────────┬─────────────────────────┤
│ 事件类型      │ 版本    │ 聚合根       │ 说明                     │
├──────────────┼─────────┼──────────────┼─────────────────────────┤
│ session      │ 1       │ sessionID    │ 会话创建，投影器写入      │
│ .created     │         │              │ session 表                │
├──────────────┼─────────┼──────────────┼─────────────────────────┤
│ session      │ 1       │ sessionID    │ 会话更新，投影器更新      │
│ .updated     │         │              │ session 表对应字段        │
│              │         │              │ (busSchema用CreatedSchema) │
├──────────────┼─────────┼──────────────┼─────────────────────────┤
│ session      │ 1       │ sessionID    │ 会话删除，投影器删除      │
│ .deleted     │         │              │ session 记录              │
├──────────────┼─────────┼──────────────┼─────────────────────────┤
│ session      │ N/A     │ N/A (Bus)    │ 文件差异变更通知          │
│ .diff        │         │              │                           │
├──────────────┼─────────┼──────────────┼─────────────────────────┤
│ session      │ N/A     │ N/A (Bus)    │ 会话错误通知              │
│ .error       │         │              │ (携带 Assistant error)    │
└──────────────┴─────────┴──────────────┴─────────────────────────┘
```

同样，Message 系统定义了 5 种事件：

```
┌──────────────────────────────────────────────────────────────────┐
│                    Message Events (MessageV2)                     │
├──────────────────┬─────────┬──────────────┬─────────────────────┤
│ 事件类型          │ 版本    │ 聚合根       │ 说明                 │
├──────────────────┼─────────┼──────────────┼─────────────────────┤
│ message.updated  │ 1       │ sessionID    │ 消息创建/更新        │
├──────────────────┼─────────┼──────────────┼─────────────────────┤
│ message.removed  │ 1       │ sessionID    │ 消息删除             │
├──────────────────┼─────────┼──────────────┼─────────────────────┤
│ message.part     │ 1       │ sessionID    │ 部件创建/更新        │
│ .updated         │         │              │                      │
├──────────────────┼─────────┼──────────────┼─────────────────────┤
│ message.part     │ N/A     │ N/A (Bus)    │ 部件增量更新 (流式)  │
│ .delta           │         │              │                      │
├──────────────────┼─────────┼──────────────┼─────────────────────┤
│ message.part     │ 1       │ sessionID    │ 部件删除             │
│ .removed         │         │              │                      │
└──────────────────┴─────────┴──────────────┴─────────────────────┘
```

### 事件处理流程

```
sync.run(def, data)
    │
    ├── 1. 提取聚合 ID (data[def.aggregate])
    │    └── 例如 session.created → data.sessionID
    │
    ├── 2. 版本检查
    │    └── 确保是当前最新版本，不允许重放旧版本
    │
    ├── 3. 立即事务 (behavior: "immediate")
    │    │
    │    ├── a. 生成新事件 ID (EventID.ascending())
    │    │
    │    ├── b. 查询当前聚合的序列号
    │    │    └── SELECT seq FROM event_sequence
    │    │        WHERE aggregate_id = ?
    │    │    └── 新 seq = (row?.seq ?? -1) + 1
    │    │
    │    └── c. 调用 process(def, event, options)
    │         │
    │         ├── 执行投影器 (Projector)
    │         │    └── 将事件数据写入/更新对应的数据库表
    │         │        (session 表 / message 表 / part 表)
    │         │
    │         ├── 记录事件序列 (EventSequenceTable)
    │         │    └── INSERT OR REPLACE aggregate_id, seq
    │         │
    │         ├── 记录事件 (EventTable)  ← 仅 WORKSPACES 模式
    │         │    └── INSERT id, seq, aggregate_id, type, data
    │         │
    │         └── 发布事件到总线
    │              ├── ProjectBus.publish(def, data)
    │              │    └── 通知项目内订阅者
    │              │
    │              └── GlobalBus.emit("event", { ... })
    │                   └── 全局事件广播 (directory, project, workspace)
    │                   └── 用于跨项目的监听和同步
    │
    └── 4. 返回 void
```

### 数据流图

```
┌─────────────┐     SyncEvent.run()     ┌────────────┐
│  API 调用    │ ──────────────────────→ │  Event     │
│  (create,   │                         │  Processor │
│   update,   │                         └─────┬──────┘
│   delete)   │                               │
└─────────────┘                     ┌─────────┼─────────┐
                                    │         │         │
                                    ▼         ▼         ▼
                              ┌─────────┐ ┌───────┐ ┌──────────┐
                              │Projector│ │Event  │ │Bus       │
                              │(写DB)   │ │Store  │ │Publish   │
                              └────┬────┘ └───────┘ └────┬─────┘
                                   │                     │
                                   ▼                     ▼
                              ┌─────────┐          ┌──────────┐
                              │ SQLite  │          │ 实时通知  │
                              │ Tables  │          │ (WebSocket│
                              └─────────┘          │  / IPC)  │
                                                   └──────────┘
```

### Session.Updated 的特殊设计

`session.updated` 事件有一个重要的双重 Schema 设计：

- **schema (投影器使用)**：`UpdatedEventSchema` — 所有字段均为可选 (`Schema.optional`)，允许部分更新
- **busSchema (总线使用)**：`CreatedEventSchema` — 包含完整的 `Info` 对象

这意味着当 Session 被更新时，总线回插入接收到的总是完整的 `Info` 快照，而非部分更新数据。这样向后兼容旧的客户端，它们期望接收完整的 Session 数据。

---

## 消息存储模型

### 消息类型 (MessageV2.Info)

消息分为两种角色（使用判别联合类型 `role`）：

```
MessageV2.Info = User | Assistant

User:
  role: "user"
  time: { created }
  agent: string
  model: { providerID, modelID, variant? }
  system?: string
  tools?: Record<string, boolean>
  format?: OutputFormat (text | json_schema)

Assistant:
  role: "assistant"
  time: { created, completed? }
  parentID: MessageID    ← 关联的 User 消息 ID
  agent: string
  modelID: ModelID
  providerID: ProviderID
  variant?: string
  path: { cwd: string, root: string }
  cost: number
  tokens: { input, output, reasoning, cache: { read, write } }
  error?: AssistantError
  structured?: any
  finish?: string
  summary?: boolean       ← 是否为压缩摘要消息
```

### 部件类型 (MessageV2.Part)

每个消息包含多个 Part，通过 `discriminator: "type"` 区分。共 12 种部件类型：

| 部件类型 | 说明 | 关键字段 |
|---------|------|---------|
| `text` | 纯文本内容 | `text`, `synthetic?`, `ignored?`, `time?`, `metadata?` |
| `reasoning` | AI 推理过程 (思维链) | `text`, `time: { start, end? }`, `metadata?` |
| `tool` | 工具调用 | `callID`, `tool`, `state: ToolState (pending/running/completed/error)` |
| `file` | 文件引用 | `mime`, `url`, `filename?`, `source?` |
| `step-start` | 步骤开始标记 | `snapshot?` |
| `step-finish` | 步骤结束标记 | `reason`, `snapshot?`, `cost`, `tokens` |
| `snapshot` | 文件快照引用 | `snapshot` |
| `patch` | 文件补丁 | `hash`, `files: string[]` |
| `agent` | Agent 引用 | `name`, `source?` |
| `subtask` | 子任务定义 | `prompt`, `description`, `agent`, `model?` |
| `retry` | 重试记录 | `attempt`, `error`, `time: { created }` |
| `compaction` | 上下文压缩标记 | `auto`, `overflow?`, `tail_start_id?` |

### 工具状态生命周期

```
ToolPart.state: ToolState (discriminator: "status")

pending ───→ running ───→ completed
  │                         │
  │                         │ (time.compacted 设置时)
  │                         ▼
  │                    输出被截断为 "[Old tool result content cleared]"
  │
  └──────→ error
               │
               └── metadata.interrupted === true?
                    → 保留 metadata.output
```

### 消息与部件的查询

```
message-v2.ts 提供的关键查询函数:

stream(sessionID): Generator<WithParts>
  └── 分批加载 (每批 50 条) 从旧到新遍历所有消息及其部件

page({ sessionID, limit, before? }):
  └── 基于游标的分页，从新到旧返回
  └── before: base64url 编码的 { id, time } 游标

filterCompacted(msgs): WithParts[]
  └── 处理压缩消息，重排和过滤已摘要的旧消息

get({ sessionID, messageID }): WithParts
  └── 获取单条消息及其所有部件

parts(messageID): Part[]
  └── 获取指定消息的所有部件
```

### 转换为模型消息

`toModelMessages(input, model, options?)` 将内部的 `WithParts[]` 转换为 AI SDK 的 `ModelMessage[]`：

1. 遍历 User 和 Assistant 消息
2. User 消息：提取 text parts + file parts → `UIMessage { role: "user" }`
3. Assistant 消息：
   - text → `{ type: "text" }`
   - reasoning → `{ type: "reasoning" }` (含 providerMetadata)
   - tool (completed/error/pending/running) → `{ type: "tool-{name}" }`
   - step-start → `{ type: "step-start" }`
4. 处理媒体附件：对于不支持 tool_result 中媒体的 Provider，将附件提取为独立的 user message
5. 不同模型转换时 (`differentModel = true`)：丢掉 providerMetadata，reasoning 转为普通 text

---

## 成本计算 (getUsage)

`getUsage` 函数从模型响应的 `LanguageModelUsage` 中计算 Token 使用量和费用：

```
输入: { model, usage, metadata? }

Token 计算:
├── input = max(0, inputTokens - cacheReadTokens - cacheWriteTokens)
│    └── 从 inputTokens 中扣除缓存读写 token（AI SDK v6 已统一包含）
├── output = max(0, outputTokens - reasoningTokens)
├── reasoning = reasoningTokens
├── cache.read = cacheReadInputTokens
└── cache.write = cacheWriteInputTokens
        └── 兼容多 Provider 的缓存写入计数来源:
            ├── anthropic → metadata.anthropic.cacheCreationInputTokens
            ├── google-vertex-anthropic → metadata.vertex.cacheCreationInputTokens
            ├── bedrock → metadata.bedrock.usage.cacheWriteInputTokens
            └── venice → metadata.venice.usage.cacheCreationInputTokens

费用计算:
├── 若 input + cache.read > 200K → 使用 model.cost.experimentalOver200K 定价
├── cost = input * cost.input / 1M
│        + output * cost.output / 1M
│        + cache.read * cost.cache.read / 1M
│        + cache.write * cost.cache.write / 1M
│        + reasoning * cost.output / 1M  (reasoning 按 output 费率计费)
└── 使用 Decimal.js 精确计算，确保无浮点精度丢失
```

---

## 查询系统

### list (项目内查询)

```
list(input?): Effect<Info[]>
  ├── directory: string      → 按目录过滤
  ├── scope: "project"      → 项目级查询 (不按目录过滤)
  ├── path: string          → 按路径精确匹配或前缀匹配
  ├── workspaceID: string   → 按工作空间过滤
  ├── roots: boolean        → 仅返回根会话 (parent_id IS NULL)
  ├── start: number         → 仅返回此时间戳之后更新的会话
  ├── search: string        → 模糊搜索标题 (LIKE %search%)
  └── limit: number         → 数量限制 (默认 100)

SQL 条件构建:
  WHERE project_id = ?
    AND workspace_id = ?          (若指定)
    AND (path = ? OR path LIKE ?/%) (若有 path)
    AND parent_id IS NULL         (若 roots = true)
    AND time_updated >= ?         (若 start)
    AND title LIKE ?              (若 search)

  ORDER BY time_updated DESC
  LIMIT limit
```

### listGlobal (跨项目查询)

```
listGlobal(input?): Generator<GlobalInfo>
  ├── directory: string      → 按目录过滤
  ├── roots: boolean        → 仅根会话
  ├── start: number         → 时间下界
  ├── cursor: number        → 游标 (time_updated < cursor)
  ├── search: string        → 标题模糊搜索
  ├── limit: number         → 数量限制 (默认 100)
  └── archived: boolean     → 是否包含已归档会话 (默认 false)

特殊处理:
  ├── 默认过滤 time_archived IS NULL (排除已归档)
  ├── 额外 JOIN project 表获取项目摘要
  │    └── 返回 { ...Info, project: { id, name?, worktree } }
  └── ORDER BY time_updated DESC, id DESC
```

### children (子会话查询)

```
children(parentID): Effect<Info[]>
  └── SELECT * FROM session WHERE parent_id = ?
      └── 不使用排序和限制
```

---

## API 参考

### 核心操作

| 方法 | 签名 | 说明 |
|------|------|------|
| `create` | `(input?: CreateInput) => Effect<Info>` | 创建新会话，生成 title/slug/id |
| `fork` | `(input: ForkInput) => Effect<Info, NotFound>` | 派生会话，可选复制到指定消息为止 |
| `get` | `(id: SessionID) => Effect<Info, NotFound>` | 按 ID 获取会话详情 |
| `remove` | `(sessionID: SessionID) => Effect<void, NotFound>` | 递归删除会话及其所有子会话 |

### 更新操作

| 方法 | 签名 | 说明 |
|------|------|------|
| `setTitle` | `({ sessionID, title }) => Effect<void>` | 更新会话标题 |
| `setArchived` | `({ sessionID, time? }) => Effect<void>` | 归档/取消归档 (time=undefined 取消) |
| `setPermission` | `({ sessionID, permission }) => Effect<void>` | 更新权限规则集 |
| `setRevert` | `({ sessionID, revert?, summary? }) => Effect<void>` | 设置回退点 |
| `clearRevert` | `(sessionID) => Effect<void>` | 清除回退点 |
| `setSummary` | `({ sessionID, summary? }) => Effect<void>` | 更新摘要统计 |
| `touch` | `(sessionID: SessionID) => Effect<void>` | 刷新最后更新时间 |

### 查询操作

| 方法 | 签名 | 说明 |
|------|------|------|
| `list` | `(input?: ListInput) => Effect<Info[]>` | 项目内会话列表 |
| `children` | `(parentID: SessionID) => Effect<Info[]>` | 查询子会话 |
| `diff` | `(sessionID: SessionID) => Effect<FileDiff[]>` | 获取文件差异 |
| `messages` | `({ sessionID, limit? }) => Effect<WithParts[]>` | 获取会话消息 |
| `findMessage` | `(sessionID, predicate) => Effect<Option<WithParts>>` | 查找匹配消息 (从新到旧) |

### 消息操作

| 方法 | 签名 | 说明 |
|------|------|------|
| `updateMessage` | `<T extends Info>(msg: T) => Effect<T>` | 创建或更新消息 |
| `removeMessage` | `({ sessionID, messageID }) => Effect<MessageID>` | 删除消息 |
| `updatePart` | `<T extends Part>(part: T) => Effect<T>` | 创建或更新部件 |
| `getPart` | `({ sessionID, messageID, partID }) => Effect<Part>` | 获取单个部件 |
| `removePart` | `({ sessionID, messageID, partID }) => Effect<PartID>` | 删除部件 |
| `updatePartDelta` | `({ sessionID, messageID, partID, field, delta }) => Effect<void>` | 对部件字段应用增量更新 (流式) |

### 工具函数

| 函数 | 签名 | 说明 |
|------|------|------|
| `fromRow` | `(row: SessionRow) => Info` | DB 行转 Info 对象 |
| `toRow` | `(info: Info) => SessionRow` | Info 对象转 DB 行 |
| `createDefaultTitle` | `(isChild?: boolean) => string` | 生成默认标题 |
| `isDefaultTitle` | `(title: string) => boolean` | 检查是否默认标题 |
| `getForkedTitle` | `(title: string) => string` | 生成派生标题 |
| `sessionPath` | `(worktree: string, cwd: string) => string` | 计算相对路径 |
| `plan` | `(input, instance) => string` | 获取 plan 文件路径 |
| `getUsage` | `(input) => { cost, tokens }` | 计算 Token 使用量和费用 |
| `listGlobal` | `(input?) => Generator<GlobalInfo>` | 跨项目会话列表生成器 |
| `listByProject` | `(input) => Generator<Info>` | 项目内会话列表生成器 |

---

## 代码示例

### 示例 1：创建会话

```typescript
import { Session } from "@/session"
import { Effect } from "effect"

const program = Effect.gen(function* () {
  // 创建一个简单的会话
  const session = yield* Session.create()

  // 创建带标题和 Agent 的会话
  const named = yield* Session.create({
    title: "重构用户服务",
    agent: "opencode",
    model: {
      providerID: ProviderID.make("anthropic"),
      modelID: ModelID.make("claude-sonnet-4-20250514"),
    },
  })

  // 创建子会话（关联到父会话）
  const child = yield* Session.create({
    parentID: session.id,
    title: "子任务：数据库迁移",
  })
})
```

### 示例 2：查询和管理会话

```typescript
import { Session } from "@/session"
import { Effect } from "effect"

const program = Effect.gen(function* () {
  // 列出项目内的根会话
  const roots = yield* Session.list({ roots: true })

  // 搜索标题包含 "重构" 的会话
  const searched = yield* Session.list({ search: "重构" })

  // 获取某个会话的详情
  const session = yield* Session.get(roots[0].id)

  // 归档会话
  yield* Session.setArchived({
    sessionID: session.id,
    time: Date.now(),
  })

  // 取消归档
  yield* Session.setArchived({
    sessionID: session.id,
    time: undefined,
  })

  // 更新标题
  yield* Session.setTitle({
    sessionID: session.id,
    title: "新版重构方案",
  })
})
```

### 示例 3：Fork 会话

```typescript
import { Session } from "@/session"
import { Effect } from "effect"

const program = Effect.gen(function* () {
  const original = yield* Session.get(someSessionID)

  // Fork 整个会话
  const fullFork = yield* Session.fork({
    sessionID: original.id,
  })

  // Fork 到指定消息为止（增量实验）
  const partialFork = yield* Session.fork({
    sessionID: original.id,
    messageID: someMessageID, // 只复���此消息之前的消息
  })
})
```

### 示例 4：操作消息和部件

```typescript
import { Session } from "@/session"
import { MessageV2 } from "@/session/message-v2"
import { Effect, Option } from "effect"

const program = Effect.gen(function* () {
  const sessionID = someSessionID

  // 获取会话的所有消息
  const msgs = yield* Session.messages({ sessionID })

  // 分页获取最近 10 条消息
  const page = MessageV2.page({ sessionID, limit: 10 })

  // 查找最后一条 assistant error 消息
  const lastError = yield* Session.findMessage(
    sessionID,
    (msg) => msg.info.role === "assistant" && !!msg.info.error,
  )
  if (Option.isSome(lastError)) {
    console.log("找到错误消息:", lastError.value)
  }

  // 创建新用户消息
  const userMsg = yield* Session.updateMessage({
    id: MessageID.ascending(),
    sessionID,
    role: "user",
    time: { created: Date.now() },
    agent: "opencode",
    model: {
      providerID: ProviderID.make("anthropic"),
      modelID: ModelID.make("claude-sonnet-4-20250514"),
    },
  })

  // 添加文本部件
  yield* Session.updatePart({
    id: PartID.ascending(),
    sessionID,
    messageID: userMsg.id,
    type: "text",
    text: "请帮我重构这段代码",
  } as MessageV2.TextPart)

  // 删除会话（递归删除子会话）
  yield* Session.remove(sessionID)
})
```

### 示例 5：跨项目全局查询

```typescript
import { Session } from "@/session"

// listGlobal 是同步生成器，可在 Effect 外使用
for (const session of Session.listGlobal({
  search: "重构",
  limit: 20,
  archived: false, // 默认排除已归档
})) {
  console.log(
    `[${session.project?.name ?? "unknown"}] ${session.title}`
  )
}
```

### 示例 6：获取成本统计

```typescript
import { Session } from "@/session"

const result = Session.getUsage({
  model: {
    id: "claude-sonnet-4-20250514",
    providerID: "anthropic",
    cost: {
      input: 3.0,    // $/MTok
      output: 15.0,  // $/MTok
      cache: {
        read: 0.30,  // $/MTok
        write: 3.75, // $/MTok
      },
    },
  },
  usage: {
    inputTokens: 10000,
    outputTokens: 5000,
    reasoningTokens: 2000,
    cachedInputTokens: 3000,
    totalTokens: 15000,
  },
  metadata: {
    anthropic: {
      cacheCreationInputTokens: 1000,
    },
  },
})

console.log(result.cost)   // 费用 (美元)
console.log(result.tokens) // { input, output, reasoning, cache: { read, write } }
```

### 示例 7：消息流式遍历

```typescript
import { MessageV2 } from "@/session/message-v2"

// 流式遍历所有���息（从旧到新）
for (const msg of MessageV2.stream(sessionID)) {
  console.log(`${msg.info.role}:`, msg.parts.length, "parts")

  for (const part of msg.parts) {
    if (part.type === "text") {
      console.log("  text:", part.text.slice(0, 100))
    }
    if (part.type === "tool") {
      console.log("  tool:", part.tool, "→", part.state.status)
    }
    if (part.type === "step-finish") {
      console.log("  finish:", part.reason, "cost:", part.cost)
    }
  }
}

// 过滤压缩后的消息（去除已被摘要的旧消息）
const compacted = MessageV2.filterCompacted(MessageV2.stream(sessionID))
```

### 示例 8：权限管理

```typescript
import { Session } from "@/session"
import { Permission } from "@/permission"
import { Effect } from "effect"

const program = Effect.gen(function* () {
  const session = yield* Session.get(someSessionID)

  yield* Session.setPermission({
    sessionID: session.id,
    permission: {
      allow: [
        { tool: "bash", pattern: "npm test" },
        { tool: "read", pattern: "*.ts" },
      ],
      deny: [
        { tool: "bash", pattern: "rm -rf" },
      ],
    },
  })
})
```

### 示例 9：回退点管理

```typescript
import { Session } from "@/session"
import { Effect } from "effect"

const program = Effect.gen(function* () {
  const sessionID = someSessionID

  // 设置回退点（保存当前状态用于撤销）
  yield* Session.setRevert({
    sessionID,
    revert: {
      messageID: MessageID.make("msg_xxx"),
      diff: "--- a/file.ts\n+++ b/file.ts\n...",
    },
    summary: {
      additions: 10,
      deletions: 3,
      files: 2,
    },
  })

  // 清除回退点
  yield* Session.clearRevert(sessionID)
})
```
