# 模型服务与 Reasoning 处理参考实现学习

> 状态：Active
> 版本归属：v1.0.2
> 主题：在实现 CodeAsk 结构化 reasoning、模型服务接入和 Agent 运行事件前，明确参考项目的实现逻辑、可借鉴点和不能照搬的边界。

## 1. 背景

v1.0.2 需要修复模型 reasoning 泄漏、上下文污染、报告污染和多 provider 接入差异问题。该能力不能只依赖 CodeAsk 自己拍脑袋设计，开发时必须实际对照成熟项目和协议资料：

- Claude Code：结构化 thinking、工具事件、长上下文治理、外部 agent 运行时。
- AnythingLLM：多模型 provider 接入、OpenAI-compatible provider 分层、RAG 管线、reasoning 字段处理。
- vLLM reasoning outputs：模型服务层把私有 thinking 格式解析成结构化 `reasoning` / `content` 的边界。
- CodeAsk 实测：火山引擎 MiniMax-M2.7 在 OpenAI-compatible stream 中返回 `delta.reasoning_content` 和 `delta.content`。

本文不是要求照搬任何项目，而是把参考逻辑转成 CodeAsk 的实现约束，避免后续代码继续堆在单个 client 或 runtime 中。

## 2. Claude Code 的关键启发

Claude Code 的主线是结构化 thinking，而不是正文标签过滤。

可借鉴：

- 按协议 block / event 区分 `thinking_delta`、`text_delta`、`tool_use`、`signature_delta`。
- 普通 UI 不把完整 thinking 当作回答展示，只展示思考状态或 transcript / verbose 模式信息。
- 长上下文治理会考虑 thinking 的 token 影响，但不会把不可复用的 signature / thinking block 无条件回放。
- 工具调用、工具结果、压缩、恢复都有明确事件链。

CodeAsk 落地约束：

- `reasoning_delta` 与 `text_delta` 从 adapter 层开始分离。
- `reasoning_delta` 不进入普通聊天气泡、`session_turns.content`、标题生成、报告生成和普通上下文摘要。
- 运行事件可以展示“正在分析”“已基于哪些证据调整方向”等公开状态，但不能默认展示原始 reasoning。

## 3. AnythingLLM 的关键启发

AnythingLLM 的模型接入层很厚，每个 provider 都有独立 class，统一实现 prompt 构造、流式处理、上下文窗口、能力声明和指标统计。

可借鉴：

- Provider 分层：`openai`、`generic-openai`、`anthropic`、`deepseek`、`openrouter`、`ollama`、`bedrock` 等都有独立适配。
- Request 参数差异通过 provider 层处理，例如 OpenRouter 的 `include_reasoning`、Generic OpenAI 的 usage stream options、Azure reasoning model type。
- 能力声明：部分 provider 会暴露 tools、reasoning、vision、image generation 等能力。
- Agent provider 与普通 chat provider 有不同调用路径，tool calling 场景需要额外兼容。

不能照搬：

- AnythingLLM 会把结构化 reasoning 字段重新包成 `<think>...</think>` 文本，再交给前端正则解析和折叠展示。
- 它的前端会通过 `<think>`、`<thinking>`、`<thought>` 等正则识别 thought chain。
- 这种方案会让 reasoning 混入普通文本、历史消息和潜在上下文，不适合 CodeAsk。

CodeAsk 落地约束：

- 借鉴 provider / profile 分层，不借鉴 `<think>` 文本通道。
- OpenAI-compatible `reasoning_content` / `reasoning` / 结构化 `thinking` 只生成内部 `reasoning_delta`。
- `content` 中出现 `<think>` 时，CodeAsk 不在后端强行解析；应标记为上游模型服务或网关接入不合规。

## 4. vLLM Reasoning Outputs 的关键启发

vLLM 的 reasoning outputs 明确了职责边界：

```text
模型服务层负责把模型私有输出解析成结构化 reasoning/content。
业务后端负责消费结构化字段。
```

可借鉴：

- 私有模型新增 reasoning 支持时，应在模型服务层实现 parser 或选择已有 parser。
- vLLM 当前文档中，推理输出字段主名是 `reasoning`，旧字段名 `reasoning_content` 属于历史兼容；CodeAsk 需要同时兼容两者。
- vLLM streaming chat completion 会把 `reasoning` 放在 `choices[0].delta` 中，`content` 仍承载最终回答。
- CodeAsk 的 OpenAI-compatible adapter 只识别最终 API 返回字段，不把 parser 逻辑写进业务后端。
- 对未知模型，先观察 stream shape，再决定 request profile 或网关配置。

