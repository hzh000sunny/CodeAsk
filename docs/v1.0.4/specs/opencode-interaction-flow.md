# OpenCode 对接完整交互流程

> 状态：Draft
> 版本归属：v1.0.4
> 目的：从完整交互链路推导所有模块职责、数据流和状态转换。本文作为后续 PRD、SDD、实施计划和 E2E 测试场景的权威参考。

---

## 0. CodeAsk MCP 传输架构

opencode 通过 MCP 协议调用 CodeAsk 的平台能力。传输方式如下：

```
opencode 进程                                        CodeAsk FastAPI
     │                                                    │
     │  opencode.json 中的 mcp 配置:                       │
     │  "mcp": {                                          │
     │    "codeask": {                                    │
     │      "type": "remote",                             │
     │      "url": "http://127.0.0.1:{port}/api/          │
     │              agent-mcp/sess_abc123"                 │
     │    }                                               │
     │  }                                                 │
     │                                                    │
     │  ① StreamableHTTP connect ─────────────────────────→│ POST /api/agent-mcp/{session_id}/message
     │     (opencode 优先 StreamableHTTP，               │   → 从 URL 路径解析 session_id
     │      fallback SSE)                                 │   → 校验 Authorization header
     │                                                    │
     │  ② initialize ────────────────────────────────────→│ 协商协议版本和能力
     │                                                    │
     │  ③ tools/list ────────────────────────────────────→│ 返回 opencode 专用 MCP tools:
     │                                                    │     list_features
     │                                                    │     get_feature_info
     │                                                    │     list_feature_repos
     │                                                    │     prepare_worktree
     │                                                    │     bind_session_features
     │                                                    │     list_session_attachments
     │                                                    │     read_session_attachment
     │                                                    │
     │  ④ tools/call(get_feature_info, ...) ─────────────→│ 处理: DB查询 + 权限校验 + 审计
     │                                                    │ 返回: feature 信息 + repo 列表
```

**关键设计决策：**

1. **MCP endpoint 内嵌在 CodeAsk FastAPI 中**，不走独立进程。FastAPI 新增 `POST/GET /api/agent-mcp/{session_id}/message` 端点，实现 StreamableHTTP transport。

2. **MCP authentication**：opencode 在 opencode.json 中配置 MCP server headers。CodeAsk 生成 `Authorization: Bearer <session_mcp_token>`，服务端校验 token 与会话匹配。

3. **Session scope**：URL 路径中的 `{session_id}` 由 CodeAsk 在阶段 0 注入到 opencode.json，opencode 不感知 CodeAsk session 概念。CodeAsk MCP handler 从 URL 中解析 session_id，保证会话隔离。

4. **此架构不在本版本实现 MCP Server 独立进程**。CodeAsk MCP 端点复用现有的 FastAPI + 会话管理体系。

5. **MCP tools 面向 opencode 重写**。v1.0.4 不复用旧 CodeAsk Agent 的 tool registry，也不把旧 `search_wiki` 作为 Wiki 主路径。

### 0.1 opencode.json 中的 MCP 配置

阶段 0 生成 opencode.json 时，包含 MCP server 配置：

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "codeask-session": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "CodeAsk Session Provider",
      "options": {
        "baseURL": "https://user-configured-url",
        "apiKey": "${OPENAI_API_KEY}"
      },
      "models": {
        "gpt-4.1": {}
      }
    }
  },
  "mcp": {
    "codeask": {
      "type": "remote",
      "url": "http://127.0.0.1:{codeask_port}/api/agent-mcp/{session_id}",
      "headers": {
        "Authorization": "Bearer {session_mcp_token}"
      },
      "timeout": 30000
    }
  }
}
```

### 0.2 LLM provider profile 选择

CodeAsk 不在 LLM 配置新增或修改时自动联网测试，也不根据厂商名、模型名、URL 域名做后端特判。配置页面提供 OpenCode Provider 下拉框和“测试连接”按钮：

1. 用户保存 LLM 配置时选择一个 OpenCode Provider，默认值为 `default`。
2. `default` 走 opencode native provider：OpenAI 协议使用 `@ai-sdk/openai`，Anthropic 协议使用 `@ai-sdk/anthropic`。
3. 用户可以显式选择 `openai-compatible`、`anthropic-compatible-bearer`、`anthropic-compatible-v1-bearer`、`openrouter` 等通用 profile。
4. 手动“测试连接”只测试当前选中的 provider，不做隐式轮转。
   - 在配置列表行点击“测试连接”时，测试对象是数据库中已保存配置，成功或失败立即写入 `llm_configs.opencode_provider_*`。
   - 在新增表单中点击“测试连接”时，测试对象是尚未保存的表单草稿；测试成功或失败进入该表单隐藏状态。只有用户点击“保存 LLM 配置”时，表单字段和 `opencode_provider_status` / `opencode_provider_tested_at` / `opencode_provider_error` / `opencode_provider_test_result_json` 一起提交并落库。
   - 在编辑表单中点击“测试连接”时，测试对象是当前表单草稿；测试成功或失败只进入该表单隐藏状态，不提前保存配置。只有用户点击“保存修改”时，表单字段和 `opencode_provider_status` / `opencode_provider_tested_at` / `opencode_provider_error` / `opencode_provider_test_result_json` 一起提交并落库。
   - 新增/编辑表单内任一影响连接或配置身份的字段再次变化后，前端必须丢弃上一次草稿测试结果，避免旧状态污染新配置。
5. 会话启动时直接使用当前显式选择的 provider 生成 `opencode.json`；如果配置错误，返回明确错误，不自动切换其它 provider。
6. 当前会话绑定记录中保留 `provider_profile_id`，用于审计本轮实际使用的 provider。

当前可选列表保持少量且通用：

| profile | 语义 |
|---|---|
| `default` | opencode native provider |
| `openai-native` | `@ai-sdk/openai` |
| `openai-compatible` | `@ai-sdk/openai-compatible` |
| `anthropic-native` | `@ai-sdk/anthropic` |
| `anthropic-compatible-bearer` | `@ai-sdk/anthropic` + 原始 Base URL + Bearer header |
| `anthropic-compatible-v1-bearer` | `@ai-sdk/anthropic` + Base URL `/v1` + Bearer header |
| `openrouter` | `@openrouter/ai-sdk-provider` |

---

## 1. 场景设定

本流程使用以下场景覆盖所有关键路径：

> 维护支付系统的工程师，在会话中报告 "feature-payment 的退款接口偶发超时"。
>
> 关联实体：
> - 特性 `feature-payment`（关联仓库 `payment-service`、`payment-gateway`）
> - 特性 `feature-order`（关联仓库 `order-service`）
> - Wiki 文档 `feature-payment/troubleshooting/timeout.md`
> - Wiki 文档 `feature-payment/api/refund.md`
> - 已验证问题报告 #42 "2026-04 退款超时定位"
>
> 用户链路：
> 1. 创建会话 → 发送问题
> 2. opencode 调查（搜索 Wiki → 确定特性 → 准备 worktree → 读代码 → 发现跨特性关联 → 搜索历史报告 → 绑定特性 → 输出结论）
> 3. 多轮追问
> 4. 会话闲置 → opencode 进程杀死 → worktree 清理
> 5. 会话恢复 → opencode 重新拉起 → 缺少 worktree 时调用 MCP 重新准备

---

## 2. 完整交互流

### 阶段 0：会话创建

```
用户操作：前端点击"新建会话"
```

**CodeAsk 后端动作：**

```
1. 创建 Session 记录 (DB: sessions 表)
   └── session_id = "sess_abc123"
   └── title = null (首次消息后自动生成)
   └── status = "active"

