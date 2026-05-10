# 结构化思考链处理与上下文隔离

> 状态：Draft
> 版本归属：设计前史；结构化 reasoning 隔离已进入 `docs/v1.0.2/plans/structured-reasoning.md`
> 主题：从 Claude Code、AnythingLLM、vLLM reasoning outputs 和真实模型 stream shape 中提炼 CodeAsk 后续演进方向，建立同时适配 OpenAI-compatible 与 Anthropic 协议的结构化 reasoning 方案。

## 1. 背景

CodeAsk 当前为了兼容部分 OpenAI-compatible 私有模型，曾临时在流式文本里过滤 `<think>...</think>` 片段，避免模型把思考链直接展示给用户。

这个方案不能作为正式架构，原因是：

- 它假设模型一定用 `<think>` 标签包裹 reasoning。
- 它只能处理混入 `content` 的文本，不能表达结构化 reasoning。
- 它无法区分“模型内部 reasoning”“可展示的 Agent 行动轨迹”“需要审计的调试信息”。
- 它容易受不规范输出、标签缺失、嵌套标签、Markdown 示例代码、模型供应商字段差异影响。
- 它没有解决 reasoning 是否进入会话历史、报告生成、标题生成、上下文压缩的问题。

因此，CodeAsk 后端不应继续把 `<think>` 标签强匹配作为 reasoning 处理能力。正式方案必须基于协议层结构化字段：

```text
OpenAI-compatible: delta.reasoning / delta.reasoning_content / delta.thinking
Anthropic: thinking_delta / redacted_thinking / text_delta
```

如果某个模型服务把 raw thinking 放进 `content` / `text` 正文里，CodeAsk 不在后端解析私有标签，应把它视为模型服务接入不合规。修复点应在模型网关或 vLLM reasoning parser 层。前端可以保留受控 UI Leak Guard 防止用户界面直接泄漏，但它只是显示保护，不是协议解析成功。

## 2. Claude Code 源码中的处理方式

Claude Code 对思考链的处理不是字符串过滤，而是围绕 Anthropic API 的结构化 content block 建立完整链路。

参考源码：

| 位置 | 作用 |
|---|---|
| `references/claude-code/claude-code/src/services/api/claude.ts` | API 请求、thinking 配置、流式 block 解析 |
| `references/claude-code/claude-code/src/utils/messages.ts` | 流式 UI 状态、消息过滤、尾部 thinking 清理、签名 block 清理 |
| `references/claude-code/claude-code/src/components/messages/AssistantThinkingMessage.tsx` | thinking UI 渲染 |
| `references/claude-code/claude-code/src/components/Message.tsx` | 普通消息中 thinking / redacted thinking 的展示规则 |
| `references/claude-code/claude-code/src/services/compact/apiMicrocompact.ts` | API context management 中的 thinking 清理策略 |
| `references/claude-code/claude-code/src/services/compact/microCompact.ts` | 本地 token 估算时对 thinking 的计数 |
| `references/claude-code/claude-code/src/services/tokenEstimation.ts` | token 计算和 thinking block 检测 |

### 2.1 Thinking 是结构化 block，不是正文字符串

Claude Code 在流式解析时按 block 类型区分内容：

- `text` / `text_delta`：用户可见的正常回答。
- `thinking` / `thinking_delta`：模型思考内容。
- `redacted_thinking`：服务端脱敏后的思考内容。
- `signature_delta`：thinking 签名，不是模型输出正文。
- `tool_use` / `input_json_delta`：工具调用输入。

在 `services/api/claude.ts` 中，`content_block_start` 遇到 `thinking` 会初始化独立的 thinking block，后续 `thinking_delta` 只追加到 `contentBlock.thinking`。`text_delta` 只追加到 `contentBlock.text`。两者从进入系统开始就是分开的。

这说明 Claude Code 的主路径不是“从最终回答里删除思考链”，而是“从协议层就不把思考链当作普通回答文本”。

### 2.2 UI 默认不展示完整思考链

Claude Code 的普通 UI 默认不会展示完整 thinking。

