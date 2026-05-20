# Provider 系统文档

Provider 系统是 OpenCode 中负责管理 AI 模型提供方的核心模块。它负责加载、配置并解析来自不同厂商的 AI 模型，最终通过 AI SDK 暴露统一的 `LanguageModelV3` 接口供上层调用。

源代码: `/home/hzh/wiki/opencode/packages/opencode/src/provider/provider.ts` (1767 行)

---

## 1. 数据结构

### 1.1 Model（模型）

每个模型由以下字段描述：

```typescript
Model {
  id: ModelID          // 模型唯一标识（带 brand 类型的字符串），如 "claude-sonnet-4-5"
  providerID: ProviderID // 所属提供方标识，如 "anthropic"
  api: {
    id: string         // API 层面的模型 ID，如 "claude-sonnet-4-5-20250929"
    url: string        // API 端点 URL
    npm: string        // 对应的 npm 包名，如 "@ai-sdk/anthropic"
  }
  name: string         // 人类可读的模型名称
  family: string       // 模型系列，如 "claude"
  capabilities: {
    temperature: boolean    // 是否支持温度参数
    reasoning: boolean      // 是否支持推理/思考
    attachment: boolean     // 是否支持附件
    toolcall: boolean       // 是否支持工具调用
    input: {                // 输入模态
      text: boolean
      audio: boolean
      image: boolean
      video: boolean
      pdf: boolean
    }
    output: {               // 输出模态
      text: boolean
      audio: boolean
      image: boolean
      video: boolean
      pdf: boolean
    }
    interleaved: boolean | { field: "reasoning_content" | "reasoning_details" }
                            // 是否支持交错内容（如推理过程穿插在输出中）
  }
  cost: {
    input: number           // 输入每 token 成本（美元）
    output: number          // 输出每 token 成本
    cache: {
      read: number          // 缓存读取每 token 成本
      write: number         // 缓存写入每 token 成本
    }
    experimentalOver200K?: { // 超过 200K 上下文窗口的额外成本
      input: number
      output: number
      cache: { read: number; write: number }
    }
  }
  limit: {
    context: number         // 最大上下文窗口（token 数）
    input: number           // 最大输入 token 数（可选）
    output: number          // 最大输出 token 数
  }
  status: "active" | "alpha" | "beta" | "deprecated"  // 模型状态
  options: Record<string, any>   // 模型级别的配置选项
  headers: Record<string, string> // 模型级别的 HTTP 头
  release_date: string           // 发布日期
  variants: Record<string, Record<string, any>>  // 模型变体（如不同推理级别）
}
```

### 1.2 Info（Provider / 提供方）

```typescript
Info (Provider) {
  id: ProviderID       // 提供方唯一标识，如 "anthropic"
  name: string         // 人类可读名称
  source: "env" | "config" | "custom" | "api"
                       // 配置来源：
                       //   "env"  - 通过环境变量检测到的 API Key
                       //   "config" - opencode.json 中配置的
                       //   "custom" - 通过 custom() 加载器激活的
                       //   "api"  - 通过 auth 存储的 API Key
  env: string[]        // 需要检测的环境变量名列表，如 ["ANTHROPIC_API_KEY"]
  key?: string         // 解析后的 API Key
  options: Record<string, any>  // 提供给 SDK 的创建选项（如 baseURL、headers 等）
  models: Record<string, Model> // 此提供方下的所有模型映射
}
```

### 1.3 其他类型

```typescript
// 模型状态枚举
ModelStatus: "alpha" | "beta" | "deprecated" | "active"

// 默认模型 ID 映射
DefaultModelIDs: Record<string, string>  // { [providerID]: modelID }

// 列表查询结果
ListResult {
  all: Info[]           // 所有提供方
  default: DefaultModelIDs  // 每个提供方的默认模型
  connected: string[]   // 已连接的提供方 ID 列表
}
```

---

## 2. 服务接口 (Service Interface)

Provider 服务通过 Effect 框架暴露以下核心方法：