CodeAsk 落地约束：

- `vllm_enable_thinking` 只是一种 request profile，不代表 CodeAsk 后端可以扫描 `<think>`。
- `extra_body={"chat_template_kwargs": {"enable_thinking": True}}` 是请求级覆盖示例，不应全局硬塞到所有 OpenAI-compatible 配置。
- 如果私有环境输出 `<think>raw</think>answer` 到 `content`，优先修复 vLLM / 网关配置。
- Live E2E 必须记录 observed stream fields，证明问题来自协议字段还是上游正文泄漏。

## 5. CodeAsk 实测结论

火山引擎 MiniMax-M2.7 在一次 OpenAI-compatible stream 实测中出现过以下字段组合：

```text
fields = ["reasoning_content", "role"]
fields = ["reasoning_content"]
fields = ["content", "reasoning_content"]
fields = ["content"]
fields = []
```

这说明：

- 结构化 `reasoning_content` 是真实存在的，不是理论设计。
- `content` 与 `reasoning_content` 可能在同一个 delta 中同时出现。
- Adapter 不能用 `if content else reasoning` 之类互斥逻辑。
- 同一 chunk 可以同时产生 `reasoning_delta` 和 `text_delta`，但只有 `text_delta` 进入可见回答。

## 6. CodeAsk 最新分层方案

v1.0.2 实现应按以下边界拆分：

| 层 | 责任 | 不允许做的事 |
|---|---|---|
| LLM 配置层 | 保存协议、模型、base url、request profile、启停状态 | 不判断业务问题范围 |
| LLM 调度层 | 全局 / 用户配置选择、负载均衡、失败冷却、会话粘性 | 不解析模型正文 |
| 协议适配层 | OpenAI-compatible / Anthropic chunk 归一化 | 不扫描 `<think>` 标签 |
| Request Profile 层 | provider 请求参数差异 | 不决定回答内容 |
| 流式归一层 | 输出 `text_delta`、`reasoning_delta`、`tool_call_delta`、`done` | 不把 reasoning 降级成普通文本 |
| Agent Runtime 层 | 组织上下文、工具、SSE、持久化 | 不把 raw reasoning 写入 turns |
| 上下文治理层 | 控制进入下一轮模型的内容 | 不把原始 reasoning 当历史记忆 |
| Agent 运行事件层 | 展示工具动作、证据、公开分析摘要 | 不展示模型原始思考链 |
| 前端展示层 | 聊天气泡、运行事件、错误提示、受控泄漏保护 | 不把正则当作协议解析器 |

### 6.1 Reasoning Leak Guard 的边界

最终方案分四层落地：

1. **结构化协议适配**：OpenAI-compatible / Anthropic 正常字段从 adapter 层分离为 `reasoning_delta` 和 `text_delta`。
2. **Request Profile**：根据模型配置启用 `volcengine_thinking`、`vllm_enable_thinking`、`anthropic_budget_thinking` 或 `custom_json` 等请求参数。
3. **模型服务 / 网关 Parser**：对于会吐 `<think>` 的私有模型，在 vLLM、模型服务或网关层把 raw thinking 转成结构化 `reasoning` / `content`。
4. **UI Leak Guard**：只用于防止 raw thinking 意外暴露到用户界面，不作为协议解析成功，不修复后端上下文。

UI Leak Guard 允许存在，但必须满足以下约束：

- 只能在显示层工作，不能修改数据库中的 `session_turns.content`。
- 不能把遮蔽后的内容回写到下一轮上下文、报告生成、标题生成或摘要压缩。
- 必须产生本地诊断事件，例如 `reasoning_leak_detected`，说明上游把疑似 raw reasoning 放进了 visible content。
- 诊断事件只记录来源、片段长度、是否遮蔽、provider/config/request id 等元数据，不记录 raw reasoning 原文。
- 必须可配置关闭，建议模式为 `disabled | warn_only | mask_in_ui`，默认使用 `mask_in_ui` 保护用户体验。
- 验收时不能把 UI Leak Guard 遮蔽成功当作结构化 reasoning 接入成功；它只能说明“上游不合规时前端没有把泄漏直接展示给用户”。

