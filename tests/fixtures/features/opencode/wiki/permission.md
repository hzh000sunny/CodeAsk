# Permission 权限系统

## 概述

Permission 系统是 OpenCode 的安全核心，负责控制 AI Agent 对工具（tool）的访问权限。每条权限规则决定对某个工具的某个操作路径是**允许（allow）**、**拒绝（deny）**还是**询问用户（ask）**。系统支持运行时交互式授权和持久化规则配置，并通过多层规则集合并实现灵活的权限组合。

---

## 数据模型

### 核心类型

| 类型 | 定义 | 说明 |
|------|------|------|
| **Action** | `"allow" \| "deny" \| "ask"` | 权限动作：允许、拒绝、询问 |
| **Rule** | `{ permission: string, pattern: string, action: Action }` | 单条权限规则 |
| **Ruleset** | `Rule[]`（可变数组） | 规则集合，数组中的顺序决定优先级 |
| **Request** | 见下方字段表 | 一次权限请求 |
| **Reply** | `"once" \| "always" \| "reject"` | 用户对权限请求的回复 |
| **Approval** | `{ projectID: string, patterns: string[] }` | 持久化审批记录（项目级） |

### Request 字段

Request 代表工具执行前发出的一次权限请求：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `PermissionID`（以 `"per"` 开头的字符串） | 请求唯一标识 |
| `sessionID` | `SessionID` | 所属会话 |
| `permission` | `string` | 权限名称（即工具 ID，如 `"bash"`, `"read"`, `"edit"`） |
| `patterns` | `string[]` | 操作目标路径/参数，逐条评估 |
| `metadata` | `Record<string, unknown>` | 附加元数据 |
| `always` | `string[]` | 当用户选择 "always" 时，应持久化审批的 patterns |
| `tool` | `{ messageID, callID }`（可选） | 关联的 LLM 消息和工具调用 ID |

### ReplyBody

```typescript
{
  reply: "once" | "always" | "reject"  // 回复类型
  message?: string                       // 可选反馈消息（reject 时用于 CorrectedError）
}
```

### PermissionID

权限请求 ID 以 `"per"` 为前缀，通过 `Identifier.ascending("permission")` 生成，保证时间有序且全局唯一。

---

## 规则评估（evaluate）

### 评估函数

```typescript
function evaluate(permission: string, pattern: string, ...rulesets: Ruleset[]): Rule
```

评估逻辑：
1. 将所有传入的规则集**展平**为一个一维数组（`rulesets.flat()`）
2. 使用 `findLast` 从后向前查找**第一条**同时满足以下两个条件的规则：
   - `permission` 名称通过通配符匹配（`Wildcard.match(permission, rule.permission)`）
   - `pattern` 通过通配符匹配（`Wildcard.match(pattern, rule.pattern)`）
3. 如果没找到任何匹配规则，**默认返回 `{ action: "ask" }`**

### 通配符匹配规则（Wildcard.match）

通配符引擎负责将模式转换为正则表达式进行匹配：

- `*` 匹配任意字符序列（转换为 `.*`）
- `?` 匹配单个字符（转换为 `.`）
- 所有反斜杠 `\` 会被统一为 `/`（跨平台规范化）
- 当模式以 ` *` 结尾（空格+通配符）时，尾部变为可选匹配。例如 `"ls *"` 既可以匹配 `"ls"` 也可以匹配 `"ls -la"`
- 在 Windows 上匹配不区分大小写（`si` 标志），其他平台区分大小写（`s` 标志）

**关键语义**：`findLast` 意味着**数组中后面的规则会覆盖前面的规则**。这在整个权限系统中是核心设计原则。

### 示例

```typescript
// 规则集：先宽泛后具体
const ruleset = [
  { permission: "read", pattern: "*", action: "allow" },        // 默认允许读所有文件
  { permission: "read", pattern: "*.env", action: "ask" },      // .env 文件需要询问
  { permission: "read", pattern: "*.env.example", action: "allow" }, // .env.example 再次允许
]

