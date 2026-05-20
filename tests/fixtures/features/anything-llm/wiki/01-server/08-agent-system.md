# 08 — Agent 系统 (Aibitat)

## 概述

Aibitat 是 AnythingLLM 自研的多 Agent 协作框架，支持多模型提供商、丰富的工具插件系统、智能工具选择和 WebSocket 实时通信。

## 核心架构

```
AgentHandler (WebSocket)
├── AIbitat (核心引擎)
│   ├── chat()        # 对话循环
│   ├── reply()        # LLM 交互
│   ├── selectNext()   # 多 Agent 路由
│   └── handleExecution() / handleAsyncExecution()  # 工具执行
├── Provider (LLM 提供商抽象)
│   ├── Tooled (原生工具调用 - OpenAI/Anthropic/Gemini)
│   └── UnTooled (提示词工具调用 - 20+ 提供商)
├── Plugins (工具插件系统)
└── Utils (工具重排序、去重、总结)
```

## AgentHandler 类

**文件**: `server/utils/agents/index.js` (773 行)

主要的 Agent 处理程序，通过 WebSocket 与前端通信。

### 初始化流程
1. 验证 `WorkspaceAgentInvocation` 存在且未过期
2. 设置 provider/model（从工作区配置或调用覆盖）
3. 创建 AIbitat 实例
4. 加载 Agent 和插件
5. 调用 `startAgentCluster()` 启动对话

### Agent 创建
系统创建两个 Agent：
- **USER** Agent: 代表人类用户，`interrupt: true`，`role: "human monitor"`
- **@agent** Agent: 工作区 Agent，加载所有配置的函数/工具

### 插件加载
通过 `#attachPlugins()` 加载：
- **标准插件**: memory, summarize, web-browsing, web-scraping, rechart, create-files, filesystem, sql-agent, gmail, outlook, google-calendar
- **技能可用性检查** (`SKILL_FILTER_CONFIG`): filesystem（需启用 + 配置路径），create-files（需启用 + 存储目录可写），gmail（需 OAuth 配置），outlook（需 OAuth 配置）
- **Flow 插件**: `@@flow_{uuid}` 前缀
- **MCP 插件**: `@@mcp_{name}` 前缀
- **导入插件**: `@@{hubId}` 格式
- **子插件**: `parent#child` 表示法（如 `filesystem-agent#read-text-file`）

### 环境变量检查
`checkSetup()` 方法验证 30+ 提供商的 API Key 等环境变量是否已配置。

## EphemeralAgentHandler

**文件**: `server/utils/agents/ephemeral.js` (642 行)

继承 `AgentHandler`，用于无状态、一次性 Agent 调用（API、Telegram、定时任务）。

### 与 AgentHandler 的区别
| 特性 | AgentHandler | EphemeralAgentHandler |
|------|-------------|----------------------|
| 通信方式 | WebSocket | HTTP (httpSocket) |
| 上下文加载 | 从 DB + overrideContext | 仅从 DB |
| 工具覆盖 | 始终加载全部 | 通过 `toolOverrides` 控制 |
| 文件上下文 | 检查调用附件 | 直接从配置获取 |
| 流式输出 | WebSocket 事件 | ReadableStream → NDJSON |

### EphemeralEventListener
模拟 WebSocket 的事件发射器，用于 HTTP 流式输出。将 AIbitat 事件（statusResponse, textStream, textResponse, finalResponse, toolApproval 等）转换为 NDJSON 格式的 SSE 流。

## AIbitat 核心引擎

**文件**: `server/utils/agents/aibitat/index.js` (1355 行)

### chat() — 对话循环
- 递归方法，持续处理消息
- 调用 `reply()` 获取 LLM 响应
- 通过 `selectNext()` 确定下一个发言的 Agent
- 递归直到 USER Agent 被选中或对话终止
- 跟踪 `maxDepth` 限制

### reply() — LLM 交互核心
- 查找当前 Agent 的 provider 配置
- 构建消息历史（系统提示 + 工具结果 + 对话历史）
- 调用 `handleExecution()`（非流式）或 `handleAsyncExecution()`（流式）

### handleExecution() — 同步工具执行
- 调用 LLM 并传递工具定义
- 逐个处理工具调用（`_currentToolCallDepth` 限制 15）
- 总数限制 `_totalToolCalls` 为 50
- 支持重试逻辑（`_errorInterceptor`）

### handleAsyncExecution() — 流式工具执行
- 使用 provider 的 `stream()` 方法
- 实时发送 `streamAgentResponse` 事件
- 检测流中的工具调用
- 支持并发工具执行

### selectNext() — 多 Agent 路由
- 使用 `interruptModel`（辅助 LLM）分析对话
- 根据 Agent 描述决定谁应该下一个发言
- 支持群聊式多 Agent 对话

### getProviderForConfig() — 提供商路由
将提供商字符串映射到对应的 Provider 类，支持 34+ 提供商。

## 提供商系统

### Provider 基类
**文件**: `server/utils/agents/aibitat/providers/ai-provider.js` (656 行)