| 方法 | 签名 | 说明 |
|------|------|------|
| `list()` | `Effect<Record<ProviderID, Info>>` | 获取所有已加载的提供方及其模型 |
| `getProvider(id)` | `Effect<Info>` | 根据 ID 获取特定提供方 |
| `getModel(providerID, modelID)` | `Effect<Model>` | 获取特定模型，失败时通过模糊搜索(fuzzysort)提供相似建议 |
| `getLanguage(model)` | `Effect<LanguageModelV3>` | 将 OpenCode 的 Model 解析为 AI SDK 的 `LanguageModelV3` 实例 |
| `closest(providerID, query)` | `Effect<{ providerID, modelID }>` | 根据关键词列表查找最匹配的模型 |
| `getSmallModel(providerID)` | `Effect<Model>` | 查找小型/廉价模型，用于标题生成等低成本任务 |
| `defaultModel()` | `Effect<{ providerID, modelID }>` | 获取默认模型，优先级: config > 最近使用 > 第一个可用 |

---

## 3. 内置提供方 (Bundled Providers)

以下供应商 SDK 直接打包在 OpenCode 中，无需额外安装：

| 提供方 ID | npm 包 | 导入函数 |
|-----------|--------|----------|
| `amazon-bedrock` | `@ai-sdk/amazon-bedrock` | `createAmazonBedrock` |
| `anthropic` | `@ai-sdk/anthropic` | `createAnthropic` |
| `azure` | `@ai-sdk/azure` | `createAzure` |
| `google` | `@ai-sdk/google` | `createGoogleGenerativeAI` |
| `google-vertex` | `@ai-sdk/google-vertex` | `createVertex` |
| `google-vertex-anthropic` | `@ai-sdk/google-vertex/anthropic` | `createVertexAnthropic` |
| `openai` | `@ai-sdk/openai` | `createOpenAI` |
| `openai-compatible` | `@ai-sdk/openai-compatible` | `createOpenAICompatible` |
| `openrouter` | `@openrouter/ai-sdk-provider` | `createOpenRouter` |
| `xai` | `@ai-sdk/xai` | `createXai` |
| `mistral` | `@ai-sdk/mistral` | `createMistral` |
| `groq` | `@ai-sdk/groq` | `createGroq` |
| `deepinfra` | `@ai-sdk/deepinfra` | `createDeepInfra` |
| `cerebras` | `@ai-sdk/cerebras` | `createCerebras` |
| `cohere` | `@ai-sdk/cohere` | `createCohere` |
| `gateway` | `@ai-sdk/gateway` | `createGateway` |
| `togetherai` | `@ai-sdk/togetherai` | `createTogetherAI` |
| `perplexity` | `@ai-sdk/perplexity` | `createPerplexity` |
| `vercel` | `@ai-sdk/vercel` | `createVercel` |
| `alibaba` | `@ai-sdk/alibaba` | `createAlibaba` |
| `gitlab` | `gitlab-ai-provider` | `createGitLab` |
| `github-copilot` | `@ai-sdk/github-copilot` | `createOpenaiCompatible` |
| `venice` | `venice-ai-sdk-provider` | `createVenice` |

---

## 4. 提供方加载流程

### 4.1 总体加载顺序

整个加载过程在 `layer` 的初始化 Effect 中完成，共 9 个步骤，按顺序执行：

