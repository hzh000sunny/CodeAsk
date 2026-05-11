# opencode 多模型协议与 Reasoning 处理学习记录

> 状态：源码学习、版本内设计收口和第一版真实 LLM 验证已完成；后续只保留为架构参考。
> 版本归属：v1.0.3
> 目的：基于 `references/opencode` 的源码学习，校准 CodeAsk v1.0.3 中 LLM reasoning 请求构造、多协议适配、reasoning 隔离和长上下文治理的开发方向。

## 1. 学习范围

本次学习不是只看 README，而是围绕 CodeAsk 当前问题做了源码级对照。重点阅读范围如下：

| 范围 | 文件 | 关注点 |
|---|---|---|
| LLM 抽象入口 | `references/opencode/packages/llm/src/llm.ts` | 公共 `LLMRequest`、`ModelRef`、`generation`、`providerOptions`、`http` patch |
| Route 分层 | `references/opencode/packages/llm/src/route/client.ts`、`route/protocol.ts` | Protocol / Endpoint / Auth / Framing 四层拆分 |
| 消息模型 | `references/opencode/packages/llm/src/schema/messages.ts` | `reasoning` 是一等 content part，不是正文标签 |
| 事件模型 | `references/opencode/packages/llm/src/schema/events.ts` | `reasoning-start/delta/end`、usage 中的 `reasoningTokens` 和 `visibleOutputTokens` |
| 请求选项 | `references/opencode/packages/llm/src/schema/options.ts` | provider-neutral generation、namespaced providerOptions、generic http patch |
| OpenAI Chat | `references/opencode/packages/llm/src/protocols/openai-chat.ts` | OpenAI-compatible `reasoning_content` 的历史回放 |
| OpenAI Responses | `references/opencode/packages/llm/src/protocols/openai-responses.ts` | `reasoning.effort/summary`、encrypted reasoning include、usage 映射 |
| OpenAI-compatible | `references/opencode/packages/llm/src/protocols/openai-compatible-chat.ts`、`providers/openai-compatible*.ts` | 同一协议复用，不为每个兼容网关复制协议实现 |
| Anthropic | `references/opencode/packages/llm/src/protocols/anthropic-messages.ts` | `thinking_delta`、signature、thinking block 回放 |
| Gemini | `references/opencode/packages/llm/src/protocols/gemini.ts` | `thought` part、`thinkingConfig`、`thoughtsTokenCount` |
| Bedrock | `references/opencode/packages/llm/src/protocols/bedrock-converse.ts` | `reasoningContent.reasoningText`、signature、Converse event stream |
| Provider transform | `references/opencode/packages/opencode/src/provider/transform.ts` | 模型能力、providerOptions namespace、缓存点、interleaved reasoning |
| Provider catalog | `references/opencode/packages/opencode/src/provider/models.ts`、`provider.ts` | `models.dev` 能力目录、模型能力覆盖、variants |
| Session LLM | `references/opencode/packages/opencode/src/session/llm.ts` | AI SDK `streamText`、message transform、providerOptions 注入 |
| Session message | `references/opencode/packages/opencode/src/session/message-v2.ts` | `ReasoningPart` 持久化和回放到 model messages |
| Session projection | `references/opencode/packages/opencode/src/session/projectors-next.ts` | stream event 到消息状态的投影 |
| Compaction | `references/opencode/packages/opencode/src/session/overflow.ts`、`compaction.ts` | overflow 阈值、工具输出剪枝、anchored summary、recent tail 保留 |
| Copilot Responses SDK | `references/opencode/packages/opencode/src/provider/sdk/copilot/responses/*.ts` | OpenAI Responses encrypted reasoning、reasoning item reference、stream parser |

## 2. 总体判断

opencode 的核心经验不是“靠模型名/厂商名写一堆 if 分支”，也不是“所有 provider 完全无差别通用”。它的主设计是：