2. 确定 Agent Backend
   ├── 读取用户 LLM 配置
   │   ├── provider = "openai" → backend = "opencode"
   │   ├── provider = "anthropic" → backend = "opencode"
   │   └── provider = "openai_compatible" → backend = "opencode"
   └── 写入 Session.metadata_json = { "agent_backend": "opencode" }

3. 创建会话数据目录
   <CODEASK_DATA_DIR>/agent_sessions/sess_abc123/
   ├── workspace/              # opencode cwd
   │   ├── wiki/               # 持久化 Wiki 工作区的零复制挂载
   │   │   └── ...             # 默认 symlink，可配置 bind mount
   │   ├── attachments/        # 会话附件 (上传后拷贝到此)
   │   └── .gitignore          # 忽略 worktree 目录
   ├── home/                   # 隔离 HOME (opencode 配置缓存)
   ├── config/
   │   └── opencode.json       # 会话级 LLM provider 配置
   ├── data/                   # opencode 数据目录 (OPENCODE_DB)
   │   └── opencode.db         # 会话隔离的 SQLite
   └── logs/
       ├── stream.jsonl        # opencode 原始 SSE 事件归档
       └── opcode-stderr.log   # opencode 进程 stderr

4. 生成 opencode.json (基于用户/全局 LLM 配置)
   {
     "provider": {
       "codeask-session": {
         "npm": "@ai-sdk/openai-compatible",
         "name": "CodeAsk Session Provider",
         "options": {
           "baseURL": "https://user-configured-url",
           "apiKey": "${OPENAI_API_KEY}"
         },
         "models": {
           "gpt-4.1": {}
         }
       }
     }
   }

5. 生成 AGENTS.md (写入 workspace 根目录)
   内容见 §3

6. 启动 opencode serve 子进程
   环境变量:
     HOME=<session_dir>/home
     OPENCODE_CONFIG_DIR=<session_dir>/config
     OPENCODE_DB=<session_dir>/data/opencode.db
     OPENAI_API_KEY=<decrypted user key>
   cwd: <session_dir>/workspace
   端口选择:
     从 CODEASK_OPENCODE_PORT_RANGE 中随机选择
     默认范围: 4200-4299
     尝试绑定 → 被占用 → 再随机选 (最多 10 次)
     全部占用 → 资源繁忙错误
   命令: opencode serve --port {selected_port} --hostname 127.0.0.1
   → 进程 PID 记录到内存

7. 创建 opencode session
   POST http://127.0.0.1:{port}/session
   Body: {
     "title": "sess_abc123",
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
       {"permission": "edit",        "action": "deny",  "pattern": "*"}
     ]
   }
   → 得到 opencode_session_id = "ses_4f8a2b1c..."

8. 写入绑定记录 (DB)
   external_agent_sessions:
     id: uuid
     session_id: "sess_abc123"
     backend_type: "opencode"
     external_session_key: "ses_4f8a2b1c..."
     session_dir: "<session_dir>"
     port: 4096
     pid: 12345
     status: "active"
     config_json: "{...opencode.json...}"
```

**此阶段不绑定 Feature。** 特性关联由模型在调查过程中判断。特性和仓库绑定是提供给模型的上下文事实，不是代码调查的硬性前置条件。用户显式指定仓库时，模型可以直接请求 CodeAsk 准备该仓库。

**opencode server 进程粒度已由 Phase 0 spike 初步确认。** opencode 1.14.48 支持一个 shared server 同时承载多个 session，并且可以按 `directory` 加载不同 workspace 下的 `opencode.json`。因此本流程后续按 shared server 优先描述：CodeAsk 为每个会话准备独立 workspace 和独立 `opencode.json`，所有 opencode HTTP 请求都必须携带 `directory`。per-session server 仅作为排障/回退模式保留。

---

### 阶段 1：用户发送第一条消息

```
用户操作：在输入框输入 "feature-payment 退款接口最近偶发超时，帮我分析一下"，点击发送
```

**CodeAsk 后端动作：**

```
1. 创建 SessionTurn (role=user)
   └── turn_id = "turn_001"

2. 组装 CodeAsk system context

   从 DB 查询:
   ├── 所有活跃特性列表 (Feature.id, name, slug, description)
   │   └── SELECT id, name, slug, description FROM features WHERE status='active'
   ├── 每个特性的关联仓库
   │   └── SELECT repo_id, name, url, default_ref FROM repos JOIN feature_repos ...
   ├── 当前会话已有附件 (如果有)
   │   └── SELECT * FROM session_attachments WHERE session_id='sess_abc123'
   ├── 用户可访问仓库列表 (用于用户显式指定仓库时的模型判断)
   └── 持久化 Wiki 工作区挂载路径: ./wiki/

   格式化为 Markdown (见 §4 Context Assembly)

