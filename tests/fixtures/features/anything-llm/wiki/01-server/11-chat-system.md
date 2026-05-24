# 11 — 聊天处理管线

## 概述

AnythingLLM 支持三种聊天模式和多条聊天处理路径，包括标准 RAG 聊天、Agent 聊天、API 聊天和嵌入组件聊天。

## 聊天模式

| 模式 | 说明 |
|------|------|
| `chat` | 标准对话模式，结合历史进行 LLM 对话，向量搜索作为补充 |
| `query` | 严格查询模式，仅基于文档内容回答，无文档时拒绝回答 |
| `automatic` | 自动模式，根据消息是否包含 `@agent` 自动在 Agent 和标准模式间切换 |

## 聊天处理流程

### 主流程（`streamChatWithWorkspace`）
**文件**: `server/utils/chats/stream.js` (318 行)

```
用户消息
├── 1. 斜杠命令处理（grepCommand）
│   ├── /reset → 重置聊天历史
│   └── 自定义预设 → 替换为提示词
├── 2. Agent 检测（grepAgents）
│   └── @agent 消息 → 进入 Agent 流程
├── 3. 查询模式检查
│   └── 无向量数据 + query 模式 → 提前返回拒绝
├── 4. 上下文收集
│   ├── 固定文档（DocumentManager.pinnedDocs）
│   ├── 解析文件（WorkspaceParsedFiles.getContextFiles）
│   └── 聊天历史（recentChatHistory）
├── 5. 向量搜索
│   └── VectorDb.performSimilaritySearch()
│       ├── 相似度阈值过滤
│       ├── TopN 限制
│       └── 可选重排序
├── 6. 来源回填（fillSourceWindow）
│   └── 从聊天历史响应中补充来源文档
├── 7. 消息压缩（LLMConnector.compressMessages）
│   └── Cannonball 方法确保不超出 Token 限制
├── 8. LLM 调用
│   ├── 流式: streamGetChatCompletion → handleStream
│   └── 非流式: getChatCompletion
└── 9. 保存聊天记录（WorkspaceChats.new）
```

### 来源回填机制（fillSourceWindow）

当向量搜索结果不足 `nDocs` 个时，从最近的聊天历史响应中补充来源文档：
- 跳过固定文档（`filterIdentifiers`）
- 跳过重复文档（`sourceIdentifier` 去重）
- 使用 `contextTexts` 累积上下文（包含所有来源）
- 使用 `sources` 仅显示当前搜索的来源（减少用户困惑）

### 去重标识（sourceIdentifier）

```javascript
sourceIdentifier(doc) → `title:${doc.title}-timestamp:${doc.published}`
```
用于防止固定文档和向量搜索结果重叠。

## API 聊天处理

### 同步聊天（`chatSync`）
**文件**: `server/utils/chats/apiChatHandler.js`

与主流程类似，但：
- 支持 `reset` 参数清除聊天历史
- 使用 `apiSessionId` 分区聊天
- 处理多模态附件（文档附件 + 图片附件）
- 文档附件通过 CollectorApi 解析
- 返回完整 JSON 响应（非 SSE）

### API 流式聊天（`streamChat`）
同上但使用 SSE 流式输出。

### OpenAI 兼容聊天
**文件**: `server/utils/chats/openaiCompatible.js` (518 行)

将 AnythingLLM 转换为 OpenAI API 兼容端点：
- `chatSync`: 返回 OpenAI 格式 `chat.completion` JSON
- `streamChat`: 通过 `PassThrough` 流拦截并重写为 OpenAI SSE 格式
- `formatJSON`: 将 AnythingLLM 块格式转为 OpenAI 格式
- 不支持 Agent 或斜杠命令

## 嵌入组件聊天

**文件**: `server/utils/chats/embed.js` (230 行)

- 仅支持 `query` 和 `chat` 模式（不支持 automatic/Agent）
- 支持提示/模型/温度覆盖
- 通过 `session_id` 区分会话
- 独立的聊天存储（`EmbedChats`）

## 斜杠命令系统

**文件**: `server/utils/chats/index.js`

### 内置命令
| 命令 | 功能 |
|------|------|
| `/reset` | 重置聊天历史（标记 include: false） |

### 自定义预设命令
通过 `SlashCommandPresets` 模型管理：
- 用户级预设（`uid`, `userId` 关联）
- 系统级预设（`uid = 0`）
- 递归替换：一条消息中支持多个命令
- 支持 API 调用的全局命令替换（`grepAllSlashCommands`）

## Agent 聊天路由

**文件**: `server/utils/chats/agents.js`

- 检测 `@agent` 提及或 `automatic` 模式下的原生工具调用模型
- 创建 `WorkspaceAgentInvocation` 记录
- 缓存附件到内存（供 AgentHandler 使用）
- 发送 WebSocket UUID 连接响应到前端

## 聊天历史管理

### 历史获取
- `recentChatHistory()`: 按用户/工作区/线程/API会话获取历史
- 按 `id: desc` 排序后反转（最新消息在最后）
- 限制 `messageLimit`（默认 20）

### 历史转换
- `convertToChatHistory()`: 转为前端格式（含附件、来源、反馈）
- `convertToPromptHistory()`: 转为 LLM 格式（`{role, content}`）

### 消息限制预算
```javascript
history = promptWindowLimit() * 0.15  // 15%
system  = promptWindowLimit() * 0.15  // 15%
user    = promptWindowLimit() * 0.7   // 70%
```

### 聊天导出
支持的格式: json, csv, jsonl, jsonAlpaca
- `exportChatsAsType(format, chatType)`: 工作区或嵌入聊天

## 提示词系统

### 系统提示词
- 工作区级: `workspace.openAiPrompt`
- 系统默认: `SystemSettings.saneDefaultSystemPrompt`
- 变量替换: `SystemPromptVariables.expandSystemPromptVariables()`

### 提示词变量
- `system` 类型: 系统范围变量
- `user` 类型: 用户特定变量
- `dynamic` 类型: 动态计算变量

### 提示词历史跟踪
- `PromptHistory` 模型记录每次提示词变更
- 跟踪变更人、时间
- 发送遥测事件
- 用于未来提示词库/助手功能
