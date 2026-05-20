# Slack 集成

Slack 包 (`@opencode-ai/slack`) 是一个 Slack Bot 集成，通过 Socket Mode 将 OpenCode AI 助手接入 Slack 工作区，在 Slack 线程中提供服务。

## 技术栈

| 技术 | 用途 |
|------|------|
| @slack/bolt | Slack 应用框架（Socket Mode） |
| @opencode-ai/sdk | OpenCode JS SDK（创建客户端和服务端实例） |

## 架构总览

```
┌─────────────────────────────────────────────────────────┐
│                      Slack 工作区                        │
│  ┌─────────────────────────────────────────────────┐   │
│  │   用户发送消息 → 线程                                │   │
│  └──────────────────────┬──────────────────────────┘   │
│                         │ WebSocket (Socket Mode)       │
│  ┌──────────────────────┴──────────────────────────┐   │
│  │              @slack/bolt App                      │   │
│  │  ┌────────────────┐  ┌───────────────────────┐   │   │
│  │  │ message handler │  │ command handler (/test)│   │   │
│  │  └───────┬────────┘  └───────────────────────┘   │   │
│  │          │                                        │   │
│  │  ┌───────┴────────────────────────────────────┐  │   │
│  │  │         会话管理 (sessions Map)              │  │   │
│  │  │  key: "{channel}-{thread}"                  │  │   │
│  │  │  value: { client, server, sessionId,        │  │   │
│  │  │           channel, thread }                  │  │   │
│  │  └───────┬────────────────────────────────────┘  │   │
│  └──────────┼──────────────────────────────────────┘   │
│             │                                            │
│  ┌──────────┴──────────────────────────────────────┐   │
│  │          @opencode-ai/sdk (opencode 实例)        │   │
│  │  ┌──────────────┐  ┌─────────────────────────┐  │   │
│  │  │ client.event │  │ client.session          │  │   │
│  │  │ .subscribe() │  │ .create/.prompt/.share  │  │   │
│  │  └──────────────┘  └─────────────────────────┘  │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

## 初始化与配置

### 环境变量

Bot 启动需要三个环境变量，参见 `.env.example`：

```bash
SLACK_BOT_TOKEN=xoxb-your-bot-token       # Bot User OAuth Token
SLACK_SIGNING_SECRET=your-signing-secret   # Signing Secret
SLACK_APP_TOKEN=xapp-your-app-token       # Socket Mode App Token
```

### 启动流程

```typescript
// 1. 创建 Slack App 实例
const app = new App({
  token: process.env.SLACK_BOT_TOKEN,
  signingSecret: process.env.SLACK_SIGNING_SECRET,
  socketMode: true,                          // 启用 Socket Mode
  appToken: process.env.SLACK_APP_TOKEN,
})

// 2. 创建 OpenCode 实例
const opencode = await createOpencode({ port: 0 })

// 3. 启动 Bot
await app.start()
```

Socket Mode 意味着 Bot 不需要公网 HTTP 端点，而是通过 WebSocket 直接连接 Slack 服务器。`port: 0` 表示 OpenCode 服务端使用随机端口。

## 会话管理

### 会话键设计

每个 Slack 线程对应一个独立的 OpenCode 会话，使用 `{channel}-{thread}` 作为会话键：

```typescript
const sessions = new Map<string, {
  client: any
  server: any
  sessionId: string
  channel: string
  thread: string
}>()
```

同一个频道中的不同线程（以及同一线程中的多条消息）共享同一个 OpenCode 会话，保持对话上下文的连续性。

当线程的根消息 `ts` 等于消息自身 `ts` 时，`thread` 使用 `message.ts`；后续回复使用 `message.thread_ts`。

### 会话生命周期

1. 用户在新线程中发送消息
2. 检查 `sessions` Map 中是否存在对应 key
3. 不存在 → 调用 `client.session.create()` 创建新会话
4. 调用 `client.session.share()` 获取分享链接，发送到线程
5. 调用 `client.session.prompt()` 将用户消息发送给 AI
6. 将 AI 的文本响应发送回 Slack 线程
7. 工具调用更新通过事件流异步推送到线程

### 创建新会话

```typescript
const createResult = await client.session.create({
  body: { title: `Slack thread ${thread}` },
})
```

会话标题使用 Slack 线程 ID 标识，便于追溯。创建失败时向用户发送错误提示。

## 事件处理

### 消息处理 (`app.message`)

核心消息流程：

```
用户发送消息
  → 过滤子类型消息 (subtype)
  → 检查消息是否有文本
  → 确定 channel + thread
  → 查找或创建 session
  → session.client.session.prompt()
  → 构建响应文本
  → say() 发送回 Slack
```

**响应构建逻辑**：

```typescript
const responseText =
  response.info?.content ||          // 优先使用 info.content
  response.parts
    ?.filter(p => p.type === "text")
    .map(p => p.text)
    .join("\n") ||                   // 回退到 text parts 拼接
  "I received your message but didn't have a response."  // 兜底
```

### 工具调用更新推送 (`opencode.client.event.subscribe`)

独立于消息处理的异步事件循环，监听 `message.part.updated` 事件：

```typescript
const events = await opencode.client.event.subscribe()
for await (const event of events.stream) {
  if (event.type === "message.part.updated") {
    const part = event.properties.part
    if (part.type === "tool") {
      // 遍历所有 session，找到匹配的 sessionID
      // 将工具完成状态推送到对应 Slack 线程
    }
  }
}
```

当工具调用完成 (`part.state.status === "completed"`) 时，Bot 向对应 Slack 线程发送一条消息，格式为：

```
*工具名称* - 工具状态标题
```

这使用户可以实时看到 AI 正在执行的工具操作（如读取文件、搜索代码等）的进度。

仅推送 `completed` 状态的事件，避免线程噪音。

### 命令处理 (`/test`)

提供一个健康检查命令：

```typescript
app.command("/test", async ({ command, ack, say }) => {
  await ack()
  await say("Bot is working! I can hear you loud and clear.")
})
```

在 Slack 中输入 `/test` 即可验证 Bot 是否正常运行。

### 调试中间件

全局中间件记录所有原始 Slack 事件：

```typescript
app.use(async ({ next, context }) => {
  console.log("Raw Slack event:", JSON.stringify(context, null, 2))
  await next()
})
```

## Slack 线程集成

### 线程消息流

```
Slack 线程                         OpenCode
────────────────────────────────────────────
用户: "帮我重构这个函数"
  └→ 创建 session
  └→ prompt("帮我重构这个函数")
  └→ response: "好的，我来帮你重构..."
                                      └→ tool: read (读取文件)
                                      └→ *read* - 读取 src/utils.ts
                                      └→ tool: edit (修改文件)
                                      └→ *edit* - 修改 src/utils.ts
  └→ "重构完成！主要改动..."
```

### 消息去重与跳过

Bolt 的消息处理器自动跳过以下类型的消息：

- `message.subtype` 存在的消息（如 `message_changed`、`message_deleted`、机器人自己的消息等）
- 缺少 `text` 字段的消息

这避免了 Bot 响应自己的消息或系统事件造成无限循环。

### 错误处理

操作失败时向用户发送友好的错误提示：
- 会话创建失败 → `"Sorry, I had trouble creating a session."`
- 消息发送失败 → `"Sorry, I had trouble processing your message."`
- 工具更新推送失败 → 静默忽略 (`.catch(() => {})`)

## 运行方式

```bash
# 开发模式（直接运行 TypeScript）
bun run src/index.ts

# 类型检查
tsgo --noEmit
```

项目使用 Bun 作为运行时，直接执行 TypeScript 源码无需预编译步骤。
