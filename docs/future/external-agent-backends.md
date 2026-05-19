# 外部 Agent Backend：Claude Code 与 opencode

> 状态：Draft
> 版本归属：待定
> 主题：让 CodeAsk 保留产品层、数据层和会话工作台，同时接入成熟 coding agent 作为可选执行引擎。

## 1. 背景

CodeAsk 当前后端 Agent Runtime 是自研实现。它的优势是和 CodeAsk 的特性、Wiki、问题报告、附件、代码仓库和行动轨迹天然集成；不足是代码 Agent 能力、上下文压缩、工具编排、代码仓库理解等成熟度仍需要长期迭代。

未来可以引入成熟外部 coding agent 作为 CodeAsk 的可选 Agent Backend：

- **Claude Code**：适合使用 Anthropic / Claude 系列模型的会话，Agent 能力成熟，代码工具、上下文压缩和任务推进能力强。
- **opencode**：适合使用 OpenAI、OpenAI-compatible、第三方网关、本地模型等配置的会话。opencode 是开源 coding agent，官方文档说明其支持 75+ LLM providers，并支持 OpenAI-compatible provider 与自定义 `baseURL`。

目标不是让 CodeAsk 变成 Claude Code 或 opencode 的壳，而是：

> CodeAsk 负责研发知识和问题定位工作台，外部 coding agent 负责成熟的 Agent 执行能力。

## 2. 核心目标

1. CodeAsk 会话仍然是用户主入口。
2. 每个 CodeAsk 会话可以拥有一个独立的外部 agent 会话目录。
3. 外部 agent 的 API key 通过环境变量或会话级配置注入，避免多个会话共享同一上下文。
4. CodeAsk 在会话层只做代理适配：
   - 上下文注入
   - 会话目录创建
   - 流式事件转发
   - 工具事件映射
   - 中断与回滚
   - 结果持久化
   - 行动轨迹审计
5. CodeAsk 自己的能力仍然保留：
   - 特性
   - Wiki
   - 问题报告
   - 会话附件
   - 用户设置
   - LLM 配置
   - 报告生成和绑定规则
   - 前端工作台

## 3. 非目标

当前规划不包含：

- 不在第一版实现代码写入、自动修改、自动提交或 PR。
- 不让外部 agent 直接成为 CodeAsk 数据库事实源。
- 不让外部 agent 绕过 CodeAsk 的会话、权限、审计和报告规则。
- 不默认开放任意 Bash / shell 写操作。
- 不要求 Claude Code 支持 OpenAI-compatible 模型。
- 不要求 opencode 完全复刻 Claude Code 行为。
- 不把 ACP 作为第一版必须协议；第一版优先走各自可用的 SDK、CLI 或 headless 通道。

## 4. Agent Backend 抽象

后端应新增统一抽象：

```text
AgentBackend
├── NativeCodeAskBackend
├── ClaudeCodeBackend
└── OpenCodeBackend
```

统一接口：

```python
class AgentBackend(Protocol):
    async def run(
        self,
        *,
        session_id: str,
        turn_id: str,
        subject_id: str,
        user_message: str,
        context: AgentBackendContext,
    ) -> AsyncIterator[ChatRuntimeEvent]:
        ...
```

前端仍消费 CodeAsk 标准事件：

```text
retrieval_context
text_delta
tool_call
tool_result
confirmation_required
error
done
```

外部 agent backend 负责把 Claude Code / opencode 的原始事件转换成 CodeAsk 标准事件。

## 5. 每会话独立运行目录

每个 CodeAsk 会话创建独立外部 agent 目录：

```text
<CODEASK_DATA_DIR>/
└── agent_sessions/
    ├── claude_code/
    │   └── <session_id>/
    │       ├── home/
    │       ├── workspace/
    │       ├── logs/
    │       │   └── stream.jsonl
    │       └── state.json
    └── opencode/
        └── <session_id>/
            ├── home/
            ├── workspace/
            ├── config/
            │   └── opencode.json
            ├── logs/
            │   └── stream.jsonl
            └── state.json
```

目录职责：

| 路径 | 作用 |
|---|---|
| `home/` | 隔离外部 agent 的 HOME、配置、认证缓存和会话状态 |
| `workspace/` | 当前会话可访问的工作目录，通常指向 CodeAsk 管理的 repo worktree 或只读聚合目录 |
| `config/` | opencode 等工具需要的会话级 provider 配置 |
| `logs/stream.jsonl` | 原始外部 agent 流式事件归档 |
| `state.json` | CodeAsk session 与外部 agent session 的映射、启动参数、工具权限和模型配置摘要 |

## 6. 模型配置路由

CodeAsk 已有 LLM 配置，需要根据配置协议选择外部 agent backend。

建议第一版规则：