```text
内部统一模型：
  LLMRequest / Message / ContentPart / LLMEvent / Usage

协议适配层：
  Protocol 负责请求体构造和 stream parser
  Endpoint 负责 URL
  Auth 负责鉴权
  Framing 负责 SSE / event stream / transport frame

Provider 层：
  声明模型能力、上下文窗口、输出限制、是否 reasoning、是否 interleaved
  把配置和 catalog 合并成 Model
  把通用 options 映射到 SDK 所需 providerOptions namespace
```

这对 CodeAsk 的启发是：我们不能再让业务 runtime、LLM client、请求 profile、UI leak guard 混在一起处理 reasoning。必须把“模型能力声明”“请求序列化”“响应解析”“历史回放”“UI 展示”拆开。

## 3. 可借鉴的架构点

### 3.0 用户可见协议选择必须表达消息格式，不表达厂商

CodeAsk 的 LLM 配置界面保留协议选择，但用户可见选项只保留：

- `OpenAI`
- `Anthropic`

这里的 `OpenAI` 和 `Anthropic` 不是厂商限定，而是消息协议格式：

```text
OpenAI:
  使用 OpenAI Chat Completions / OpenAI-compatible 消息格式。
  可用于 OpenAI 官方服务，也可用于任何明确提供 OpenAI-compatible API 的第三方厂商或私有网关。

Anthropic:
  使用 Anthropic Messages 消息格式。
  可用于 Anthropic 官方服务，也可用于任何明确提供 Anthropic-compatible API 的第三方厂商或私有网关。
```

本版本明确不做以下行为：

- 不根据 URL 域名推断厂商；
- 不根据 URL 路径探测协议；
- 不根据模型名判断应走 OpenAI 还是 Anthropic；
- 不在配置保存时自动尝试多协议请求。

用户选择哪个协议，后端就按哪个消息协议构造请求。这样既保留了必要的协议边界，也避免把 `OpenAI Compatible` 这种实现细节暴露给普通用户。历史数据中的 `openai_compatible` 仅作为兼容内部值保留，前端展示和编辑时视为 `OpenAI`。

同一个私有模型网关 base URL 可以同时支持 OpenAI Chat Completions 和 Anthropic Messages 两种协议。CodeAsk 的 UI 不要求用户为 Anthropic 额外理解 endpoint 细节；后端在 Anthropic adapter 中负责把 base URL 规范化为 `/v1/messages` 完整请求 URL，已填写完整 `/v1/messages` endpoint 时保持不变。

### 3.1 Protocol / Endpoint / Auth / Framing 分离

`packages/llm/src/route/protocol.ts` 明确说明：Protocol 只表达一个 API 的语义契约，负责：

- common `LLMRequest` 如何变成 provider-native body；
- body schema 如何校验；
- provider stream event 如何归一化成 common `LLMEvent`。

Endpoint、Auth、Framing 不属于 Protocol。

CodeAsk 当前虽然有 `protocol = openai | openai_compatible | anthropic`，但 `src/codeask/llm/client.py` 仍把 LiteLLM 请求构造、stream 解析、工具 delta、reasoning 解析、debug log 放在一个 client 里。v1.0.3 的合理方向是逐步拆成：

```text
src/codeask/llm/
├── messages.py              # 内部消息 part 和历史回放
├── events.py                # 内部 LLM events
├── protocols/
│   ├── openai_chat.py        # OpenAI / OpenAI-compatible chat completions
│   └── anthropic_messages.py # Anthropic messages
├── request_options.py        # 通用 request patch / capability serializer
└── client.py                 # 只负责调用 LiteLLM / transport
```

本版本不一定一次性做完全部目录重构，但不能继续往 `request_profiles.py` 里堆厂商 profile。

### 3.2 Reasoning 是一等消息 part

opencode 的 `ContentPart` 里有独立 `reasoning` part；`LLMEvent` 里有 `reasoning-start`、`reasoning-delta`、`reasoning-end`；session 层有 `ReasoningPart` 持久化结构。

这说明成熟实现不会把思考链作为普通 `content` 字符串再靠 `<think>` 删除。合理链路是：

