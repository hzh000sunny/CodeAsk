# @opencode-ai/sdk — JavaScript SDK 文档

`@opencode-ai/sdk` 是 OpenCode 的官方 JavaScript SDK，用于以编程方式与 OpenCode 服务器交互。它允许开发者在自己的应用中启动 OpenCode 进程、创建客户端连接、管理会话、发送提示词、订阅事件流等。

## 目录

- [安装与入口](#安装与入口)
- [架构概览](#架构概览)
- [客户端 (Client)](#客户端-client)
  - [创建客户端](#创建客户端)
  - [配置选项](#配置选项)
  - [API 子模块](#api-子模块)
- [服务端 (Server)](#服务端-server)
  - [创建服务器](#创建服务器)
  - [服务器选项](#服务器选项)
  - [TUI 进程管理](#tui-进程管理)
- [进程管理](#进程管理)
- [事件订阅模型](#事件订阅模型)
  - [全局事件流](#全局事件流)
  - [事件类型一览](#事件类型一览)
- [会话管理 API](#会话管理-api)
  - [会话 CRUD](#会话-crud)
  - [发送提示词 (Prompt)](#发送提示词-prompt)
  - [异步提示词](#异步提示词)
  - [命令执行](#命令执行)
  - [会话控制](#会话控制)
- [其他 API 模块](#其他-api-模块)
- [V2 API](#v2-api)
  - [V2 与 V1 的主要差异](#v2-与-v1-的主要差异)
  - [V2 独有新模块](#v2-独有新模块)
- [错误处理](#错误处理)
  - [错误拦截器](#错误拦截器)
  - [错误类型](#错误类型)
- [使用示例](#使用示例)
  - [完整示例：启动服务并创建会话](#完整示例启动服务并创建会话)
  - [事件订阅示例](#事件订阅示例)
  - [批量处理示例](#批量处理示例)
  - [V2 API 示例](#v2-api-示例)
  - [TUI 进程管理示例](#tui-进程管理示例)
- [类型系统](#类型系统)
  - [核心消息类型](#核心消息类型)
  - [Part 类型](#part-类型)
  - [事件类型](#事件类型)
  - [配置类型](#配置类型)
- [兼容性](#兼容性)

---

## 安装与入口

```bash
npm install @opencode-ai/sdk
```

包采用 ES Module 格式（`"type": "module"`），需在 Node.js 22+ 环境下使用。唯一的运行时依赖是 `cross-spawn`，用于跨平台进程启动。

### 导出入口

| 入口路径 | 说明 |
|---------|------|
| `@opencode-ai/sdk` | 主入口，导出 `createOpencode`、`createOpencodeClient`、`createOpencodeServer` |
| `@opencode-ai/sdk/client` | 客户端模块 |
| `@opencode-ai/sdk/server` | 服务端模块 |
| `@opencode-ai/sdk/v2` | V2 API 入口 |
| `@opencode-ai/sdk/v2/client` | V2 客户端模块 |
| `@opencode-ai/sdk/v2/server` | V2 服务端模块 |
| `@opencode-ai/sdk/v2/gen/client` | V2 生成的底层 HTTP 客户端 |

### 主入口函数

```typescript
import { createOpencode, createOpencodeClient, createOpencodeServer } from "@opencode-ai/sdk"

// 一步到位：同时创建服务器和客户端
const { client, server } = await createOpencode(options)

// 分别创建
const server = await createOpencodeServer(options)
const client = createOpencodeClient({ baseUrl: server.url })
```

`createOpencode` 是便捷函数，内部调用 `createOpencodeServer` 启动 opencode 进程，然后使用返回的 `url` 创建客户端。返回的对象同时包含 `client` 和 `server` 引用。

---

## 架构概览

SDK 由以下核心模块组成：

```
src/
├── index.ts           # 主入口，聚合导出
├── client.ts           # 客户端创建（V1）
├── server.ts           # 服务端进程管理（V1）
├── process.ts          # 底层进程控制
├── error-interceptor.ts # 错误拦截器
├── gen/                # @hey-api/openapi-ts 生成的代码
│   ├── types.gen.ts    # 全部类型定义
│   ├── sdk.gen.ts      # SDK 封装类 (OpencodeClient)
│   ├── client.gen.ts   # 底层 HTTP 客户端工厂
│   └── client/         # 客户端基础设施
└── v2/                 # V2 API 模块
    ├── index.ts
    ├── client.ts       # V2 客户端创建
    ├── server.ts       # V2 服务端进程管理
    ├── data.ts         # 消息构造工具
    └── gen/            # V2 生成的代码（新版 @hey-api/openapi-ts）
```

数据流路径为：

```
用户代码
  └─> createOpencodeClient(config)
       └─> createClient(config)  (底层 HTTP 客户端)
            └─> HTTP 拦截器链
                 ├─> 请求拦截器 (rewrite): 注入 directory/workspace 参数
                 ├─> 响应拦截器 (V2): 检测 text/html 错误
                 └─> 错误拦截器 (wrapClientError): 规范化错误对象
       └─> new OpencodeClient(...)  (SDK 高级封装)
            └─> client.session.prompt(...)
            └─> client.event.subscribe(...)
            └─> ...
```

---

## 客户端 (Client)

### 创建客户端

```typescript
import { createOpencodeClient } from "@opencode-ai/sdk"

const client = createOpencodeClient({
  baseUrl: "http://127.0.0.1:4096",   // OpenCode 服务器地址
  directory: "/path/to/project",       // 可选：项目目录
  // 以下为可选配置
  throwOnError: false,                 // 是否抛出错误（默认 false）
  responseStyle: "fields",             // "data" | "fields"
  parseAs: "auto",                     // 响应解析方式
})
```

### 配置选项

| 选项 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `baseUrl` | `string` | 必填 | OpenCode 服务器的基地址，格式为 `http://host:port` |
| `directory` | `string` | 无 | 项目目录路径。设置后会自动通过 `x-opencode-directory` 请求头传递，并自动注入到 GET/HEAD 请求的查询参数中 |
| `fetch` | `function` | `globalThis.fetch` | 自定义 fetch 实现，SDK 默认设置 `req.timeout = false` |
| `headers` | `object` | `{}` | 额外的自定义请求头 |
| `throwOnError` | `boolean` | `false` | 为 `true` 时在非 2xx 响应时抛出错误；为 `false` 时通过 `result.error` 返回错误 |
| `responseStyle` | `"data" \| "fields"` | `"fields"` | `"data"` 只返回响应数据；`"fields"` 返回 `{ data, request, response }` 结构 |
| `parseAs` | `string` | `"auto"` | 响应体解析方式：`"auto"`、`"json"`、`"text"`、`"stream"` 等 |

#### directory 机制

当设置了 `directory` 选项后，SDK 的行为如下：

1. **请求头注入**：每次请求自动添加 `x-opencode-directory` 请求头（值为 `encodeURIComponent(directory)`）
2. **查询参数注入**：对于 GET 和 HEAD 请求，请求拦截器会将 `x-opencode-directory` 头转换为 URL 查询参数 `?directory=...`，然后删除该请求头

这意味着你可以在创建客户端时一次性指定工作目录，后续所有 API 调用都会自动携带该目录信息，无需每次手动传递。

### API 子模块

`OpencodeClient` 实例通过属性访问开放以下子模块：

| 子模块 | 路径 | 说明 |
|--------|------|------|
| `client.global` | `/global` | 全局事件流 |
| `client.project` | `/project` | 项目列表与当前项目 |
| `client.session` | `/session` | 会话管理（CRUD、提示词、命令等） |
| `client.pty` | `/pty` | 伪终端会话管理 |
| `client.config` | `/config` | 配置读取与更新 |
| `client.provider` | `/provider` | 模型提供商列表与 OAuth 认证 |
| `client.command` | `/command` | 命令列表 |
| `client.find` | `/find` | 文件搜索、文本搜索、符号搜索 |
| `client.file` | `/file` | 文件列表、读取、状态 |
| `client.tool` | `/experimental/tool` | 工具 ID 列表与工具 Schema 列表 |
| `client.instance` | `/instance` | 实例释放 |
| `client.path` | `/path` | 当前路径信息 |
| `client.vcs` | `/vcs` | VCS 信息 |
| `client.app` | `/agent`, `/log` | 代理列表与日志写入 |
| `client.mcp` | `/mcp` | MCP 服务器管理 |
| `client.lsp` | `/lsp` | LSP 状态 |
| `client.formatter` | `/formatter` | 格式化器状态 |
| `client.tui` | `/tui` | TUI 界面控制（提示词追加、对话框打开等） |
| `client.auth` | `/auth` | 认证凭据设置 |
| `client.event` | `/event` | 事件订阅（SSE） |

每个子模块的方法签名遵循统一模式：

```typescript
// 以 session.create 为例：
const result = await client.session.create({
  body: { parentID: "xxx", title: "My Session" },
  query: { directory: "/path/to/project" },
  throwOnError: true,
})

// result 结构（responseStyle: "fields"）：
// { data: Session, request: Request, response: Response }
```

---

## 服务端 (Server)

### 创建服务器

```typescript
import { createOpencodeServer } from "@opencode-ai/sdk"

const server = await createOpencodeServer({
  hostname: "127.0.0.1",
  port: 4096,
  timeout: 5000,
  config: {
    // OpenCode 配置对象
    logLevel: "DEBUG",
    model: "anthropic/claude-sonnet-4-20250514",
  },
  signal: abortController.signal,
})

console.log(server.url)  // "http://127.0.0.1:4096"

// 关闭服务器
server.close()
```

### 服务器选项

| 选项 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `hostname` | `string` | `"127.0.0.1"` | 服务器绑定的主机名 |
| `port` | `number` | `4096` | 服务器监听的端口 |
| `timeout` | `number` | `5000` | 等待服务器启动的超时时间（毫秒） |
| `config` | `Config` | `{}` | OpenCode 的完整配置对象，通过环境变量 `OPENCODE_CONFIG_CONTENT` 传递 |
| `signal` | `AbortSignal` | 无 | 用于取消服务器启动的 AbortSignal |

### 服务器启动流程

1. SDK 使用 `cross-spawn` 库启动 `opencode serve` 子进程
2. 子进程参数：`serve --hostname=127.0.0.1 --port=4096`
3. 若配置了 `config.logLevel`，追加 `--log-level=<level>` 参数
4. 完整的 `Config` 对象通过环境变量 `OPENCODE_CONFIG_CONTENT` 以 JSON 字符串形式传递
5. SDK 监控 stdout，等待输出中包含 `"opencode server listening on <url>"` 的行
6. 通过正则解析出服务器 URL 并返回
7. 若超时、进程退出或发生错误，Promise 会被 reject

### 进程管理

`close()` 方法用于终止 opencode 进程：

```typescript
server.close()
```

内部实现调用 `process.ts` 中的 `stop()` 函数：
- 如果进程已经退出，不做任何操作
- Windows 平台：使用 `taskkill /pid <pid> /T /F` 强制终止
- 其他平台：调用 `proc.kill()` 发送终止信号

### TUI 进程管理

SDK 还提供了 `createOpencodeTui` 函数用于启动 opencode 的终端 UI 模式：

```typescript
import { createOpencodeTui } from "@opencode-ai/sdk"

const tui = createOpencodeTui({
  project: "/path/to/project",
  model: "anthropic/claude-sonnet-4-20250514",
  session: "existing-session-id",
  agent: "build",
  config: {
    logLevel: "INFO",
  },
  signal: abortController.signal,
})

// 关闭 TUI
tui.close()
```

与 `createOpencodeServer` 不同，TUI 进程使用 `stdio: "inherit"`，将子进程的输入输出直接连接到父进程的终端。

---

## 进程管理

`process.ts` 提供两个底层工具函数，供 Server 和 TUI 模块使用。

### stop(proc)

终止一个子进程：

```typescript
import { stop } from "./process.js"

stop(proc)  // proc: ChildProcess
```

- 若进程已退出（`exitCode` 或 `signalCode` 不为 null），则跳过
- Windows 平台使用 `taskkill` 强制终止进程树
- 其他平台调用 `proc.kill()`

### bindAbort(proc, signal, onAbort?)

将 `AbortSignal` 绑定到进程生命周期：

```typescript
import { bindAbort } from "./process.js"

const clear = bindAbort(proc, abortSignal, () => {
  console.log("进程被中止")
})

// 取消绑定时调用
clear()
```

- 当 `signal.aborted` 为 true 时立即执行中止
- 注册 `abort` 事件监听器，触发时终止进程并调用 `onAbort`
- 进程退出或出错时自动清理监听器
- 返回 `clear` 函数用于手动解除绑定

---

## 事件订阅模型

OpenCode 通过 Server-Sent Events (SSE) 提供实时事件流。SDK 提供了两个事件端点：

### 全局事件流

```typescript
// 订阅全局事件（包含 directory 和 payload）
const stream = await client.global.event({
  query: { directory: "/path/to/project" },
})

// stream 是异步可迭代对象
for await (const event of stream) {
  // event: { directory: string, payload: Event }
  switch (event.payload.type) {
    case "session.created":
      console.log("会话已创建:", event.payload.properties.info.title)
      break
    case "message.updated":
      console.log("消息已更新:", event.payload.properties.info.id)
      break
  }
}
```

### 事件订阅

```typescript
// 订阅事件（直接返回 Event 对象）
const stream = await client.event.subscribe({
  query: { directory: "/path/to/project" },
})

for await (const event of stream) {
  // event: Event（不含 directory 包装）
  console.log("事件类型:", event.type)
}
```

### 事件类型一览

SDK 定义了以下事件类型（位于 `src/gen/types.gen.ts`）：

| 事件类型 | 说明 |
|---------|------|
| `server.instance.disposed` | 实例已释放 |
| `server.connected` | 服务器连接成功 |
| `installation.updated` | 安装版本已更新 |
| `installation.update-available` | 有可用更新 |
| `session.created` | 会话已创建 |
| `session.updated` | 会话已更新 |
| `session.deleted` | 会话已删除 |
| `session.diff` | 会话 diff 变更 |
| `session.error` | 会话发生错误 |
| `session.status` | 会话状态变更（idle/busy/retry） |
| `session.idle` | 会话进入空闲状态 |
| `session.compacted` | 会话已压缩 |
| `message.updated` | 消息已更新 |
| `message.removed` | 消息已删除 |
| `message.part.updated` | 消息 Part 已更新（可携带 delta 增量） |
| `message.part.removed` | 消息 Part 已删除 |
| `permission.updated` | 权限请求已更新 |
| `permission.replied` | 权限请求已回复 |
| `file.edited` | 文件已编辑 |
| `file.watcher.updated` | 文件监视器检测到变更 |
| `todo.updated` | 待办事项已更新 |
| `command.executed` | 命令已执行 |
| `tui.prompt.append` | TUI 提示词追加 |
| `tui.command.execute` | TUI 命令执行 |
| `tui.toast.show` | TUI 通知显示 |
| `pty.created` | PTY 会话已创建 |
| `pty.updated` | PTY 会话已更新 |
| `pty.exited` | PTY 会话已退出 |
| `pty.deleted` | PTY 会话已删除 |
| `lsp.client.diagnostics` | LSP 诊断信息更新 |
| `lsp.updated` | LSP 服务器状态更新 |
| `vcs.branch.updated` | VCS 分支已更新 |

---

## 会话管理 API

会话 (Session) 是 OpenCode 的核心概念，代表一次对话上下文。SDK 通过 `client.session` 提供完整的会话生命周期管理。

### 会话 CRUD

```typescript
// 列出所有会话
const { data: sessions } = await client.session.list()
// sessions: Session[]

// 创建新会话
const { data: session } = await client.session.create({
  body: {
    parentID: "parent-session-id",  // 可选：父会话 ID，用于 fork
    title: "My Session",            // 可选：会话标题
  },
})

// 获取单个会话
const { data: session } = await client.session.get({
  path: { id: sessionId },
})

// 更新会话属性
const { data: session } = await client.session.update({
  path: { id: sessionId },
  body: { title: "New Title" },
})

// 删除会话
const { data: ok } = await client.session.delete({
  path: { id: sessionId },
})
```

### 发送提示词 (Prompt)

```typescript
const { data: result } = await client.session.prompt({
  path: { id: sessionId },
  body: {
    agent: "build",                        // 可选：指定 agent
    model: {                               // 可选：指定模型
      providerID: "anthropic",
      modelID: "claude-sonnet-4-20250514",
    },
    system: "You are a helpful assistant", // 可选：系统提示词
    tools: {                               // 可选：可用工具
      read: true,
      write: true,
      bash: true,
    },
    parts: [                               // 必填：消息 parts
      {
        type: "text",
        text: "请帮我分析这段代码",
      },
      {
        type: "file",
        mime: "text/plain",
        url: "file:///path/to/code.ts",
      },
    ],
  },
})

// result: { info: AssistantMessage, parts: Part[] }
```

#### 支持的 Part 输入类型

| 类型 | 必需字段 | 说明 |
|------|---------|------|
| `text` | `type: "text"`, `text: string` | 普通文本输入 |
| `file` | `type: "file"`, `mime: string`, `url: string` | 文件引用输入 |
| `agent` | `type: "agent"`, `name: string` | 指定 Agent |
| `subtask` | `type: "subtask"`, `prompt: string`, `description: string`, `agent: string` | 子任务 |

文本 Part 还支持以下可选属性：
- `synthetic?: boolean` — 标记为合成内容
- `ignored?: boolean` — 标记为忽略内容
- `time?: { start: number, end?: number }` — 时间范围
- `metadata?: Record<string, unknown>` — 自定义元数据

### 异步提示词

`promptAsync` 在创建提示词后立即返回（204 No Content），不等待 AI 响应完成。适用于需要先启动任务再通过事件流获取结果的场景。

```typescript
await client.session.promptAsync({
  path: { id: sessionId },
  body: {
    parts: [{ type: "text", text: "生成长报告..." }],
  },
})
// 立即返回，通过事件流监听消息更新
```

### 命令执行

```typescript
// 执行预定义命令
const { data: result } = await client.session.command({
  path: { id: sessionId },
  body: {
    command: "explain",
    arguments: "src/server.ts:1-50",
    agent: "explore",
  },
})

// 执行 Shell 命令
const { data: result } = await client.session.shell({
  path: { id: sessionId },
  body: {
    command: "ls -la src/",
    agent: "general",
    model: {
      providerID: "anthropic",
      modelID: "claude-sonnet-4-20250514",
    },
  },
})
```

### 会话控制

```typescript
// Fork 会话（在指定消息处分支）
const { data: newSession } = await client.session.fork({
  path: { id: sessionId },
  body: { messageID: "msg-123" },
})

// 中止会话
await client.session.abort({ path: { id: sessionId } })

// 获取会话状态
const { data: statuses } = await client.session.status()
// statuses: { [sessionId: string]: SessionStatus }
// SessionStatus: { type: "idle" } | { type: "busy" } | { type: "retry", ... }

// 获取子会话
const { data: children } = await client.session.children({
  path: { id: sessionId },
})

// 获取会话待办事项
const { data: todos } = await client.session.todo({
  path: { id: sessionId },
})

// 获取会话消息列表
const { data: messages } = await client.session.messages({
  path: { id: sessionId },
  query: { limit: 50 },
})
// messages: Array<{ info: Message, parts: Part[] }>

// 获取单条消息
const { data } = await client.session.message({
  path: { id: sessionId, messageID: "msg-123" },
})

// 获取会话 diff
const { data: diffs } = await client.session.diff({
  path: { id: sessionId },
  query: { messageID: "msg-123" },
})

// 撤销/恢复消息
const { data: session } = await client.session.revert({
  path: { id: sessionId },
  body: { messageID: "msg-123", partID: "part-456" },
})
await client.session.unrevert({ path: { id: sessionId } })

// 分享/取消分享会话
const { data: shared } = await client.session.share({
  path: { id: sessionId },
})
await client.session.unshare({ path: { id: sessionId } })

// 摘要会话
await client.session.summarize({
  path: { id: sessionId },
  body: {
    providerID: "anthropic",
    modelID: "claude-haiku",
  },
})

// 初始化 AGENTS.md
await client.session.init({
  path: { id: sessionId },
  body: {
    providerID: "anthropic",
    modelID: "claude-sonnet-4-20250514",
    messageID: "msg-123",
  },
})
```

### 权限响应

```typescript
await client.postSessionIdPermissionsPermissionId({
  path: { id: sessionId, permissionID: "perm-789" },
  body: { response: "once" },  // "once" | "always" | "reject"
})
```

---

## 其他 API 模块

### Project

```typescript
const { data: projects } = await client.project.list()
const { data: current } = await client.project.current()
```

### PTY (伪终端)

```typescript
const { data: ptys } = await client.pty.list()
const { data: pty } = await client.pty.create({
  body: { command: "/bin/bash", args: [], cwd: "/path", title: "Terminal" },
})
const { data: pty } = await client.pty.get({ path: { id: ptyId } })
const { data: pty } = await client.pty.update({
  path: { id: ptyId },
  body: { title: "New Title", size: { rows: 40, cols: 120 } },
})
await client.pty.connect({ path: { id: ptyId } })
await client.pty.remove({ path: { id: ptyId } })
```

### Config

```typescript
const { data: config } = await client.config.get()
const { data: updated } = await client.config.update({ body: { model: "...", theme: "..." } })
const { data: providers } = await client.config.providers()
```

### Provider

```typescript
const { data } = await client.provider.list()
const { data } = await client.provider.auth()
const { data } = await client.provider.oauth.authorize({ path: { id: providerId }, body: { method: 0 } })
const { data } = await client.provider.oauth.callback({ path: { id: providerId }, body: { method: 0, code: "..." } })
```

### MCP (Model Context Protocol)

```typescript
const { data: status } = await client.mcp.status()
const { data } = await client.mcp.add({
  body: {
    name: "my-server",
    config: {
      type: "local",
      command: ["node", "server.js"],
      enabled: true,
    },
  },
})
await client.mcp.connect({ path: { name: "my-server" } })
await client.mcp.disconnect({ path: { name: "my-server" } })

// MCP 认证流程
const { data } = await client.mcp.auth.start({ path: { name: "my-server" } })
// 获取 authorizationUrl 后打开浏览器...
const { data } = await client.mcp.auth.callback({
  path: { name: "my-server" },
  body: { code: "oauth-code" },
})
// 或一步到位（自动打开浏览器）
const { data } = await client.mcp.auth.authenticate({ path: { name: "my-server" } })
```

### File & Find

```typescript
const { data: files } = await client.file.list({ query: { path: "/src" } })
const { data: content } = await client.file.read({ query: { path: "/src/index.ts" } })
const { data: status } = await client.file.status()

const { data: matches } = await client.find.text({ query: { pattern: "TODO" } })
const { data: paths } = await client.find.files({ query: { query: "*.ts" } })
const { data: symbols } = await client.find.symbols({ query: { query: "createClient" } })
```

### TUI

```typescript
await client.tui.appendPrompt({ body: { text: "追加内容" } })
await client.tui.submitPrompt()
await client.tui.clearPrompt()
await client.tui.executeCommand({ body: { command: "agent_cycle" } })
await client.tui.showToast({
  body: {
    title: "提示",
    message: "操作成功",
    variant: "success",
    duration: 3000,
  },
})
await client.tui.publish({
  body: {
    type: "tui.prompt.append",
    properties: { text: "追加内容" },
  },
})
await client.tui.openHelp()
await client.tui.openSessions()
await client.tui.openThemes()
await client.tui.openModels()
```

### 其他

```typescript
const { data: commands } = await client.command.list()
const { data: agents } = await client.app.agents()
await client.app.log({
  body: { service: "my-service", level: "info", message: "Hello" },
})
await client.instance.dispose()
const { data: pathInfo } = await client.path.get()
const { data: vcsInfo } = await client.vcs.get()
const { data: lspStatus } = await client.lsp.status()
const { data: formatterStatus } = await client.formatter.status()
const { data: toolIds } = await client.tool.ids()
const { data: toolList } = await client.tool.list({
  query: { provider: "anthropic", model: "claude-sonnet-4-20250514" },
})
await client.auth.set({
  path: { id: "provider-id" },
  body: { type: "api", key: "sk-xxx" },
})
```

---

## V2 API

V2 API 位于 `@opencode-ai/sdk/v2`，是基于新版 `@hey-api/openapi-ts` 生成的下一代 API 客户端。入口提供与 V1 相同的顶层函数签名。

### 导入方式

```typescript
import {
  createOpencode,
  createOpencodeClient,
  createOpencodeServer,
  createOpencodeTui,
  data,           // 消息构造工具
} from "@opencode-ai/sdk/v2"
```

### V2 与 V1 的主要差异

| 特性 | V1 (`src/gen/`) | V2 (`src/v2/gen/`) |
|------|-----------------|---------------------|
| Workspace 支持 | 不支持 | 支持 `experimental_workspaceID` 配置，通过 `x-opencode-workspace` 头和 `workspace` 查询参数传递 |
| SSE 实现 | `client.get.sse()` 函数子属性 | `client.sse.get()` 独立的 SSE 命名空间，支持所有 HTTP 方法 |
| 拦截器机制 | `interceptors.request._fns` | `interceptors.request.fns`（结构不完全相同） |
| 响应拦截器 | 无 | 检测 `text/html` 响应并抛出错误 |
| 类型系统 | 整体导出类型定义 | 分离的类型模块，支持 `buildClientParams` |
| 注册表机制 | 无 | `HeyApiRegistry` 支持按 key 管理客户端实例 |
| Session API | 仅有 `/session/{id}/...` 路由 | 额外提供 `QUESTION`（问题）、`PERMISSION`（权限）、`PART`（Part 操作）、`SYNC`（同步）、`V2` 等路由 |

#### Workspace 支持（V2 独有）

```typescript
const client = createOpencodeClient({
  baseUrl: "...",
  directory: "/path/to/project",
  experimental_workspaceID: "workspace-123",
})
```

当设置了 `experimental_workspaceID` 后：
1. 请求头自动添加 `x-opencode-workspace`
2. GET/HEAD 请求的参数改写同时处理 `directory` 和 `workspace` 两个查询参数

#### HTML 响应检测（V2 独有）

V2 客户端增加了响应拦截器，当服务器返回 `content-type: text/html` 时自动抛出错误：

```
"Request is not supported by this version of OpenCode Server (Server responded with text/html)"
```

这用于检测版本不兼容的情况。

### V2 独有新模块

| 子模块 | 说明 |
|--------|------|
| `client.worktree` | Git worktree 管理（创建、列表、删除、重置） |
| `client.question` | 问题列表、回复、拒绝 |
| `client.permission` | 权限请求列表、回复、响应 |
| `client.part` | Part 级别的 CRUD（更新、删除） |
| `client.sync` | 同步操作 |
| `client.v2` | V2 特定 API |
| `client.experimental` | 实验性功能命名空间（Console、Session、Workspace 等） |

#### data 工具（V2 独有）

```typescript
import { data } from "@opencode-ai/sdk/v2"

// 构造用户消息，自动填充 id、time、role 等字段
const msg = data.message.user({
  sessionID: "session-123",
  agent: "build",
  model: { providerID: "anthropic", modelID: "claude-sonnet-4-20250514" },
  parts: [
    { type: "text", text: "Hello" },
  ],
})

console.log(msg.info)   // UserMessage（含自动生成的 id、time、role）
console.log(msg.parts)  // Part[]（含自动填充的 id、messageID、sessionID）
```

---

## 错误处理

### 错误拦截器

SDK 实现了 `wrapClientError` 错误拦截器（`src/error-interceptor.ts`），附加到 HTTP 客户端的 `interceptors.error` 链上。

**触发条件**：仅在调用方设置了 `throwOnError: true` 时才生效。使用 `result.error` 路径（默认 `throwOnError: false`）的调用方不受影响，可以继续按原始结构访问错误字段。

**行为**：
1. 如果错误已经是 `Error` 实例，原样返回
2. 如果错误是带有 `name`/`message` 属性的对象（OpenCode 错误响应的常见格式），提取消息文本构造 `Error`
3. 如果是非空字符串，直接用字符串创建 `Error`
4. 如果以上都不是（空 body、网络失败等），生成描述性错误消息

**消息提取优先级**：
1. `error.data.message`
2. `error.message`
3. `error.name`
4. 回退：`"{METHOD} {URL} -> {STATUS} {STATUS_TEXT}"`

**错误结构**：

```typescript
// 抛出的 Error 对象包含：
new Error(message, {
  cause: {
    body: originalError,    // 原始错误体
    status: response.status // HTTP 状态码
  }
})
```

### 错误类型

SDK 从类型系统中定义了以下错误：

| 错误类型 | 说明 |
|---------|------|
| `BadRequestError` | 请求参数错误，类型为 `"Params" \| "Headers" \| "Query" \| "Body" \| "Payload"` |
| `NotFoundError` | 资源未找到 |
| `ProviderAuthError` | 提供商认证错误 |
| `ApiError` | API 调用错误（含 `statusCode`、`isRetryable`、`responseHeaders`、`responseBody`） |
| `MessageOutputLengthError` | 消息输出长度超限 |
| `MessageAbortedError` | 消息被中止 |
| `UnknownError` | 未知错误 |

每个错误都遵循 `{ name: string, data: { message: string, ... } }` 结构。

---

## 使用示例

### 完整示例：启动服务并创建会话

```typescript
import { createOpencode } from "@opencode-ai/sdk"

// 一步创建服务和客户端
const { client, server } = await createOpencode({
  port: 4096,
  config: {
    model: "anthropic/claude-sonnet-4-20250514",
  },
})

try {
  // 创建会话
  const session = await client.session.create({
    body: { title: "代码分析" },
  })
  console.log("会话已创建:", session.data.id)

  // 发送提示词
  const reply = await client.session.prompt({
    path: { id: session.data.id },
    body: {
      parts: [
        {
          type: "text",
          text: "请分析 src/server.ts 的架构设计",
        },
      ],
    },
  })
  console.log("回复消息:", reply.data.info.id)
  console.log("回复内容:", reply.data.parts)

  // 获取会话消息
  const messages = await client.session.messages({
    path: { id: session.data.id },
  })
  console.log("消息数:", messages.data.length)
} finally {
  server.close()
}
```

### 事件订阅示例

```typescript
import { createOpencode } from "@opencode-ai/sdk"

const { client, server } = await createOpencode()

// 订阅事件流
const eventStream = await client.event.subscribe()

// 在后台处理事件
;(async () => {
  for await (const event of eventStream) {
    switch (event.type) {
      case "session.created":
        console.log("新会话:", event.properties.info.title)
        break
      case "message.part.updated":
        if (event.properties.delta) {
          process.stdout.write(event.properties.delta)
        }
        break
      case "todo.updated":
        console.log("待办更新:", event.properties.todos)
        break
      case "session.error":
        console.error("会话错误:", event.properties.error)
        break
    }
  }
})()

// 执行操作触发事件
const session = await client.session.create({ body: { title: "测试" } })
await client.session.prompt({
  path: { id: session.data.id },
  body: {
    parts: [{ type: "text", text: "写一个 hello world 函数" }],
  },
})
```

### 批量处理示例

```typescript
import { createOpencodeServer, createOpencodeClient } from "@opencode-ai/sdk"

const server = await createOpencodeServer()
const client = createOpencodeClient({ baseUrl: server.url })

const files = ["src/a.ts", "src/b.ts", "src/c.ts"]

// 并行处理多个文件（每个文件创建独立会话）
const tasks = files.map(async (file) => {
  const session = await client.session.create()
  console.log("处理文件:", file)
  await client.session.prompt({
    path: { id: session.data.id },
    body: {
      parts: [
        { type: "file", mime: "text/plain", url: `file://${process.cwd()}/${file}` },
        { type: "text", text: "为这个文件的每个公开函数编写单元测试" },
      ],
    },
  })
  console.log("完成:", file)
})

await Promise.all(tasks)
server.close()
```

### V2 API 示例

```typescript
import { createOpencode } from "@opencode-ai/sdk/v2"
import { data } from "@opencode-ai/sdk/v2"

const { client, server } = await createOpencode({
  config: { model: "anthropic/claude-sonnet-4-20250514" },
})

// 使用 data 工具构造消息
const msg = data.message.user({
  sessionID: "session-xxx",
  agent: "build",
  model: { providerID: "anthropic", modelID: "claude-sonnet-4-20250514" },
  parts: [{ type: "text", text: "优化这段代码的性能" }],
})

// V2 的 Part 操作
const { data: parts } = await client.part.list({
  // ... 获取会话消息的 parts
})

// V2 的权限管理
const { data: permissions } = await client.permission.list()
await client.permission.reply({
  permissionID: "perm-123",
  body: { sessionID: "session-xxx", response: "allow" },
})

// 带 workspace 的客户端
const v2client = createOpencodeClient({
  baseUrl: server.url,
  directory: "/path/to/project",
  experimental_workspaceID: "ws-456",
  throwOnError: true,  // V2 特有的错误处理
})
```

### TUI 进程管理示例

```typescript
import { createOpencodeTui } from "@opencode-ai/sdk"

const controller = new AbortController()

const tui = createOpencodeTui({
  model: "anthropic/claude-sonnet-4-20250514",
  agent: "build",
  config: {
    theme: "dark",
    logLevel: "INFO",
  },
  signal: controller.signal,
})

// 10 分钟后自动关闭
setTimeout(() => {
  tui.close()
}, 10 * 60 * 1000)
```

---

## 类型系统

### 核心消息类型

```typescript
// 用户消息
interface UserMessage {
  id: string
  sessionID: string
  role: "user"
  time: { created: number }
  summary?: {
    title?: string
    body?: string
    diffs: FileDiff[]
  }
  agent: string
  model: { providerID: string; modelID: string }
  system?: string
  tools?: { [key: string]: boolean }
}

// 助手消息
interface AssistantMessage {
  id: string
  sessionID: string
  role: "assistant"
  time: { created: number; completed?: number }
  error?: ProviderAuthError | UnknownError | MessageOutputLengthError | MessageAbortedError | ApiError
  parentID: string
  modelID: string
  providerID: string
  mode: string
  path: { cwd: string; root: string }
  summary?: boolean
  cost: number
  tokens: {
    input: number
    output: number
    reasoning: number
    cache: { read: number; write: number }
  }
  finish?: string
}

// 消息联合类型
type Message = UserMessage | AssistantMessage
```

### Part 类型

| Part 类型 | 字段 |
|-----------|------|
| `text` | `type: "text"`, `text: string`, `synthetic?`, `ignored?`, `time?`, `metadata?` |
| `reasoning` | `type: "reasoning"`, `text: string`, `time`, `metadata?` |
| `tool` | `type: "tool"`, `callID`, `tool`, `state` (pending/running/completed/error) |
| `file` | `type: "file"`, `mime`, `url`, `filename?`, `source?` |
| `step-start` | `type: "step-start"`, `snapshot?` |
| `step-finish` | `type: "step-finish"`, `reason`, `cost`, `tokens`, `snapshot?` |
| `snapshot` | `type: "snapshot"`, `snapshot` |
| `patch` | `type: "patch"`, `hash`, `files` |
| `agent` | `type: "agent"`, `name`, `source?` |
| `retry` | `type: "retry"`, `attempt`, `error`, `time` |
| `compaction` | `type: "compaction"`, `auto` |
| `subtask` | `type: "subtask"`, `prompt`, `description`, `agent` |

### 事件类型

```typescript
type Event =
  | { type: "server.instance.disposed"; properties: { directory: string } }
  | { type: "session.created";       properties: { info: Session } }
  | { type: "session.updated";       properties: { info: Session } }
  | { type: "session.deleted";       properties: { info: Session } }
  | { type: "session.diff";          properties: { sessionID: string; diff: FileDiff[] } }
  | { type: "session.status";        properties: { sessionID: string; status: SessionStatus } }
  | { type: "session.idle";          properties: { sessionID: string } }
  | { type: "session.compacted";     properties: { sessionID: string } }
  | { type: "session.error";         properties: { sessionID?: string; error?: ... } }
  | { type: "message.updated";       properties: { info: Message } }
  | { type: "message.removed";       properties: { sessionID: string; messageID: string } }
  | { type: "message.part.updated";  properties: { part: Part; delta?: string } }
  | { type: "message.part.removed";  properties: { sessionID: string; messageID: string; partID: string } }
  | { type: "permission.updated";    properties: Permission }
  | { type: "permission.replied";    properties: { ... } }
  | { type: "file.edited";           properties: { file: string } }
  | { type: "file.watcher.updated";  properties: { file: string; event: "add" | "change" | "unlink" } }
  | { type: "todo.updated";          properties: { sessionID: string; todos: Todo[] } }
  | { type: "command.executed";      properties: { name: string; sessionID: string; arguments: string; messageID: string } }
  | { type: "pty.created";           properties: { info: Pty } }
  | { type: "pty.updated";          properties: { info: Pty } }
  | { type: "pty.exited";           properties: { id: string; exitCode: number } }
  | { type: "pty.deleted";          properties: { id: string } }
  | { type: "vcs.branch.updated";   properties: { branch?: string } }
  | { type: "server.connected";     properties: {} }
  | { type: "installation.updated"; properties: { version: string } }
  | { type: "installation.update-available"; properties: { version: string } }
  | { type: "lsp.updated";          properties: {} }
  | { type: "lsp.client.diagnostics"; properties: { serverID: string; path: string } }
  | { type: "tui.prompt.append";    properties: { text: string } }
  | { type: "tui.command.execute";  properties: { command: string } }
  | { type: "tui.toast.show";       properties: { title?, message, variant, duration? } }
```

### 配置类型

完整的 `Config` 类型包含以下主要配置域：

| 配置域 | 说明 |
|--------|------|
| `model` | 默认模型 `"provider/model"` 格式 |
| `small_model` | 小型模型（用于标题生成等辅助任务） |
| `theme` | UI 主题名称 |
| `keybinds` | 自定义快捷键配置 |
| `agent` | Agent 配置（plan、build、general、explore 等） |
| `provider` | 模型提供商配置与模型覆盖 |
| `mcp` | MCP 服务器配置（local/remote） |
| `lsp` | LSP 服务器配置 |
| `formatter` | 代码格式化器配置 |
| `command` | 自定义命令模板 |
| `permission` | 权限策略（edit、bash、webfetch 等） |
| `tools` | 工具开关 |
| `plugin` | 插件列表 |
| `instructions` | 额外的指令文件或模式 |
| `watcher` | 文件监视器忽略规则 |
| `share` | 会话分享策略 |
| `autoupdate` | 自动更新策略 |
| `enterprise` | 企业版配置 |
| `experimental` | 实验性功能（hooks、telemetry、primary_tools 等） |

---

## 兼容性

- **运行时要求**：Node.js 22+（基于 `@tsconfig/node22`）
- **模块格式**：ES Module (`"type": "module"`, `"module": "nodenext"`)
- **编译目标**：ES2022，含 DOM 类型（`lib: ["es2022", "dom", "dom.iterable"]`）
- **平台支持**：Linux、macOS、Windows（`cross-spawn` 确保跨平台进程启动）
- **唯一运行时依赖**：`cross-spawn`
- **开发依赖**：`@hey-api/openapi-ts`（用于从 OpenAPI 规范生成客户端代码）、TypeScript