| CodeAsk LLM 配置 | 推荐 Backend | 说明 |
|---|---|---|
| `anthropic` | Claude Code | 通过 `ANTHROPIC_API_KEY` 注入，优先使用 Claude Code 成熟 Agent 能力 |
| `openai` | opencode | 通过 opencode provider 配置和环境变量注入 |
| `openai_compatible` | opencode | 通过 `baseURL` 和 provider config 适配第三方网关或私有模型 |
| 其它未来协议 | 待定 | 后续按 agent 支持情况扩展 |

关键原则：

1. Claude Code backend 不强行适配 OpenAI-compatible 模型。
2. OpenAI / OpenAI-compatible 模型优先走 opencode backend。
3. 如果用户有个人 LLM 配置，优先使用用户配置。
4. 如果用户没有个人配置，再使用可用全局配置池。
5. 如果当前 backend 不支持选中的 LLM 配置，应明确报错或回退到可用 backend，不能静默换模型。

## 7. Claude Code Backend

Claude Code backend 适用于 Anthropic / Claude 模型。

建议运行方式：

- 优先评估 Claude Code SDK / headless mode。
- 每轮调用前设置独立环境变量：

```text
HOME=<CODEASK_DATA_DIR>/agent_sessions/claude_code/<session_id>/home
ANTHROPIC_API_KEY=<decrypted key>
```

可选能力：

- `cwd` 指向当前会话 workspace。
- 通过 allowed tools 限制只读能力。
- 使用 AbortController 或子进程 kill 实现中断。
- 原始事件写入 `logs/stream.jsonl`。

第一版建议只开放只读工具：

```text
Read
Grep
Glob
LS
必要的 CodeAsk MCP tools
```

暂不开放：

```text
Write
Edit
MultiEdit
任意 Bash
git commit / push
```

## 8. opencode Backend

opencode backend 适用于 OpenAI、OpenAI-compatible、第三方网关和本地模型。

选择 opencode 的原因：

- opencode 是开源 coding agent。
- 官方文档说明它支持大量 LLM provider。
- 官方 provider 文档说明可配置 `baseURL`，适合 OpenAI-compatible 网关、私有模型服务和模型代理。
- 它可以补上 Claude Code 对非 Anthropic provider 的限制。

建议运行方式：

```text
HOME=<CODEASK_DATA_DIR>/agent_sessions/opencode/sessions/<session_id>/home
OPENCODE_CONFIG_DIR=<CODEASK_DATA_DIR>/agent_sessions/opencode/sessions/<session_id>/config
OPENAI_API_KEY=<decrypted key>
```

会话级 `opencode.json` 由 CodeAsk 生成：

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "codeask-openai-compatible": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "CodeAsk OpenAI Compatible",
      "options": {
        "baseURL": "https://example.com/v1"
      },
      "models": {
        "model-name": {}
      }
    }
  }
}
```

具体配置字段需要以后续 opencode 当前版本官方配置 schema 为准。本文只定义 CodeAsk 的适配方向。

第一版同样只开放只读工具和 CodeAsk MCP tools，不开放自动代码修改。

## 9. CodeAsk MCP Tools 与文件上下文

外部 agent 接入时，MCP 只适合承载必须由 CodeAsk 代理的元数据、权限和环境准备能力。能够以文件形式暴露的知识内容，优先作为 workspace 文件目录提供给外部 agent，让其使用原生 `glob/grep/read` 能力自主判断，避免 CodeAsk 再封装一层不稳定的检索/读取工具。

v1.0.4 opencode 路线的第一批 MCP tools：

```text
list_features
get_feature_info
list_feature_repos
prepare_worktree
bind_session_features
list_session_attachments
read_session_attachment
```

Wiki 和问题报告作为文件目录挂载：

```text
./wiki/<feature_slug>/knowledge-base/
./wiki/<feature_slug>/problem-reports/verified/
./wiki/<feature_slug>/problem-reports/drafts/
```

已验证问题报告仅作参考，只有报错、场景、根因完全一致时，才能判断为同一问题；草稿报告只作为弱背景。未来如果引入 RAG 服务，可以新增独立 MCP 能力，但不再恢复旧的 opencode report search/read 封装作为主路径。

后续可增加：

```text
prepare_problem_report
list_feature_repos
get_feature_context
search_codeask_sources
```

原则：

- MCP tools 只提供候选事实和可回源引用。
- 不在 MCP tools 中硬编码“下一步应该查代码”。
- 是否使用 Wiki、报告、附件或代码，仍由外部 agent 模型自行判断。
- MCP tools 的调用结果必须回写 CodeAsk `agent_traces`，便于前端展示和审计。

## 10. 会话中断与回滚

外部 agent backend 必须遵守 CodeAsk 现有会话语义：

1. 用户点击停止后，终止外部 agent 当前 turn。
2. 删除本轮未完成的 assistant turn。
3. 删除本轮新增的可见行动轨迹。
4. 原始 `stream.jsonl` 可保留用于后端审计，但不能作为下一轮模型上下文继续使用。
5. 下一轮必须从 CodeAsk 已持久化的 session turns 和 summaries 重建上下文。

不能出现：

- 前端看似回滚，外部 agent 下一轮仍记得被停止内容。
- CodeAsk DB 没有记录，但外部 agent session 继续沿用未完成上下文。
- 停止后行动轨迹残留在前端。

## 11. 行动轨迹映射

外部 agent 事件需要映射到 CodeAsk trace：

| 外部事件 | CodeAsk trace |
|---|---|
| assistant text delta | 不单独写 trace，只进入消息流 |
| tool start | `tool_call` |
| tool result | `tool_result` |
| permission request | `confirmation_required` |
| context compact | `context_compaction` |
| agent error | `error` |
| agent done | `done` |

每条 trace metadata 至少包含：

```json
{
  "backend": "claude_code | opencode",
  "external_event_type": "tool_result",
  "raw_event_ref": "agent_sessions/.../logs/stream.jsonl#42"
}
```

## 12. 权限与安全边界

第一版必须保守：

1. 默认只读。
2. 不允许外部 agent 访问整个服务器文件系统。
3. 工作目录必须限制在 CodeAsk 为当前会话准备的 workspace。
4. API key 只通过子进程环境变量或 SDK 参数注入，不写入日志、不返回前端。
5. 不共享真实用户 HOME。
6. 不共享不同 CodeAsk session 的外部 agent home。
7. 不允许外部 agent 绕过 CodeAsk 直接读取其它会话附件。
8. 所有工具调用必须进入行动轨迹或审计日志。

后续如开放写操作，需要单独版本设计：

- worktree 隔离
- diff 预览
- 用户确认
- 回滚
- commit / patch 管理
- 权限审计

## 13. 数据模型草案

新增表：

```text
external_agent_sessions
```

字段：

```text
id
session_id
backend_type              # claude_code | opencode
external_session_key
session_dir
cwd
home_dir
status                   # active | stopped | failed | archived
config_json
created_at
updated_at
```

可选新增：

```text
external_agent_events
```

如果原始事件只落文件，DB 可只保留 `raw_event_ref`。

## 14. 后端模块边界

建议新增：

```text
src/codeask/agent/backends/
├── __init__.py
├── protocol.py
├── native_backend.py
├── external_session_store.py
├── event_mapping.py
├── claude_code/
│   ├── backend.py
│   ├── runner.py
│   └── config.py
└── opencode/
    ├── backend.py
    ├── runner.py
    └── config.py
