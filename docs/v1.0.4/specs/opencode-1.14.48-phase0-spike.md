# opencode 1.14.48 Phase 0 Spike 记录

> 版本：v1.0.4
> 测试日期：2026-05-13
> opencode 版本：`1.14.48`
> 测试目的：在开发 `src/codeask/agent/opencode_compat/` 前，用真实 opencode 行为验证 HTTP、MCP、事件流、真实 LLM 配置、shared server、Wiki 挂载、worktree 准备和会话恢复语义。ACP 做探索性验证但 v1.0.4 暂不纳入实现范围；`abort + revert` 深度回滚列遗留增强项。

---

## 1. 测试环境

| 项 | 值 |
|---|---|
| opencode CLI | `opencode` |
| 版本输出 | `1.14.48` |
| opencode 源码 | `/home/hzh/workspace/CodeAsk/references/opencode` |
| opencode 本地 wiki | `/home/hzh/wiki/opencode-docs` |
| CodeAsk DB | `/home/hzh/.codeask/data.db` |
| 测试隔离方式 | 每次测试使用临时 `HOME`、`XDG_DATA_HOME`、`XDG_CONFIG_HOME`、`XDG_CACHE_HOME` |
| 认证方式 | `OPENCODE_SERVER_USERNAME` + `OPENCODE_SERVER_PASSWORD`，HTTP Basic Auth |

所有真实 LLM 测试均从 CodeAsk 数据库读取配置，通过 CodeAsk 的 `data_key` 解密后只写入临时 opencode 配置；测试文档不记录 API Key。

---

## 2. CLI 与服务能力

### 2.1 `opencode --version`

结果：

```text
1.14.48
```

### 2.2 `opencode serve`

测试命令形态：

```bash
HOME=/tmp/.../home \
XDG_DATA_HOME=/tmp/.../data \
XDG_CONFIG_HOME=/tmp/.../config \
XDG_CACHE_HOME=/tmp/.../cache \
OPENCODE_SERVER_USERNAME=codeask \
OPENCODE_SERVER_PASSWORD=phase0 \
opencode serve --hostname 127.0.0.1 --port 46123 --pure --log-level DEBUG
```

观察结果：

| 项 | 结果 |
|---|---|
| 首次启动 | 会自动执行一次 SQLite migration |
| 监听地址 | `http://127.0.0.1:<port>` |
| `/global/health` | 返回 `{"healthy":true,"version":"1.14.48"}` |
| 未带 Basic Auth | 返回 `401 Unauthorized` |
| `/doc` | 返回 OpenAPI JSON |

结论：

- CodeAsk 可以用 Basic Auth 包住 opencode server。
- 每个隔离数据目录首次启动都有 migration 成本，但本次实测很快完成。
- 生产实现需要持久化 opencode 数据目录，避免每轮重新 migration。

---

## 3. HTTP API 与事件流

### 3.1 Session 创建

测试：

```bash
curl -u codeask:phase0 -X POST http://127.0.0.1:46123/session
```

返回示例：

```json
{
  "id": "ses_1e2f05eafffede4wb59JoFau3W",
  "slug": "curious-circuit",
  "projectID": "global",
  "directory": "/tmp/codeask-opencode-spike-XMQafW/workspace",
  "title": "New session - 2026-05-12T16:40:24.144Z",
  "version": "1.14.48"
}
```

结论：

- `POST /session` 可创建会话。
- session 绑定了 `directory`，CodeAsk 必须在所有后续请求里保持 workspace 路由一致。

### 3.2 `/event` 与 `/global/event`

实测：

| Endpoint | 事件形态 | 观察 |
|---|---|---|
| `/event` | `data: {"id":...,"type":"server.connected","properties":{}}` | 更偏实例事件，直接 payload |
| `/global/event` | `data: {"directory":...,"project":"global","payload":{...}}` | 包含 directory/project，可观察跨 workspace/session 事件 |

`/global/event` 中 session 创建事件示例：

```json
{
  "directory": "/tmp/codeask-opencode-spike-XMQafW/workspace",
  "project": "global",
  "payload": {
    "type": "session.created",
    "properties": {
      "sessionID": "ses_...",
      "info": {
        "directory": "/tmp/codeask-opencode-spike-XMQafW/workspace"
      }
    }
  }
}
```