```
  ┌────────────────────────────────────────────────────────────────┐
  │                      Provider 加载流程                           │
  ├────────────────────────────────────────────────────────────────┤
  │                                                                 │
  │  Step 1: 加载 models.dev 数据库                                  │
  │          └─ 从 models.dev 服务获取所有已知模型的元数据               │
  │          └─ 通过 fromModelsDevProvider() 转换为 Info 结构           │
  │                                                                 │
  │  Step 2: 加载插件 (plugins)                                      │
  │          └─ 调用 plugin.provider.models() 获取插件模型              │
  │          └─ 应用插件对模型的修改（在读取 config 之前执行）            │
  │                                                                 │
  │  Step 3: 加载配置提供方 (config providers)                         │
  │          └─ 遍历 cfg.provider 中的配置                             │
  │          └─ 合并用户自定义模型到 database 中                         │
  │          └─ 处理每个字段的覆盖逻辑（name, env, options, models 等）   │
  │          └─ 从 models.dev 数据构建 variants                       │
  │                                                                 │
  │  Step 4: 检测环境变量 (env)                                       │
  │          └─ 扫描每个提供方的 env 字段中定义的环境变量                  │
  │          └─ 如果发现对应的 API Key，标记 source 为 "env"              │
  │                                                                 │
  │  Step 5: 加载存储的 Auth Key                                      │
  │          └─ 从 auth service 读取已存储的 API key                    │
  │          └─ 标记 source 为 "api"                                  │
  │                                                                 │
  │  Step 6: 加载插件 Auth Loader                                     │
  │          └─ 调用 plugin.auth.loader() 获取额外配置                   │
  │          └─ 合并 options 到 provider 中                            │
  │                                                                 │
  │  Step 7: 执行 custom() 加载器                                     │
  │          └─ 对每个注册的自定义加载器执行 Effect                       │
  │          └─ 如果 autoload=true 或 provider 已存在，则激活该提供方      │
  │          └─ 注册 modelLoader、varsLoader、discoverModels 等钩子     │
  │          └─ 合并 options 到 provider                               │
  │                                                                 │
  │  Step 8: 重新应用 config 覆盖                                     │
  │          └─ 再次遍历 config providers，覆盖 name、env、options        │
  │                                                                 │
  │  Step 9: 运行发现加载器 (discovery loaders)                        │
  │          └─ 当前仅 gitlab 支持：discoverWorkflowModels()            │
  │          └─ 将发现的模型添加到 provider.models 中                    │
  │                                                                 │
  │  Step 10: 过滤 (Filter)                                          │
  │          └─ 应用 enabled_providers / disabled_providers 过滤        │
  │          └─ 移除 alpha 状态模型（除非开启 experimental flag）         │
  │          └─ 移除 deprecated 状态模型                                │
  │          └─ 应用 per-provider 的 blacklist / whitelist 过滤         │
  │          └─ 移除 gpt-5-chat-latest 等特定模型                       │
  │          └─ 如果 provider 下没有模型，移除整个 provider               │
  │                                                                 │
  └────────────────────────────────────────────────────────────────┘
```

### 4.2 合并策略 (mergeProvider)

核心的 `mergeProvider(providerID, partial)` 函数：

1. 如果 providers 中已存在该提供方，使用 `mergeDeep` 深度合并
2. 如果不存在，从 database 中查找匹配项，再深度合并
3. 如果 database 中也找不到，跳过

这一机制使得配置可以从多个来源（插件、config、env、custom loader）逐层叠加。

---

## 5. 各提供方的详细配置 (custom() Loaders)

每个提供方都有一个对应的 `custom()` 加载器，负责提供方特定的初始化逻辑：

### 5.1 anthropic

- **autoload**: 始终为 `false`（仅当通过 env/config 检测到 key 时才激活）
- **特殊配置**: 设置 `anthropic-beta` 请求头启用实验特性：
  - `interleaved-thinking-2025-05-14` - 交错思考
  - `fine-grained-tool-streaming-2025-05-14` - 细粒度工具流式输出
- **模型获取**: 使用默认的 `sdk.languageModel()`

### 5.2 opencode

- **认证检测**: 检查环境变量中的 API Key、auth 存储、或 config 中的 apiKey
- **付费模型过滤**: 如果没有认证，将 cost.input > 0 的模型移除（仅保留免费模型）
- **无认证模式**: 设置 `apiKey: "public"` 提供公开访问
- **autoload**: 当有可用模型时设为 `true`

### 5.3 openai

- **API 选择**: 使用 Responses API（`sdk.responses(modelID)`）而非 Chat Completions API
- **autoload**: `false`

### 5.4 xai (Grok)

- **API 选择**: 使用 Responses API（`sdk.responses(modelID)`）
- **autoload**: `false`

### 5.5 github-copilot

- **API 选择逻辑**:
  - 如果 SDK 没有 `responses` 和 `chat` 方法，使用 `languageModel()`
  - 对于 GPT-5+ 模型（`gpt-5-*` 但非 `gpt-5-mini`），使用 Responses API
  - 其他模型使用 Chat API（`sdk.chat()`）