在 `AssistantThinkingMessage.tsx` 中，只有以下场景会展示完整 thinking：

- transcript 模式。
- verbose 模式。

普通模式下只展示轻量折叠提示，例如 `∴ Thinking`。在 `Message.tsx` 中，`thinking` 和 `redacted_thinking` 也会根据 transcript / verbose 判断是否渲染。

这意味着 Claude Code 没有把 reasoning 当作普通用户答案展示，而是把它作为调试或 transcript 信息处理。

### 2.3 Streaming UI 中 thinking 不进入可见回答

在 `utils/messages.ts` 的流式事件处理中：

- `content_block_start` 为 `thinking` 或 `redacted_thinking` 时，会把 stream mode 设置为 `thinking`。
- `content_block_start` 为 `text` 时，会把 stream mode 设置为 `responding`。
- `text_delta` 会追加到可见 streaming text。
- `thinking_delta` 只更新长度统计，不追加到可见回答。
- `signature_delta` 被排除在输出长度和可见内容之外。

这说明 Claude Code 的 UI 层明确区分“正在思考”和“正在回答”。思考状态可以被展示为状态，但思考内容默认不直接进入聊天气泡。

### 2.4 Thinking 会参与上下文和 token 管理

Claude Code 并不是简单丢弃 thinking。

在 `microCompact.ts` 和 `tokenEstimation.ts` 中，thinking block 会参与 token 估算：

- `thinking` 计入 `block.thinking` 的 token。
- `redacted_thinking` 计入 `block.data` 的 token。
- `signature_delta` 作为签名元数据，不按普通模型输出计入可见输出长度。

这说明 reasoning 可能仍是模型上下文的一部分，必须纳入上下文预算，而不能只在 UI 层隐藏。

### 2.5 Claude Code 会按 API 约束清理 thinking

Claude Code 有多处清理 thinking 的规则，这些规则不是为了美化 UI，而是为了满足 API 协议和上下文有效性。

关键规则：

1. **尾部 thinking 清理**

   `utils/messages.ts` 中的 `filterTrailingThinkingFromLastAssistant` 会移除最后一条 assistant message 尾部的 thinking / redacted thinking block。

   原因是 API 不允许 assistant message 以 thinking block 结束。

2. **孤立 thinking 消息过滤**

   流式过程中可能出现 thinking-only 的分片消息。Claude Code 会过滤不应回放的孤立 thinking，避免下一轮请求携带非法消息结构。

3. **签名 block 清理**

   `stripSignatureBlocks` 会清理 `thinking`、`redacted_thinking`、`connector_text` 等带签名 block。

   原因是 thinking signature 和生成它的 API key / 模型绑定。登录、换 key 或模型切换后，旧签名可能失效，继续回放会导致 API 拒绝。

4. **上下文管理清理**

   `apiMicrocompact.ts` 中定义了 `clear_thinking_20251015` 策略：

   - 如果上下文有 thinking 且不是 redacted-thinking 模式，可以启用 thinking 清理。
   - 如果需要清理全部旧 thinking，可以只保留最近 1 个 thinking turn。
   - 如果不需要清理，则可以保留全部 thinking。

这说明 Claude Code 对 reasoning 的处理是“结构化保留 + 规则化清理”，不是简单隐藏或简单删除。

### 2.6 Thinking 配置会影响 API 参数

Claude Code 会根据模型能力和配置决定 thinking 参数：

- 支持 adaptive thinking 的模型，使用 adaptive thinking。
- 不支持 adaptive thinking 的模型，使用 budgeted thinking。
- thinking budget 会受到 `max_tokens` 约束，确保 `max_tokens > thinking.budget_tokens`。
- thinking 启用时，temperature 等参数也受到 API 约束。
- API key 校验、某些非 agent 查询或 fallback 请求会显式禁用 thinking。

这意味着 reasoning 能力不是单纯的展示开关，而是请求协议、模型能力、输出预算、上下文管理共同作用的结果。

## 3. 对 CodeAsk 当前方案的判断

CodeAsk 当前 `<think>` 过滤属于临时调试方案，不应进入正式架构。

