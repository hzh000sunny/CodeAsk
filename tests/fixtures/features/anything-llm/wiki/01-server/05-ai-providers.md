# 05 — LLM 提供商系统

## 架构概览

AnythingLLM 支持 35+ 个 LLM 提供商，通过统一的接口模式进行抽象。所有提供商通过 `server/utils/helpers/index.js` 中的工厂函数进行实例化。

## 核心工厂函数

### `getLLMProvider({ provider, model })`
根据 `LLM_PROVIDER` 环境变量（或传入的 provider 参数）实例化对应的 LLM 类，同时附加当前的嵌入引擎。

### `getLLMProviderClass({ provider })`
返回提供商的类（而非实例），用于访问静态方法（如 `promptWindowLimit`）。

### `getBaseLLMProviderModel({ provider })`
返回指定提供商的默认模型名称（从环境变量读取）。

## 统一接口（所有提供商必须实现）

| 方法 | 说明 |
|------|------|
| `streamingEnabled()` | 是否支持流式响应 |
| `promptWindowLimit(model)` | 返回模型上下文窗口大小 |
| `isValidChatCompletionModel(model)` | 验证模型是否适合聊天 |
| `constructPrompt({systemPrompt, contextTexts, chatHistory, userPrompt, attachments})` | 构建消息数组 |
| `getChatCompletion(messages, {temperature})` | 非流式完成 |
| `streamGetChatCompletion(messages, {temperature})` | 流式完成 |
| `handleStream(response, stream, {uuid, sources})` | 处理流式响应，写入 SSE |
| `embedTextInput(text)` / `embedChunks(chunks)` | 嵌入代理（委托给嵌入引擎） |
| `compressMessages(promptArgs, rawHistory)` | 消息压缩（适应上下文窗口） |

## 提供商分类

### 原生 SDK 提供商

| 提供商 | SDK | 默认模型 | 特点 |
|--------|-----|----------|------|
| **OpenAI** | `openai` (Responses API) | gpt-4o | 使用新版 Responses API，支持视觉、推理模型 |
| **Anthropic** | `@anthropic-ai/sdk` | claude-3-5-sonnet | 原生 Messages API，支持 Prompt Caching |
| **Cohere** | `cohere-ai` | command-r-plus | 原生 SDK，自定义流处理 |
| **AWS Bedrock** | `@aws-sdk/client-bedrock-runtime` | - | 支持 IAM/API Key/STS 多种认证，推理内容提取 |
| **Ollama** | `ollama` (原生) | - | 原生 Ollama SDK，支持 thinking/reasoning，num_ctx 配置 |

### OpenAI 兼容提供商

以下提供商使用 OpenAI SDK 但指向不同的 Base URL：

| 提供商 | Base URL | 流处理 | 特点 |
|--------|----------|--------|------|
| **Azure OpenAI** | 动态（formatBaseUrl） | V2 默认 | 支持 reasoning 模型（o1/o3），用户角色模拟 |
| **Gemini** | `generativelanguage.googleapis.com/v1beta/openai/` | V2 默认 | OpenAI 兼容层，实验性模型检测 |
| **DeepSeek** | `api.deepseek.com/v1` | 自定义 | reasoning_content 提取，thinking 标签包装 |
| **Groq** | `api.groq.com/openai/v1` | V2 默认 | 视觉模型特殊 prompt 结构，使用 Groq 计时 |
| **Mistral** | `api.mistral.ai/v1` | V2 默认 | 默认温度 0.0（较低） |
| **Perplexity** | `api.perplexity.ai` | 自定义 | 引文系统，URL 内联链接 |
| **OpenRouter** | `openrouter.ai/api/v1` | 自定义 | reasoning delta，Perplexity 引文处理 |
| **Together AI** | `api.together.xyz/v1` | V2 默认 | 模型获取和缓存 |
| **Fireworks AI** | `api.fireworks.ai/inference/v1` | V2 默认 | context_length 过滤 |
| **xAI (Grok)** | `api.x.ai/v1` | V2 默认 | Grok 模型系列 |
| **Novita** | `api.novita.ai/v3/openai` | 自定义（超时） | 功能检测（function-calling, reasoning, vision） |
| **CometAPI** | `api.cometapi.com/v1` | 自定义（超时） | 非聊天模型过滤模式 |
| **ApiPie** | `apipie.ai/v1` | 自定义 | 模型子类型验证（chat/chatx） |
| **PPIO** | `api.ppinfra.com/v3/openai/` | V2 默认 | 模型获取和缓存 |
| **Moonshot AI** | `api.moonshot.ai/v1` | V2 默认 | - |
| **SambaNova** | `api.sambanova.ai/v1` | 自定义 | total_tokens_per_sec 指标 |
| **Foundry** | 动态 + `/v1` | 自定义（超时） | 本地 GPU，推理内容处理，模型卸载 |
| **Gitee AI** | `ai.gitee.com/v1` | 自定义 | reasoning_content，Legacy Model Map |
| **NVIDIA NIM** | 动态 + `/v1` | V2 默认 | 动态 token 限制设置 |
| **Z.AI** | `api.z.ai/api/paas/v4` | V2 默认 | Vercel AI Gateway |
| **Dell Pro AI Studio** | 动态 + `/v1/openai` | V2 默认 | 无需 API Key |
| **Privatemode** | 动态 + `/v1` | V2 默认 | 硬编码上下文窗口 |