3. 发送消息到 opencode
   POST http://127.0.0.1:{port}/session/ses_4f8a2b1c.../message
   Body: {
     "system": "<CodeAsk assembled context>",
     "messages": [
       {"role": "user", "content": "feature-payment 退款接口最近偶发超时，帮我分析一下"}
     ]
   }

4. 消费 SSE 事件流
   GET http://127.0.0.1:{port}/event
   → 循环读取 opencode SSE 事件
   → 每个事件映射为 CodeAsk ChatRuntimeEvent
   → 写入 agent_traces
   → 通过 SSE 转发到前端

   关键事件映射:
   ├── message.part.delta (text)      → text_delta
   ├── message.updated (tool parts)   → tool_call / tool_result
   ├── session.status (busy/idle)     → 状态切换
   └── session.error                  → error
```

**前端展示：**
- 消息流中逐字显示文本增量
- 行动轨迹中显示 opencode 的工具调用（grep/wiki → read → MCP → read code → ...）
- 行动轨迹标注 `backend: opencode`

---

### 阶段 2：OpenCode Agent 自主调查

opencode 收到消息后，模型基于 system context 和工具能力自主决策。以下是预期调查链路（实际顺序由模型决定）：

```
Step 1: 理解问题，搜索 Wiki
  模型看到 system context 中有 Wiki 路径 ./wiki/
  决定先搜索退款相关文档

  opencode 调用 grep:
    目录: ./wiki/
    关键词: "退款" "refund" "超时"
  → 返回匹配行和文件路径

  opencode 调用 read:
    文件: ./wiki/feature-payment/api/refund.md
    文件: ./wiki/feature-payment/troubleshooting/timeout.md
  → 读到的内容: "退款超时可能与订单服务回调有关"

  [CodeAsk 转发工具事件]
  ├── tool_call: { name: "grep", arguments: { pattern: "退款|refund|超时", path: "./wiki/" } }
  ├── tool_result: { ... }
  ├── tool_call: { name: "read", arguments: { filePath: "./wiki/.../timeout.md" } }
  └── tool_result: { ... }

Step 2: 确定特性，获取仓库信息
  模型判断需要查代码，需要知道 payment 特性关联了哪些仓库

  opencode 调用 CodeAsk MCP:
    get_feature_info(feature_slug="feature-payment")

  → CodeAsk MCP handler:
    a. 查询 DB:
       SELECT f.*, r.id as repo_id, r.name as repo_name, r.url
       FROM features f
       JOIN feature_repos fr ON fr.feature_id = f.id
       JOIN repos r ON r.id = fr.repo_id
       WHERE f.slug = 'feature-payment'
    b. 返回:
       {
         "feature_id": 1,
         "name": "feature-payment",
         "slug": "feature-payment",
         "description": "支付核心系统",
         "repos": [
           {"id": "payment-service", "name": "payment-service", "url": "git@...", "default_ref": "main"},
           {"id": "payment-gateway", "name": "payment-gateway", "url": "git@...", "default_ref": "main"}
         ]
       }

  [CodeAsk 转发工具事件]
  ├── tool_call: { name: "get_feature_info", arguments: { feature_slug: "feature-payment" } }
  └── tool_result: { ... }

Step 3: 准备代码环境
  模型需要查看代码

  opencode 调用 CodeAsk MCP:
    prepare_worktree(repo_id="payment-service", ref="main")

  → CodeAsk MCP handler:
    a. 校验权限: 当前用户是否有该 repo 的访问权限
    b. WorktreeManager.ensure_worktree("payment-service", "sess_abc123")
    c. worktree 创建在: <session_dir>/workspace/payment-service/
    d. 写入审计日志:
       action: "worktree.create"
       session_id: "sess_abc123"
       repo_id: "payment-service"
       ref: "main"
       commit: "abc123def..."
    e. 返回:
       {
         "path": "./payment-service/",
         "repo_id": "payment-service",
         "ref": "main",
         "commit": "abc123def456..."
       }

  [CodeAsk 转发工具事件]
  ├── tool_call: { name: "prepare_worktree", arguments: { repo_id: "payment-service", ref: "main" } }
  └── tool_result: { path: "./payment-service/", commit: "abc123def456..." }

Step 4: 在 worktree 中搜索代码
  模型在 worktree 目录中搜索

  opencode 调用 grep:
    目录: ./payment-service/
    关键词: "refund" "timeout"
  → 发现 src/handlers/refund.go

  opencode 调用 read:
    文件: ./payment-service/src/handlers/refund.go
  → 发现退款逻辑中调用了 order-service 的 gRPC:
    orderClient.ProcessRefund(ctx, request)
    // 未设置超时

  [CodeAsk 转发工具事件]
  ├── tool_call: { name: "grep", arguments: { ... } }
  ├── tool_result: { ... }
  ├── tool_call: { name: "read", arguments: { ... } }
  └── tool_result: { ... }

Step 5: 交叉特性判断
  模型判断 "退款超时可能与订单服务有关" → 需要交叉分析

  opencode 调用 CodeAsk MCP:
    get_feature_info(feature_slug="feature-order")

  → 返回:
    {
      "feature_id": 2,
      "name": "feature-order",
      "repos": [{"id": "order-service", "name": "order-service", ...}]
    }

  opencode 调用 CodeAsk MCP:
    prepare_worktree(repo_id="order-service", ref="main")
  → 返回: { path: "./order-service/", commit: "def789..." }

  opencode 调用 grep:
    目录: ./order-service/
    关键词: "ProcessRefund" "callback" "timeout"
  → 发现 src/callback/handler.go

  opencode 调用 read:
    文件: ./order-service/src/callback/handler.go
  → 发现回调未设置超时时间，确认根因

  [CodeAsk 转发工具事件]
  └── ... (同上模式)

Step 6: 参考历史报告
  模型判断可能有类似问题已被记录

  opencode 调用自身 glob/grep:
    ./wiki/feature-payment/problem-reports/verified/
    ./wiki/feature-order/problem-reports/verified/

  → 命中: ./wiki/feature-order/problem-reports/verified/2026-04-退款超时定位.md

  opencode 调用自身 read:
    ./wiki/feature-order/problem-reports/verified/2026-04-退款超时定位.md

  → 读取完整报告内容，仅作为参考；只有报错、场景、根因完全一致时，才能认为是同一个问题。

  [CodeAsk 转发工具事件]
  └── ...