```text
provider structured reasoning field
  -> protocol adapter emits reasoning event
  -> session stores reasoning part or diagnostic metadata
  -> UI 默认不混入 answer
  -> 下一轮请求按协议决定是否回放
```

CodeAsk 当前 `LLMEvent` 已经有 `reasoning_delta`，但 `LLMMessage.ContentBlock` 还没有 `ReasoningBlock`。这会导致一个关键缺口：即使本轮解析出了 reasoning，也缺少结构化方式决定“哪些 reasoning 可以或必须回放给下一轮模型”。DeepSeek / OpenAI-compatible thinking 模型报错 `reasoning_content in thinking mode must be passed back`，本质就是历史回放层不完整。

### 3.3 ProviderOptions 要 namespace 化，通用 patch 作为逃生口

opencode 把 provider-specific 参数放在 `providerOptions.<provider>` 下，例如：

- `providerOptions.openai.reasoningEffort`
- `providerOptions.openai.reasoningSummary`
- `providerOptions.anthropic.thinking`
- `providerOptions.gemini.thinkingConfig`
- `providerOptions.bedrock.reasoningConfig`

同时它保留通用 `http.body / headers / query` 作为 raw overlay。`ModelRef.native` 只用于真正 provider-private 的信息，并且注释明确：如果某能力被多个 route 使用，就应该提升为 typed field。

CodeAsk 的对应设计应是：

```text
protocol_family = openai | openai_compatible | anthropic
reasoning_capability:
  enabled: bool
  request_shape: openai_reasoning_effort | openai_extra_body | anthropic_thinking | custom_patch
  history_policy: none | interleaved_field | signed_block
request_patch:
  body / extra_body / headers / query
```

这里的 `request_patch` 是通用补丁，不是 `volcengine_thinking`、`vllm_enable_thinking` 这种厂商 profile。

### 3.4 OpenAI-compatible 可以复用协议，但仍需能力声明

opencode 的 `openai-compatible-chat.ts` 直接复用 `OpenAIChat.protocol`，只改变 route id 和 endpoint。这是正确方向：DeepSeek、Cerebras、TogetherAI 等不应各自复制完整 chat completions 协议。

但 opencode 也不是完全不做差异处理。它通过 catalog / config 声明：

- 模型是否支持 reasoning；
- 是否需要 interleaved reasoning；
- interleaved 字段名是 `reasoning_content` 还是 `reasoning_details`；
- 上下文窗口和 output limit；
- providerOptions 应挂在哪个 SDK namespace。

对 CodeAsk 来说，这意味着：

```text
OpenAI-compatible 是协议族，不是“所有网关请求参数都一样”。
差异应由用户配置/能力声明/通用 patch 表达，而不是 CodeAsk 根据厂商名猜。
```

### 3.5 Interleaved reasoning 是解决历史回放的关键

opencode 在 `provider/transform.ts` 中有一段非常关键的逻辑：

- 如果模型能力声明 `interleaved.field = reasoning_content | reasoning_details`；
- assistant 历史消息里有 `reasoning` part；
- 转换请求时会把 reasoning parts 合并；
- 从 content 中移除 reasoning part；
- 写到 assistant message 的 `providerOptions.openaiCompatible[field]`。

它还特别注释：即使 reasoning 内容为空，也要设置该字段，因为某些 provider 会返回空 `reasoning_content`，后续请求仍然需要回传。

CodeAsk 需要吸收这个思想，但不要用模型名特判。建议：

```text
llm_configs 增加能力声明：
  reasoning_history_policy = none | openai_interleaved
  reasoning_history_field = reasoning_content | reasoning_details

当且仅当用户或迁移明确声明该能力时：
  assistant reasoning part -> 对应历史消息字段
```

这样可以解决“必须回传 reasoning_content”的协议问题，同时不违背用户反复强调的“不能根据厂商/模型名硬判断”。

### 3.6 Anthropic / Bedrock / Gemini 都是协议内结构化 reasoning

opencode 对不同协议的处理方式很清晰：