结论：

- CodeAsk 前端行动轨迹建议优先消费 `/global/event`，因为它带 `directory`，更适合多 workspace 或 shared server 设计。
- 如果采用 per-session server，`/event` 也可用，但仍建议统一按 `/global/event` 建模，后续切 shared server 成本更低。
- opencode 事件里同时有业务事件和 `sync` 事件，前端需要过滤/折叠，不能原样全量展示。

### 3.3 `prompt_async` 真实模型测试

使用 CodeAsk DB 中启用的真实配置：

| 配置 | 协议 | 模型 |
|---|---|---|
| 火山-OpenAI-MiniMax-M2.7 | `openai` | `MiniMax-M2.7` |

测试路径：

1. 生成临时 opencode provider 配置。
2. 启动 `opencode serve`。
3. `POST /session` 创建会话。
4. 订阅 `/global/event`。
5. `POST /session/:id/prompt_async` 发送：

```json
{
  "model": {
    "providerID": "codeask_<cfg-id>",
    "modelID": "MiniMax-M2.7"
  },
  "parts": [
    { "type": "text", "text": "请只回答：CodeAsk smoke ok" }
  ]
}
```

观察结果：

| 项 | 结果 |
|---|---|
| `prompt_async` HTTP 状态 | `204` |
| `/global/event` 数量 | 59 个事件 |
| 事件类型样本 | `server.connected`, `session.next.agent.switched`, `session.next.model.switched`, `message.updated`, `message.part.updated`, `session.status`, `session.diff` |
| SQLite assistant text part | `CodeAsk smoke ok` |
| SQLite assistant reasoning part | 存在 |
| tokens | `input=7254`, `output=5`, `reasoning=42`, `total=7301` |

SQLite 中 assistant message 摘要：

```json
{
  "role": "assistant",
  "agent": "build",
  "modelID": "MiniMax-M2.7",
  "providerID": "codeask_<cfg-id>",
  "finish": "stop",
  "tokens": {
    "total": 7301,
    "input": 7254,
    "output": 5,
    "reasoning": 42
  }
}
```

结论：

- `prompt_async` 是 CodeAsk 主路径的更合适选择：请求快速返回，后续通过 SSE + session DB/API 追踪。
- opencode 会把 reasoning 作为结构化 part 存储，而不是混在 text 中；这比 CodeAsk v1.0.2/v1.0.3 的 `<think>` 强过滤方案更接近目标。
- CodeAsk 前端可以在行动轨迹中展示 reasoning 摘要或片段，但需要产品上定义可见范围。

### 3.4 Message API 路径注意事项

opencode 1.14.48 的消息列表路径不是 `/session/:id/messages`，而是：

```text
GET /session/:sessionID/message
```

单条消息路径是：

```text
GET /session/:sessionID/message/:messageID
```

误用 `/session/:id/messages` 会命中 opencode UI fallback，返回 HTML。

结论：

- CodeAsk `opencode_compat/http.py` 必须以 opencode OpenAPI/source 为准，不要按 REST 直觉拼路径。
- 所有请求都必须带正确 workspace 路由参数或 header，避免 session 存在但读取为空。

---

## 4. 真实 LLM 配置矩阵

测试方式：

- 读取 CodeAsk DB 中 9 条 LLM 配置，包括启用和禁用配置。
- 每条配置生成临时 opencode provider。
- 使用 `opencode run --format json --pure --dir <workspace>` 发送短 prompt。
- 通过 opencode SQLite 校验 assistant text/reasoning/error。

provider 映射策略：

| CodeAsk 协议 | opencode provider npm |
|---|---|
| `openai` / `openai_compatible` | `@ai-sdk/openai-compatible` |
| `anthropic` | `@ai-sdk/anthropic` |

矩阵结果：