提供通用基础设施：
- Token 使用跟踪（`resetUsage`, `recordUsage`, `getUsage`）
- 多模态消息格式化（`formatMessageWithAttachments`）
- 流式/非流式基类实现
- LangChain 模型创建（`LangChainChatModel`，支持 30+ 提供商）
- 系统提示生成（`systemPrompt`）

### 工具调用模式

#### Tooled（原生工具调用）
**文件**: `providers/helpers/tooled.js` (385 行)

用于 OpenAI, Anthropic, Azure, Gemini, DeepSeek 等支持原生 function calling 的模型：
- `formatFunctionsToTools()`: 将内部函数格式转为 OpenAI tool 格式
- `formatMessagesForTools()`: 转换消息格式，处理 function → tool_calls 映射
- `tooledStream()`: 流式工具调用，跟踪 `tool_call_index` 增量
- `tooledComplete()`: 非流式工具调用，JSON 解析修复，重试支持

#### UnTooled（提示词工具调用）
**文件**: `providers/helpers/untooled.js` (438 行)

用于 20+ 不支持原生 function calling 的模型：
- `showcaseFunctions()`: 生成 few-shot 示例，训练模型输出 JSON
- `buildToolCallMessages()`: 将工具描述注入系统提示
- `functionCall()`: 解析模型输出中的 JSON 函数调用
- `streamingFunctionCall()`: 累积流式文本并解析函数调用
- `isMCPTool()`: MCP 工具冷却管理

### 提供商特性矩阵

| 提供商 | 工具调用方式 | 流式 | 特殊功能 |
|--------|-------------|------|----------|
| OpenAI | 原生 (Responses API) | ✓ | 新版 API，gpt-5/o系列温度强制为1 |
| Anthropic | 原生 (Messages API) | ✓ | cache_control, system prompt分离 |
| Gemini | 原生 (兼容层) | ✓ | gtc__ 前缀，thought_signature |
| Azure | 原生 | ✓ | reasoning模型，用户角色模拟 |
| DeepSeek | 原生 | ✓ | reasoning_content，thinking模型 |
| Ollama | 混合（运行时检测） | ✓ | thinking字段，capabilities检测 |
| LM Studio | 混合（运行时检测） | ✓ | 模型能力检测 |
| Novita | 混合（硬编码列表） | ✓ | deepseek/qwen工具模型检测 |
| Groq | ENV 标志 | ✓ | 视觉模型特殊处理 |
| Generic OpenAI | 运行时检测 | ✓ | 高度灵活 |
| Bedrock | ENV 标志 (LangChain) | ✓ | IAM/API Key认证 |
| Cohere | UnTooled 始终 | ✓ | 原生CohereClientV2 SDK |
| LocalAI | ENV 标志 | ✓ | - |
| LiteLLM | ENV 标志 | ✓ | - |
| 其他 20+ | UnTooled | ✓ | 标准模式 |

## 工具重排序（ToolReranker）

**文件**: `server/utils/agents/aibitat/utils/toolReranker.js` (226 行)

智能工具选择：
- 可配置（`AGENT_SKILL_RERANKER_ENABLED`）
- 默认 Top N = 5（可配置 `AGENT_SKILL_RERANKER_TOP_N`）
- 将工具描述转为文本文档
- 使用 `NativeEmbeddingReranker` 计算相关性
- 每次处理 25 个文档
- 失败时优雅回退（返回所有工具）

## 去重系统（Deduplicator）

**文件**: `server/utils/agents/aibitat/utils/dedupe.js` (153 行)

三层防护：
1. SHA-256 哈希去重：跟踪 `toolName + args` 的哈希
2. 冷却期：30秒内相同调用被拒绝
3. 唯一标记：某些工具一次对话只能调用一次

## WebSocket 插件

**文件**: `server/utils/agents/aibitat/plugins/websocket.js` (272 行)

浏览器通信插件：
- `introspect()`: 发送状态更新
- `socket.send()`: 发送类型化消息
- `requestToolApproval()`: 工具审批流程（白名单检查 → 前端确认 → 2分钟超时）
- `askForFeedback()`: Agent 中断机制（前端输入 → 5分钟超时）
- 支持 `WEBSOCKET_BAIL_COMMANDS`（exit, stop, halt, /reset）

## HTTP Socket 插件

**文件**: `server/utils/agents/aibitat/plugins/http-socket.js` (252 行)

用于 HTTP/Telegram/定时任务：
- 工具审批通过 IPC（Bree worker）或 Telegram 机制
- 无 Telegram 上下文时自动拒绝
- 首次消息后关闭连接

## Chat History 插件

**文件**: `server/utils/agents/aibitat/plugins/chat-history.js` (203 行)

持久化 Agent 对话：
- `MESSAGE_SENT` 事件：创建/更新 `WorkspaceChats` 记录
- `MESSAGE_SENT_PAIR` 事件：存储 Agent 响应、引文、附件
- 支持对话重新生成（查找最后用户消息，修剪工具调用历史）
- 自动重命名线程