这类输入看似可以通过字符串过滤处理：

```text
模型或网关没有返回结构化 reasoning 字段，
而是把思考链以 <think>...</think> 混入 delta.content。
```

但 CodeAsk 后端不应承担这种解析责任：

| 问题 | 风险 |
|---|---|
| 强依赖标签 | 模型可能输出 `<thinking>`、`<reasoning>`、中文标签，或不闭合标签 |
| 误伤正文 | 用户让模型解释 `<think>` 标签、生成示例代码或分析日志时，可能被错误过滤 |
| 无法表达结构化事件 | 前端不知道哪些是 reasoning，哪些是 answer，哪些是 trace |
| 难以审计 | 过滤后 reasoning 丢失，无法在开发模式分析模型为什么做错 |
| 可能污染上下文 | 如果只过滤 UI，不过滤持久化和下一轮上下文，仍可能进入后续请求 |
| 职责越界 | 模型服务没有输出结构化协议，业务后端被迫猜测模型私有文本格式 |

因此，正式设计应明确：

```text
CodeAsk 后端不解析 content/text 中的私有 reasoning 标签。
CodeAsk 只消费模型服务明确返回的结构化 reasoning 字段。
```

如果某个私有环境出现 `<think>` 泄漏，推荐修复方式是：

- vLLM 服务端配置对应 `--reasoning-parser`，让输出变成 `reasoning` + `content`。
- 模型网关在服务层把 raw model output 转换成结构化字段。
- 关闭该模型服务的 raw reasoning 输出。
- 如果无法提供结构化字段，则该模型在 CodeAsk 中按普通 content 模型接入，不启用 reasoning 能力。
- 如果普通 content 中仍泄漏 raw thinking，UI Leak Guard 可以在显示层遮蔽并提示上游不合规，但不得修改数据库或后续上下文。

### 3.2 四层保护模型

1. **协议适配层**：消费 OpenAI-compatible / Anthropic 的结构化 reasoning 字段。
2. **Request Profile 层**：用模型配置声明是否启用 `volcengine_thinking`、`vllm_enable_thinking`、`anthropic_budget_thinking` 或自定义请求体。
3. **模型服务 / 网关 Parser 层**：私有模型 raw thinking 必须在 vLLM、模型服务或网关中解析成结构化字段。
4. **UI Leak Guard 层**：只作为最后一道显示层保护，可配置 `disabled | warn_only | mask_in_ui`，触发时记录 `reasoning_leak_detected` 诊断，不回写数据库，不进入上下文。

## 4. CodeAsk 后续目标

CodeAsk 后续应建立 provider-neutral 的结构化 reasoning 通道。

目标不是把思考链完整展示给用户，而是把以下概念分离：

| 类型 | 是否用户默认可见 | 是否可入上下文 | 是否持久化 | 说明 |
|---|---:|---:|---:|---|
| `answer_text` | 是 | 是 | 是 | 最终回答内容 |
| `agent_trace` | 是 | 可摘要进入 | 是 | 工具调用、证据、行动轨迹 |
| `reasoning` | 否 | 按模型协议决定 | 可选 | 原始模型思考，不作为普通回答 |
| `redacted_reasoning` | 默认否 | 按模型协议决定 | 可选 | 已脱敏或供应商处理过的 reasoning |
| `tool_call` | 是 | 是 | 是 | 模型调用工具 |
| `tool_result_summary` | 是 | 是 | 是 | 工具结果摘要 |
| `tool_result_raw` | 否 | 否 | 是 | 完整工具结果，供审计和展开 |

用户需要看到的是：

- AI 的回答。
- Agent 做了哪些工具动作。
- 使用了哪些证据。
- 哪些结果被截断。
- 哪些地方需要用户确认。

用户不应该默认看到模型原始思考链。

## 4.1 AnythingLLM 的补充参考

AnythingLLM 在多模型 provider 接入上有成熟工程实践，但它对 reasoning 的展示策略不适合 CodeAsk 直接照搬。

可借鉴：