| 配置 | 协议 | 模型 | DB enabled | 结果 | 观察 |
|---|---|---|---:|---|---|
| 火山-Anthropic-glm-5.1 | anthropic | glm-5.1 | 是 | 失败 | 401，URL 为 `https://ark.cn-beijing.volces.com/api/coding/messages`，网关提示缺少或错误 Authorization |
| 火山-Anthropic-minimax-m2.7 | anthropic | minimax-m2.7 | 否 | 失败 | 同上，401 |
| 火山-OpenAI-glm-5.1 | openai | glm-5.1 | 否 | 通过 | assistant text 正常，reasoning part 存在 |
| DeepSeek-Anthropic | anthropic | deepseek-v4-flash | 否 | 通过 | assistant text 正常，reasoning part 存在 |
| DeepSeek-Anthropic-Pro | anthropic | deepseek-v4-pro | 否 | 通过 | assistant text 正常，reasoning part 存在 |
| DeepSeek-OpenAI | openai | deepseek-v4-flash | 否 | 通过 | assistant text 正常，reasoning part 存在 |
| 火山-OpenAI-MiniMax-M2.7 | openai | MiniMax-M2.7 | 是 | 通过 | assistant text 正常，reasoning part 存在 |
| 火山-OpenAI-minimax-m2.7 | openai | minimax-m2.7 | 否 | 通过 | assistant text 正常，reasoning part 存在 |
| DeepSeek-OpenAI-Pro | openai | deepseek-v4-pro | 否 | 通过 | assistant text 正常，reasoning part 存在 |

关键结论：

1. OpenAI 兼容协议在 opencode 1.14.48 中通过 `@ai-sdk/openai-compatible` 可稳定工作。
2. DeepSeek 的 Anthropic endpoint 可以通过 `@ai-sdk/anthropic` 工作。
3. 火山的 Anthropic endpoint 在当前映射下失败。错误不是模型回答失败，而是请求认证头或 endpoint 形态不匹配。
4. v1.0.4 不能简单假设“CodeAsk 协议字段为 anthropic，就必然可用 `@ai-sdk/anthropic`”。至少需要：
   - 在配置测试入口中显示 opencode provider smoke 结果；
   - 对失败配置给出明确提示，而不是进入会话后才失败；
   - 对 provider 映射保留扩展点，不能写死不可修改。
   - 保存最近一次 opencode smoke 错误摘要和成功 profile 可作为遗留增强项，不阻塞主流程。

### 4.1 Anthropic provider profile 补充测试

针对火山 Anthropic 失败问题，继续做最小变量测试。

测试对象：

| 配置 | base_url | 模型 |
|---|---|---|
| 火山-Anthropic-glm-5.1 | `https://ark.cn-beijing.volces.com/api/coding` | `glm-5.1` |
| 火山-Anthropic-minimax-m2.7 | `https://ark.cn-beijing.volces.com/api/coding` | `minimax-m2.7` |
| DeepSeek-Anthropic | `https://api.deepseek.com/anthropic` | `deepseek-v4-flash` |
| DeepSeek-Anthropic-Pro | `https://api.deepseek.com/anthropic` | `deepseek-v4-pro` |

测试 profile：

| profile | 配置方式 | 火山结果 | DeepSeek 结果 |
|---|---|---|---|
| `anthropic-default` | `@ai-sdk/anthropic` + 原始 `base_url` | 失败，打到 `/api/coding/messages`，401 | 通过 |
| `anthropic-auth-header` | 原始 `base_url` + `Authorization: Bearer` | 失败，404 | 未作为候选 |
| `anthropic-base-v1-auth` | `baseURL=<base_url>/v1` + `Authorization: Bearer` | 通过 | 通过 |
| `openai-compatible-same-url` | `@ai-sdk/openai-compatible` + Anthropic 配置的 key/base_url | 失败，404 | 未作为候选 |

关键结论：

- 火山 Anthropic 不是不能用 Anthropic provider factory，而是需要 `baseURL` 指向 `/v1` 层，并使用 Bearer 鉴权。
- `anthropic-base-v1-auth` 在本轮测试的火山和 DeepSeek Anthropic 配置上均通过，可以抽象为 `anthropic-compatible-v1-bearer` profile。
- 这不应写成厂商特判，也不应无限扩展候选 profile。推荐实现为：每个协议只保留少量通用候选，优先选择真实配置矩阵中全部通过的 profile。
- 成功 profile 持久化和自动重测先列为遗留增强项；主功能阶段先使用当前实测通过的 profile 打通完整流程。
- v1.0.4 初版 Anthropic 候选应优先使用 `anthropic-compatible-v1-bearer`，因为它覆盖了当前实测的火山和 DeepSeek Anthropic 配置；`anthropic-default` 仅作为 fallback 或显式兼容项保留。