Step 7: 确定特性绑定
  模型确认问题涉及 feature-payment 和 feature-order

  opencode 调用 CodeAsk MCP:
    bind_session_features(feature_ids=[1, 2])

  → CodeAsk MCP handler:
    a. BEGIN TRANSACTION
    b. DELETE FROM session_features WHERE session_id='sess_abc123'
    c. INSERT INTO session_features (session_id, feature_id, source)
       VALUES ('sess_abc123', 1, 'agent'),
              ('sess_abc123', 2, 'agent')
    d. COMMIT
    e. 写入审计日志:
       action: "session.bind_features"
       session_id: "sess_abc123"
       feature_ids: [1, 2]
       source: "agent"

Step 8: 输出调查结论
  opencode 模型基于以上所有证据生成最终回答:

  "经过分析，退款超时的根因在 order-service 的回调处理中未设置超时时间。"

  附带证据引用:
  - wiki/feature-payment/troubleshooting/timeout.md — 提到退款与订单回调的关联
  - payment-service/src/handlers/refund.go:120 — 调用 orderClient.ProcessRefund 处
  - order-service/src/callback/handler.go:55 — 回调 handler 缺少超时设置
  - 历史报告 #42 — 2026-04 退款超时定位 (已验证)

  [CodeAsk 转发]
  ├── text_delta (逐字)
  ├── evidence (证据列表)
  └── done
```

**关键原则：模型自主决策每一步。** CodeAsk 不预判"应该先查 Wiki 还是先查代码"，不强制走固定流程。

---

### 阶段 3：多轮追问

```
用户操作：在同一会话中追问 "那具体应该怎么修？"
```

**CodeAsk 后端动作：**

```
1. 创建 SessionTurn (role=user, turn_id="turn_002")

2. 将历史 turns (turn_001 的 user message + assistant 回答) 作为 messages 传入

3. POST /session/ses_4f8a2b1c.../message
   Body: {
     "system": "<同上 context (特性已绑定，此处可包含已绑定的 feature 信息)>",
     "messages": [
       // turn_001 的 user/assistant 消息 (由 opencode SQLite 已有，可省略)
       {"role": "user", "content": "那具体应该怎么修？"}
     ]
   }

4. opencode 已有完整上下文 (之前轮次的工具调用结果、代码、报告都在 SQLite 中)
   模型直接基于已有信息回答修复方案

5. SSE 流转发同阶段 1
```

**注意：** opencode SQLite 中已经保存了上一轮的完整上下文（tool calls/results），不需要 CodeAsk 重新注入。CodeAsk 只需要传入新的 user message。

---

### 阶段 4：会话闲置 → 清理

```
系统触发：会话 30 分钟无活跃消息
```

**CodeAsk 定时任务 (CleanupCron)：**

```
1. 查询超时会话
   SELECT * FROM sessions
   WHERE status = 'active'
   AND updated_at < NOW() - INTERVAL '30 minutes'

2. 对每个超时会话:
   a. POST /session/{opencode_sid}/abort  (如果有进行中的 turn)
   b. 发送 SIGTERM 给 opencode 子进程
      ├── 等待 5 秒
      └── 超时未退出 → SIGKILL
   c. 清理 git worktree:
      git worktree remove <session_dir>/workspace/payment-service --force
      git worktree remove <session_dir>/workspace/order-service --force
   d. 更新 DB:
      UPDATE external_agent_sessions SET status='idle' WHERE session_id='sess_abc123'
   e. 写入审计日志:
      action: "agent.cleanup"
      session_id: "sess_abc123"
      reason: "timeout"
      cleaned: ["worktrees: payment-service, order-service", "process: pid=12345"]

3. 会话数据目录保留 (home/ config/ data/ logs/ workspace/{wiki, attachments}/)
   只清理 worktree 和进程，不删除 DB 和日志
```

**不清理的内容：**
- `data/opencode.db` — 会话历史持久化
- `logs/stream.jsonl` — 审计归档
- `config/opencode.json` — 重启时复用
- `workspace/wiki/` — 持久化 Wiki 工作区的零复制挂载
- `workspace/attachments/` — 会话附件

---

### 阶段 5：会话恢复

```
用户操作：重新打开会话 sess_abc123，发送新消息 "order-service 的超时配置是在哪里？"
```

**CodeAsk 后端动作：**

```
1. 查询会话状态
   Session.status = 'active'
   ExternalAgentSession.status = 'idle'
   ExternalAgentSession.external_session_key = "ses_4f8a2b1c..."

2. 检查 opencode 子进程是否存活
   ├── 已死 → 重新启动
   └── 存活 → 复用

3. 检查配置是否变更
   对比 ExternalAgentSession.config_hash 与当前最新配置的 hash:
   ├── 未变更 → 复用旧 opencode.json，不重启
   └── 已变更 (用户换了模型/API key/provider) →
      a. 重新生成 <session_dir>/config/opencode.json
      b. 写入最新 config_hash 到 ExternalAgentSession
      c. 标记需要重启 (opencode 不支持 MCP server 在线热更新)

4. 重新启动 opencode serve (如需要)
   环境变量: 同阶段 0 (HOME, OPENCODE_DB, OPENAI_API_KEY 使用最新值, etc.)
   命令: opencode serve --port <selected_port> --hostname 127.0.0.1
   cwd: <session_dir>/workspace
   → 端口选择策略: 从 CODEASK_OPENCODE_PORT_RANGE (默认 4200-4299) 中随机选
     ├── 尝试端口 → 被占用 → 再随机选
     ├── 最多重试 10 次
     └── 全部占用 → 错误 (资源繁忙)
   → 更新 ExternalAgentSession.port

5. 验证 opencode 会话存在
   GET http://127.0.0.1:{port}/session/ses_4f8a2b1c...
   → 200 OK (会话在 SQLite 中)
   → 消息历史完整保留

