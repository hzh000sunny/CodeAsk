# LLM 网关设计

## 1. 目标

LLM 网关隔离模型供应商差异，为 Agent 提供统一流式接口和工具调用解码。

一期直接支持 OpenAI 和 Anthropic，同时保留 OpenAI-compatible 私有模型接入能力。Agent 运行时不能依赖任何供应商原始消息格式，只能依赖 CodeAsk 内部定义的通用 LLM 协议。

核心原则：

- Agent 只构造 `LLMRequest`，只消费 `LLMEvent`。
- 工具定义使用 CodeAsk 内部 `ToolDef`，由适配器转换成供应商格式。
- 工具调用、流式 token、stop reason、usage 都归一化。
- 供应商差异只存在于 `codeask.llm` 包内部。
- 轨迹日志可以保留供应商原始事件，但业务逻辑不得依赖原始事件。

## 2. 接口

```python
class LLMClient(Protocol):
    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolDef],
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[LLMEvent]:
        ...
```

实际实现按 provider 拆分：

```python
class OpenAIClient(LLMClient): ...
class AnthropicClient(LLMClient): ...
class OpenAICompatibleClient(OpenAIClient): ...
```

`LLMGateway` 根据 `llm_configs.protocol` 选择具体 client：

```python
class LLMGateway:
    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        config = self.config_repo.get_default_or(request.config_id)
        client = self.client_factory.create(config.protocol)
        async for event in client.stream(request):
            yield event
```

## 3. 通用请求模型

Agent 调用 LLM 网关时使用统一请求：

```python
class LLMRequest(BaseModel):
    config_id: str | None
    messages: list[LLMMessage]
    tools: list[ToolDef]
    tool_choice: ToolChoice | None
    max_tokens: int
    temperature: float
    metadata: dict[str, Any] = {}
```

通用消息：

```python
class LLMMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: list[ContentBlock]
    tool_call_id: str | None = None
```

通用内容块：

```python
class TextBlock(BaseModel):
    type: Literal["text"]
    text: str

class ToolCallBlock(BaseModel):
    type: Literal["tool_call"]
    id: str
    name: str
    arguments: dict

class ToolResultBlock(BaseModel):
    type: Literal["tool_result"]
    tool_call_id: str
    content: str | dict
    is_error: bool = False
```

一期以文本和工具调用为主。图片、文件、多模态内容后续增加新的 `ContentBlock` 类型，不改变 Agent 主循环。

## 4. 通用事件模型

LLM 网关输出统一事件流：

```python
class LLMEvent(BaseModel):
    type: Literal[
        "message_start",
        "text_delta",
        "tool_call_start",
        "tool_call_delta",
        "tool_call_done",
        "message_stop",
        "usage",
        "error",
    ]
    data: dict
```

关键事件含义：

| 事件 | 含义 |
|---|---|
| `text_delta` | 模型输出的文本增量 |
| `tool_call_start` | 开始一个工具调用，含 id 和 name |
| `tool_call_delta` | 工具参数 JSON 的增量片段 |
| `tool_call_done` | 工具参数完整，可交给 Agent 校验并执行 |
| `message_stop` | 模型本轮停止，含归一化 stop reason |
| `usage` | token 使用量 |
| `error` | 供应商错误归一化结果 |

归一化 stop reason：

```text
end_turn
tool_call
max_tokens
stop_sequence
content_filter
error
unknown
```

## 5. 工具调用归一化

CodeAsk 内部工具定义：

```python
class ToolDef(BaseModel):
    name: str
    description: str
    input_schema: dict
```

适配规则：

| CodeAsk | OpenAI | Anthropic |
|---|---|---|
| `ToolDef.name` | `tools[].function.name` | `tools[].name` |
| `ToolDef.description` | `tools[].function.description` | `tools[].description` |
| `ToolDef.input_schema` | `tools[].function.parameters` | `tools[].input_schema` |
| `tool_result` | role=`tool` message | content block `tool_result` |

Agent 只处理 CodeAsk 内部 `tool_call_id`。适配器负责把供应商 tool id 映射到内部 id，并在回填结果时转换成供应商要求的消息结构。

## 6. Provider 适配器