evaluate("read", "src/index.ts", ruleset)
// → { action: "allow" }

evaluate("read", ".env", ruleset)
// → { action: "ask" }  （*.env 匹配，位置靠后，覆盖了 *）

evaluate("read", ".env.example", ruleset)
// → { action: "allow" } （*.env.example 匹配，位置最靠后）
```

---

## 路径模式展开（expand）

用户配置的权限路径支持 shell 风格展开：

```typescript
function expand(pattern: string): string {
  if (pattern.startsWith("~/")) return os.homedir() + pattern.slice(1)
  if (pattern === "~") return os.homedir()
  if (pattern.startsWith("$HOME/")) return os.homedir() + pattern.slice(5)
  if (pattern.startsWith("$HOME")) return os.homedir() + pattern.slice(5)
  return pattern
}
```

| 输入 | 展开结果 |
|------|----------|
| `~/projects/*` | `/home/user/projects/*` |
| `~` | `/home/user` |
| `$HOME/data/*` | `/home/user/data/*` |
| `$HOME` | `/home/user` |
| `./src/*` | `./src/*`（保持不变） |

此展开仅在 `fromConfig` 函数中生效，即将用户配置转换为内部规则集时。

---

## Ask / Reply 流程

### Ask 流程（请求权限）

Ask 是工具执行前调用的权限检查入口。其函数签名为：

```typescript
ask(input: AskInput): Effect<void, DeniedError | RejectedError | CorrectedError>
```

`AskInput` 包含 `Request` 的所有字段，外加一个 `ruleset: Ruleset`（来自当前 Agent 的规则集）。

```
┌──────────────────────────────────────────────────────────────────────┐
│                           Ask Flow                                  │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  工具调用 ctx.ask({ permission, patterns, ... })                     │
│       │                                                              │
│       ▼                                                              │
│  对每个 pattern 依次求值:                                            │
│    evaluate(permission, pattern, ruleset, approved)                  │
│       │                                                              │
│       ├── 任一 rule.action === "deny"                                │
│       │       │                                                      │
│       │       └── 抛出 DeniedError({ ruleset })                     │
│       │            （附带有匹配 deny 的规则供 AI 参考）               │
│       │                                                              │
│       ├── rule.action === "allow"                                    │
│       │       │                                                      │
│       │       └── 继续下一个 pattern                                 │
│       │                                                              │
│       └── rule.action === "ask" (或默认)                             │
│               │                                                      │
│               └── needsAsk = true                                    │
│                                                                      │
│  如果 needsAsk === false → 直接返回（所有 pattern 均允许）           │
│                                                                      │
│  如果 needsAsk === true:                                             │
│       │                                                              │
│       ▼                                                              │
│  1. 创建 Deferred（Promise 风格的挂起机制）                          │
│  2. 将 { info: Request, deferred } 加入 pending Map                  │
│  3. 发布 Event.Asked 事件（通知 UI 显示权限询问）                    │
│  4. 挂起等待 Deferred 被 resolve                                    │
│       │                                                              │
│       ├── Deferred 成功 → ask 返回 void（工具继续执行）              │
│       │                                                              │
│       └── Deferred 失败 → 抛出对应错误:                              │
│            - RejectedError（用户拒绝）                               │
│            - CorrectedError（用户拒绝并附反馈）                      │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### Reply 流程（响应用户决定）

```typescript
reply(input: ReplyInput): Effect<void>
```

`ReplyInput` = `{ requestID: PermissionID, reply: Reply, message?: string }`

```
┌──────────────────────────────────────────────────────────────────────┐
│                          Reply Flow                                 │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  用户做出决定 → reply({ requestID, reply, message? })                │
│       │                                                              │
│       ▼                                                              │
│  在 pending Map 中查找 requestID                                     │
│       │                                                              │
│       ├── 未找到 → 直接返回（请求可能已超时或被处理）                 │
│       │                                                              │
│       └── 找到 → 从 pending 中删除该条目                             │
│            │                                                         │
│            ▼                                                        │
│         发布 Event.Replied 事件                                      │
│            │                                                         │
│            ├── reply === "reject"                                    │
│            │     │                                                   │
│            │     ├── 有 message → fail Deferred(CorrectedError)      │
│            │     ├── 无 message → fail Deferred(RejectedError)       │
│            │     │                                                   │
│            │     └── 级联拒绝: 遍历 pending 中同 sessionID 的所有    │
│            │         其他请求，全部 fail(RejectedError)              │
│            │                                                        │
│            ├── reply === "once"                                      │
│            │     │                                                   │
│            │     └── succeed Deferred（仅本次有效，不改变 approved）  │
│            │                                                        │
│            └── reply === "always"                                    │
│                  │                                                   │
│                  ├── succeed Deferred                                │
│                  ├── 将 always patterns 加入 approved 规则集:        │
│                  │   { permission, pattern, action: "allow" }        │
│                  │                                                   │
│                  └── 自动审批: 遍历 pending 中同 sessionID 的其他    │
│                      请求，如果其所有 patterns 现在均被 approved     │
│                      规则评估为 "allow"，则自动 succeed 该 Deferred  │
│                      并发布 Event.Replied("always")                  │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 时序图

```
    Tool          Permission.Service        Bus/UI          User        State
     │                   │                     │              │            │
     │── ctx.ask() ────▶ │                     │              │            │
     │                   │── evaluate() ────────────────────────────────▶│ (ruleset+approved)
     │                   │◀── rule ─────────────────────────────────────│
     │                   │                     │              │            │
     │  (如果 deny)      │                     │              │            │
     │◀── DeniedError ──│                     │              │            │
     │                   │                     │              │            │
     │  (如果需要 ask)   │                     │              │            │
     │                   │── 创建 Deferred ────────────────────────────▶│ (pending.set)
     │                   │── publish Asked ──▶│              │            │
     │   [挂起等待...]   │                     │── 展示询问 ─▶│            │
     │                   │                     │◀── 用户选择 ─│            │
     │                   │◀── reply() ────────│              │            │
     │                   │                     │              │            │
     │  (如果 once)      │                     │              │            │
     │                   │── succeed Deferred ─────────────────────────▶│ (pending.delete)
     │◀── return ───────│                     │              │            │
     │                   │                     │              │            │
     │  (如果 always)    │                     │              │            │
     │                   │── approved.push({allow}) ────────────────────▶│
     │                   │── succeed Deferred ─────────────────────────▶│ (pending.delete)
     │◀── return ───────│                     │              │            │
     │                   │                     │              │            │
     │  (如果 reject)    │                     │              │            │
     │                   │── fail Deferred ────────────────────────────▶│ (pending.delete)
     │◀── RejectedError ─│                     │              │            │
     │                   │── 级联拒绝其他请求 ──────────────────────────▶│
```

---

## 规则合并与优先级

### Permission.merge

```typescript
function merge(...rulesets: Ruleset[]): Ruleset {
  return rulesets.flat()
}
```

合并逻辑极其简单：将多个规则集拼接为一个大数组。**优先级完全由数组顺序决定**——因为 `evaluate` 使用 `findLast`，所以数组后面（即合并中靠后的规则集）的规则会覆盖前面的。

### Agent 权限合并模式

每个 Agent 的权限由多层层规则合并而来。典型模式如下（以 `build` agent 为例）：

```
Permission.merge(
  defaults,        // 第一层: 全局默认规则
  agentSpecifics,  // 第二层: Agent 特有规则（覆盖默认）
  user,            // 第三层: 用户自定义规则（最高优先级）
)
```

**具体各层**：

1. **defaults（全局默认）**：
   - `"*": "allow"` — 默认允许所有工具
   - `"doom_loop": "ask"` — 检测到循环时询问
   - `"external_directory": { "*": "ask", ...truncate/技能白名单: "allow" }`
   - `"question": "deny"` — 禁止向用户提问
   - `"repo_clone": "deny"` — 禁止克隆仓库
   - `"repo_overview": "deny"` — 禁止仓库概览
   - `"read": { "*": "allow", "*.env": "ask", "*.env.*": "ask", "*.env.example": "allow" }` — 敏感文件保护

2. **agentSpecifics（Agent 特有规则）**：不同 Agent 有不同的权限配置：

   | Agent | 特殊规则 |
   |-------|----------|
   | **build** | `question: "allow"`, `plan_enter: "allow"` |
   | **plan** | `question: "allow"`, `plan_exit: "allow"`, `edit: { "*": "deny" }` + 计划目录白名单 |
   | **general** | `todowrite: "deny"` |
   | **explore** | `"*": "deny"` + 只允许读类工具（`grep`, `glob`, `list`, `bash`, `read`, `webfetch`, `websearch`） |
   | **scout** | `"*": "deny"` + 允许读类工具 + `codesearch`, `repo_clone`, `repo_overview` |
   | **compaction** | `"*": "deny"` |
   | **title/summary** | `"*": "deny"` |

3. **user（用户配置）**：来自 `opencode.json` 中的 `permission` 字段，优先级最高。

### 用户自定义 Agent 的权限合并

```typescript
// 已有 agent：追加合并
item.permission = Permission.merge(
  item.permission,
  Permission.fromConfig(value.permission ?? {})
)

// 新建 agent：基于 defaults + user
item.permission = Permission.merge(defaults, user)
```

---

## 从配置转换（fromConfig）

```typescript
function fromConfig(permission: ConfigPermission.Info): Ruleset
```

`fromConfig` 将用户友好的配置格式转换为内部规则集。

### 配置格式

用户配置支持两种写法：

**简写（字符串值）**：直接对一个权限名设置全局行为
```json
{
  "permission": {
    "question": "deny",
    "doom_loop": "ask"
  }
}
```
转换结果：`{ permission: "question", action: "deny", pattern: "*" }`

**完整写法（对象值）**：对权限名的不同路径设置不同行为
```json
{
  "permission": {
    "read": {
      "*": "allow",
      "*.env": "ask",
      "*.env.*": "ask",
      "*.env.example": "allow"
    },
    "bash": {
      "*": "allow",
      "~/scripts/*": "allow"
    }
  }
}
```
转换结果：路径经过 `expand()` 展开后生成对应规则。

**更简写（直接 Action 值）**：顶级直接写一个 Action 字符串
```json
{
  "permission": "deny"
}
```
相当于 `{ "*": "deny" }`，关闭所有工具。

### 配置类型

| 配置键 | 类型 | 说明 |
|--------|------|------|
| `read`, `edit`, `glob`, `grep`, `list`, `bash`, `task` | `Rule`（Action 或 Object） | 支持路径级别控制 |
| `external_directory`, `repo_clone`, `repo_overview`, `lsp`, `skill` | `Rule`（Action 或 Object） | 支持路径级别控制 |
| `todowrite`, `question`, `webfetch`, `websearch`, `codesearch`, `doom_loop` | `Action`（仅字符串值） | 不支持路径级别，仅全局开关 |

---

## 错误类型

### 错误层次结构

```
Error (联合类型)
├── DeniedError      — 规则拒绝（用户配置了 deny 规则）
├── RejectedError    — 用户拒绝（运行时的交互式拒绝）
└── CorrectedError   — 用户拒绝并附反馈
```

### DeniedError

```typescript
class DeniedError {
  ruleset: any  // 匹配 deny 的相关规则
  message: "The user has specified a rule which prevents you from using this specific tool call. Here are some of the relevant rules {...}"
}
```

**触发条件**：在 Ask 流程中，任一 pattern 被 `ruleset` 或 `approved` 中的规则评估为 `"deny"`。

**携带信息**：`ruleset` 字段包含了所有 permission 名称匹配的 deny 规则（过滤后的规则集），使 AI 能了解被拒绝的原因。

### RejectedError

```typescript
class RejectedError {
  message: "The user rejected permission to use this specific tool call."
}
```

**触发条件**：
- 用户选择 `"reject"` 且未提供反馈消息
- 级联拒绝时，同一 session 的其他等待请求也被此错误终止
- 服务销毁时（`Effect.addFinalizer`），所有 pending 请求都会被此错误终止

### CorrectedError

```typescript
class CorrectedError {
  feedback: string
  message: "The user rejected permission to use this specific tool call with the following feedback: {feedback}"
}
```

**触发条件**：用户选择 `"reject"` 时附带消息，如提供修改建议或说明原因。AI 可以读取 `feedback` 字段进行调整后重试。

---

## 持久化审批（always vs once）

### once（仅本次）

- Deferred 成功 → 工具继续执行
- **不修改** `approved` 规则集
- 下次相同工具的相同操作**仍需重新询问**

### always（永久记住）

- Deferred 成功 → 工具继续执行
- 将 `always` 数组中的每个 pattern 以 `{ permission, pattern, action: "allow" }` **追加**到 `approved` 规则集末尾
- `approved` 规则集会持久化到数据库（`PermissionTable`），跨会话保留
- 下次相同工具的相同操作**自动允许**，无需再次询问

**自动审批传播**：当用户对某个请求选择 "always" 后，系统会立即遍历所有 pending 请求：

```
pending 中同 sessionID 的其他请求
    → 用更新后的 approved 规则集重新评估其所有 patterns
    → 如果全部为 "allow"
    → 自动 succeed 这些请求的 Deferred
    → 发布 Event.Replied("always")
```

这意味着一次 "always" 回复可能会连带批准多个已经在排队的同类请求。

### approved 的持久化

```
启动时：
  Database.use(db => db.select().from(PermissionTable)
    .where(eq(PermissionTable.project_id, context.project.id)).get())
  → state.approved = row?.data ?? []

销毁时：
  Effect.addFinalizer → 清理所有 pending Deferred (fail with RejectedError)
```

`approved` 规则集的存储与当前项目绑定（通过 `project_id`）。不同项目的 approved 规则互不干扰。

---

## 工具禁用（disabled）

```typescript
function disabled(tools: string[], ruleset: Ruleset): Set<string>
```

`disabled` 函数用于在 LLM 请求前过滤掉被完全禁用的工具，使其不出现在发送给模型的定义中。

**处理逻辑**：
1. 对于每个工具名，如果它在 `EDIT_TOOLS`（`["edit", "write", "apply_patch"]`）中，统一映射到 `"edit"` 权限名
2. 在规则集中 `findLast` 查找匹配的规则
3. 只有当规则的 `pattern === "*"` 且 `action === "deny"` 时，才将该工具加入禁用集

**关键细节**：
- 只有 `pattern: "*"` 的 deny 规则才会导致工具被禁用。如果 deny 规则仅针对特定路径（如 `edit: { "*.lock": "deny" }`），工具仍然可用
- `edit`, `write`, `apply_patch` 三个工具共享 `"edit"` 权限名。禁用编辑权限会同时禁用这三个工具

**使用场景**（在 `resolveTools` 中）：

```typescript
const disabled = Permission.disabled(
  Object.keys(input.tools),
  Permission.merge(input.agent.permission, input.permission ?? [])
)
// 过滤掉 disabled 的工具和用户显式禁用的工具
return Record.filter(input.tools, (_, k) => 
  input.user.tools?.[k] !== false && !disabled.has(k)
)
```

---

## 事件系统

### Event.Asked

```typescript
Event.Asked = BusEvent.define("permission.asked", Request)
```

**触发时机**：当 Ask 流程判定需要询问用户时，在挂起 Deferred 之后立即发布。

**携带数据**：完整的 `Request` 对象（包含 permission、patterns、tool 信息等）。

**消费方**：UI 层（前端）监听此事件，向用户展示权限请求对话框。

### Event.Replied

```typescript
Event.Replied = BusEvent.define("permission.replied", {
  sessionID: SessionID,
  requestID: PermissionID,
  reply: Reply
})
```

**触发时机**：每次 `reply()` 处理一个请求时发布（包括自动审批的情况）。

**携带数据**：`sessionID`、被回复的 `requestID`、回复类型（once/always/reject）。

**消费方**：UI 层监听此事件，关闭对应的权限请求对话框。

---

## 配置示例

### 基础示例：限制编辑权限

```json
{
  "permission": {
    "edit": {
      "*": "ask",
      "*.md": "allow",
      "*.ts": "allow",
      "*.lock": "deny"
    }
  }
}
```

效果：
- 编辑 `.md` 和 `.ts` 文件 → 自动允许
- 编辑 `.lock` 文件 → 直接拒绝
- 编辑其他类型文件 → 询问用户

### 示例：创建只读 Agent

```json
{
  "agent": {
    "reviewer": {
      "permission": {
        "*": "deny",
        "read": "allow",
        "grep": "allow",
        "glob": "allow",
        "list": "allow",
        "webfetch": "allow"
      },
      "description": "只读代码审查 agent"
    }
  }
}
```

### 示例：敏感文件保护

```json
{
  "permission": {
    "read": {
      "*": "allow",
      "*.env": "ask",
      "*.env.*": "ask",
      "*.pem": "ask",
      "*.env.example": "allow",
      "~/.*": "ask"
    }
  }
}
```

### 示例：全局开关

```json
{
  "permission": {
    "question": "deny",
    "doom_loop": "ask",
    "repo_clone": "deny"
  }
}
```

### 示例：限制外部目录访问

```json
{
  "permission": {
    "external_directory": {
      "*": "deny",
      "~/projects/*": "allow",
      "/tmp/*": "allow",
      "$HOME/.config/*": "ask"
    }
  }
}
```

路径中的 `~/` 和 `$HOME` 会被自动展开为实际 home 目录路径。

---

## 服务架构

### Service 接口

```typescript
interface Interface {
  readonly ask: (input: AskInput) => Effect<void, Error>
  readonly reply: (input: ReplyInput) => Effect<void>
  readonly list: () => Effect<ReadonlyArray<Request>>
}
```

### State 管理

```
State {
  pending: Map<PermissionID, PendingEntry>   // 等待用户决定的请求
  approved: Ruleset                           // 已持久化的审批规则（项目级）
}
```

- **pending**：内存映射表，存储当前会话中所有等待用户决定的权限请求及其 Deferred
- **approved**：从数据库加载（`PermissionTable`），跨会话持久化。在 "always" 回复时动态追加

### 工具与权限的集成

工具通过 `Tool.Context` 中的 `ask()` 方法请求权限：

```typescript
// 工具执行上下文中
interface Context {
  ask(input: Omit<Permission.Request, "id" | "sessionID" | "tool">): Effect<void>
}
```

工具调用 `ctx.ask({ permission, patterns, always, metadata })` 来触发权限检查流程。`id` 和 `sessionID` 由上层自动补充，`tool` 信息（`messageID`, `callID`）来自 LLM 工具调用上下文。

### 生命周期

1. **启动**：从数据库加载 `approved` 规则集
2. **运行**：动态管理 `pending` 请求，处理 ask/reply 流程
3. **关闭**：`Effect.addFinalizer` 清理所有 pending Deferred，全部 fail 为 RejectedError

---

## 总结

Permission 系统的设计体现了以下原则：

1. **安全优先**：默认行为是 `"ask"`（询问用户），无规则匹配时不会自动允许
2. **显式覆盖**：通过 `findLast` + 数组合并实现越靠后优先级越高的规则覆盖策略
3. **用户可控**：支持 `once`/`always`/`reject` 三种粒度的交互式授权，`always` 可持久化
4. **级联效应**：`reject` 会结束同一会话的所有 pending 请求；`always` 会自动审批符合条件的 pending 请求
5. **分层组合**：通过 `Permission.merge` 实现默认规则 + Agent 规则 + 用户规则的灵活叠加
6. **工具过滤**：`disabled` 函数在 LLM 调用前过滤完全禁用的工具，避免模型生成无法执行的工具调用