| 协议 | 请求/历史回放 | Stream 解析 |
|---|---|---|
| Anthropic Messages | assistant reasoning part -> `thinking` block，signature 写入 metadata | `thinking_delta` -> reasoning delta，`signature_delta` -> reasoning end metadata |
| Gemini | assistant reasoning part -> `{text, thought: true}`，请求用 `thinkingConfig` | `part.thought` -> reasoning delta，usage `thoughtsTokenCount` |
| Bedrock Converse | assistant reasoning part -> `reasoningContent.reasoningText`，signature 写入 block | `reasoningContent.text` -> reasoning delta |
| OpenAI Responses | reasoning item / item_reference / encrypted_content | reasoning summary events -> reasoning delta/end |
| OpenAI Chat compatible | `reasoning_content` 等 interleaved field | `delta.reasoning_content` / `delta.reasoning` -> reasoning delta |

这说明 CodeAsk 的协议适配应以“字段结构”而不是“标签字符串”为准。

### 3.7 上下文压缩不是每轮压缩

opencode 的 `overflow.ts` 与 `compaction.ts` 提供了值得参考的策略：

- 先计算可用上下文窗口：context 或 input limit 扣掉输出保留区；
- 达到 overflow 才触发自动压缩；
- 压缩前可以先剪旧工具输出；
- 默认保留最近若干轮，并按 token 预算保留最近上下文；
- 生成 anchored summary，结构固定包含 Goal、Constraints、Progress、Key Decisions、Next Steps、Critical Context、Relevant Files；
- 压缩失败时可重放最近一条用户消息，或者停止。

CodeAsk 当前 `src/codeask/agent/chat_runtime/compaction.py` 已经有自动压缩方向，但应继续补齐两层能力：

- 工具输出剪枝：旧工具原文可清理，只保留摘要/证据引用；
- reasoning 历史策略：原始 reasoning 默认不优先进入长期摘要，除非协议要求用于下一轮回放。

## 4. 不能照搬的部分

### 4.1 opencode 也存在模型/厂商经验分支

需要客观看待：opencode 并不是完全无模型名判断。`provider/transform.ts` 中存在不少经验规则，例如：

- GPT-5 family 的 reasoning effort variants；
- Gemini thinking level / thinking budget；
- DeepSeek assistant message 必须带 reasoning；
- DashScope `enable_thinking`；
- LiteLLM proxy 需要 `_noop` tool 兼容；
- Kimi、Qwen、GLM、MiniMax、Mistral 等 temperature/topP 默认值。

这些分支是 mature tool 在大规模兼容中的现实工程取舍，但不能原样搬到 CodeAsk。原因：

- CodeAsk 当前没有 opencode 那样的 `models.dev` catalog 和 provider SDK 生态；
- 用户明确不接受后端根据厂商/模型名强行猜测；
- CodeAsk 的私有部署场景里，同一个模型名可能经过不同网关，参数含义不稳定；
- 错误的自动猜测会比保守失败更危险。

因此，CodeAsk 应吸收“集中在 adapter / capability 层处理”的架构，不吸收“在业务层散落模型名规则”的做法。

### 4.2 不照搬 AI SDK，但可照搬分层

opencode 基于 Vercel AI SDK 和 TypeScript provider ecosystem。CodeAsk 后端当前基于 Python + LiteLLM。不能直接照搬类和 SDK 调用，但可以照搬这些边界：

- 内部消息结构必须强于 provider 原始 JSON；
- provider request options 必须 namespace 化；
- stream parser 必须归一化事件；
- reasoning 和 visible answer 必须从协议层分离；
- provider metadata 必须保留给历史回放和 debug；
- 所有兼容性 patch 必须有配置来源、测试和审计。

## 5. 对 CodeAsk 当前实现的差距判断

当前 CodeAsk 的相关文件：