- 为 OpenAI、Generic OpenAI、DeepSeek、OpenRouter、Ollama、Anthropic、Bedrock 等 provider 分别建立 adapter。
- 在 provider 层处理请求参数差异，例如 OpenRouter 的 `include_reasoning`、Generic OpenAI 的 usage stream options、Azure 的 reasoning model type。
- 在 provider 层读取结构化字段，例如 `reasoning_content`、`reasoning`、`message.thinking`。
- 在工具调用场景下处理 provider 特殊要求，例如 DeepSeek thinking model 对历史 assistant message 的 `reasoning_content` 兼容要求。

不能照搬：

- AnythingLLM 会把结构化 reasoning 包成 `<think>...</think>`，再交给前端用正则拆分并展示 thought chain。
- 这种做法会让 reasoning 混入普通文本通道、历史消息和复制逻辑，容易污染下一轮上下文、报告生成和标题生成。

CodeAsk 的取舍：

```text
借鉴 provider / request profile / stream handler 分层。
拒绝 <think> 文本通道。
拒绝前端正则作为协议修补层。
```

更详细的参考结论见 `../v1.0.2/specs/model-provider-reference-lessons.md`。

## 5. 建议架构

### 5.1 LLM 事件模型

建议扩展内部 LLM event：

```text
message_start
text_delta
reasoning_start
reasoning_delta
reasoning_stop
tool_call_start
tool_call_delta
tool_call_done
message_stop
error
```

其中：

- `text_delta` 只承载用户可见回答。
- `reasoning_delta` 承载供应商返回的结构化 reasoning，默认不进入聊天气泡。
- `tool_call_*` 进入 Agent 行动轨迹。
- `message_stop` 应携带 stop reason、usage、reasoning usage 等信息。

### 5.2 Provider 适配层

每个 provider adapter 应负责把供应商返回规范化：

| Provider 返回 | CodeAsk 内部事件 |
|---|---|
| Anthropic `thinking_delta` | `reasoning_delta` |
| Anthropic `redacted_thinking` | `reasoning_delta`，标记 `redacted=true` |
| OpenAI-compatible `reasoning_content` | `reasoning_delta` |
| OpenAI-compatible `reasoning` | `reasoning_delta` |
| OpenAI-compatible `thinking` | `reasoning_delta`，仅当 provider 明确以结构化字段返回 |
| 普通 `content` | `text_delta` |
| Anthropic `text_delta` | `text_delta` |
| `content` / `text` 内嵌 `<think>` 等标签 | 不解析；视为上游模型服务未提供合规结构化 reasoning |

关键原则：

1. 先识别结构化字段。
2. 再处理 provider 已知的 reasoning 字段。
3. 不从 `content` / `text` 正文中强匹配 reasoning 标签。
4. 任何结构化 reasoning 都不能混入普通 `text_delta`。
5. 如果上游把 raw reasoning 放进正文，CodeAsk 只能通过 debug shape 识别接入不合规，不能在后端猜测过滤。

### 5.3 OpenAI-compatible 协议适配

OpenAI-compatible 流式返回通常是：

```json
{
  "choices": [
    {
      "delta": {
        "content": "正式回答"
      }
    }
  ]
}
```

Reasoning 模型或网关可能返回：

```json
{
  "choices": [
    {
      "delta": {
        "reasoning": "思考内容"
      }
    }
  ]
}
```

或旧字段：

```json
{
  "choices": [
    {
      "delta": {
        "reasoning_content": "思考内容"
      }
    }
  ]
}
```

CodeAsk 的 OpenAI-compatible adapter 应执行：

```text
delta.reasoning          -> reasoning_delta
delta.reasoning_content  -> reasoning_delta
delta.thinking           -> reasoning_delta，仅限结构化字段
delta.content            -> text_delta
delta.tool_calls         -> tool_call_*
```

不执行：

```text
delta.content 里扫描 <think>
delta.content 里扫描 </think>
delta.content 里扫描 <reasoning>
```

火山引擎 MiniMax-M2.7 的一次实测返回格式为：

```text
choices[0].delta.reasoning_content
choices[0].delta.content
```