- **autoload**: `false`

### 5.6 azure

- **资源名解析优先级**（从高到低）:
  1. `provider.options.resourceName` (config 中配置)
  2. `auth.metadata.resourceName` (auth 存储中)
  3. `env["AZURE_RESOURCE_NAME"]` (环境变量)
- **模型获取**: `selectAzureLanguageModel()` 根据 `useCompletionUrls` 选项选择合适的 API：
  - `useChat && sdk.chat` -> `sdk.chat(modelID)`
  - `sdk.responses` -> `sdk.responses(modelID)`
  - `sdk.messages` -> `sdk.messages(modelID)`
  - `sdk.chat` -> `sdk.chat(modelID)`
  - 默认 -> `sdk.languageModel(modelID)`
- **环境变量导出**: 将解析到的 `resourceName` 导出为 `AZURE_RESOURCE_NAME`

### 5.7 azure-cognitive-services

- 从环境变量 `AZURE_COGNITIVE_SERVICES_RESOURCE_NAME` 获取资源名
- 构建 baseURL: `https://{resourceName}.cognitiveservices.azure.com/openai`
- 模型获取逻辑与 azure 相同

### 5.8 amazon-bedrock

- **区域解析优先级**:
  1. config 中 `options.region`
  2. 环境变量 `AWS_REGION`
  3. 默认值 `us-east-1`

- **凭据配置优先级**:
  1. `AWS_PROFILE`（config > env）
  2. `AWS_ACCESS_KEY_ID`
  3. `AWS_BEARER_TOKEN_BEDROCK`（env 或 auth key）
  4. `AWS_WEB_IDENTITY_TOKEN_FILE`
  5. 容器凭据（ECS/EKS）
  6. `fromNodeProviderChain()` 默认凭据链

- **跨区域推理配置**: 自动为模型添加区域前缀：
  - **US 区域**: 对 claude/nova/deepseek 系列添加 `us.` 前缀
  - **EU 区域** (eu-west-1/2/3, eu-north-1, eu-central-1, eu-south-1/2): 对 claude/nova-lite/nova-micro/llama3/pixtral 添加 `eu.` 前缀
  - **AP 区域**: 
    - 澳大利亚 (ap-southeast-2/4): 对 sonnet-4-5/haiku 使用 `au.` 前缀
    - 东京 (ap-northeast-1): 对 claude/nova 系列使用 `jp.` 前缀
    - 其他 APAC: 对 claude/nova 系列使用 `apac.` 前缀
  - 已有前缀的模型（`global.`/`us.`/`eu.`/`jp.`/`apac.`/`au.`）跳过前缀添加

### 5.9 google-vertex

- **项目 ID 解析优先级**:
  1. `provider.options.project`
  2. `GOOGLE_CLOUD_PROJECT`
  3. `GCP_PROJECT`
  4. `GCLOUD_PROJECT`

- **位置解析优先级**:
  1. `provider.options.location`
  2. `GOOGLE_VERTEX_LOCATION`
  3. `GOOGLE_CLOUD_LOCATION`
  4. `VERTEX_LOCATION`
  5. 默认 `us-central1`

- **认证**: 使用 `google-auth-library` 的 `GoogleAuth` 自动获取访问令牌
- **端点计算**: `{location}-aiplatform.googleapis.com`（global 时使用 `aiplatform.googleapis.com`）
- **autoload**: 当 project 存在时为 `true`

### 5.10 google-vertex-anthropic

- 类似 google-vertex，但用于通过 Vertex AI 访问 Anthropic 模型
- **位置默认值**: `global`（而非 `us-central1`）
- 无自定义 fetch 函数（不需要 GoogleAuth token 注入）

### 5.11 cloudflare-workers-ai

- **认证要求**: `CLOUDFLARE_ACCOUNT_ID` + `CLOUDFLARE_API_KEY`
- **baseURL 短路**: 如果已配置 baseURL，跳过账户 ID 检查
- **User-Agent**: 包含 OpenCode 版本和系统信息
- **环境变量导出**: 将 `CLOUDFLARE_ACCOUNT_ID` 导出供环境变量替换使用