## 7. Agent 运行事件中的“分析思路”

用户需要看到的是可审计的分析思路，不是模型原始 chain-of-thought。

因此，v1.0.2 可以在 Agent 运行事件中扩展以下公开事件：

| 事件类型 | 用户可见 | 来源 | 内容要求 |
|---|---:|---|---|
| `llm_input` | 是 | Runtime 请求前审计 | 消息数、工具数、上下文规模、最近工具结果摘要；不展示 prompt 原文和 raw reasoning |
| `context_prepared` | 是 | Runtime 组装结果 | 本轮给模型注入了哪些候选：特性、Wiki、报告、附件、仓库 |
| `analysis_note` | 是 | 基于可见上下文 / 工具事件的公开摘要 | 简短说明当前分析方向，不包含 raw reasoning |
| `evidence_selected` | 是 | 工具结果 / RAG 召回 | 被采用的证据路径、标题、片段摘要 |
| `uncertainty` | 是 | 模型公开回答或工具结果 | 当前不确定点、需要用户确认的信息 |
| `next_step_hint` | 是 | 模型公开回答或工具调用意图 | 下一步可能查 Wiki、读报告、查代码或追问 |
| `reasoning_observed` | 管理员 / debug | LLM adapter shape debug | 只显示字段名、长度、是否 redacted，不显示原文 |

`analysis_note` 的生成原则：

- `llm_input`、`tool_result`、`runtime_state` 等调试展示优先由结构化字段确定性格式化，不能为每个行动轨迹事件新增模型摘要请求。
- 可以由模型在普通可见回答中明确写出，也可以由 Runtime 根据已发生工具事件生成短摘要。
- 内容必须来自用户问题、RAG 候选、工具调用、工具结果、证据引用或模型可见的公开回答。
- 不得使用 `reasoning_delta` 原文。
- 不得伪造模型没有做过的工具动作。
- 不得把后端规则写死成“已判断属于某特性”“必须查代码”等业务结论；如果需要表达，只能说“本轮上下文包含这些候选，模型随后选择了这些动作”。

示例：

```json
{
  "event_type": "analysis_note",
  "payload": {
    "title": "分析方向",
    "summary": "本轮上下文包含 AnythingLLM 特性、8 篇 Wiki 和 1 份报告。模型优先读取了与 ingestion / retrieval 相关的 Wiki，再补充搜索向量召回关键词。",
    "source": "trace_summary",
    "raw_reasoning_used": false
  }
}
```

这类运行事件能让用户理解 Agent 为什么做这些动作，同时避免泄露或污染模型原始思考链。

## 8. 开发时必须执行的参考动作

实现 v1.0.2 structured reasoning 前，开发者必须完成以下检查，并在 PR / commit 说明或验收记录中留下证据：

1. 对照 Claude Code：
   - 确认 Anthropic `thinking_delta` / `text_delta` / `signature_delta` 的处理边界。
   - 确认 UI 默认不展示完整 thinking 的产品边界。
2. 对照 AnythingLLM：
   - 确认 OpenAI-compatible provider 如何读取 `reasoning_content` / `reasoning`。
   - 明确不采用 `<think>` 文本通道作为主协议；前端只允许受控 UI Leak Guard。
3. 对照 vLLM：
   - 确认私有模型 `<think>` 解析应在模型服务层完成。
   - 确认 CodeAsk 只消费结构化字段。
4. 对照真实模型：
   - 至少记录一次 live stream observed fields。
   - 对火山 MiniMax、火山 GLM、DeepSeek v4 分别确认是否返回 reasoning 字段或只返回 content。

## 9. 验收关注点

- 多参考项目只作为实现依据，不允许把多套方案混成一套不可维护逻辑。
- Provider 差异进入 request profile / adapter，不进入业务 runtime。
- Agent 运行事件可以更透明，但展示的是公开分析摘要和证据链，不是 raw reasoning。
- 所有 reasoning 隔离必须有单元测试、集成测试和 live E2E。
- 如果 live 模型返回 raw `<think>` 到 `content`，验收应失败或标记上游不合规；前端可用 UI Leak Guard 防止用户界面泄漏，但不能通过后端正则过滤让它“看起来成功”。
