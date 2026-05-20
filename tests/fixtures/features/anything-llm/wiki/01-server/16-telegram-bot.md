# 16 — Telegram 机器人

## 概述

完整的 Telegram Bot 集成，支持 Bot 命令、Agent 对话、流式聊天响应和语音输出。

## 架构

```
Telegram Webhook → handleTelegramChat (job/子进程)
  → TelegramBot (node-telegram-bot-api, polling: false)
  → streamResponse (utils/telegramBot/chat/stream.js)
      ├── Agent 检测 → handleAgentResponse (chat/agent.js)
      ├── 标准 RAG 管道 → 固定文档 + 向量搜索 + LLM
      └── 流式编辑 → 实时更新 Telegram 消息
```

## 聊天处理流程（streamResponse）

**文件**: `server/utils/telegramBot/chat/stream.js` (470 行)

### 完整处理流程
1. 发送 `typing` 指示器
2. 获取聊天历史
3. **Agent 检测**：
   - 检查历史中是否有 `@agent` 消息（`historyIsAgentic()`）
   - 检查当前消息是否为 Agent 调用（`AgentHandler.isAgentInvocation()`）
   - 如命中 → 委托给 `handleAgentResponse()`
4. 保持 `typing` 指示器（每 4 秒更新）
5. 收集固定文档上下文
6. 执行向量搜索 + 来源回填
7. 消息压缩
8. LLM 响应生成
9. 持久化 + 传递（含可选语音）

### 流式响应处理（createStreamHandler）
实时编辑 Telegram 消息的流式处理：
- **消息分片**：超长文本自动分割（`MAX_MSG_LEN`）
- **节流编辑**：防止超过 Telegram 速率限制（`STREAM_EDIT_INTERVAL`）
- **编辑指示器**：未完成消息显示光标字符（`CURSOR_CHAR`）
- **最终格式化**：完成时进行 Markdown 格式化
- 状态管理：`messageId`, `msgOffset`, `lastEditTime`

### 流式消息状态机
```
收到 token → 追加到 completeText
  → splitMessageIfOverflow()：超限 → 完成当前消息，创建新消息
  → startNewMessageIfNeeded()：无活动消息 → 发送新消息
  → scheduleThrottledEdit()：编辑现有消息（节流）
```

## 命令系统

**文件**: `server/utils/telegramBot/utils/commands/index.js`

### 9 个内置命令

| 命令 | 处理器 | 功能 |
|------|--------|------|
| `/start` | handleStart | 初始化机器人，显示欢迎信息 |
| `/switch` | showWorkspaceMenu | 切换工作区或线程（内联菜单） |
| `/model` | showModelMenu | 更改 LLM 模型（内联菜单） |
| `/new` | handleNewThread | 创建新对话线程 |
| `/history` | handleHistory | 显示最近消息（如 `/history 25`） |
| `/status` | handleStatus | 显示当前工作区和模型 |
| `/reset` | handleReset | 清除当前线程的聊天历史 |
| `/help` | handleHelp | 显示所有可用命令 |
| `/proof` | handleProof | 显示上次回复的引用来源 |
| `/abort` | handleAbort | 停止当前正在生成的响应 |

### BotContext 接口
```javascript
ctx = {
  bot:       TelegramBot 实例,
  config:    机器人配置,
  getState:  (chatId) → { workspaceSlug, threadSlug },
  setState:  (chatId, updates) → void,
  log:       (text, ...args) → void
}
```

## 导航系统

**文件**: `server/utils/telegramBot/utils/navigation/`

- 内联键盘构建
- 回调处理（按钮点击）
- 分页列表（工作区、线程、模型）
- 菜单状态管理

## Agent 集成

**文件**: `server/utils/telegramBot/chat/agent.js`

- 通过 `EphemeralAgentHandler` 处理 Agent 对话
- 使用 `http-socket.js` 插件进行 HTTP 通信
- 工具审批通过 Telegram IPC 机制处理
- Agent 输出格式化（支持 Markdown 和文件链接）

## 消息工具

**文件**: `server/utils/telegramBot/utils/`

- `sendFormattedMessage()`: 发送 Markdown 格式消息
- `editMessage()`: 编辑现有消息
- `sendVoiceResponse()`: 生成并发送语音回复
- `MAX_MSG_LEN`: 消息最大长度
- `STREAM_EDIT_INTERVAL`: 编辑节流间隔
- `CURSOR_CHAR`: 未完成指示器字符

## 数据持久化

- 聊天记录存储到 `WorkspaceChats`（带 thread_id）
- 在 AnythingLLM UI 中可见
- 支持完整的聊天历史导出

## API 端点

**文件**: `server/endpoints/telegram.js`

注册 Telegram webhook 和消息接收端点，处理来自 Telegram 的更新。