```

不要把外部 agent 逻辑塞进现有 `chat_runtime/runtime.py`。

`chat_runtime` 可以继续作为 native backend；外部 backend 应通过统一 `AgentBackend` 接口接入 session API。

## 15. 候选落地顺序

### 阶段 1：文档和实验

- 明确 Claude Code backend 和 opencode backend 的边界。
- 在本地用一个会话目录验证：
  - Claude Code 可通过 env key 启动。
  - opencode 可通过 OpenAI-compatible config 启动。
  - 两者均能流式输出。
  - 两者均可中断。
  - 两者均可限制工作目录。

### 阶段 2：CodeAsk MCP Server

- 先让外部 agent 能读取 CodeAsk Wiki、报告、附件和特性。
- MCP tools 只读。
- MCP 调用写入 CodeAsk trace。

### 阶段 3：Claude Code Backend

- 支持 Anthropic 配置。
- 支持每会话目录。
- 支持流式转发。
- 支持行动轨迹映射。
- 支持中断回滚。

### 阶段 4：opencode Backend

- 支持 OpenAI / OpenAI-compatible 配置。
- 生成会话级 opencode config。
- 支持流式转发、行动轨迹映射和中断回滚。

### 阶段 5：统一前端开关

- 管理员可配置默认 Agent Backend。
- 用户可选择个人默认 Agent Backend。
- 会话可显示当前 backend。
- 失败时给出明确错误提示。

## 16. 待验证问题

1. Claude Code SDK / headless stream 是否能稳定暴露工具事件和 compact 事件。
2. opencode 当前版本的可编程接口是否适合长期嵌入，还是应先通过 CLI / JSON stream 适配。
3. opencode 对 OpenAI-compatible provider 的配置 schema 在目标版本中是否稳定。
4. 两个外部 agent 是否都能可靠限制 cwd 和 HOME。
5. 停止生成后，外部 agent 是否有可控的上下文回滚机制。
6. 外部 agent 原始事件是否足够映射到 CodeAsk 当前行动轨迹。
7. 多用户并发时进程和资源限制如何设计。
8. API key 注入是否应走用户个人配置、全局配置，还是会话临时配置。

## 17. 参考

- Claude Code SDK 文档：`https://docs.anthropic.com/en/docs/claude-code/sdk`
- Claude Code TypeScript SDK 文档：`https://docs.anthropic.com/es/docs/claude-code/sdk/sdk-typescript`
- Claude Code MCP in SDK 文档：`https://docs.anthropic.com/en/docs/claude-code/sdk/sdk-mcp`
- opencode GitHub：`https://github.com/anomalyco/opencode`
- opencode 官方站点：`https://opencode.ai/`
- opencode provider 文档：`https://opencode.ai/docs/providers`