6. 检查 worktree 是否存在
   payment-service/ → 不存在 (已被阶段 4 清理)
   order-service/ → 不存在

6. 不需要提前恢复 worktree — opencode 在调查过程中会再次调用 prepare_worktree MCP

7. 发送消息
   POST /session/ses_4f8a2b1c.../message
   Body: {
     "system": "<最新 context，包含会话已绑定 features=[1,2]>",
     "messages": [{"role": "user", "content": "order-service 的超时配置是在哪里？"}]
   }

8. opencode 加载历史消息 (来自 SQLite)，理解当前上下文
   模型判断需要查看 order-service 代码
   → 调用 prepare_worktree(repo_id="order-service")
   → worktree 重建: <session_dir>/workspace/order-service/
   → grep/read 代码
   → 回答

9. SSE 流转发同阶段 1
```

**关键恢复语义：**
- opencode 的 SQLite 保留了完整对话历史和工具调用结果 → 模型记得之前做了什么
- worktree 按需重建：模型调 MCP 时 CodeAsk 重建，对模型透明
- 恢复的会话继续写入同一个 `agent_traces`
- 前端的 Agent 行动轨迹按 turn 分组展示，恢复后的新 turn 是新的一组

---

## 3. 会话 Workspace 布局

opencode 启动时的 cwd 结构：

```text
<session_dir>/workspace/
├── wiki/                          # 只读，CodeAsk 管理的 git repo
│   ├── feature-payment/
│   │   ├── api/
│   │   │   └── refund.md
│   │   ├── architecture.md
│   │   └── troubleshooting/
│   │       └── timeout.md
│   └── feature-order/
│       └── ...
├── attachments/                   # 会话附件 (用户上传)
│   ├── error.log
│   └── trace.json
├── payment-service/               # git worktree (opencode 调 MCP 创建)
│   ├── src/
│   │   └── handlers/
│   │       └── refund.go
│   └── ...
├── order-service/                 # git worktree (opencode 调 MCP 创建)
│   ├── src/
│   │   └── callback/
│   │       └── handler.go
│   └── ...
├── AGENTS.md                      # CodeAsk 写入的静态规则
└── .gitignore                     # 忽略 worktree 目录
```

**路径规则：**
- `wiki/` 始终存在，opencode 始终可以搜索
- `attachments/` 在用户上传后存在
- `<repo-name>/` 仅在 opencode 调用 `prepare_worktree` MCP 后出现
- 所有路径对 opencode 透明的，就是普通的目录结构

---

## 4. Context Assembly

每次发送消息到 opencode 时，CodeAsk 组装的 system context：

```markdown
<!-- CodeAsk Context (managed by CodeAsk, do not modify) -->

## 会话信息
- Session ID: sess_abc123
- 会话目录: /data/agent_sessions/sess_abc123/workspace
- 已绑定特性: feature-payment (id=1), feature-order (id=2)  ← 阶段 2 Step 7 后才有

## 工作区布局
```
./
├── wiki/                   # Wiki 文档 (使用 grep/glob/read 搜索)
├── attachments/            # 会话附件 (使用 read 读取)
├── <repo-name>/            # 代码仓库 worktree (通过 MCP prepare_worktree 创建)
├── AGENTS.md               # 本文件 + CodeAsk 上下文 (已注入到你的 system prompt)
└── .gitignore
```

## 可用特性

下表列出当前系统中所有活跃特性及其关联仓库。
你可以自行判断会话涉及哪些特性，调查完成后调用 `bind_session_features` 绑定。

| ID | 名称 | Slug | 描述 | 关联仓库 |
|----|------|------|------|----------|
| 1 | feature-payment | feature-payment | 支付核心系统 | payment-service, payment-gateway |
| 2 | feature-order | feature-order | 订单系统 | order-service |
| 3 | feature-user | feature-user | 用户系统 | user-service |

## CodeAsk MCP 工具

你可以通过 MCP 工具访问 CodeAsk 的平台能力。
这些是唯一能获取 DB 数据和管理代码环境的方式。

### list_features
列出当前用户可见的活跃特性，可按 query 模糊过滤。
- 参数: query? (string), limit? (number, 默认 50)
- 返回: { features: [{ feature_id, name, slug, description, wiki_path, repo_count }] }

### get_feature_info
获取特性详情和关联仓库列表。
- 参数: feature_id? (number), slug? (string), name? (string)
- 返回: { feature_id, name, slug, description, wiki_path, repos: [{repo_id, name, default_ref, description}] }

### list_feature_repos
列出特性关联仓库；也可在用户显式指定仓库时按 query 搜索用户可访问仓库。
- 参数: feature_id? (number), query? (string), limit? (number, 默认 20)
- 返回: { repos: [{ repo_id, name, default_ref, feature_ids }] }

### prepare_worktree
为指定仓库的指定 ref 创建 git worktree。
- 参数: repo_id? (string), repo_name? (string), ref? (string, 默认 default ref), reason? (string)
- 返回: { path, repo_id, ref, commit }
- 注意: worktree 使用现有 WorktreeManager 从数据目录 bare repo 创建，再暴露到 opencode cwd 下，相对路径可直接 read/grep

### bind_session_features
将会话绑定到特性列表。调用时机：确认会话涉及哪些特性后。
- 参数: feature_ids (int[]), reason? (string)
- 返回: { bound: feature_ids }

### list_session_attachments
列出当前会话的附件元数据。
- 参数: query? (string), limit? (number, 默认 20)
- 返回: [{ id, display_name, original_filename, description, size, mime_type }]

### read_session_attachment
读取无法直接用 opencode read 工具处理的附件内容或元数据。
- 参数: attachment_id (string), max_chars? (number, 默认 12000)
- 返回: { attachment_id, filename, content, truncated }