### 本地/自托管提供商

| 提供商 | 特点 |
|--------|------|
| **LM Studio** | 模型能力检测（tools/vision），legacy/v1 API 路径，上下文窗口缓存 |
| **LocalAI** | OpenAI 兼容，本地 Token 计数 |
| **Ollama** | 原生 SDK，模型能力检测，自定义 fetch 超时，认证支持 |
| **KoboldCPP** | 纯文本，本地 Token 计数，max_tokens 传递 |
| **TextGenWebUI** | 简单 OpenAI 兼容，单一模型端点 |
| **Docker Model Runner** | Docker Hub 模型发现，本地/远程模型列表 |
| **HuggingFace** | TGI 端点，system prompt 通过 user 角色模拟，默认温度 0.2 |
| **LiteLLM** | LiteLLM 代理，始终返回有效模型 |

### 特殊提供商

| 提供商 | 特点 |
|--------|------|
| **Generic OpenAI** | 最灵活，支持任意 OpenAI 兼容端点，自定义 Header，llama.cpp 计时提取 |
| **Lemonade** | Lemonade 服务器，模型预加载，功能标签检测 |
| **LiteLLM** | 运行时提示 Token 计算 |

## 消息压缩策略（Cannonball 方法）

所有提供商使用统一的压缩算法：

```
上下文窗口分配：
- 系统提示（System）: 最多 15%
- 历史消息（History）: 最多 15%
- 用户提示（User）: 最多 70%
```

压缩过程：
1. 如果用户提示超限 → 劫持整个线程
2. 系统提示压缩 → cannonball（从中间截断）
3. 历史消息压缩 → 从最近消息开始切片，cannonball 消息对

## 模型映射（ContextWindowFinder）

通过 LiteLLM 的 `model_prices_and_context_window.json` 获取模型上下文窗口：

- 定期从 GitHub 拉取（3天 TTL）
- 缓存到 `storage/models/context-windows/context-windows.json`
- 回退到 `legacy.js` 硬编码映射
- 支持的映射：anthropic, openai, cohere, gemini, groq, xai, deepseek, moonshot, zai, sambanova

## 流式处理模式

### V2 默认流处理（`handleDefaultStreamResponseV2`）
用于 20+ 提供商：直接从 OpenAI 兼容流读取 chunks，聚合全文，提取 usage，写入 SSE。

### 自定义流处理（带超时）
用于 CometAPI, Foundry, Novita, OpenRouter, Perplexity：
- 基于间隔的陈旧检测（每 500ms 检查）
- 可配置的超时时间
- 处理不返回 `finish_reason` 的模型

### 推理内容流处理
用于 Anthropic, Bedrock, DeepSeek, GenericOpenAI, GiteeAI, Ollama, SambaNova, OpenRouter：
- 提取 `reasoning_content` / `thinking` 字段
- 包装在 `&lt;think&gt;&lt;/think&gt;` 标签中
- 区分推理过程和最终输出

## Token 性能监控（LLMPerformanceMonitor）

- `countTokens(messages)`: 使用 TokenManager 统计
- `measureAsyncFunction(func)`: 测量非流式调用的持续时间
- `measureStream({func, messages, ...})`: 测量流式调用，附加 `.metrics` 到流对象