---

## 5. Shared Server 多 Session 与每 Workspace 配置

### 5.1 单 server 全局预加载多 provider

测试方式：

1. 启动一个 `opencode serve`。
2. 在 `OPENCODE_CONFIG_CONTENT` 中放入 CodeAsk DB 的 9 条 provider。
3. 创建两个不同 workspace：
   - `workspaceA`
   - `workspaceB`
4. 分别创建 session，并发调用：
   - session A：DeepSeek-Anthropic / `deepseek-v4-flash`
   - session B：火山-OpenAI-MiniMax-M2.7 / `MiniMax-M2.7`

结果：

| 项 | session A | session B |
|---|---|---|
| workspace | `workspaceA` | `workspaceB` |
| provider | `codeask_51fe0837af001668` | `codeask_dd619536ce9f6bb7` |
| model | `deepseek-v4-flash` | `MiniMax-M2.7` |
| prompt_async | `204` | `204` |
| assistant text | `CodeAsk shared A ok` | `CodeAsk shared B ok` |
| reasoning part | 存在 | 存在 |
| error | 无 | 无 |

`/global/event` 事件样本同时包含两个 workspace 的事件：

```json
{
  "directory": "/tmp/.../workspaceB",
  "payload": {
    "type": "message.updated",
    "properties": {
      "sessionID": "ses_..."
    }
  }
}
```

结论：

- 一个 opencode server 可以同时承载多个 session。
- 每次 prompt 可以通过 payload 中的 `model.providerID/modelID` 指定不同 provider/model。
- `/global/event` 可以通过 `directory + sessionID` 做前端事件归属。

### 5.2 单 server + 每 workspace 独立 `opencode.json`

这是更接近 CodeAsk 的目标形态：不把所有 provider 放进 server 全局配置，而是在每个会话 workspace 内写自己的 `opencode.json`。

测试方式：

1. 启动一个 `opencode serve`，不设置 `OPENCODE_CONFIG_CONTENT`。
2. `workspaceA/opencode.json` 只配置 DeepSeek-Anthropic。
3. `workspaceB/opencode.json` 只配置火山-OpenAI-MiniMax-M2.7。
4. 分别请求：

```bash
GET /config/providers?directory=<workspaceA>
GET /config/providers?directory=<workspaceB>
```

5. 分别创建 session 并发送 prompt。

结果：

| workspace | 可见 CodeAsk provider | 模型 | 回答 |
|---|---|---|---|
| A | `codeask_51fe0837af001668` | `deepseek-v4-flash` | `workspace A isolated config ok` |
| B | `codeask_dd619536ce9f6bb7` | `MiniMax-M2.7` | `workspace B isolated config ok` |

结论：

- opencode 1.14.48 支持一个 server 按 `directory` 加载不同 workspace 下的配置。
- 这说明 v1.0.4 可以优先设计 shared server：CodeAsk 为每个会话 workspace 写独立 `opencode.json`，请求时始终携带 `directory`。
- 每 workspace 独立 LLM provider 配置已验证通过。

### 5.3 Shared server 下每 workspace 独立 MCP 配置

测试方式：

1. 启动一个 shared `opencode serve`。
2. `workspaceA/opencode.json` 配置本地 MCP server `codeask_a`。
3. `workspaceB/opencode.json` 配置本地 MCP server `codeask_b`。
4. 分别请求：

```bash
GET /mcp?directory=<workspaceA>
GET /mcp?directory=<workspaceB>
```

结果：

```json
{
  "mcpA": {
    "codeask_a": {
      "status": "connected"
    }
  },
  "mcpB": {
    "codeask_b": {
      "status": "connected"
    }
  }
}
```

结论：

- shared server 下 MCP 配置也可以按 workspace `opencode.json` 隔离。
- CodeAsk 可以为每个会话 workspace 写入只属于该会话的 MCP endpoint/token。
- remote StreamableHTTP MCP 后续已补测：URL 指向 MCP 根路径即可，headers 可透传，`tools/list` 和 `tools/call` 可用；工具调用事件可从 `/global/event` 和 message parts 获取。

### 5.4 Shared server 三会话并发 smoke

测试日期：2026-05-13。