注意:
- Wiki 文档请直接用 grep/glob/read 搜索 ./wiki/ 目录；不要调用旧 CodeAsk `search_wiki`
- 问题报告也是 Wiki 文件目录的一部分，请直接用 grep/glob/read 搜索 `./wiki/<feature_slug>/problem-reports/`
- 优先读取 `problem-reports/verified/`；报告只作为参考，除非报错、场景和根因完全一致
- `problem-reports/drafts/` 只作为弱背景，不作为结论依据
- 代码请先通过 prepare_worktree 准备环境，再用 grep/glob/read
- 附件可直接 read ./attachments/ 下的文件
- 不要猜测特性绑定，调查完成后再调用 bind_session_features
<!-- End CodeAsk Context -->
```

**规则：**
- 特性列表仅包含 `status='active'` 的特性
- 如果会话已有绑定特性，在"会话信息"中明确列出
- context 在 system prompt 的最后一段，不会覆盖 opencode 自己的 prompt
- context 由 CodeAsk 每个 turn 动态生成（特性、附件可能变化）

---

## 5. CodeAsk MCP 工具规格

### 5.1 get_feature_info

```
功能: 查询特性元数据和关联仓库 (数据在 DB，opencode 无法从文件获取)

输入:
  feature_slug: string  # 特性 slug

处理:
  1. SELECT f.*, array_agg(json_build_object(...)) as repos
     FROM features f
     JOIN feature_repos fr ON fr.feature_id = f.id
     JOIN repos r ON r.id = fr.repo_id
     WHERE f.slug = $feature_slug AND f.status = 'active'
     GROUP BY f.id
  2. 如果未找到，返回错误

输出:
  {
    "feature_id": int,
    "name": "feature-payment",
    "slug": "feature-payment",
    "description": "支付核心系统",
    "repos": [
      {"id": "payment-service", "name": "payment-service",
       "url": "git@github.com:org/payment-service.git", "default_ref": "main"}
    ]
  }

权限: 所有用户可读 (特性元数据公开)
审计: 不记录 (只读)
```

### 5.2 prepare_worktree

```
功能: 为仓库创建 git worktree。opencode 无法自己执行 git 操作，必须由 CodeAsk 代理。

输入:
  repo_id: string   # 仓库 ID
  ref: string|null  # git ref (branch/tag/commit)，null 时使用 default_ref

处理:
  1. 校验用户对 repo_id 的访问权限
  2. 解析 ref → commit SHA
     WorktreeManager.resolve_ref(repo_id, ref or default_ref)
  3. 创建 worktree
     path = WorktreeManager.ensure_worktree(repo_id, session_id, commit_sha)
     实际路径: <session_dir>/workspace/<repo_name>/
  4. 如果 worktree 已存在且 commit 相同 → 直接返回路径
     如果 worktree 已存在但 commit 不同 → 删除旧的，创建新的

输出:
  {
    "path": "./payment-service/",     # 相对 cwd 的路径
    "repo_id": "payment-service",
    "ref": "main",
    "commit": "abc123def456..."
  }

错误:
  - repo 不存在 → "repo not found: {repo_id}"
  - ref 无效 → "ref {ref} does not resolve in {repo_id}"
  - 权限不足 → "permission denied: {repo_id}"

权限: 需要用户对该 repo 有读取权限
审计:
  action: "worktree.create"
  session_id: ...
  repo_id: ...
  ref: ...
  commit: ...
  result: "success" | "error"
```

### 5.3 bind_session_features

```
功能: 将会话绑定到特性列表。由模型在调查完成后调用。

输入:
  feature_ids: int[]

处理:
  1. 校验所有 feature_id 存在且状态为 active
  2. BEGIN TRANSACTION
  3. DELETE FROM session_features WHERE session_id = $session_id AND source = 'agent'
  4. INSERT INTO session_features (session_id, feature_id, source, created_at)
     VALUES ($session_id, $feature_id, 'agent', NOW())
     FOR EACH feature_id
  5. COMMIT

输出:
  {
    "bound": [1, 2],
    "features": [{id: 1, name: "feature-payment", slug: "..."}, ...]
  }

权限: 无特殊限制 (任何用户可绑定)
审计:
  action: "session.bind_features"
  session_id: ...
  feature_ids: ...
  source: "agent"
```

### 5.4 list_session_attachments

```
功能: 列出当前会话附件的元数据。附件文件在 ./attachments/ 下可用 grep/read，
     但元数据 (display_name, description, reference_names) 只在 DB。

输入: 无 (session_id 从 opencode → CodeAsk 上下文获取)

处理:
  SELECT * FROM session_attachments WHERE session_id = $session_id

输出:
  [
    {
      "id": "att_xyz",
      "display_name": "退款接口错误日志",
      "original_filename": "error.log",
      "aliases": ["退款日志"],
      "reference_names": ["error.log"],
      "description": "用户上传的退款接口超时日志",
      "size": 1048576,
      "mime_type": "text/plain",
      "file_path": "./attachments/error.log"
    }
  ]

权限: 会话隔离 (只能看到本会话的附件)
```

### 5.5 Wiki 与问题报告目录

opencode runtime 不提供 `search_reports` / `read_report` MCP 工具。问题报告和知识库一起导出为会话 workspace 下的 Markdown 文件，由 opencode 自己使用 `glob`、`grep`、`read` 访问。

```
./wiki/<feature_slug>/
├── README.md
├── knowledge-base/
│   └── *.md
└── problem-reports/
    ├── verified/
    │   └── *.md
    └── drafts/
        └── *.md
```

处理要求：

1. `knowledge-base/` 是主知识库，先用于理解特性边界、术语和流程。
2. `problem-reports/verified/` 是已验证问题定位报告，只能作为参考；报错、场景、根因完全一致时，才可判断为同类问题。
3. `problem-reports/drafts/` 是草稿报告，只作为弱背景，不能单独支撑结论。
4. 模型需要查报告时，使用 opencode 原生文件工具在 `./wiki/<feature_slug>/problem-reports/` 中检索和读取，不经过 CodeAsk 封装检索工具。

---

## 6. 状态机

### 6.1 CodeAsk 会话 Agent Backend 状态

```
                    ┌──────────┐
        会话创建     │          │
     ──────────────→│ STARTING │
                    │          │
                    └─────┬────┘
                          │ opencode 进程启动成功 + session 创建成功
                          ▼
                    ┌──────────┐
          ┌─────────│  ACTIVE  │─────────┐
          │         │          │         │
          │         └─────┬────┘         │
          │               │              │
          │  用户发消息    │   30min 无活动 │
          │               ▼              │
          │         ┌──────────┐         │
          │         │  BUSY    │         │
          │         │ (SSE流)  │         │
          │         └─────┬────┘         │
          │               │              │
          │  turn 完成     │  用户点停止   │
          │               ▼              │
          │         ┌──────────┐         │
          │         │  ACTIVE  │         │
          │         └──────────┘         │
          │                              │
          │                              ▼
          │                        ┌──────────┐
          │                        │   IDLE   │
          │                        │ (进程已杀) │
          │                        └─────┬────┘
          │                              │
          │              用户重新发消息    │
          │                              ▼
          │                        ┌──────────┐
          └────────────────────────│ RESTORING│
                                   │ (重拉进程)│
                                   └─────┬────┘
                                         │ 恢复成功
                                         ▼
                                   ┌──────────┐
                                   │  ACTIVE  │
                                   └──────────┘