| 文件 | 现状 | 差距 |
|---|---|---|
| `src/codeask/llm/types.py` | 有 `LLMEvent.reasoning_delta`，但没有 `ReasoningBlock` | 无法结构化回放 reasoning history |
| `src/codeask/llm/reasoning.py` | 能识别 OpenAI-compatible `reasoning/reasoning_content/thinking` 和 Anthropic events | 还缺 provider metadata、start/end id、signature/encrypted state |
| `src/codeask/llm/request_profiles.py` | `volcengine_thinking`、`vllm_enable_thinking`、`anthropic_budget_thinking`、`custom_json` | 命名仍是 vendor/gateway profile，不符合 v1.0.3 要求 |
| `src/codeask/llm/client.py` | LiteLLM 调用、OpenAI stream parser、tool delta、reasoning debug 放在一个 client | 协议序列化和 stream 解析耦合过重 |
| `src/codeask/llm/gateway.py` | 已有全局配置选择、失败冷却、会话粘性 | 与 provider capability / protocol serializer 还未解耦 |

## 6. v1.0.3 开发方向

### 6.1 请求侧先从 profile 迁移到 capability + patch

本版本要优先处理用户正在遇到的 reasoning 请求和历史回放问题。建议落地最小可维护版本：

```text
LLM 配置新增：
  protocol: openai | openai_compatible | anthropic
  reasoning_enabled: bool
  reasoning_request:
    mode: none | openai_effort | anthropic_thinking | extra_body_patch | body_patch
    effort?: low | medium | high | ...
    budget_tokens?: int
    patch_json?: object
  reasoning_history:
    mode: none | openai_interleaved
    field?: reasoning_content | reasoning_details
```

迁移策略：

- 旧 `none` -> `reasoning_enabled=false`。
- 旧 `anthropic_budget_thinking` -> `protocol=anthropic` + `reasoning_request.mode=anthropic_thinking`。
- 旧 `custom_json` -> `reasoning_request.mode=body_patch/extra_body_patch`，保留原 JSON。
- 旧 `volcengine_thinking`、`vllm_enable_thinking` 不作为长期名称继续暴露；迁移成显式 patch，并在 UI 中显示为“自定义请求补丁”。

### 6.2 历史回放要补 reasoning part

需要在内部消息中增加 `ReasoningBlock` 或等价结构：

```text
ReasoningBlock:
  type = reasoning
  text
  provider
  field
  redacted
  encrypted_content / signature / provider_metadata
```

普通聊天气泡不显示它；报告生成、标题生成默认不读取它；但下一轮请求构造器可以按配置决定是否回放。

### 6.3 Adapter 只消费结构化字段

继续坚持：

- `delta.reasoning` -> reasoning event
- `delta.reasoning_content` -> reasoning event
- `delta.thinking` 只有作为结构化字段时 -> reasoning event
- `delta.content` -> visible text
- 不把后端扫描 `<think>`、`</think>`、`<thinking>` 当成主要协议解析能力；v1.0.3 只允许保留极窄的 `<think>` 最后防线，用于阻止不合规模型服务把 raw thinking 写入可见回答、数据库和后续上下文。

前端 leak guard 只能是显示保护，不是协议解析。

### 6.4 行动轨迹只展示公开分析，不展示 raw reasoning

用户希望在 Agent 行动轨迹看到“分析思路”。结合 opencode 和 Claude Code 的经验，CodeAsk 应展示：

- 本轮模型配置、上下文规模、工具数量；
- 是否观察到结构化 reasoning 字段、字段长度和 chunk 数；
- 模型调用了哪些工具；
- 工具返回了哪些证据；
- 哪些结果被截断；
- 当前是否发生上下文压缩。

不应展示 raw `reasoning_delta`。如果未来做管理员调试视图，也要单独权限、单独保留策略。

### 6.5 上下文压缩应升级为两段式

opencode 的压缩策略可以作为 CodeAsk 后续改造目标：

1. 触发条件：超过可用上下文阈值，而不是每轮压缩。
2. 压缩前剪枝：旧工具输出先压缩或清空原文。
3. 摘要结构：保持目标、约束、已完成、进行中、决策、下一步、关键上下文、相关文件。
4. 保留尾部：保留最近几轮完整对话。
5. reasoning 策略：默认不进入 summary；协议要求回放的 reasoning metadata 单独处理。