### 5.12 cloudflare-ai-gateway

- **认证要求**: `CLOUDFLARE_ACCOUNT_ID` + `CLOUDFLARE_GATEWAY_ID` + `CLOUDFLARE_API_TOKEN` (或 `CF_AIG_TOKEN`)
- **SDK**: 使用 `ai-gateway-provider` 的 `createAiGateway` + `createUnified` (Unified API)
- **模型格式**: 使用 `provider/model` 格式，如 `anthropic/claude-sonnet-4-5`
- **Gateway 选项**: metadata, cacheTtl, cacheKey, skipCache, collectLog
- **baseURL 短路**: 已配置时跳过

### 5.13 gitlab

- **认证**: OAuth (access token) 或 API key，回退到 `GITLAB_TOKEN` 环境变量
- **实例 URL**: `GITLAB_INSTANCE_URL` 环境变量或 `https://gitlab.com`
- **Duo Agent Platform**: 启用 `duo_agent_platform` 和 `duo_agent_platform_agentic_chat` feature flags
- **AI Gateway Headers**: User-Agent + `anthropic-beta: context-1m-2025-08-07`
- **模型发现**: 
  - `discoverModels()` 作为 discovery loader 在 Step 9 执行
  - 调用 `discoverWorkflowModels()` 获取项目中的工作流模型
  - 为发现的模型创建完整的 Model 结构，设置 `options.workflowRef`
  - 发现的模型 ID 前缀为 `duo-workflow-`
- **模型获取**: 
  - 工作流模型使用 `sdk.workflowChat()` 
  - 其他模型使用 `sdk.agenticChat()`

### 5.14 openrouter / nvidia / zenmux / kilo

- 设置 HTTP Referer 和 Title 头标识为 OpenCode
- `openrouter`: `HTTP-Referer: https://opencode.ai/`, `X-Title: opencode`
- `nvidia`: 同上
- `zenmux`: 同上
- `kilo`: 同上
- **autoload**: `false`

### 5.15 vercel

- 设置小写版本的 referer 和 title 头: `http-referer`, `x-title`

### 5.16 cerebras

- 设置 `X-Cerebras-3rd-Party-Integration: opencode` 标识头

### 5.17 sap-ai-core

- **认证**: `AICORE_SERVICE_KEY` (环境变量或 auth 存储)
- **其他配置**: `AICORE_DEPLOYMENT_ID`, `AICORE_RESOURCE_GROUP`

### 5.18 llmgateway

- 设置 referer 头并额外添加 `X-Source: opencode`

---

## 6. 模型解析与 SDK 加载 (resolveSDK)

当调用 `getLanguage(model)` 时，触发 SDK 实例的解析和加载。流程如下：

### 6.1 选项构建

```typescript
1. 从 provider.options 获取基础选项
2. 对 google-vertex 且非 openai-compatible 的模型，删除自定义 fetch
3. 对 openai-compatible SDK，默认设置 includeUsage=true
4. baseURL 解析:
   a. 先取 options.baseURL，再取 model.api.url
   b. 通过 varsLoader 替换 ${VAR_NAME} 占位符
   c. 通过环境变量替换剩余的 ${VAR_NAME} 占位符
5. 设置 apiKey（优先 options.apiKey，回退 provider.key）
6. 合并 model.headers 到 options.headers
```

### 6.2 Fetch 定制

为每个请求设置自定义 `fetch` 函数：

- **超时控制**: 通过 `AbortSignal.timeout(options.timeout)` 设置请求超时
- **SSE 块超时 (chunkTimeout)**: 如果配置了 `chunkTimeout`，包装 SSE 响应流，在超时时恢复读取
- **信号组合**: 合并原始 signal、chunkTimeout signal、timeout signal，使用 `AbortSignal.any()`
- **OpenAI itemId 清理**: 对于 `@ai-sdk/openai` 和 `@ai-sdk/azure`，在 POST 请求中移除 input 数组中各元素的 `id` 字段（除非 `store=true`）