```

### 6.2 ExternalAgentSessions 状态

```
STARTING  → ACTIVE  → IDLE  → RESTORING  → ACTIVE
                ↓                  ↓ (失败)
              ERROR              ERROR
```

### 6.3 数据库记录 (external_agent_sessions)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| session_id | FK → sessions.id | CodeAsk 会话 ID |
| backend_type | "opencode" | "claude_code" | Agent 后端类型 |
| external_session_key | string | opencode 的 session ID (ses_xxx) |
| session_dir | string | 会话数据目录绝对路径 |
| port | int | opencode HTTP 端口 |
| pid | int | opencode 子进程 PID |
| status | "starting"\|"active"\|"busy"\|"idle"\|"error" | 后端状态 |
| config_hash | string | 当前 opencode.json + env 的 SHA256，用于检测配置变更 |
| config_json | JSON | opencode.json 配置快照 |
| last_active_at | datetime | 最后一次 SSE 事件的时间 |
| created_at | datetime | |
| updated_at | datetime | |

---

## 7. 进程生命周期管理

### 7.1 启动

```python
class OpenCodeProcessManager:
    async def start(self, session_id: str, session_dir: Path) -> OpenCodeProcess:
        env = {
            "HOME": str(session_dir / "home"),
            "OPENCODE_CONFIG_DIR": str(session_dir / "config"),
            "OPENCODE_DB": str(session_dir / "data" / "opencode.db"),
            "OPENAI_API_KEY": self._decrypt_key(user_llm_config.api_key),
        }
        proc = await asyncio.create_subprocess_exec(
            "opencode", "serve",
            "--port", "0",
            "--hostname", "127.0.0.1",
            cwd=str(session_dir / "workspace"),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=open(session_dir / "logs" / "opencode-stderr.log", "a"),
        )
        # 解析 stdout 第一行: "Server listening on http://127.0.0.1:4096"
        line = await asyncio.wait_for(proc.stdout.readline(), timeout=10)
        port = self._parse_port(line)
        return OpenCodeProcess(proc=proc, port=port, pid=proc.pid)
```

### 7.2 停止

```python
async def stop(self, session_id: str):
    proc = self._processes.get(session_id)
    if not proc:
        return
    # 先中断当前 turn
    await self._http.post(f"/session/{opencode_sid}/abort")
    # 优雅终止
    proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=5)
    except asyncio.TimeoutError:
        proc.kill()
    del self._processes[session_id]
```

### 7.3 空闲清理

```python
async def cleanup_idle_sessions(self):
    idle_sessions = await self._db.query(
        "SELECT * FROM external_agent_sessions "
        "WHERE status IN ('active', 'busy') "
        "AND last_active_at < NOW() - INTERVAL '30 minutes'"
    )
    for s in idle_sessions:
        await self.stop(s.session_id)
        await self._worktree_mgr.cleanup_session_worktrees(s.session_id)
        await self._db.update(
            "UPDATE external_agent_sessions SET status='idle' WHERE id=?", s.id
        )
```

### 7.4 恢复

```python
async def ensure_running(self, session_id: str) -> OpenCodeProcess:
    existing = self._processes.get(session_id)
    if existing and existing.returncode is None:
        return existing
    # 重新启动
    session = await self._db.get_external_session(session_id)
    proc = await self.start(session_id, Path(session.session_dir))
    # 验证会话存在
    resp = await self._http.get(f"/session/{session.external_session_key}")
    if resp.status != 200:
        # 会话在 opencode DB 中丢失 (极端情况: DB 文件被删)
        # → 重新创建 opencode session
        new_sid = await self._create_opencode_session(proc.port)
        await self._db.update(..., external_session_key=new_sid)
    self._processes[session_id] = proc
    return proc
