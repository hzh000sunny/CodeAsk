# CodeAsk × OpenCode 对接方案

> 状态：设计前史；v1.0.4 已正式启动，当前版本契约以 `docs/v1.0.4/` 为准
> 关联文档：[外部 Agent Backend：Claude Code 与 opencode](./external-agent-backends.md)
> 前置阅读：本文为早期方案存档，若与 v1.0.4 文档冲突，以 `docs/v1.0.4/` 为准。
> 本文聚焦：**OpenCode 兼容实现的设计前史——状态机、API 对接、事件映射、代码级流程。**

## 2026-05-12 v1.0.4 启动后的收敛结论

本文保留为设计前史和实现参考。v1.0.4 已经进入版本目录，最新契约见：

- `docs/v1.0.4/prd/opencode-backend.md`
- `docs/v1.0.4/design/opencode-backend.md`
- `docs/v1.0.4/plans/opencode-backend.md`
- `docs/v1.0.4/specs/opencode-interaction-flow.md`

相对本文早期草案，v1.0.4 已收敛为以下原则：

1. **新会话不回退 CodeAsk native Agent**。opencode 不可用时明确报错，不静默切回旧 runtime。
2. **Wiki 主路径是文件系统 grep/read**。CodeAsk 维护持久化 Wiki 工作区，特性为一级目录，结构与现有特性 Wiki 树一致；会话通过 symlink / bind mount 等零复制方式访问 `workspace/wiki`。
3. **v1.0.4 不复制整份 Wiki**。不采用每会话 `cp`；目录硬链接也不作为第一版方案。
4. **MCP tools 面向 opencode 重写**。不复用旧 Agent tool registry；工具参数必须简单、稳定、JSON object 化。
5. **opencode server 形态需要 Phase 0 spike 决定**。v1.0.4 Phase 0 已证明 opencode 1.14.48 的 shared server 可以按 `directory` 同时承载多个 session，并且每个 workspace 可使用独立 `opencode.json` 隔离 provider 配置、remote MCP endpoint、MCP token 和工具列表。
6. **特性和仓库绑定不是硬前置条件**。CodeAsk 把特性、Wiki、仓库事实提供给模型，由模型在多轮上下文中判断；用户显式指定仓库时，即使没有匹配特性，也允许准备 worktree 并审计。
7. **前端 Agent 行动轨迹基于 opencode 事件重设计**。不保留旧 CodeAsk Agent 阶段流，除非某些 UI 组件复用确有必要。
8. **目标 opencode 版本必须声明并实测**。用户后续提供版本后，v1.0.4 的 API、MCP、permission、event stream 都以该版本 spike 为准；`abort + revert` 深度回滚作为遗留增强项。
9. **实现模块独立**。v1.0.4 不再采用本文早期的通用 `AgentBackend` 抽象；opencode 兼容实现放在 `src/codeask/agent/opencode_compat/`，不抽公共 backend，不复用旧 native Agent runtime。

---

## 目录