### 6.3 SDK 实例化

1. **计算缓存键**: 对 `{providerID, npm, options}` 做 `Hash.fast()`，避免重复创建
2. **查找缓存**: 如果缓存命中，直接返回
3. **加载 SDK**:
   - **内置提供方**: 从 `BUNDLED_PROVIDERS` 动态 import，调用工厂函数
   - **npm 包**: 通过 `Npm.add()` 安装并获取入口点，动态 import
   - **本地文件**: 直接通过 `file://` 路径 import
4. **调用工厂函数**: `create*(options)` 获得 SDK 实例
5. **缓存 SDK 实例**

### 6.4 语言模型创建

SDK 实例创建后，从 SDK 获取具体的语言模型：

- 如果有 `modelLoader`（custom loader 注册的）: 调用 `modelLoader(sdk, model.api.id, options)`
- 否则: 调用 `sdk.languageModel(model.api.id)`

如果抛出 `NoSuchModelError`，转换为 OpenCode 的 `ModelNotFoundError`。

---

## 7. 成本计算 (cost)

### 7.1 成本数据结构

成本数据来自 `models.dev` 服务，通过 `cost()` 函数转换：

```typescript
models.dev 格式 -> OpenCode Model.cost 格式

input          -> cost.input
output         -> cost.output
cache_read     -> cost.cache.read
cache_write    -> cost.cache.write
context_over_200k.input          -> cost.experimentalOver200K.input
context_over_200k.output         -> cost.experimentalOver200K.output
context_over_200k.cache_read     -> cost.experimentalOver200K.cache.read
context_over_200k.cache_write    -> cost.experimentalOver200K.cache.write
```

所有成本均以美元($)每 token 为单位。未提供时默认为 0。

### 7.2 模型变体中的成本覆盖

模型的 `experimental.modes` 中的每个 mode（如 `thinking`、`reasoning_effort`）可以携带独立的 cost 配置，与基础 cost 通过 `mergeDeep` 合并。

---

## 8. 模型排序与选择

### 8.1 模型排序 (sort)

`sort()` 函数用于对模型列表排序，优先级规则如下：

1. **最高优先级** (desc): ID 包含以下关键词的模型优先：
   - `gpt-5` (GPT-5 系列)
   - `claude-sonnet-4` (Claude Sonnet 4 系列)
   - `big-pickle` (内部代号)
   - `gemini-3-pro` (Gemini 3 Pro 系列)
2. **次优先级** (asc): 不包含 `latest` 的模型优先（即非 `*-latest` 版本排在前面）
3. **最后** (desc): 按模型 ID 字典序降序（字母序靠后的优先）

### 8.2 默认模型选择 (defaultModel)

优先级从高到低：

1. **显式配置**: `config.model` 中的值，格式为 `providerID/modelID`
2. **最近使用**: 从 `state/model.json` 读取历史记录，取最新且当前可用的
3. **首个可用**: 遍历所有提供方的模型，取排序后的第一个
   - 优先选择 config.provider 中列出的提供方
   - 排除没有模型或过滤掉的提供方

### 8.3 小型模型选择 (getSmallModel)

用于标题生成等低成本任务。搜索优先级：

| Provider | 优先级顺序 |
|----------|-----------|
| github-copilot | `gpt-5-mini` > `claude-haiku-4.5` > 默认列表 |
| opencode | `gpt-5-nano` |
| 默认 | `claude-haiku-4-5` > `claude-haiku-4.5` > `3-5-haiku` > `3.5-haiku` > `gemini-3-flash` > `gemini-2.5-flash` > `gpt-5-nano` |

对于 amazon-bedrock，额外处理跨区域前缀：
- 优先 `global.` 前缀的匹配
- 其次当前区域前缀的匹配
- 最后不带前缀的匹配

也可以通过 `config.small_model` 显式指定。

### 8.4 模糊匹配 (closest)

`closest(providerID, query)` 按顺序遍历 query 中的每个关键词，然后在 provider 的所有模型中做子串匹配，返回第一个匹配结果。

---

## 9. 模型过滤规则