```

### 7.5 端口范围分配

```python
class PortAllocator:
    def __init__(self, port_range: str = "4200-4299"):
        start, end = port_range.split("-")
        self._range = range(int(start), int(end) + 1)
        self._used: set[int] = set()

    def allocate(self) -> int:
        available = [p for p in self._range if p not in self._used]
        if not available:
            raise RuntimeError("No available ports in range")
        for _ in range(10):
            port = random.choice(available)
            if self._is_port_free(port):
                self._used.add(port)
                return port
        raise RuntimeError("Failed to allocate port after 10 retries")

    def release(self, port: int) -> None:
        self._used.discard(port)

    def _is_port_free(self, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return True
            except OSError:
                return False
```

环境变量 `CODEASK_OPENCODE_PORT_RANGE` 控制端口范围，默认 `4200-4299`。

### 7.6 配置变更检测与重启

opencode 不支持 MCP server 的在线热更新（MCP 连接仅在启动时建立），因此配置变更需要重启对应 workspace 的运行上下文。shared server 模式下优先重建该会话 workspace 的 `opencode.json`，必要时重启 shared server 或切换到 per-session server 排障模式。

**配置变更检测：**

```python
def _compute_config_hash(self, session_id: str) -> str:
    """计算当前最新配置的 SHA256，与 DB 中的 config_hash 对比"""
    llm_config = self._llm_gateway.get_session_config(session_id)
    codeask_port = self._settings.port
    data = json.dumps({
        "provider": llm_config.to_opencode_provider(),
        "mcp_url": f"http://127.0.0.1:{codeask_port}/api/agent-mcp/{session_id}",
        "api_key_sha256": sha256(llm_config.api_key).hexdigest(),
    }, sort_keys=True)
    return sha256(data.encode()).hexdigest()
```

**会话恢复时的判断流程：**

```
new_hash = _compute_config_hash(session_id)
stored_hash = external_session.config_hash

if new_hash == stored_hash:
    // 配置未变更
    if process_is_alive:
        reuse_process()
    else:
        restart_process(reuse_config=True)
else:
    // 配置已变更 → 重新生成 opencode.json → 重启
    regenerate_opencode_json(session_id, llm_config)
    kill_old_process(session_id)
    start_new_process(session_id)
    update_config_hash(session_id, new_hash)
```

**什么变化会触发重启：**
- 用户更换 LLM provider
- 用户更换 API key
- 用户更换模型
- CodeAsk 端口变化 (极少见)

**什么变化不会触发重启：**
- 用户在同一 provider 下微调参数 (如 temperature)
- 用户的个人 LLM 配置没变
- 全局 LLM 配置池变化但 session 有粘性

---

## 8. AGENTS.md 内容

CodeAsk 在 `workspace/AGENTS.md` 写入的规则：

```markdown
# AGENTS.md

## 环境说明

你在 CodeAsk 平台中运行，作为一个研发问题调查 Agent。
你的工作目录 (cwd) 是一个会话隔离的工作区。

## 工作区规则

1. 所有调查活动限制在 cwd 范围内。
2. 不要尝试访问 cwd 以外的文件系统路径。
3. 不要执行 shell 命令（已禁用）。
4. 不要修改任何文件（已禁用 Write/Edit/Bash）。

## 可用能力

### 文件搜索
- 使用 grep 搜索 Wiki 文档 (./wiki/)
- 使用 glob 查找文件
- 使用 read 读取文件内容
- 使用 list 列出目录

### 代码调查
- 需要查看代码时，先调用 CodeAsk MCP 的 `get_feature_info` 了解特性关联的仓库
- 然后调用 `prepare_worktree` 让 CodeAsk 准备代码环境
- worktree 准备好后，使用 grep/read 在仓库目录中搜索和分析

### 附件
- 使用 `list_session_attachments` 查看会话附件
- 使用 read 读取 ./attachments/ 下的文件

### Wiki
- 直接 grep/read ./wiki/ 目录，不需要通过 MCP

### 历史报告
- 直接 grep/read `./wiki/<feature_slug>/problem-reports/`，优先参考 `verified/`
- 已验证报告也只作为参考，除非报错、场景和根因完全一致
- 草稿报告只作为弱背景

## CodeAsk MCP 工具

所有 MCP 工具通过标准的 MCP 协议调用。
每个工具调用会被审计记录。

- get_feature_info: 获取特性详情和仓库绑定
- prepare_worktree: 准备代码仓库 worktree
- bind_session_features: 确定会话涉及的特性
- list_session_attachments: 列出会话附件
```

---

## 9. E2E 测试场景

基于上述完整流程，E2E 测试覆盖以下场景：

| 场景 | 覆盖阶段 | 验证点 |
|------|---------|--------|
| opencode API spike | Phase 0 | 目标 opencode 版本的 server/message/prompt_async/event/MCP/permission 主路径实测；abort/revert 深度回滚列遗留增强 |
| 会话创建 | 阶段 0 | 数据目录结构正确；opencode 进程启动；session 绑定记录写入 |
| Wiki 工作区 | 阶段 0 | `workspace/wiki` 零复制指向持久化 Wiki 工作区；特性为一级目录 |
| 首次问答 (wiki 搜索) | 阶段 1 + 2 (Step 1) | system context 正确注入；opencode 能 grep/read wiki；SSE 流转发 |
| MCP 工具调用 | 阶段 2 (Step 2-3) | get_feature_info 返回正确；prepare_worktree 创建目录；权限校验 |
| 显式仓库访问 | 阶段 2 (Step 3) | 用户指定仓库时，无需先绑定特性也能准备 worktree，并写入审计 |
| 跨特性分析 | 阶段 2 (Step 5) | 第二次 get_feature_info + prepare_worktree 成功 |
| 特性绑定 | 阶段 2 (Step 7) | bind_session_features 写入 DB；审计日志记录 |
| 历史报告参考 | 阶段 2 (Step 6) | opencode 使用 glob/grep/read 访问 `./wiki/<feature_slug>/problem-reports/`；MCP 工具列表不包含报告检索/读取工具 |
| 多轮追问 | 阶段 3 | 同一 opencode session 接收第二条消息；上下文保留 |
| 空闲清理 | 阶段 4 | 超时后进程被杀；worktree 被清理；DB 标记 idle |
| 会话恢复 | 阶段 5 | opencode 重新启动；session 仍可访问；worktree 按需重建 |
| 用户中断 | 遗留增强 | 主功能阶段先保证停止输出和状态清理；POST abort + revert 深度回滚后续单独验证 |
| 错误恢复 | — | opencode 崩溃后重建 session；DB 文件损坏的降级处理 |

---

## 10. 待验证问题

1. opencode 目标版本 — 用户后续提供 CodeAsk v1.0.4 对应 opencode 版本后，Phase 0 必须以该版本为准。
2. opencode MCP client 集成 — 需用真实版本验证 remote MCP URL 应指向根路径还是 message endpoint。
3. opencode Session SQLite 在跨进程重启后是否完全保留消息历史。
4. 一个 opencode server 是否可以安全服务多个 CodeAsk 会话，并隔离 workspace、LLM 配置、MCP token 和历史。
5. `message` 与 `prompt_async` 哪个更适合作为 CodeAsk 发送消息主路径。
6. `/event` 与 `/global/event` 的事件差异和订阅策略。
7. abort + revert 是否能彻底清理中断 turn 的 opencode 内部上下文。此项不阻塞主功能开发，作为遗留增强项。
8. 多会话并发资源限制：端口、内存、DB 连接。
9. opencode 会话迁移：如果 opencode 版本升级导致 DB schema 变更，已有会话如何迁移。
10. wiki 目录实时性：v1.0.4 默认 live view，后续是否需要会话级快照。
11. MCP Server OAuth：当前设计使用 Bearer token，后续可升级为 OAuth。