## 7. v1.0.3 验收补充

本次学习后，v1.0.3 的 reasoning 请求侧收口不能只验证“看起来没有 `<think>`”。当前已经补充以下验收要求，并在 `../plans/acceptance-checklist.md` 记录执行结果：

- OpenAI-compatible `delta.reasoning_content` 与 `delta.content` 同 chunk 时，两者都被正确处理。
- OpenAI-compatible 历史 assistant reasoning 可以按配置回放到 `reasoning_content` 或 `reasoning_details`。
- 未配置 reasoning history policy 时，不根据模型名自动回放。
- Anthropic thinking 请求只在 `protocol=anthropic` 且配置启用时发送。
- 自定义 patch 能覆盖 body / extra_body，但 patch 来源可审计。
- 切换模型配置后，不盲目回放旧 provider 的不可复用 reasoning metadata。
- 报告生成、标题生成、普通回答上下文不读取 raw reasoning。
- Agent 行动轨迹只显示 reasoning 观察摘要，不显示 raw reasoning。
- Live E2E 至少覆盖 OpenAI-compatible 与 Anthropic 两类配置；如果真实模型不可用，保留 fake/spy LLM 断言实际请求 payload。

## 8. 结论

opencode 给 CodeAsk 的核心启发是：**兼容性可以存在，但必须被关进协议/adapter/capability 边界里**。

CodeAsk v1.0.3 已停止继续扩张 vendor-style reasoning profile，第一版请求侧和历史回放侧已经按以下方向收口：

```text
协议族 + 能力声明 + 通用 request patch + 结构化 reasoning part + 协议化历史回放
```

这既能解决用户当前遇到的 `reasoning_content` 回放错误，也能避免后续每接一个模型就新增一段厂商硬编码。

## 9. CodeAsk 第一版落地记录

2026-05-11 已完成第一版后端切片：

- 新增 `src/codeask/llm/request_options.py`，作为 provider-neutral request option 构造入口。
- `src/codeask/llm/request_profiles.py` 降级为兼容 wrapper；旧 `volcengine_thinking`、`vllm_enable_thinking`、`custom_json` 不再是新架构主接口，只是迁移 alias。
- 新增 `ReasoningBlock`，让内部 LLM message 可以表达结构化 reasoning。
- LiteLLM client 默认不把 `ReasoningBlock` 写入普通 `content`。
- 只有当请求 metadata 显式声明：

```json
{
  "reasoning_history": {
    "mode": "openai_interleaved",
    "field": "reasoning_content"
  }
}
```

或：

```json
{
  "reasoning_history": {
    "mode": "openai_interleaved",
    "field": "reasoning_details"
  }
}
```

时，OpenAI-compatible assistant 历史才会回放对应 interleaved reasoning 字段。

本轮有意没有做的事情：

- 没有根据模型名、厂商名或 base URL 自动判断 reasoning 参数。
- 没有把 `<think>` 标签扫描作为主 reasoning 方案；后续补充的最后防线只做泄漏隔离，并转换成内部 `reasoning_delta(content_think_tag)` 诊断。
- 没有把 raw reasoning 放入报告、标题生成或普通 answer text。
- 没有把 provider adapter、capability 和 request patch 暴露给普通用户。前端 LLM 配置页只保留 `OpenAI` / `Anthropic` 两个消息格式选项，历史 `openai_compatible` 仅作为内部兼容值保留并在 UI 中显示为 `OpenAI`。

2026-05-11 追加验证：

- LLM 配置 UI 协议选项已收口为 `OpenAI` / `Anthropic`，不再展示 `OpenAI Compatible`。
- 使用真实数据目录 `/home/hzh/.codeask` 逐个验证全部 7 个启用 LLM 配置，覆盖 OpenAI 消息格式、Anthropic 消息格式、全局配置和用户配置；结果 `passed=7 failed=0 marker_leaks=0 empty_answers=0`。