1. [架构全景](#1-架构全景)
2. [OpenCode 侧能力盘点](#2-opencode-侧能力盘点)
3. [状态机设计](#3-状态机设计)
4. [对接流程详解](#4-对接流程详解)
5. [事件映射表](#5-事件映射表)
6. [知识上下文注入](#6-知识上下文注入)
7. [会话生命周期](#7-会话生命周期)
8. [错误处理](#8-错误处理)
9. [实现要点](#9-实现要点)
10. [待验证项](#10-待验证项)

---

## 1. 架构全景

### 1.1 角色分工

```
┌──────────────────────────────────────────────────────────────┐
│                     CodeAsk (Python)                          │
│                                                              │
│  ┌──────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │ 知识检索   │  │ 上下文拼装    │  │ AgentBackend 路由      │ │
│  │ Wiki/RAG  │  │              │  │ Native | Claude | Open  │ │
│  └─────┬─────┘  └──────┬───────┘  └───────────┬────────────┘ │
│        │               │                      │               │
│        │    CodeAsk 知识上下文                  │               │
│        ▼               ▼                      ▼               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │              OpenCodeBackend (Python)                    │ │
│  │                                                         │ │
│  │  ① 管理 OpenCode 子进程生命周期                           │ │
│  │  ② 生成会话级 opencode.json 配置                          │ │
│  │  ③ 调用 OpenCode HTTP API (session + message)            │ │
│  │  ④ 订阅 OpenCode SSE 事件流                               │ │
│  │  ⑤ 将 OpenCode 事件映射为 CodeAsk ChatRuntimeEvent        │ │
│  │  ⑥ 处理中断 / 错误 / 回滚                                  │ │
│  └──────────────────────────┬──────────────────────────────┘ │
│                             │                                 │
│               HTTP (localhost:随机端口)                        │
│               Basic Auth / SSE                                │
└─────────────────────────────┼────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                    OpenCode (TypeScript/Bun)                   │
│                                                              │
│  HTTP API Server (Effect HttpServer)                         │
│  ├── POST /session            创建会话                        │
│  ├── POST /session/:id/message  发送消息 (Agent 循环)         │
│  ├── GET  /event              SSE 事件流                      │
│  ├── POST /session/:id/abort   中断会话                       │
│  └── ...                                                     │
│                                                              │
│  Agent 循环                                                   │
│  ├── LLM 调用 (22+ 提供商)                                    │
│  ├── 工具执行 (Read/Write/Edit/Grep/Glob/Shell/...)          │
│  ├── 上下文压缩 (Compaction)                                   │
│  └── 子代理 (Task/Explore/Plan)                               │
└──────────────────────────────────────────────────────────────┘
```

### 1.2 关键边界

| 边界 | CodeAsk 职责 | OpenCode 职责 |
|------|-------------|--------------|
| 知识检索 | Wiki 搜索、RAG、报告搜索、特性解析 | 不感知 |
| 上下文拼装 | 将检索结果格式化为 Markdown，嵌入 system prompt | 接收并使用 |
| Agent 循环 | 不参与 | 全权负责 LLM 调用 + 工具执行 |
| 工具调用 | 不提供代码工具 | Read/Write/Edit/Grep/Glob/Shell 等 |
| 代码仓库 | 管理 worktree、提供仓库路径 | 在指定目录下操作 |
| 会话持久化 | CodeAsk DB (SessionTurn) | OpenCode SQLite (内部) |
| 事件审计 | 全部 trace 写入 agent_traces | 原始事件写入 stream.jsonl |

---

## 2. OpenCode 侧能力盘点

### 2.1 OpenCode Server 模式

OpenCode 支持以 HTTP Server 模式运行，对外暴露 REST API + SSE 事件流：

```bash
opencode serve --port 0 --hostname 127.0.0.1
# --port 0 表示自动分配端口（优先 4096，其次随机）
# --hostname 127.0.0.1 仅本地访问
```

认证方式（可选，建议启用）：
```bash
export OPENCODE_SERVER_PASSWORD=<random-password>
# 请求时携带: Authorization: Basic base64(opencode:<password>)
```

### 2.2 核心 API 端点

完整端点列表参见 `external-agent-backends.md` 第 8 节。以下是 CodeAsk 对接必需的最小集合：

| 方法 | 路径 | 用途 | 关键 |
|------|------|------|------|
| `POST` | `/session` | 创建会话 | 可指定 agent、model、permission |
| `POST` | `/session/:id/message` | 发送消息，触发 Agent 循环 | **同步返回**最终 assistant message |
| `GET` | `/event` | SSE 事件流 | 实时接收 text_delta、tool_call、状态变更 |
| `POST` | `/session/:id/abort` | 中断 | 终止正在执行的 Agent 循环 |
| `DELETE` | `/session/:id` | 删除会话 | 清理 |

### 2.3 发送消息的 Payload

```typescript
// POST /session/:id/message 的请求体
{
  messageID?: string,           // 可选，不传则自动生成
  agent?: string,               // "general" | "build" | "plan" | "explore"
  model?: {
    providerID: string,         // 如 "openai", "anthropic"
    modelID: string             // 如 "gpt-4o", "claude-sonnet-4-6"
  },
  system?: string,              // ★ 系统提示词 —— CodeAsk 知识上下文注入点
  parts: [                      // ★ 消息内容 —— 多 Part 结构
    {
      type: "text",
      text: "用户问题 + 知识检索结果"
    }
  ]
}
```

### 2.4 SSE 事件流

`GET /event` 返回 `text/event-stream`，关键事件类型：

| 事件 type | properties 关键字段 | 含义 |
|-----------|-------------------|------|
| `session.status` | `sessionID, status: { type: "busy"\|"idle"\|"retry" }` | 会话状态变更 |
| `message.updated` | 完整 MessageV2.WithParts | 消息/Part 创建或更新 |
| `message.part.delta` | `sessionID, messageID, partID, delta: string` | **流式文本增量** |
| `session.error` | `sessionID, error: { name, data }` | 错误 |
| `session.diff` | `sessionID, diff: FileDiff[]` | 文件变更 |

### 2.5 消息的返回

`POST /session/:id/message` 是**同步**端点——请求会阻塞直到 Agent 循环完成，然后返回最终的 `MessageV2.WithParts`：

```typescript
// 返回结构
{
  info: {
    id: "msg01...",
    sessionID: "ses01...",
    role: "assistant",
    cost: 0.0123,
    tokens: { input: 1500, output: 800, reasoning: 0, cache: { read: 0, write: 0 } },
    modelID: "gpt-4o",
    providerID: "openai",
    agent: "general",
    finish: "stop"             // "stop" | "tool-calls" | "length" | "error"
  },
  parts: [
    { id: "prt01...", type: "step-start" },
    { id: "prt02...", type: "text", text: "这是流式文本的完整内容..." },
    { id: "prt03...", type: "tool", callID: "...", tool: "read",
      state: { status: "completed", input: {...}, output: "...", title: "Read foo.ts" } },
    { id: "prt04...", type: "step-finish", reason: "stop", cost: 0.0123 }
  ]
}
```

**关键点**：虽然响应是同步返回的，但**实时流式增量**通过 SSE (`/event`) 推送。所以 CodeAsk 的对接策略是：

1. 先订阅 `GET /event` (SSE)，开始接收事件
2. 再调用 `POST /session/:id/message` (同步)，触发 Agent 循环
3. 在 SSE 流中消费 `message.part.delta` 做流式展示
4. 当收到 `session.status { type: "idle" }` 时，Agent 循环已结束
5. 此时 `POST /session/:id/message` 的同步响应也返回了，可做最终校验

---

## 3. 状态机设计

### 3.1 CodeAsk 侧：OpenCodeBackend 状态机

```
                    ┌─────────────┐
                    │   IDLE      │  ← 初始状态 / 一轮完成后回到这里
                    └──────┬──────┘
                           │ run() 被调用
                           ▼
                    ┌─────────────┐
                    │ PREPARING   │  创建会话目录、生成 opencode.json、
                    │             │  启动 opencode serve 子进程、创建 Session
                    └──────┬──────┘
                           │
                           ▼
                    ┌─────────────┐
                    │ SUBSCRIBING │  建立 SSE 连接，开始接收事件
                    └──────┬──────┘
                           │
                           ▼
                    ┌─────────────┐
                    │  STREAMING  │  POST /session/:id/message 已发送
                    │             │  正在消费 SSE 事件，映射为 CodeAsk 事件
                    │             │  ← 可能被 abort() 中断
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │  DONE    │ │ ABORTING │ │  ERROR   │
        │ 正常完成  │ │ 用户中断  │ │ 异常错误  │
        └────┬─────┘ └────┬─────┘ └────┬─────┘
             │            │            │
             └────────────┼────────────┘
                          │ 清理 → IDLE
                          ▼
                    ┌─────────────┐
                    │   IDLE      │
                    └─────────────┘
```

### 3.2 OpenCode 侧：Session 状态

OpenCode 的 Session 状态（可从 SSE 的 `session.status` 事件获取）：

```
                    ┌──────────┐
                    │   IDLE   │  ← 空闲，可接收新消息
                    └─────┬────┘
                          │ POST /session/:id/message
                          ▼
                    ┌──────────┐
                    │   BUSY   │  Agent 循环执行中
                    │          │  LLM 调用 ⇄ 工具执行 ⇄ 子代理
                    └─────┬────┘
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │   IDLE   │ │  RETRY   │ │ (error)  │
        │  正常完成  │ │ 限流重试  │ │ 异常终止  │
        └──────────┘ └────┬─────┘ └──────────┘
                          │ 重试完成后
                          ▼
                    ┌──────────┐
                    │   IDLE   │
                    └──────────┘
```

### 3.3 双状态机协同时序

```
CodeAsk Backend              OpenCode HTTP API              OpenCode Agent
─────┬──────                 ──────┬──────                 ──────┬──────
     │                             │                             │
     │  IDLE                       │                             │
     │                             │                             │
     │  ① PREPARING                │                             │
     │  ─── 生成 opencode.json     │                             │
     │  ─── spawn opencode serve  │                             │
     │  ─── POST /session  ──────►│  创建 Session ──────────────►│
     │  ◄──── Session.Info ───────│                             │
     │                             │                             │
     │  ② SUBSCRIBING              │                             │
     │  ─── GET /event (SSE) ────►│  建立 SSE 连接               │
     │  ◄── server.connected ─────│                             │
     │                             │                             │
     │  ③ STREAMING                │                             │
     │  ─── POST /session/:id/    │                             │
     │       message ────────────►│  创建 User Message ─────────►│
     │                             │                             │  IDLE
     │                             │  session.status: busy ─────►│
     │  ◄── session.status ───────│                             │  BUSY
     │                             │                             │
     │                             │                    ┌────────┤  LLM 调用
     │                             │                    │        │
     │  ◄── message.part.delta ───│◄───────────────────┘        │
     │      (text_delta)          │  text token by token        │
     │                             │                             │
     │  ◄── message.updated ──────│◄── tool call detected       │
     │      (tool_call)           │                             │  Tool 执行
     │                             │                             │
     │  ◄── message.updated ──────│◄── tool completed           │
     │      (tool_result)         │                             │
     │                             │                             │
     │  ◄── message.part.delta ───│◄── 继续文本生成             │
     │                             │                             │
     │                    ┌────────┤ 循环直到 finish≠"tool-calls"│
     │                    │        │                             │
     │  ◄── session.status ───────│◄── Agent 循环结束           │  IDLE
     │      (idle)                │                             │
     │                             │                             │
     │  ④ DONE                     │                             │
     │  ─── 收集最终 Message       │                             │
     │  ─── 持久化 CodeAsk Trace   │                             │
     │  ─── 回到 IDLE              │                             │
     │                             │                             │
```

### 3.4 中断流程

```
CodeAsk Backend              OpenCode HTTP API
─────┬──────                 ──────┬──────
     │                             │
     │  STREAMING                  │  BUSY
     │                             │
     │  用户点击停止                │
     │                             │
     │  ① ABORTING                 │
     │  ─── AbortController        │
     │       .abort()              │
     │  ─── POST /session/:id/    │
     │       abort ───────────────►│  终止 Agent 循环
     │                             │  session.status: idle
     │                             │
     │  ② 清理                      │
     │  ─── 关闭 SSE                │
     │  ─── 删除本 turn trace       │
     │  ─── 不持久化本轮消息         │
     │  ─── 回到 IDLE               │
     │                             │
     │  下一轮：用上一轮的          │
     │  Session 继续                │
```

**重要**：中断后不删除 OpenCode Session。下一轮消息继续使用同一个 Session ID，OpenCode 内部保留之前的对话历史。这保证了 OpenCode 能看到完整上下文。

---

## 4. 对接流程详解

### 4.1 第一步：启动 OpenCode Server

CodeAsk 在需要时（首次使用 opencode 兼容模块，或 shared server 不存在/已退出）启动一个全局或会话级的 opencode server 子进程。

```python
# 伪代码：runner.py
import subprocess
import json
import httpx
import secrets

async def start_opencode_server(session_id: str, config: OpenCodeBackendConfig) -> OpenCodeServerHandle:
    """
    启动 opencode serve 子进程，返回可用的 HTTP 地址和认证信息。
    """
    # 1. 准备独立 HOME 目录
    home_dir = f"{DATA_DIR}/agent_sessions/opencode/{session_id}/home"
    config_dir = f"{DATA_DIR}/agent_sessions/opencode/{session_id}/config"
    workspace_dir = f"{DATA_DIR}/agent_sessions/opencode/{session_id}/workspace"
    os.makedirs(home_dir, exist_ok=True)
    os.makedirs(config_dir, exist_ok=True)
    os.makedirs(workspace_dir, exist_ok=True)

    # 2. 生成会话级 opencode.json
    opencode_config = build_opencode_config(config.llm_config)
    with open(f"{config_dir}/opencode.json", "w") as f:
        json.dump(opencode_config, f)

    # 3. 生成随机密码（每会话独立）
    password = secrets.token_urlsafe(32)

    # 4. 启动子进程
    env = {
        **os.environ,
        "HOME": home_dir,
        "OPENCODE_CONFIG_DIR": config_dir,
        "OPENCODE_SERVER_PASSWORD": password,
        # 注入 LLM API key
        **build_provider_env(config.llm_config),
    }

    proc = await asyncio.create_subprocess_exec(
        "opencode", "serve",
        "--port", "0",
        "--hostname", "127.0.0.1",
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    # 5. 等待 server 就绪（轮询健康检查或解析 stdout）
    port = await wait_for_server_ready(proc, timeout=30.0)

    # 6. 返回句柄
    return OpenCodeServerHandle(
        proc=proc,
        base_url=f"http://127.0.0.1:{port}",
        auth=("opencode", password),
        home_dir=home_dir,
        config_dir=config_dir,
        workspace_dir=workspace_dir,
    )
```

### 4.2 第二步：构建 opencode.json

根据 CodeAsk 的 LLM 配置，生成 OpenCode 能识别的 provider 配置。

> v1.0.4 Phase 0 已证明 provider 映射不能只按厂商名或固定 URL 特判。当前实现采用少量、通用、用户可见的 OpenCode Provider profile：`default` 走 opencode native provider，用户也可以显式选择 `openai-compatible`、`anthropic-compatible-bearer`、`anthropic-compatible-v1-bearer` 或 `openrouter`。保存配置时不自动联网测试，管理页提供手动“测试连接”按钮；会话启动不做隐式轮转。

```python
def build_opencode_config(llm_config: LLMConfig) -> dict:
    """
    将 CodeAsk 的 LLMConfig 映射为 OpenCode 的 config.json。
    真实实现不按厂商名特判，而是先选择少量通用 profile。

    CodeAsk LLMConfig 字段:
      - protocol: "anthropic" | "openai" | "openai_compatible"
      - base_url: str | None
      - api_key: str            (已解密)
      - model_name: str
      - max_tokens: int | None
      - temperature: float | None
    """
    profile = select_provider_profile(llm_config)
    provider_id = profile.provider_id
    return {
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            provider_id: {
                "npm": profile.npm,
                "name": profile.display_name,
                "options": profile.build_options(llm_config),
                "models": {
                    llm_config.model_name: {}
                }
            }
        }
    }

def select_provider_profile(llm_config: LLMConfig) -> ProviderProfile:
    """
    v1.0.4 使用显式选择策略：
    - default + openai/openai_compatible: @ai-sdk/openai
    - default + anthropic: @ai-sdk/anthropic
    - 显式选择 openai-compatible / anthropic-compatible-bearer / anthropic-compatible-v1-bearer / openrouter 时按用户选择生成配置
    - 保存配置时不自动联网测试；手动测试只测试当前选择的 profile

    遗留增强项：后台定期重测和更完整的诊断面板。
    """
    return selected_profile(llm_config)
```

**映射规则**：

| CodeAsk protocol | OpenCode providerID | OpenCode npm 包 |
|-----------------|--------------------|-----------------|
| `openai` / `openai_compatible` + `default` | `codeask-<cfg_id>` | `@ai-sdk/openai` |
| `anthropic` + `default` | `codeask-<cfg_id>` | `@ai-sdk/anthropic` |
| 显式 `openai-compatible` | `codeask-<cfg_id>` | `@ai-sdk/openai-compatible` |
| 显式 `anthropic-compatible-bearer` | `codeask-<cfg_id>` | `@ai-sdk/anthropic` + Bearer header |
| 显式 `anthropic-compatible-v1-bearer` | `codeask-<cfg_id>` | `@ai-sdk/anthropic` + `baseURL=<base_url>/v1` + Bearer header |
| `google` | `google` | (内置) |

profile 的选择规则以 `docs/v1.0.4/specs/opencode-1.14.48-phase0-spike.md` 和 `docs/v1.0.4/design/opencode-backend.md` 为准；此处伪代码只表达配置生成边界，不再代表最终 provider profile。

### 4.3 第三步：创建 OpenCode Session

```python
async def create_opencode_session(
    handle: OpenCodeServerHandle,
    context: AgentBackendContext,
) -> str:
    """
    在 OpenCode 中创建一个 Session，返回 sessionID。
    """
    async with httpx.AsyncClient(auth=handle.auth) as client:
        resp = await client.post(
            f"{handle.base_url}/session",
            params={
                "directory": handle.workspace_dir,
            },
            json={
                "title": f"CodeAsk-{context.session_id}",
                "agent": context.agent or "general",
                "model": {
                    "providerID": map_provider_id(context.llm_config.protocol),
                    "modelID": context.llm_config.model_name,
                },
                # ★ 权限规则（findLast 策略，务必加白名单，见下文详解）
                "permission": [
                    # ── 白名单：显式 allow 所有只读工具 ──
                    {"permission": "read",        "action": "allow", "pattern": "*"},
                    {"permission": "grep",        "action": "allow", "pattern": "*"},
                    {"permission": "glob",        "action": "allow", "pattern": "*"},
                    {"permission": "list",        "action": "allow", "pattern": "*"},
                    {"permission": "web_search",  "action": "allow", "pattern": "*"},
                    {"permission": "web_fetch",   "action": "allow", "pattern": "*"},
                    {"permission": "task",        "action": "allow", "pattern": "*"},
                    {"permission": "todo_write",  "action": "allow", "pattern": "*"},
                    {"permission": "skill",       "action": "allow", "pattern": "*"},
                    {"permission": "question",    "action": "allow", "pattern": "*"},
                    {"permission": "lsp",         "action": "allow", "pattern": "*"},
                    {"permission": "plan_enter",  "action": "allow", "pattern": "*"},
                    {"permission": "plan_exit",   "action": "allow", "pattern": "*"},
                    # ── 黑名单：deny 危险写入操作 ──
                    {"permission": "bash",        "action": "deny",  "pattern": "*"},
                    # edit/write/apply_patch 三个工具共享 permission key "edit"
                    {"permission": "edit",        "action": "deny",  "pattern": "*"},
                ],
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["id"]  # SessionID，如 "ses01ABCDEF..."
```

**Permission 规则详解（关键）**：

OpenCode 的权限系统有两个重要特性必须在配置时考虑：

**1. 默认行为是 `ask`——会阻塞**：

`permission/evaluate.ts:9-15` 中，当没有任何规则匹配时，默认返回 `{ action: "ask" }`。这意味着工具调用会触发一个 `Deferred`，**永久阻塞**直到有人调用 HTTP API 的 `/permission` reply 端点。在 CodeAsk 集成场景下，没有人在另一端回复权限请求，所以必须通过白名单显式 allow。

**2. `findLast` 策略——靠后的规则覆盖靠前的**：

```typescript
// permission/evaluate.ts
const match = rules.findLast(
  (rule) => Wildcard.match(permission, rule.permission) && Wildcard.match(pattern, rule.pattern),
)
return match ?? { action: "ask", permission, pattern: "*" }
```

两条匹配条件：
- `Wildcard.match(permission, rule.permission)` —— 工具权限名匹配 `rule.permission`
- `Wildcard.match(pattern, rule.pattern)` —— 文件路径匹配 `rule.pattern`

从规则列表**末尾向前**查找，第一个同时满足两个条件的规则生效。

**3. `edit`/`write`/`apply_patch` 共享 permission key**：

`permission/index.ts:309` 中定义：`const EDIT_TOOLS = ["edit", "write", "apply_patch"]`，这三个工具用 `"edit"` 作为 permission key。所以一条 `edit:deny:*` 即可禁止所有文件写入操作。

**4. 规则匹配示例**：

以 Grep 工具调用 `grep("pattern", "src/")` 为例：

```
规则列表末尾开始查找：
  {"permission": "edit", "action": "deny",  "pattern": "*"}
    → Wildcard.match("grep", "edit") → false，跳过

  {"permission": "bash", "action": "deny",  "pattern": "*"}
    → Wildcard.match("grep", "bash") → false，跳过

  {"permission": "plan_exit", "action": "allow", "pattern": "*"}
    → Wildcard.match("grep", "plan_exit") → false，跳过

  ... 继续向前 ...

  {"permission": "grep", "action": "allow", "pattern": "*"}
    → Wildcard.match("grep", "grep") → true  ✅
    → Wildcard.match("src/", "*") → true      ✅
    → 命中！action = "allow" → 自动通过，不阻塞
```

以 Edit 工具调用 `edit("src/foo.ts", ...)` 为例：

```
规则列表末尾开始查找：
  {"permission": "edit", "action": "deny",  "pattern": "*"}
    → Wildcard.match("edit", "edit") → true      ✅
    → Wildcard.match("src/foo.ts", "*") → true   ✅
    → 命中！action = "deny" → 拒绝，返回 DeniedError
```

**5. 后续如需开放部分写入**，在 deny 规则之前插入 allow 即可（findLast 先命中 allow）：

```json
"permission": [
    // ... 白名单 ...
    {"permission": "write", "action": "allow", "pattern": "docs/**/*.md"},  // 允许写文档
    {"permission": "bash",  "action": "deny",  "pattern": "*"},
    {"permission": "edit",  "action": "deny",  "pattern": "*"},
]
```

### 4.3b 配置层总览：三层配置，全部自动化

CodeAsk 集成涉及三层配置，**全部由 OpenCodeBackend 程序化生成，最终用户无感知**：

```
┌─────────────────────────────────────────────────────────┐
│ 配置层 1: opencode.json                                  │
│ ─────────────────────────────────────────────────────── │
│ 位置: <session_dir>/config/opencode.json                │
│ 作用: LLM 提供商配置（模型名、API key、baseURL）          │
│ 生成者: OpenCodeBackend (config.py / build_opencode_config)│
│ 时机: 子进程启动前写入                                     │
├─────────────────────────────────────────────────────────┤
│ 配置层 2: AGENTS.md                                      │
│ ─────────────────────────────────────────────────────── │
│ 位置: <session_dir>/workspace/AGENTS.md                  │
│ 作用: 静态行为规则（语言、回答风格、工作约束）              │
│ 生成者: OpenCodeBackend (创建 Session 前写入 workspace)    │
│ 时机: 创建 Session 前写入                                  │
│ 加载: OpenCode Instruction 服务自动读取                   │
│ 注意: 此层内容放在 system prompt 第 2 段，优先级高         │
├─────────────────────────────────────────────────────────┤
│ 配置层 3: Session Permission                             │
│ ─────────────────────────────────────────────────────── │
│ 位置: POST /session 的 JSON body.permission 字段         │
│ 作用: 工具权限白名单/黑名单（工具是否可用、是否需要确认）   │
│ 生成者: OpenCodeBackend (backend.py / create_opencode_session)│
│ 时机: 创建 OpenCode Session 时一次性设定                   │
│ 评估: findLast 策略，每轮工具调用自动生效，无需人工审批     │
└─────────────────────────────────────────────────────────┘
```

**关键点**：三层中只有第 3 层（Permission）影响"会不会卡住"的问题。只要在 Session 创建时显式写了白名单 allow 规则，所有只读工具调用全程无阻塞——`ctx.ask()` → `permission.ask()` → `evaluate()` → 命中 allow → 直接返回，Deferred 不会被创建。

### 4.4 第四步：发送消息并消费流

这是核心流程——CodeAsk 将知识上下文注入 OpenCode，并消费 SSE 流式事件。

```python
async def run_opencode_turn(
    handle: OpenCodeServerHandle,
    opencode_session_id: str,
    turn_context: TurnContext,
) -> AsyncIterator[ChatRuntimeEvent]:
    """
    执行一轮 OpenCode Agent 对话。

    参数:
      handle: OpenCode server 句柄
      opencode_session_id: 已创建的 OpenCode Session ID
      turn_context: 当前轮上下文（用户消息 + 知识检索结果）
    """
    async with httpx.AsyncClient(auth=handle.auth, timeout=None) as client:

        # ─── 4.4a: 拼装 System Prompt（知识上下文注入点）───
        system_prompt = build_system_prompt(turn_context)

        # ─── 4.4b: 拼装消息 Parts ───
        parts = build_message_parts(turn_context)

        # ─── 4.4c: 先建立 SSE 连接 ───
        sse_stream = await establish_sse_stream(
            client, handle.base_url, handle.workspace_dir
        )

        # ─── 4.4d: 发送消息（触发 Agent 循环）───
        # 使用 asyncio.Task 并发：一边发送消息等待同步返回，一边消费 SSE
        message_task = asyncio.create_task(
            client.post(
                f"{handle.base_url}/session/{opencode_session_id}/message",
                params={"directory": handle.workspace_dir},
                json={
                    "system": system_prompt,
                    "agent": turn_context.agent or "general",
                    "model": {
                        "providerID": map_provider_id(turn_context.llm_config.protocol),
                        "modelID": turn_context.llm_config.model_name,
                    },
                    "parts": parts,
                },
            )
        )

        # ─── 4.4e: 消费 SSE 事件流 ───
        tool_calls_in_flight: dict[str, str] = {}  # callID -> toolName
        accumulated_text = ""

        async for sse_event in sse_stream:
            event = parse_sse_event(sse_event)

            if event.type == "session.status":
                status = event.properties.status
                if status["type"] == "busy":
                    pass  # Agent 开始工作
                elif status["type"] == "idle":
                    # Agent 循环结束，退出 SSE 消费
                    break
                elif status["type"] == "retry":
                    yield ChatRuntimeEvent(
                        type="runtime_state",
                        data={"state": "retrying", "message": status.get("message")}
                    )

            elif event.type == "message.part.delta":
                # ★ 流式文本增量 → CodeAsk text_delta
                delta = event.properties.delta
                accumulated_text += delta
                yield ChatRuntimeEvent(type="text_delta", data={"delta": delta})

            elif event.type == "message.updated":
                # 消息/Part 更新 → 检测工具调用和结果
                for part in event.properties.parts or []:
                    if part.get("type") != "tool":
                        continue

                    tool_state = part.get("state", {})
                    tool_name = part.get("tool", "unknown")
                    call_id = part.get("callID", "")

                    if tool_state.get("status") == "running":
                        # 工具开始执行
                        tool_calls_in_flight[call_id] = tool_name
                        yield ChatRuntimeEvent(
                            type="tool_call",
                            data={
                                "tool": tool_name,
                                "call_id": call_id,
                                "input": tool_state.get("input", {}),
                            }
                        )

                    elif tool_state.get("status") == "completed":
                        # 工具执行完成
                        yield ChatRuntimeEvent(
                            type="tool_result",
                            data={
                                "tool": tool_name,
                                "call_id": call_id,
                                "output": tool_state.get("output", ""),
                                "title": tool_state.get("title", ""),
                                "metadata": tool_state.get("metadata", {}),
                            }
                        )

                    elif tool_state.get("status") == "error":
                        yield ChatRuntimeEvent(
                            type="tool_result",
                            data={
                                "tool": tool_name,
                                "call_id": call_id,
                                "error": tool_state.get("error", "Unknown error"),
                            }
                        )

            elif event.type == "session.error":
                error_data = event.properties.get("error", {})
                yield ChatRuntimeEvent(
                    type="error",
                    data={
                        "name": error_data.get("name", "UnknownError"),
                        "data": error_data.get("data", {}),
                    }
                )

        # ─── 4.4f: 等待同步响应完成 ───
        resp = await message_task
        resp.raise_for_status()
        final_message = resp.json()

        # ─── 4.4g: 发送 done 事件 ───
        yield ChatRuntimeEvent(
            type="done",
            data={
                "message_id": final_message["info"]["id"],
                "cost": final_message["info"].get("cost", 0),
                "tokens": final_message["info"].get("tokens", {}),
                "finish": final_message["info"].get("finish", "stop"),
            }
        )
```

### 4.5 第五步：中断处理

```python
async def abort_opencode_turn(
    handle: OpenCodeServerHandle,
    opencode_session_id: str,
    active_tasks: list[asyncio.Task],
) -> None:
    """
    中断当前轮 Agent 执行。
    """
    logger.info(f"Aborting opencode session {opencode_session_id}")

    # 1. 取消本地的 asyncio Task（SSE 消费、HTTP 请求）
    for task in active_tasks:
        if not task.done():
            task.cancel()

    # 2. 调用 OpenCode abort 端点
    try:
        async with httpx.AsyncClient(auth=handle.auth, timeout=5.0) as client:
            await client.post(
                f"{handle.base_url}/session/{opencode_session_id}/abort",
                params={"directory": handle.workspace_dir},
            )
    except Exception as e:
        logger.warning(f"OpenCode abort API call failed: {e}")
        # 如果 API 调用失败，尝试 kill 子进程作为最后手段
        # handle.proc.kill()

    # 3. 等待 Task 取消完成
    await asyncio.gather(*active_tasks, return_exceptions=True)

    # 4. 注意：不删除 OpenCode Session。
    #    下一轮继续用同一个 Session，上下文不丢失。
    #    但 CodeAsk 侧的本轮 trace 需要删除（由调用方处理）。
```

---

## 5. 事件映射表

### 5.1 SSE 事件 → CodeAsk ChatRuntimeEvent 完整映射

| OpenCode SSE event.type | 触发条件 | CodeAsk ChatRuntimeEvent | 映射逻辑 |
|-------------------------|---------|--------------------------|---------|
| `message.part.delta` | LLM 每输出一段文本 | `text_delta` | `data.delta = properties.delta` |
| `message.updated` + `part.type=="tool"` + `status=="running"` | 工具开始执行 | `tool_call` | `data.tool = part.tool`, `data.input = part.state.input` |
| `message.updated` + `part.type=="tool"` + `status=="completed"` | 工具执行完成 | `tool_result` | `data.output = part.state.output`, `data.title = part.state.title` |
| `message.updated` + `part.type=="tool"` + `status=="error"` | 工具执行失败 | `tool_result` (带 error) | `data.error = part.state.error` |
| `session.status` + `type=="busy"` | Agent 开始工作 | (内部状态，不对外发事件) | 更新 backend 内部状态 |
| `session.status` + `type=="idle"` | Agent 循环结束 | 退出 SSE 循环，发 `done` | — |
| `session.status` + `type=="retry"` | 限流重试中 | `runtime_state` | `data.state = "retrying"` |
| `session.error` | 任何错误 | `error` | `data.name` + `data.data` |
| `session.diff` | 文件变更 | (第一版只读，不发此事件) | 后续版本可用于展示 diff |

### 5.2 工具名称映射

OpenCode 有 19 个内置工具。CodeAsk 需要将工具名映射为前端可展示的友好名称：

| OpenCode Tool ID | 中文名 | 第一版是否开放 | 备注 |
|-----------------|--------|:---:|------|
| `read` | 读取文件 | ✅ | 核心只读工具 |
| `glob` | 文件搜索 | ✅ | 模式匹配找文件 |
| `grep` | 内容搜索 | ✅ | ripgrep 搜索 |
| `web_search` | 网络搜索 | ✅ | 根据 provider 自动启用 |
| `web_fetch` | 网页抓取 | ✅ | 获取 URL 内容 |
| `task` | 子代理 | ✅ | 委托子任务 |
| `skill` | 技能 | ✅ | 加载领域技能 |
| `list` | 列出目录 | ✅ | |
| `bash` | Shell | ❌ | 权限规则中 deny |
| `edit` | 编辑文件 | ❌ | 权限规则中 deny |
| `write` | 写入文件 | ❌ | 权限规则中 deny（保留用于写 Markdown 报告） |
| `apply_patch` | 应用补丁 | ❌ | |
| `question` | 向用户提问 | ✅ | 需要确认的工具 |
| `todo_write` | 待办事项 | ✅ | 任务管理 |
| `task_output` | 获取任务输出 | ✅ | 查看后台任务结果 |
| `plan_enter` | 进入计划模式 | ✅ | 仅在 CLI 模式启用 |
| `plan_exit` | 退出计划模式 | ✅ | 仅在 CLI 模式启用 |
| `lsp` | 语言服务器 | ✅ | 诊断信息（实验性） |
| `code_search` | 代码搜索 | ✅ | 实验性 Scout 工具 |

### 5.3 工具事件展示

CodeAsk 前端已有 `ToolCallEvent.tsx` 和 `ToolResultEvent.tsx` 组件。OpenCode 工具事件映射后的 JSON 结构：

```json
// tool_call
{
  "type": "tool_call",
  "data": {
    "tool": "grep",
    "call_id": "toolu_01ABC...",
    "input": {
      "pattern": "authenticate",
      "path": "src/auth"
    }
  }
}

// tool_result
{
  "type": "tool_result",
  "data": {
    "tool": "grep",
    "call_id": "toolu_01ABC...",
    "output": "src/auth/login.ts:42:  async authenticate(user: User)",
    "title": "Grep: authenticate in src/auth",
    "metadata": {
      "truncated": false
    }
  }
}
```

---

## 6. 知识上下文注入

这是 CodeAsk 核心价值保留的关键——将 Wiki、RAG、报告搜索结果作为 OpenCode 的 System Prompt 和第一条 User Message 注入。

### 6.1 System Prompt 构建

```python
def build_system_prompt(turn_context: TurnContext) -> str:
    """
    将 CodeAsk 的知识检索结果构建为 OpenCode 的 system prompt。

    system prompt 放在 OpenCode 已有的指令（AGENTS.md / CLAUDE.md）之后，
    作为补充的领域知识。
    """
    parts = []

    # ── 基础角色 ──
    parts.append("""你是一位研发 troubleshooting 助手，在 CodeAsk 工作台中协助用户分析和解决技术问题。

你拥有以下 CodeAsk 知识库的检索结果作为参考上下文。请优先使用这些信息理解用户的问题。
""")

    # ── 1. Wiki 检索结果 ──
    if turn_context.wiki_hits:
        parts.append("## Wiki 知识库检索结果\n")
        for hit in turn_context.wiki_hits[:8]:
            parts.append(f"""
### {hit.title}
- **来源特性**: {hit.feature_name or "全局"}
- **路径**: {hit.path or "—"}
- **匹配片段**:
{hit.snippet or "(完整文档见下方内容)"}

{h truncate(hit.body_markdown, 3000)}
""")

    # ── 2. 报告检索结果 ──
    if turn_context.report_hits:
        parts.append("## 相关问题报告\n")
        for hit in turn_context.report_hits[:6]:
            parts.append(f"""
### {hit.title}
- **报告时间**: {hit.created_at}
- **问题摘要**:
{h truncate(hit.body_markdown, 2000)}
""")

    # ── 3. 特性信息 ──
    if turn_context.feature_candidates:
        parts.append("## 相关特性\n")
        for feat in turn_context.feature_candidates[:8]:
            parts.append(f"""
- **{feat.name}** (`{feat.id}`): {feat.description or "—"}
  - 关联仓库: {", ".join(feat.repo_names) if feat.repo_names else "—"}
""")

    # ── 4. 代码仓库信息 ──
    if turn_context.repo_candidates:
        parts.append("## 可访问的代码仓库\n")
        for repo in turn_context.repo_candidates[:8]:
            parts.append(f"- **{repo.repo_name}**: {repo.description or "—"} (路径: {repo.worktree_path})")

    # ── 5. 附件信息 ──
    if turn_context.attachment_candidates:
        parts.append("## 会话附件\n")
        for att in turn_context.attachment_candidates[:6]:
            parts.append(f"- **{att.filename}**: {att.description or "—"}")

    # ── 6. 工作目录提示 ──
    parts.append(f"""
## 当前工作环境
- 工作目录: {turn_context.workspace_dir}
- 可使用 Read/Grep/Glob 等只读工具探索代码仓库
""")

    return "\n".join(parts)
```

### 6.2 消息 Parts 构建

```python
def build_message_parts(turn_context: TurnContext) -> list[dict]:
    """
    构建 OpenCode 消息的 parts 数组。

    用户消息 + 知识库上下文放在同一个 text part 中。
    """
    parts = []

    # 主体：用户问题 + 知识库精简摘要
    user_message = turn_context.user_message

    if turn_context.attachments:
        attachment_list = "\n".join(
            f"- {att.filename}" for att in turn_context.attachments
        )
        user_message = f"{user_message}\n\n## 附件文件\n{attachment_list}"

    parts.append({
        "type": "text",
        "text": user_message,
    })

    # 附件文件内容（作为 file part）
    for att in (turn_context.attachments or []):
        if att.content:
            parts.append({
                "type": "file",
                "mime": att.mime_type or "text/plain",
                "filename": att.filename,
                "url": f"data:{att.mime_type or 'text/plain'};base64,{b64encode(att.content)}",
            })

    return parts
```

### 6.3 上下文注入的两种模式

| 注入位置 | 内容 | 持久性 | 适用场景 |
|---------|------|--------|---------|
| **system 字段** | 知识库检索结果 | 本轮有效 | Wiki 命中、报告命中等检索结果 |
| **AGENTS.md 文件** | CodeAsk 角色定义、长期规则 | 跨轮持久 | 行为约束、工具使用规则、格式要求 |

**System Prompt** 用于注入本轮检索到的动态知识（Wiki 命中、报告命中），适合每轮变化的上下文。

**AGENTS.md**（OpenCode 的 Instruction 系统自动加载）用于注入静态规则，如：
```
# <workspace>/AGENTS.md
你工作在 CodeAsk 工作台中。
请用中文回复。
回答时引用来源（Wiki 文档路径、报告标题等）。
不猜测代码行为，先用 Read/Grep 工具确认。
```

CodeAsk 可以在创建 OpenCode Session 前，将这类规则写入 workspace 目录下的 AGENTS.md 文件。

---

## 7. 会话生命周期

### 7.1 创建 → 多轮对话 → 销毁

```
CodeAsk Session 创建
       │
       ▼
┌──────────────────────────────────────────────────┐
│ OpenCodeBackend.ensure_session()                 │
│                                                  │
│  1. mkdir 隔离目录                                │
│  2. 生成 opencode.json (LLM 配置)                  │
│  3. 写入 AGENTS.md (CodeAsk 规则)                  │
│  4. spawn opencode serve                          │
│  5. POST /session → OpenCode Session ID           │
│  6. 记录 external_agent_sessions 表                │
└──────────────────┬───────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────┐
│ Turn 1                                           │
│                                                  │
│  ① CodeAsk 知识检索 → TurnContext                  │
│  ② build_system_prompt(turn_context)              │
│  ③ GET /event (SSE)                              │
│  ④ POST /session/:id/message                     │
│     {                                            │
│       system: "## Wiki 检索结果\n...",            │
│       parts: [{type:"text", text:"用户问题..."}]   │
│     }                                            │
│  ⑤ 消费 SSE → 映射为 ChatRuntimeEvent              │
│  ⑥ 持久化 CodeAsk trace                           │
│  ⑦ 持久化 OpenCode 原始事件到 stream.jsonl         │
└──────────────────┬───────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────┐
│ Turn 2 (同一 CodeAsk Session, 同一 OpenCode Session) │
│                                                  │
│  ① 新一轮知识检索（可能命中了新的 Wiki 文档）         │
│  ② build_system_prompt(新 TurnContext)             │
│  ③ POST /session/:id/message                     │
│     {                                            │
│       system: "## Wiki 检索结果\n(新结果)...",     │
│       parts: [{type:"text", text:"追问..."}]       │
│     }                                            │
│                                                  │
│  OpenCode 保留 Turn 1 的对话历史                    │
│  + Turn 2 的 system prompt 补充了新的知识上下文      │
└──────────────────┬───────────────────────────────┘
                   │
                   ▼
                   ...
                   │
                   ▼
┌──────────────────────────────────────────────────┐
│ CodeAsk Session 删除 / 归档                        │
│                                                  │
│  1. DELETE /session/:opencode_id                 │
│  2. 停止 opencode serve 子进程                    │
│  3. 清理隔离目录（或归档）                          │
│  4. 更新 external_agent_sessions.status = archived │
└──────────────────────────────────────────────────┘
```

### 7.2 Session 复用策略

| 会话粒度 | 方案 A：每 Session 一个 OpenCode Session | 方案 B：每 Turn 一个 OpenCode Session |
|---------|--------------------------------------|-------------------------------------|
| 对话连续性 | ✅ 多轮自然连续 | ❌ 每轮独立，需重建上下文 |
| 上下文膨胀 | 需依赖 OpenCode compaction | 天然受控 |
| Token 消耗 | 后续轮次包含历史 | 每轮都重新发送完整上下文 |
| 实现复杂度 | 低 | 高（需 CodeAsk 管理上下文重建） |
| 推荐 | **✅ 第一版采用** | 后续评估 |

**第一版采用方案 A**：一个 CodeAsk Session 对应一个 OpenCode Session，多轮消息靠 OpenCode 的会话管理能力和 Compaction 机制来维持上下文。

---

## 8. 错误处理

### 8.1 错误分类与处理

```python
class OpenCodeError(Exception):
    """OpenCode backend 基础异常"""
    pass

class OpenCodeConnectionError(OpenCodeError):
    """无法连接 OpenCode server（子进程未启动 / 端口不通）"""
    pass

class OpenCodeAuthError(OpenCodeError):
    """OpenCode 认证失败"""
    pass

class OpenCodeSessionError(OpenCodeError):
    """Session 级别错误（session 不存在、已删除）"""
    pass

class OpenCodeAgentError(OpenCodeError):
    """Agent 执行错误（LLM 错误、上下文溢出、超时等）"""
    pass

class OpenCodeAbortedError(OpenCodeError):
    """用户主动中断"""
    pass
```

### 8.2 错误处理流程

```
错误发生
    │
    ├── 子进程未启动 / 端口不通
    │   → OpenCodeConnectionError
    │   → 是否重试启动？（最多 1 次）
    │   → 仍失败：返回 error 事件给前端，提示用户
    │   → v1.0.4 新会话不回退到 NativeBackend
    │
    ├── POST /session/:id/message 返回 5xx
    │   → OpenCodeAgentError
    │   → 提取 error body 中的 error.name 和 error.data
    │   → 映射为 ChatRuntimeEvent(type="error", ...)
    │   → 不重试，让用户手动重试
    │
    ├── SSE 连接断开（非预期）
    │   → 尝试重新订阅 SSE（最多 1 次）
    │   → 仍失败：abort，返回 error 事件
    │
    ├── 上下文溢出 (ContextOverflowError)
    │   → OpenCode 内部会尝试 Compaction
    │   → 如果 Compaction 后仍然溢出：
    │      → 返回 error 给前端
    │      → 建议用户缩小问题范围 或 开启新 Session
    │
    └── 限流 (Rate Limit)
        → OpenCode 内部做 retry（session.status.type == "retry"）
        → CodeAsk 转发 retry 状态给前端
        → 不额外干预
```

### 8.3 OpenCode 错误 → CodeAsk 映射

| OpenCode error.name | CodeAsk 处理 |
|--------------------|-------------|
| `ProviderAuthError` | 提示用户检查 API key 配置 |
| `MessageOutputLengthError` | 提示“输出过长”，建议缩小问题范围 |
| `MessageAbortedError` | 正常中断，不报错 |
| `ContextOverflowError` | 提示“上下文溢出”，建议新开会话 |
| `UnknownError` | 显示 data.message |
| `APIError` | 显示 data.message |

---

## 9. 实现要点

### 9.1 OpenCode Server 子进程管理

```python
class OpenCodeProcessManager:
    """
    管理 OpenCode serve 子进程。
    支持进程池复用（按 workspace 隔离）和心跳保活。
    """

    def __init__(self):
        self._processes: dict[str, OpenCodeServerHandle] = {}

    async def get_or_create(
        self,
        session_id: str,
        workspace_dir: str,
        llm_config: LLMConfig,
    ) -> OpenCodeServerHandle:
        """
        按 session_id 获取或创建 OpenCode 进程。
        如果已有该 session 的进程且健康，直接复用。
        """
        if session_id in self._processes:
            handle = self._processes[session_id]
            if await self._health_check(handle):
                return handle
            else:
                # 进程不健康，重新启动
                await self._stop(handle)
                del self._processes[session_id]

        handle = await self._start(session_id, workspace_dir, llm_config)
        self._processes[session_id] = handle
        return handle

    async def _health_check(self, handle: OpenCodeServerHandle) -> bool:
        """检查 OpenCode server 是否存活"""
        try:
            async with httpx.AsyncClient(auth=handle.auth, timeout=5.0) as client:
                resp = await client.get(f"{handle.base_url}/global/health")
                return resp.status_code == 200
        except Exception:
            return False

    async def stop_all(self):
        """停止所有子进程（shutdown 时调用）"""
        for handle in self._processes.values():
            await self._stop(handle)
        self._processes.clear()

    async def _stop(self, handle: OpenCodeServerHandle):
        """优雅停止一个子进程：先发 SIGTERM，3 秒后 SIGKILL"""
        try:
            handle.proc.terminate()
            try:
                await asyncio.wait_for(handle.proc.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                handle.proc.kill()
                await handle.proc.wait()
        except ProcessLookupError:
            pass  # 进程已退出
```

### 9.2 并发限流

多个用户并发使用 OpenCode Backend 时，每个 Session 独占一个 OpenCode 子进程。需要考虑：

```python
# 全局限制
MAX_CONCURRENT_OPENCODE_PROCESSES = 10

class OpenCodeConcurrencyLimit:
    """使用 asyncio.Semaphore 限制并发 OpenCode 进程数"""
    def __init__(self):
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_OPENCODE_PROCESSES)

    async def acquire(self):
        await self._semaphore.acquire()

    def release(self):
        self._semaphore.release()
```

### 9.3 日志与审计

```python
class OpenCodeEventLogger:
    """
    将 OpenCode 原始 SSE 事件写入 stream.jsonl，
    并将关键事件映射为 CodeAsk trace。
    """

    def __init__(self, session_dir: str):
        self._jsonl_path = Path(session_dir) / "logs" / "stream.jsonl"
        self._jsonl_path.parent.mkdir(parents=True, exist_ok=True)

    def log_raw_event(self, sse_event: dict):
        """追加原始事件到 JSONL"""
        with open(self._jsonl_path, "a") as f:
            f.write(json.dumps(sse_event, ensure_ascii=False) + "\n")

    def build_trace_metadata(
        self, event_type: str, sse_event: dict, line_number: int
    ) -> dict:
        """构建 CodeAsk trace 的 metadata"""
        return {
            "backend": "opencode",
            "external_event_type": event_type,
            "raw_event_ref": f"{self._jsonl_path}#{line_number}",
        }
```

### 9.4 与 CodeAsk 现有代码的集成点

不改动现有 `chat_runtime/runtime.py`。早期草案曾计划新增 `src/codeask/agent/backends/` 通用 backend 层；v1.0.4 已收敛为独立模块，不采用该结构。新增文件应以版本目录设计为准：

```text
src/codeask/agent/opencode_compat/
├── __init__.py
├── sessions.py
├── config.py
├── profiles.py
├── process.py
├── http.py
├── events.py
├── workspace.py
├── worktrees.py
└── mcp/
```

集成点（`src/codeask/app.py` 和 `src/codeask/api/sessions.py`）只调用 opencode 专用入口，不建立通用 backend router：

```python
# app.py: 注册 opencode 兼容模块
from codeask.agent.opencode_compat import OpenCodeCompat

opencode_compat = OpenCodeCompat(
    data_dir=settings.codeask_data_dir,
)
```

### 9.5 Provider ID 映射函数

```python
def map_provider_id(codeask_protocol: str) -> str:
    """
    CodeAsk LLM protocol → OpenCode providerID
    """
    mapping = {
        "openai": "codeask-openai-compatible",
        "anthropic": "codeask-anthropic-compatible",
        "google": "google",
        "openai_compatible": "codeask-openai-compatible",  # 在 opencode.json 中自定义
    }
    return mapping.get(codeask_protocol, "codeask-openai-compatible")

def map_model_id(codeask_model_name: str) -> str:
    """
    CodeAsk model_name → OpenCode modelID。
    通常直接透传，但如果 CodeAsk 内部用的别名和 OpenCode 不一致时需要映射。
    """
    # 第一版直接透传
    return codeask_model_name
```

---

## 10. 待验证项

以下问题需要在 PoC 阶段通过实际运行来验证：

### 10.1 SSE 事件时序

`POST /session/:id/message` 是同步端点，在 Agent 循环完成后才返回。SSE (`GET /event`) 是实时推送。
**需验证**：SSE 中是否会先于 POST 响应收到 `session.status { type: "idle" }`？如果是，用哪个事件作为 "done" 信号更可靠？

**建议方案**：以 SSE `session.status.idle` 作为循环结束信号，以 POST 响应作为最终数据校验。两者都到达后再发 `done` 事件。

### 10.2 单 Session 并发消息

OpenCode 的 Session **不支持并发消息**——对一个 Session 连续发两个 `POST /session/:id/message`，第二个请求会怎样？
**需验证**：是返回错误、还是在第一个完成后自动处理第二个？

**当前假设**：CodeAsk 侧保证同一 Session 同时只有一个 Turn 在执行。如果用户在前一轮未完成时又发消息，应排队或提示等待。

### 10.3 Permission 规则格式

需验证 Permission 的 `pattern` 是否支持 glob（如 `*`、`**/*`），以及 deny 规则是否真的能阻止 Shell/Edit/Write 工具。
如果 Permission 规则不够用，备选方案是在创建 Session 时通过 `tools` 参数显式禁用工具。

### 10.4 opencode.json 的 baseURL 字段

OpenCode 的 OpenAI-compatible provider `options.baseURL` 字段名需确认（可能是 `baseURL`、`baseUrl` 或 `base_url`）。以实际版本的 config schema 为准。

### 10.5 子进程资源占用

单个 OpenCode serve 进程的内存占用（Bun 运行时 + SQLite + 会话状态）需实测。
10 个并发 Session = 10 个 OpenCode 进程是否可行？

**缓解策略**：如有必要，可以按 Session 复用 OpenCode 进程（多个 Session 共享一个 serve 进程），通过 `Session.create` 在同一个 serve 中创建多个 Session。

### 10.6 上下文溢出后的行为

当 CodeAsk 的知识注入内容 + OpenCode 自身指令 + 多轮对话历史超过模型上下文窗口时：
- OpenCode 的 Compaction 是否能正确压缩知识上下文？
- 压缩后的行为是否符合预期（不会丢失关键的 Wiki 检索结果）？

---

## 附录 A：完整 API 调用示例

```python
# -*- coding: utf-8 -*-
"""
完整的 OpenCode Backend 调用示例。
展示从启动到一轮对话完成为止的完整交互。
"""

import asyncio
import httpx
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

# ============================================================
# 第一步：启动 OpenCode server
# ============================================================

DATA_DIR = "/var/lib/codeask/data/agent_sessions/opencode"
SESSION_ID = "ses_demo_001"
SESSION_DIR = f"{DATA_DIR}/{SESSION_ID}"
HOME_DIR = f"{SESSION_DIR}/home"
CONFIG_DIR = f"{SESSION_DIR}/config"
WORKSPACE_DIR = "/home/user/projects/my-service"
PASSWORD = secrets.token_urlsafe(32)

os.makedirs(HOME_DIR, exist_ok=True)
os.makedirs(CONFIG_DIR, exist_ok=True)

# 写入 opencode.json
opencode_config = {
    "$schema": "https://opencode.ai/config.json",
    "provider": {
        "openai": {
            "options": {"apiKey": os.environ["OPENAI_API_KEY"]},
            "models": {"gpt-4o": {}}
        }
    }
}
with open(f"{CONFIG_DIR}/opencode.json", "w") as f:
    json.dump(opencode_config, f, indent=2)

# 写入 AGENTS.md（CodeAsk 规则注入）
agents_md = """# CodeAsk 工作台规则
你运行在 CodeAsk 研发 troubleshooting 工作台中。
- 用中文回复
- 回答时引用来源（Wiki 文档路径、报告标题等）
- 不猜测代码行为，先用 Read/Grep 工具确认
- 只读操作（不允许修改代码）
"""
with open(f"{WORKSPACE_DIR}/AGENTS.md", "w") as f:
    f.write(agents_md)

# 启动子进程
proc = subprocess.Popen(
    ["opencode", "serve", "--port", "0", "--hostname", "127.0.0.1"],
    env={
        **os.environ,
        "HOME": HOME_DIR,
        "OPENCODE_CONFIG_DIR": CONFIG_DIR,
        "OPENCODE_SERVER_PASSWORD": PASSWORD,
    },
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)

# 等待就绪（实际应解析 stdout 获取端口，这里简化）
import time; time.sleep(3)
PORT = 4096  # 假设
BASE_URL = f"http://127.0.0.1:{PORT}"
AUTH = httpx.BasicAuth("opencode", PASSWORD)


# ============================================================
# 第二步：创建 OpenCode Session
# ============================================================

async def create_session() -> str:
    async with httpx.AsyncClient(auth=AUTH, timeout=10.0) as client:
        resp = await client.post(
            f"{BASE_URL}/session",
            params={"directory": WORKSPACE_DIR},
            json={
                "title": f"CodeAsk-{SESSION_ID}",
                "agent": "general",
                "model": {"providerID": "openai", "modelID": "gpt-4o"},
                "permission": [
                    {"permission": "read",        "action": "allow", "pattern": "*"},
                    {"permission": "grep",        "action": "allow", "pattern": "*"},
                    {"permission": "glob",        "action": "allow", "pattern": "*"},
                    {"permission": "list",        "action": "allow", "pattern": "*"},
                    {"permission": "web_search",  "action": "allow", "pattern": "*"},
                    {"permission": "web_fetch",   "action": "allow", "pattern": "*"},
                    {"permission": "task",        "action": "allow", "pattern": "*"},
                    {"permission": "todo_write",  "action": "allow", "pattern": "*"},
                    {"permission": "skill",       "action": "allow", "pattern": "*"},
                    {"permission": "question",    "action": "allow", "pattern": "*"},
                    {"permission": "lsp",         "action": "allow", "pattern": "*"},
                    {"permission": "plan_enter",  "action": "allow", "pattern": "*"},
                    {"permission": "plan_exit",   "action": "allow", "pattern": "*"},
                    {"permission": "bash",        "action": "deny",  "pattern": "*"},
                    {"permission": "edit",        "action": "deny",  "pattern": "*"},
                ],
            },
        )
        resp.raise_for_status()
        session_data = resp.json()
        print(f"[OK] OpenCode Session 创建: {session_data['id']}")
        return session_data["id"]


# ============================================================
# 第三步 & 第四步：发送消息 + 消费 SSE 流
# ============================================================

async def send_message_and_stream(session_id: str):
    async with httpx.AsyncClient(auth=AUTH, timeout=None) as client:

        # 3a. 建立 SSE 连接
        sse_url = f"{BASE_URL}/event?directory={WORKSPACE_DIR}"
        sse_response = await client.send(
            httpx.Request("GET", sse_url),
            stream=True,
        )

        # 3b. 拼装 Prompt（知识上下文在此注入）
        system_prompt = """## Wiki 知识库检索结果

### 用户认证流程
- **来源特性**: auth-service (auth-svc)
- **路径**: /wiki/auth/authentication-flow
- **内容摘要**: 系统采用 JWT + Refresh Token 双令牌机制。
  Access Token 有效期 15 分钟，Refresh Token 有效期 7 天。
  认证入口在 `src/auth/login.ts` 的 `authenticate()` 函数。

## 相关问题报告
### 生产环境 Token 刷新失败
- **报告时间**: 2026-04-15
- **问题摘要**: 用户反映在移动端切换网络后 Refresh Token 刷新失败...

## 可访问的代码仓库
- **my-service**: 核心服务 (路径: /home/user/projects/my-service)
- **auth-svc**: 认证服务 (路径: /home/user/projects/auth-svc)
"""

        # 3c. 发送消息（异步，不等待完成）
        message_task = asyncio.create_task(
            client.post(
                f"{BASE_URL}/session/{session_id}/message",
                params={"directory": WORKSPACE_DIR},
                json={
                    "system": system_prompt,
                    "agent": "general",
                    "model": {"providerID": "openai", "modelID": "gpt-4o"},
                    "parts": [
                        {
                            "type": "text",
                            "text": "用户在移动端切换网络后，Refresh Token 刷新失败。请帮我分析可能的原因。"
                        }
                    ],
                },
            )
        )

        # 3d. 消费 SSE 事件
        accumulated_text = ""

        async for line in sse_response.aiter_lines():
            if not line.startswith("data:"):
                continue

            data_str = line[5:].strip()
            if not data_str:
                continue

            try:
                event = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            event_type = event.get("type", "")
            props = event.get("properties", {})

            if event_type == "session.status":
                status_type = props.get("status", {}).get("type", "")
                if status_type == "busy":
                    print("[STATUS] Agent 开始工作...")
                elif status_type == "idle":
                    print("[STATUS] Agent 循环完成")
                    break
                elif status_type == "retry":
                    print(f"[STATUS] 重试中: {props['status'].get('message', '')}")

            elif event_type == "message.part.delta":
                delta = props.get("delta", "")
                accumulated_text += delta
                print(delta, end="", flush=True)

            elif event_type == "message.updated":
                for part in props.get("parts", []):
                    if part.get("type") != "tool":
                        continue
                    state = part.get("state", {})
                    tool_name = part.get("tool", "?")
                    if state.get("status") == "running":
                        print(f"\n[TOOL] 调用 {tool_name}...")
                    elif state.get("status") == "completed":
                        print(f"[TOOL] {tool_name} 完成: {state.get('title', '')}")
                        output = state.get("output", "")
                        if len(output) < 500:
                            print(output)

            elif event_type == "session.error":
                error = props.get("error", {})
                print(f"\n[ERROR] {error.get('name')}: {error.get('data', {}).get('message', '')}")

        # 3e. 等待同步响应完成
        resp = await message_task
        final_message = resp.json()

        print(f"\n[DONE] cost=${final_message['info'].get('cost', 0):.4f}, "
              f"tokens={final_message['info'].get('tokens', {})}")

        return final_message


# ============================================================
# 运行
# ============================================================

async def main():
    session_id = await create_session()
    await send_message_and_stream(session_id)

    # 清理
    proc.terminate()
    proc.wait()

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 附录 B：文件结构总览

```
CodeAsk 部署后，OpenCode Backend 涉及的文件：

代码（CodeAsk repo）:
  src/codeask/agent/opencode_compat/
  ├── __init__.py
  ├── sessions.py                  # opencode 会话绑定、状态、恢复
  ├── config.py                    # opencode.json + AGENTS.md
  ├── profiles.py                  # provider profile
  ├── process.py                   # shared server 生命周期
  ├── http.py                      # opencode HTTP API
  ├── events.py                    # 原始事件归档与前端映射
  ├── workspace.py                 # workspace / wiki / attachments
  ├── worktrees.py                 # worktree 暴露
  └── mcp/

数据（运行时）:
  <CODEASK_DATA_DIR>/
  └── agent_sessions/
      └── opencode/
          └── <session_id>/
              ├── home/                    # 隔离 HOME
              ├── workspace/ -> /path/to/repo  # 软链接到代码仓库
              ├── config/
              │   └── opencode.json        # 会话级 LLM 配置
              ├── logs/
              │   └── stream.jsonl         # 原始 SSE 事件归档
              └── state.json               # 映射元数据
```

---

## 参考资料

- [OpenCode GitHub](https://github.com/anomalyco/opencode)
- [OpenCode 配置文档](https://opencode.ai/docs/providers)
- [本目录: 外部 Agent Backend 总设计](./external-agent-backends.md)
- [OpenCode 知识库](/home/hzh/wiki/opencode-docs/index.md) — 项目内部模块文档