这类返回可以由结构化字段适配直接处理。

### 5.4 Anthropic 协议适配

Anthropic 流式协议以事件和 content block 为核心。

典型 thinking 开始：

```json
{
  "type": "content_block_start",
  "index": 0,
  "content_block": {
    "type": "thinking",
    "thinking": ""
  }
}
```

Thinking delta：

```json
{
  "type": "content_block_delta",
  "index": 0,
  "delta": {
    "type": "thinking_delta",
    "thinking": "思考内容"
  }
}
```

正式回答 delta：

```json
{
  "type": "content_block_delta",
  "index": 1,
  "delta": {
    "type": "text_delta",
    "text": "正式回答"
  }
}
```

CodeAsk 的 Anthropic adapter 应执行：

```text
content_block.type = thinking            -> reasoning_start
delta.type = thinking_delta              -> reasoning_delta
content_block.type = redacted_thinking   -> reasoning_delta(redacted=true)
delta.type = text_delta                  -> text_delta
content_block.type = tool_use            -> tool_call_start
delta.type = input_json_delta            -> tool_call_delta
delta.type = signature_delta             -> provider metadata，不展示
```

不执行：

```text
text_delta 里扫描 <think>
text_delta 里扫描 <thinking>
```

这与 Claude Code 主链路一致：thinking 是结构化 block，不是正文字符串过滤。

### 5.5 vLLM reasoning outputs 的接入边界

vLLM 的 reasoning outputs 设计提供了一个重要边界：

```text
模型服务层负责把模型原始输出解析成 reasoning/content 结构化字段。
业务后端只消费结构化字段。
```

如果私有模型原始输出包含 `<think>` 等模型私有格式，应优先在 vLLM 服务端通过 `--reasoning-parser` 解决，例如：

```bash
vllm serve <model> --reasoning-parser <parser-name>
```

服务端解析后，OpenAI-compatible API 应返回：

```text
delta.reasoning
delta.content
```

或兼容旧字段：

```text
delta.reasoning_content
delta.content
```

CodeAsk 不实现 vLLM parser 的标签解析逻辑，也不把 vLLM parser 名称翻译成后端正文扫描规则。CodeAsk 只关心模型服务最终返回的结构化字段。

### 5.6 Reasoning 请求配置

不同协议和网关开启 reasoning 的请求参数不同，不能全局硬塞同一个参数。

建议引入 `ReasoningRequestProfile`：

```text
none
volcengine_thinking
vllm_enable_thinking
anthropic_budget_thinking
anthropic_adaptive_thinking
custom_json
```

示例：

```text
volcengine_thinking:
  extra_body = {"thinking": {"type": "enabled"}}

vllm_enable_thinking:
  extra_body = {"chat_template_kwargs": {"enable_thinking": true}}

anthropic_budget_thinking:
  thinking = {"type": "enabled", "budget_tokens": 4096}
```

这些 profile 只控制请求参数，不控制正文标签解析。

### 5.7 UI 展示

前端建议采用三层展示：

1. **普通聊天气泡**

   只显示 `answer_text`。

2. **Agent 行动轨迹**

   显示工具调用、工具结果摘要、证据、警告、截断信息。

3. **开发 / 管理员调试视图**

   可选展示 reasoning 字段摘要或完整结构化 reasoning。默认关闭。

不建议把 reasoning 放在普通用户聊天气泡里，也不建议用“展开思考链”作为默认产品能力。

### 5.7.1 Agent 运行事件中的公开分析思路

隐藏 raw reasoning 不等于让 Agent 变成黑盒。CodeAsk 应通过 Agent 运行事件展示公开、可审计的分析思路。

允许展示：

- 本轮准备了哪些候选上下文：特性、Wiki、报告、附件、仓库。
- 模型实际调用了哪些工具。
- 工具命中了哪些证据。
- 哪些证据被用于回答。
- 当前有哪些不确定点。
- 下一步建议查 Wiki、读报告、查代码或追问用户。

不允许展示：