### 6.1 OpenAI

OpenAI 适配器负责：

- 调用 Chat Completions 或 Responses API 的具体实现，实施阶段按 SDK 稳定性选择。
- 把 CodeAsk `ToolDef` 转为 OpenAI tool schema。
- 把 OpenAI streaming delta 转成 `LLMEvent`。
- 把 OpenAI tool calls 转成内部 `tool_call_*` 事件。
- 把内部 `tool_result` 转成供应商要求的工具结果消息。

### 6.2 Anthropic

Anthropic 适配器负责：

- 调用 Anthropic Messages API。
- 把 CodeAsk `ToolDef` 转为 Anthropic tool schema。
- 把 Anthropic content block streaming 转成 `LLMEvent`。
- 把 `tool_use` block 转成内部 `tool_call_*` 事件。
- 把内部 `tool_result` 转成 Anthropic `tool_result` content block。

### 6.3 OpenAI-compatible

OpenAI-compatible 适配器用于私有部署模型服务。它复用 OpenAI 适配器的大部分逻辑，但配置允许：

- 自定义 `base_url`。
- 自定义认证头。
- 关闭或降级部分不兼容能力。
- 标记是否支持原生工具调用。

如果私有模型不支持工具调用，实施阶段需要明确降级策略：要么拒绝作为 Agent 模型使用，要么由网关做 JSON tool-call 兼容解析。默认推荐拒绝，避免 Agent 行为不稳定。

## 7. 能力

- 流式 token 归一化。
- tool call 解码和参数增量拼接。
- tool result 消息适配。
- 超时控制。
- 指数退避重试。
- 错误标准化。
- usage 归一化。
- 模型配置切换。
- provider 能力探测。

## 8. 配置

LLM 配置存 SQLite：

- scope (`user` / `global`)
- owner_subject_id（用户配置所属 subject；全局配置为空）
- protocol
- base_url
- api_key_encrypted
- model_name
- max_tokens（API 默认 `200 * 1024`；配置页不展示）
- temperature（API 默认 `0.2`；配置页不展示）
- enabled
- is_default（历史兼容字段；新 workbench 不提供设为默认操作）
- rpm_limit（保留字段；当前不配置）
- quota_remaining（保留字段；当前不配置）

`protocol` 一期取值：

```text
openai
anthropic
```

新 workbench 的协议选择只展示 OpenAI 和 Anthropic。`openai_compatible` 仍保留为历史兼容和后端扩展能力，但不是当前 UI 可选项。

API Key 使用 Fernet 加密，master key 来自 `CODEASK_DATA_KEY`（与 `deployment-security.md` §5 锁定的环境变量名一致）。

运行时选择规则：

1. 如果请求显式指定 `config_id`，网关只能使用当前用户可访问的配置。
2. 未指定时，先选择当前 `subject_id` 下启用的用户配置。
3. 用户没有启用配置时，选择启用的全局配置。
4. 多个启用配置按创建时间稳定选择；新 workbench 不提供默认配置切换。

管理员可以看到全局配置的 masked key；普通用户不能通过列表 API 获取全局配置。

后续负载均衡策略：

- 当前阶段不维护 `rpm_limit` 和 `quota_remaining`，供应商 429、余额不足或其它调用失败直接通过会话错误返回。

建议增加能力字段：

```json
{
  "supports_tools": true,
  "supports_streaming": true,
  "supports_usage": true,
  "max_context_tokens": 200000
}
```

能力字段可以由用户配置，也可以由后端通过一次健康检查探测后写入。

## 9. 错误模型

供应商错误统一映射为：

```python
class LLMError(BaseModel):
    provider: str
    error_code: str
    message: str
    retryable: bool
    raw: dict | None = None
```

重试策略：

- 网络超时、429、部分 5xx：指数退避重试，最多 3 次。
- 鉴权失败、模型不存在、工具 schema 非法：不重试，直接返回错误。
- 流式中断：返回可恢复错误，Agent 当前轮停止在可重试状态。

## 10. 扩展

- 本地模型特定适配。
- 大小杯模型分流。
- prompt cache。
- 多模态输入。
- provider 级限流与配额。