测试目的：验证 shared `opencode serve` 不只是串行可用，而是可以同时承载多个 CodeAsk 会话。

测试方式：

1. 从 CodeAsk DB 读取真实启用配置 `火山-OpenAI-MiniMax-M2.7`。
2. 启动一个隔离的 `opencode serve`。
3. 创建 3 个 workspace，每个 workspace 写入自己的 `opencode.json` 和独立 provider id。
4. 每个 workspace 创建一个 opencode session。
5. 并发调用 3 次 `POST /session/:id/prompt_async?directory=<workspace>`。
6. 轮询 `GET /session/:id/message?directory=<workspace>`，等待各自 marker。

结果：

| session | workspace | prompt marker | 结果 |
|---|---|---|---|
| 0 | `workspace_0` | `CodeAsk concurrent 0 ok` | 通过 |
| 1 | `workspace_1` | `CodeAsk concurrent 1 ok` | 通过 |
| 2 | `workspace_2` | `CodeAsk concurrent 2 ok` | 通过 |

结论：

- 一个 shared `opencode serve` 可以同时处理多个 workspace/session 的真实 LLM 请求。
- 每个 session 返回了自己的 marker，没有发现回答串话。
- v1.0.4 可以按 shared server 优先实现；实现上必须保证所有创建、发送、读取、revert、abort 请求都携带 `directory`。

---

## 6. MCP 测试

### 6.1 本地 stdio MCP

测试配置：

```json
{
  "mcp": {
    "codeask_test": {
      "type": "local",
      "command": ["node", "/tmp/codeask-opencode-mcp-local/mcp-server.js"],
      "enabled": true,
      "timeout": 5000
    }
  }
}
```

本地 MCP server 实现了：

- `initialize`
- `tools/list`
- `tools/call`

测试：

```bash
curl -u codeask:phase0 http://127.0.0.1:46125/mcp
```

结果：

```json
{
  "codeask_test": {
    "status": "connected"
  }
}
```

结论：

- opencode 可以通过配置加载 MCP server，并在 `/mcp` 暴露连接状态。
- CodeAsk v1.0.4 的 MCP tools 需要遵守标准 MCP JSON schema，参数必须是 object。
- 本地 MCP 已验证；远程 StreamableHTTP MCP 已用临时 MCP server 补测通过。

### 6.2 源码确认的远程 MCP 行为

源码位置：

- `references/opencode/packages/opencode/src/mcp/index.ts`
- `references/opencode/packages/opencode/src/config/mcp.ts`

确认行为：

| 项 | 行为 |
|---|---|
| remote MCP transport | 优先 `StreamableHTTPClientTransport` |
| fallback | `SSEClientTransport` |
| headers | 支持 `headers` 配置 |
| OAuth | 支持 OAuth；CodeAsk 第一版建议 `oauth: false` + Bearer token |
| tool schema | opencode 会把 MCP tool 转成 AI SDK dynamic tool |
| 参数 | `arguments` 必须是 JSON object |

补充实测：

- `opencode.json` 中 remote MCP URL 指向 MCP 根路径 `/mcp` 即可。
- `headers.Authorization` 和自定义 `X-CodeAsk-Session` 会透传到 MCP server。
- opencode 连接时优先尝试 StreamableHTTP；本次临时 server 收到 `initialize`、`notifications/initialized`、`tools/list` 和 `tools/call`。
- 模型可调用转换后的工具名，例如 `codeask_test_echo_tool`。
- `/global/event` 本次采集 59 条事件，其中包含 `message.part.updated`、`message.part.delta`、`session.status` 和大量 `sync`；前端应折叠 `sync`，工具卡片以 `message.part.updated` 的 tool part 和 message API 快照为准。

CodeAsk 设计影响：

- CodeAsk MCP endpoint 第一版建议走 StreamableHTTP transport。
- `opencode.json` 中 remote MCP URL 配置 CodeAsk MCP 根路径。
- MCP tool schema 要保持简单，避免模型构造失败。

### 6.3 Shared server 下 remote MCP token 隔离

测试日期：2026-05-13。

测试目的：验证 shared `opencode serve` 下，不同 workspace 的 remote MCP URL、headers、session token 不会串。

测试方式：