- `reasoning_delta` 原文。
- Anthropic `thinking_delta` 原文。
- OpenAI-compatible `reasoning_content` 原文。
- 任何从 `<think>` 标签中解析出来的内容。

建议事件：

```text
llm_input
context_prepared
analysis_note
evidence_selected
uncertainty
next_step_hint
reasoning_observed
```

其中 `reasoning_observed` 只用于管理员 / debug，且只能记录字段名、长度、redacted 标记和 provider，不记录 raw reasoning。

`llm_input` 用于模型请求前的公开审计，只展示消息数量、工具数量、上下文规模、最近工具结果摘要等结构化元数据。它不能展示 prompt 原文、raw `reasoning_delta`、Anthropic `thinking_delta` 或 OpenAI-compatible `reasoning_content`。行动轨迹中的这类调试摘要应由 Runtime 已有事件字段确定性生成，不能为了每张卡片额外调用 LLM。

### 5.8 持久化策略

建议数据库或会话存储区分：

```text
messages
├── visible_text
├── tool_calls
├── tool_results
├── evidence_refs
└── metadata

debug_reasoning
├── session_id
├── turn_id
├── provider
├── model
├── redacted
├── content_ref / encrypted_content
└── retention_policy
```

默认策略：

- 普通消息历史不保存原始 reasoning。
- 如果开启调试审计，可以保存到单独区域。
- 保存时应考虑加密、脱敏、保留期限和管理员权限。
- 报告生成、标题生成、普通上下文重放默认不读取原始 reasoning。

### 5.9 上下文策略

CodeAsk 后续应明确：

- reasoning 不等于用户可见记忆。
- reasoning 不应默认进入长期会话摘要。
- 如果供应商 API 要求 thinking block 在后续请求中保留，则由 provider adapter 按协议处理。
- 如果切换模型、provider、API key，应清理不可复用的 signature / reasoning block。
- 长上下文压缩时，优先保留用户意图、AI 结论、工具证据、报告草稿，不优先保留原始思考链。

### 5.10 调试与未知模型接入

未知模型接入时，CodeAsk 可以提供 stream shape debug，但 debug 的目标是识别协议字段，而不是解析正文标签。

允许记录：

```json
{
  "fields": ["reasoning_content", "content"],
  "has_reasoning_field": true,
  "has_content": true,
  "content_preview": "短截断预览"
}
```

不允许把 debug preview 用作后端解析规则。

判断标准：

```text
存在结构化 reasoning 字段 -> CodeAsk 支持 reasoning 隔离。
不存在结构化 reasoning 字段 -> CodeAsk 按普通 content 模型处理。
content/text 内嵌 raw thinking -> 上游模型服务接入不合规，应在网关/vLLM 层修复。
```

## 6. 风险与约束

### 6.1 不能把“隐藏思考链”理解为“关闭模型思考”

隐藏 reasoning 的展示，不等于禁用模型的 reasoning 能力。

模型是否使用内部 reasoning，取决于模型、API 参数和供应商协议。CodeAsk 应做的是：

- 不把原始 reasoning 暴露给普通用户。
- 不让 reasoning 污染普通上下文。
- 把有价值的行动事实转成 Agent 轨迹、证据和可解释摘要。

### 6.2 不应把 reasoning 当作产品解释能力

用户需要的是可验证解释：

- 查了哪些 Wiki。
- 查了哪些代码。
- 哪些证据支持结论。
- 哪些地方存在不确定性。
- 下一步建议是什么。

这些应该来自工具事件和证据链，而不是展示模型原始思考链。

### 6.3 不同供应商协议差异很大

OpenAI、Anthropic、OpenAI-compatible 私有模型、火山引擎、MiniMax 私有部署、vLLM、LiteLLM 网关返回字段可能不同。

因此，CodeAsk 需要 provider adapter 明确处理协议字段差异，不能在业务层统一用字符串匹配兜底。

### 6.4 模型服务必须承担原始输出解析责任

如果模型原始输出包含私有格式，例如：

```text
<think>raw reasoning</think>answer
```

CodeAsk 不负责把它拆成 reasoning 和 answer。模型服务或网关必须先把它转换为结构化协议：