加载完成后，在最终输出前对模型进行多层过滤：

1. **disabled_providers**: 全局禁用列表，完全移除这些提供方
2. **enabled_providers**: 全局启用白名单，未列出的提供方被移除
3. **模型状态过滤**:
   - `alpha` 状态: 除非 `OPENCODE_ENABLE_EXPERIMENTAL_MODELS` flag 开启，否则移除
   - `deprecated` 状态: 直接移除
4. **特例移除**: `gpt-5-chat-latest` 和 OpenRouter 的 `openai/gpt-5-chat` 被硬编码移除
5. **per-provider 黑白名单**:
   - `blacklist`: 包含的模型 ID 被移除
   - `whitelist`: 只有列表中的模型被保留
6. **空提供方清理**: 如果提供方下没有模型，整个提供方被移除

---

## 10. 模型变体系统 (ProviderTransform)

### 10.1 变体生成

`ProviderTransform.variants(model)` 根据模型的能力自动生成变体：

- 推理模型支持 `reasoning_effort` 变体（如 `low`, `medium`, `high`）
- 变体通过 options 传递参数，如 `{ reasoning_effort: "high" }`
- 同时也会查找 providerOptions 的 SDK key 映射（通过 `sdkKey(npm)` 函数）

### 10.2 变体合并

变体来自两个来源，通过 `mergeDeep` 合并：

1. **自动生成的变体**: 从 `ProviderTransform.variants()` 生成
2. **用户配置的变体**: `config.provider[providerID].models[modelID].variants`

可通过设置 `disabled: true` 禁用某个变体。合并时会过滤掉被禁用的变体并移除 `disabled` 字段。

### 10.3 SDK Key 映射

变体选项中需要使用正确的 SDK provider key：

| npm 包 | SDK Key |
|--------|---------|
| `@ai-sdk/github-copilot` | `copilot` |
| `@ai-sdk/azure` | `azure` |
| `@ai-sdk/openai` | `openai` |
| `@ai-sdk/amazon-bedrock` | `bedrock` |
| `@ai-sdk/anthropic` / `@ai-sdk/google-vertex/anthropic` | `anthropic` |
| `@ai-sdk/google-vertex` | `vertex` |
| `@ai-sdk/google` | `google` |
| `@ai-sdk/gateway` | `gateway` |
| `@openrouter/ai-sdk-provider` | `openrouter` |
| `ai-gateway-provider` | `openaiCompatible` |

---

## 11. 数据来源

### 11.1 models.dev 数据库

`models.dev` 服务提供所有模型的元数据（名称、能力、成本、限制等），通过 `fromModelsDevProvider()` 转换为 OpenCode 的 Provider 结构。用户可通过 `opencode.json` 的 `provider` 字段覆盖或扩展这些数据。

### 11.2 模型解析流程

```
models.dev Model          fromModelsDevModel()        OpenCode Model
─────────────────         ────────────────────        ──────────────
model.id                  -> ModelID.make(id)         id
model.name                -> name                     name
model.family              -> family                   family
model.provider.api/npm    -> api.url / api.npm        api
model.status              -> status                   status
model.temperature         -> capabilities.temperature capabilities
model.reasoning           -> capabilities.reasoning
model.attachment          -> capabilities.attachment
model.tool_call           -> capabilities.toolcall
model.modalities.input    -> capabilities.input       (text/audio/image/video/pdf)
model.modalities.output   -> capabilities.output
model.interleaved         -> capabilities.interleaved
model.cost                -> cost() 转换              cost
model.limit               -> limit                    limit
model.release_date        -> release_date             release_date
```

---

## 12. 错误处理

| 错误类型 | 触发条件 | 附加信息 |
|----------|---------|---------|
| `ModelNotFoundError` | `getModel()` 找不到模型或提供方 | `suggestions: string[]` (模糊匹配建议) |
| `InitError` | `resolveSDK()` 中 SDK 初始化失败 | `providerID`, `cause` (原始错误) |

模糊搜索使用 `fuzzysort` 库，配置 `limit: 3, threshold: -10000` 以获取最多 3 个建议。