1. 启动一个 shared `opencode serve`。
2. 启动两个临时 StreamableHTTP MCP server：
   - `codeask_a`，期望 header `Authorization: Bearer token-A`，`X-CodeAsk-Session: sess-A`
   - `codeask_b`，期望 header `Authorization: Bearer token-B`，`X-CodeAsk-Session: sess-B`
3. `workspace_A/opencode.json` 只配置 `codeask_a`。
4. `workspace_B/opencode.json` 只配置 `codeask_b`。
5. 分别请求 `GET /mcp?directory=<workspace_A>` 和 `GET /mcp?directory=<workspace_B>`。

结果：

```json
{
  "mcp_status": {
    "A": { "codeask_a": { "status": "connected" } },
    "B": { "codeask_b": { "status": "connected" } }
  },
  "headers": [
    { "server": "codeask_a", "authorization": "Bearer token-A", "session": "sess-A" },
    { "server": "codeask_b", "authorization": "Bearer token-B", "session": "sess-B" }
  ]
}
```

结论：

- opencode 会按 workspace `opencode.json` 连接对应 remote MCP。
- remote MCP headers 可以透传，并且每个 workspace 的 token/session header 独立。
- CodeAsk 可以用单个 shared opencode server，同时给每个 CodeAsk 会话下发独立 MCP endpoint/token。

---

## 7. ACP 探索记录（v1.0.4 暂不考虑）

### 7.1 初始化

测试：

```bash
printf '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":1,"clientCapabilities":{}}}\n' \
  | opencode acp --cwd /tmp/workspace --hostname 127.0.0.1 --port 0 --pure
```

结果摘要：

```json
{
  "protocolVersion": 1,
  "agentCapabilities": {
    "loadSession": true,
    "mcpCapabilities": {
      "http": true,
      "sse": true
    },
    "promptCapabilities": {
      "embeddedContext": true,
      "image": true
    },
    "sessionCapabilities": {
      "close": {},
      "fork": {},
      "list": {},
      "resume": {}
    }
  },
  "agentInfo": {
    "name": "OpenCode",
    "version": "1.14.48"
  }
}
```

### 7.2 `session/new`

交互式写入：

```json
{"jsonrpc":"2.0","id":2,"method":"session/new","params":{"cwd":"/tmp/codeask-opencode-acp-live/workspace","mcpServers":[]}}
```

返回摘要：

```json
{
  "sessionId": "ses_...",
  "configOptions": [
    { "id": "model", "name": "Model", "type": "select" },
    { "id": "mode", "name": "Session Mode", "type": "select" }
  ],
  "models": {
    "currentModelId": "opencode/big-pickle"
  },
  "modes": {
    "currentModeId": "build"
  }
}
```

随后收到通知：

```json
{
  "method": "session/update",
  "params": {
    "update": {
      "sessionUpdate": "available_commands_update",
      "availableCommands": [
        { "name": "init" },
        { "name": "review" },
        { "name": "compact" }
      ]
    }
  }
}
```

### 7.3 ACP 源码确认

源码位置：

- `references/opencode/packages/opencode/src/cli/cmd/acp.ts`
- `references/opencode/packages/opencode/src/acp/agent.ts`
- `references/opencode/packages/opencode/src/acp/session.ts`

确认行为：

- `opencode acp` 会内部启动 opencode HTTP server。
- ACP 使用 JSON-RPC over stdio，不是 HTTP API。
- ACP session 会映射到内部 opencode session。
- `session/prompt` 最终调用 opencode SDK 的 `session.prompt`。
- `cancel` 最终调用 opencode SDK 的 `session.abort`。
- ACP 支持 MCP server 信息透传，`initialize` 声明了 `http` 与 `sse` MCP 能力。

CodeAsk 设计影响：

| 维度 | HTTP server | ACP |
|---|---|---|
| CodeAsk 实现复杂度 | 低，直接 HTTP + SSE | 中，需要实现 ACP client |
| 事件流 | opencode 原始事件完整 | ACP `session/update` 抽象事件 |
| 前端行动轨迹 | 可保留更完整工具细节 | 需要重新映射 ACP update |
| MCP | opencode 原生读取配置 | ACP 可透传 mcpServers |
| 中断 | `/abort` + `/revert` 可组合 | `cancel` 只对应 abort，回滚仍需额外确认 |
| 多会话 | 可 shared server 或 per-session server | 每个 ACP 进程内部也启动 server，需管理 stdio 子进程 |