```text
reasoning = raw reasoning
content = answer
```

这条边界是为了避免 CodeAsk 后端持续积累模型私有文本格式特判。

## 7. 待纳入版本时的验收标准

当该能力进入具体版本时，至少需要以下验收项：

- Anthropic structured thinking 不进入普通聊天正文。
- OpenAI-compatible `reasoning_content` 不进入普通聊天正文。
- OpenAI-compatible `reasoning` 不进入普通聊天正文。
- Anthropic `text_delta` 和 OpenAI-compatible `content` 不做标签扫描。
- 私有模型 `<think>...</think>` 泄漏到 `content` 时，系统能通过 debug shape 标记为上游不合规，但不在后端强行解析。
- vLLM / 网关已结构化输出的 reasoning 能被正确隔离。
- Agent 行动轨迹仍能展示工具调用、工具结果、证据和失败原因。
- 报告生成不会包含原始 reasoning。
- 会话标题生成不会包含原始 reasoning。
- 切换模型配置或 API key 后，不回放不可复用的 reasoning signature。
- 上下文压缩会优先保留用户意图、回答结论和证据，不优先保留原始 reasoning。
- 管理员调试模式能查看 reasoning 字段摘要和 stream shape，便于定位 provider 接入问题。
- 所有 reasoning 处理逻辑有单元测试、OpenAI-compatible 流式字段测试、Anthropic block 测试和端到端会话测试。

## 8. 推荐落地顺序

1. 移除或停用 CodeAsk 后端基于 `<think>` 的正文标签过滤。
2. 扩展内部 LLM event，增加 `reasoning_start`、`reasoning_delta`、`reasoning_stop`。
3. 在 OpenAI-compatible adapter 中识别 `reasoning`、`reasoning_content`、结构化 `thinking` 字段。
4. 在 Anthropic adapter 中识别 `thinking_delta`、`redacted_thinking`、`signature_delta`、`text_delta`。
5. 增加 `ReasoningRequestProfile`，区分火山引擎、vLLM、Anthropic 等请求参数。
6. 增加 stream shape debug，只记录字段结构和短 preview，不把 preview 用于解析。
7. 前端和持久化层明确区分 `answer_text`、`agent_trace`、`debug_reasoning`。
8. 报告、标题、上下文压缩统一只读取可见回答和证据，不读取原始 reasoning。
9. 为 OpenAI-compatible 与 Anthropic 两种协议分别增加测试矩阵。
10. 后续如接入 Claude Code / opencode backend，应把外部 agent 的 thinking / trace 转换为 CodeAsk 标准事件，而不是直接透传原始输出。

## 9. 结论

Claude Code 的源码说明，成熟 Agent 产品不会依赖“从字符串里删思考链”作为主方案。

vLLM reasoning outputs 的设计进一步说明，模型私有 reasoning 格式应在模型服务层通过 parser 转成结构化字段，而不是由业务后端解析正文。

更合理的架构是：

```text
模型服务层输出结构化 reasoning/content
协议适配层识别 reasoning
运行时隔离 reasoning
UI 默认隐藏 reasoning
上下文按规则保留或清理 reasoning
用户侧展示行动轨迹和证据链
```

CodeAsk 不应继续把 `<think>` 强匹配作为兼容兜底。后续必须迁移到同时支持 OpenAI-compatible 与 Anthropic 的结构化 reasoning 事件模型。否则随着接入更多模型、更多网关和外部 agent backend，思考链泄漏、上下文污染、报告污染和调试困难都会反复出现。

## 10. 参考

- vLLM Reasoning Outputs: https://docs.vllm.ai/en/stable/features/reasoning_outputs/
- vLLM How to support a new reasoning model: https://docs.vllm.ai/en/stable/features/reasoning_outputs/#how-to-support-a-new-reasoning-model
- Claude Code 源码参考：`references/claude-code/claude-code/src/services/api/claude.ts`
- Claude Code thinking UI 参考：`references/claude-code/claude-code/src/components/messages/AssistantThinkingMessage.tsx`