阶段结论：

- ACP 是可行方案，但用户已明确 v1.0.4 暂不考虑 ACP。
- v1.0.4 第一版继续走 HTTP server，因为 CodeAsk 需要完整事件审计、SSE 原始事件、SQLite 恢复和后续扩展停止回滚控制。
- ACP 保留为后续替代接入方案，尤其适合未来做“CodeAsk 作为 ACP Client”或接入其它 ACP agent。

---

## 8. 会话恢复、回滚与中断

### 8.1 SQLite 恢复

测试步骤：

1. 使用真实 MiniMax 配置创建 session 并完成一次回答。
2. 停止 opencode server。
3. 使用同一个 `XDG_DATA_HOME` / workspace 重新启动 opencode server。
4. 查询：

```bash
curl -u codeask:phase0 \
  'http://127.0.0.1:46127/session?directory=/tmp/codeask-opencode-http-real-k88j5hi0/workspace'
```

结果：

- 原 session 可恢复。
- session title 已由 opencode 更新为 `CodeAsk smoke确认`。
- session 记录包含原 `model` 和 `providerID`。

结论：

- opencode session history 存在 SQLite 中，可以跨进程恢复。
- CodeAsk 每个会话必须保存 opencode 数据目录、workspace、server 版本、provider hash。
- 补充恢复测试已验证：同一数据目录和 workspace 下，opencode server 换端口重启后仍可读取原 session message，并可继续发送第二轮 prompt。
- 实现不要假设重启后必须复用旧端口。首次尝试同端口立即重启曾出现 opencode serve 异常退出；CodeAsk 应允许端口重新分配，并在 `external_agent_sessions` 中更新当前端口和进程信息。

### 8.2 Revert / Unrevert

测试：

```bash
POST /session/:id/revert?directory=<workspace>
{ "messageID": "<user-message-id>" }

POST /session/:id/unrevert?directory=<workspace>
```

观察：

- `revert` 返回 session info，并包含：

```json
{
  "revert": {
    "messageID": "msg_..."
  }
}
```

- `unrevert` 返回 session info，`revert` 字段被清除。

结论：

- opencode 1.14.48 的 revert/unrevert API 可用。
- CodeAsk 停止生成时不能只调用 `abort`，还需要在确认本轮 user message/part 后调用 `revert`，否则可能留下半轮上下文。

### 8.3 Abort + Revert 实测

源码确认：

- `POST /session/:id/abort` 调用 `promptSvc.cancel(sessionID)`。
- ACP `cancel` 也调用 SDK `session.abort`。

实测步骤：

1. 发送一个长输出 prompt。
2. 0.8 秒后调用 `POST /session/:id/abort`。
3. 读取 message 列表，确认 assistant message 为 `MessageAbortedError`。
4. 使用本轮 user message id 调用 `POST /session/:id/revert`。
5. 再发送新 prompt：`请只回答：CodeAsk abort cleanup ok`。

结果：

```json
{
  "abort_status": 200,
  "assistant_before_revert": [
    {
      "error": {
        "name": "MessageAbortedError",
        "data": {
          "message": "Aborted"
        }
      },
      "parts": []
    }
  ],
  "revert_result": {
    "messageID": "msg_..."
  },
  "followup_text": "CodeAsk abort cleanup ok",
  "final_message_roles": ["user", "assistant"]
}
```

结论：

- `abort` 可以中断正在生成的 turn。
- 仅 `abort` 会留下 aborted assistant message；CodeAsk 必须随后按本轮 user message 调用 `revert`。
- `revert` 后再发送新 prompt，opencode 会清理被 revert 的消息范围，后续上下文干净。

### 8.4 Permission 拒绝实测

配置：

```json
{
  "permission": {
    "bash": "deny",
    "edit": "deny",
    "write": "deny",
    "read": "allow",
    "grep": "allow"
  }
}
```

prompt：

```text
请调用 bash 工具执行 echo CODEASK_PERMISSION_TEST，然后告诉我执行结果。
```

结果：

```json
{
  "tools": [
    {
      "tool": "invalid",
      "state": {
        "status": "completed",
        "input": {
          "tool": "Bash",
          "error": "Model tried to call unavailable tool 'Bash'. Available tools: glob, grep, invalid, question, read, skill, task, todowrite, webfetch."
        }
      }
    }
  ],
  "assistant_text": "抱歉，当前环境中无法执行 bash 命令。"
}
```

结论：

- deny `bash` 后，Bash 工具不会进入可用工具列表。
- 模型尝试调用 `Bash` 时不会卡死在 permission prompt，而是形成 `invalid` tool 结果。
- 前端行动轨迹需要展示这种“模型尝试了不可用工具”的事件，否则用户会误以为工具静默失败。


---

## 9. 当前结论与实现建议

### 9.1 第一版推荐路径

v1.0.4 第一版建议：

1. 使用 opencode HTTP server 作为主接入方式。
2. 使用 `/global/event` 作为主事件源。
3. 使用 `prompt_async` 发送消息。
4. 使用 opencode SQLite/session API 作为恢复和补偿读取来源。
5. 优先采用 shared server：每个 CodeAsk 会话有独立 workspace 和独立 `opencode.json`，所有 opencode HTTP 请求携带 `directory`。
6. MCP 走 opencode remote MCP，CodeAsk 提供 StreamableHTTP endpoint。
7. ACP 暂不纳入 v1.0.4。

### 9.2 必须修正或补充的设计点

| 设计点 | 结论 |
|---|---|
| Message API 路径 | 使用 `/session/:id/message`，不是 `/messages` |
| workspace 路由 | 所有 session/message/revert 请求必须带 directory 或等价 header |
| provider 映射 | 不能假设 anthropic 都能走 `@ai-sdk/anthropic`；火山 Anthropic 已失败 |
| Anthropic profile | 候选必须少量且通用；当前优先 `anthropic-compatible-v1-bearer`，因为真实 Anthropic 配置均通过；`anthropic-default` 仅作 fallback |
| provider profile 缓存 | 不进入 v1.0.4 第一版主线；先用当前已实测通过的少量 profile 打通流程，成功 profile 持久化和 smoke 结果缓存列为遗留增强项 |
| 真实配置测试 | v1.0.4 必须保留“opencode provider smoke test”入口 |
| reasoning | opencode 已结构化保存 reasoning part，前端应基于结构化事件展示，不做 `<think>` 字符串过滤 |
| 事件流 | 需要折叠 `sync`、高频 `message.part.updated`，否则行动轨迹会噪声过大 |
| abort/revert | 停止生成的深度上下文回滚需要组合 abort + revert；此项作为遗留增强，不阻塞主功能 |
| shared server | 已实测可行；实现必须始终携带 `directory` |
| Wiki 挂载 | `workspace/wiki` 使用 symlink 可被 opencode read；删除 symlink 不会删除真实 Wiki，后续可恢复入口 |
| worktree | 现有 WorktreeManager 可从数据目录 bare repo 为 session 创建/清理独立 worktree，opencode 只需读取暴露后的 workspace 相对路径 |
| ACP | 暂不纳入 v1.0.4 |

### 9.3 后续待测清单

- [x] remote StreamableHTTP MCP 最小连通测试：opencode 可连接 URL 根路径、传递 headers、完成 `tools/list` 和 `tools/call`。
- [ ] 停止生成主功能：先实现停止输出和状态清理；`abort + revert` 深度上下文回滚单独作为遗留增强验证。
- [x] 一个 opencode server 多 session、多 workspace、多 LLM 配置隔离测试。
- [x] shared server 下每 workspace 独立 MCP server、MCP token 和工具列表隔离测试。
- [x] MCP tool 调用事件在 `/global/event` 和 message parts 中的样本。
- [x] 权限规则中 deny Bash/Edit/Write 时，模型触发对应工具后的事件和错误形态。
- [x] 火山 Anthropic 配置失败的兼容策略：通过 `anthropic-compatible-v1-bearer` profile 实测通过。
- [x] Wiki symlink 被删除后真实 Wiki 文件仍存在，重新创建 symlink 后可恢复读取。
- [x] 使用真实 repo `e35077cf009f4fdc` 验证现有 WorktreeManager 可创建并清理 session worktree。
- [x] shared server 重启恢复测试：同一数据目录和 workspace 下，换端口重启后可读取原 session message，并继续第二轮 prompt。
