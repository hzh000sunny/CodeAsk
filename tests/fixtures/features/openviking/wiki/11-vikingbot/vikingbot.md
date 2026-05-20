# 11 VikingBot 代理框架 (bot/vikingbot)

## 1. 模块概览

VikingBot 是基于 OpenViking 构建的 AI Agent 框架，提供多通道聊天机器人、沙箱工具执行、LLM 可观测性和 FUSE 文件系统挂载。

| 子模块 | 用途 |
|---|---|
| `agent/` | ReAct 代理循环 + 工具系统 + 上下文构建 |
| `channels/` | 12 种通信通道 (Telegram, Discord, Slack, Feishu...) |
| `providers/` | LLM 提供商抽象 (LiteLLM + OpenAI 兼容) |
| `sandbox/` | 4 种沙箱后端 (Direct, Docker, K8s, SRT) |
| `hooks/` | 钩子系统 (生命周期回调) |
| `openviking_mount/` | OpenViking ↔ 本地文件系统挂载 (FUSE + API) |
| `bus/` | 异步消息总线 (发布/订阅) |
| `session/` | 会话管理 (JSONL 持久化) |
| `cron/` | 定时任务调度 (at/every/cron) |
| `heartbeat/` | 心跳服务 (定时唤醒代理) |
| `observability/` | 反馈统计 + 响应结果评估 |
| `integrations/` | Langfuse LLM 可观测性集成 |
| `config/` | 分层配置 (Pydantic Schema) |

---

## 2. Agent 核心 (agent/)

### 2.1 AgentLoop - ReAct 循环

```python
class AgentLoop:
    """核心代理循环: 观察 → 思考 → 行动 → 观察"""
    
    async def process(message, session, bus) -> None:
        # 1. 构建上下文 (ContextBuilder)
        # 2. 循环 (至多 max_iterations):
        #    a. LLM 调用 (含工具定义)
        #    b. 如有工具调用:
        #       - 并行执行工具 (asyncio.gather)
        #       - 注入工具结果
        #       - 继续循环
        #    c. 如无工具调用: 输出响应
        # 3. 发布 OutboundMessage 到总线
```

### 2.2 ContextBuilder - 上下文构建

```python
class ContextBuilder:
    """构建 LLM 提示词上下文"""
    
    # 上下文组成:
    # 1. System Prompt (SOUL.md + AGENTS.md)
    # 2. 用户身份 (USER.md)
    # 3. 可用技能 (skills/)
    # 4. 记忆 (OpenViking search + MEMORY.md + HISTORY.md)
    # 5. 工作区信息 (WORKSPACE.md)
    # 6. 对话历史 (最近 N 轮)
    # 7. 当前用户消息
```

### 2.3 工具系统 (agent/tools/)

#### 工具基类

```python
class ToolBase(ABC):
    name: str
    description: str
    parameters: Dict[str, Any]   # JSON Schema
    
    @abstractmethod
    async def execute(ctx, **params) -> Any
    
    def to_schema() -> Dict:      # → OpenAI function schema
```

#### 内置工具清单

| 工具文件 | 工具 | 说明 |
|---|---|---|
| `filesystem.py` | `read`, `write`, `ls`, `mkdir`, `rm`, `mv`, `tree` | 文件系统操作 (工作区) |
| `shell.py` | `shell` | Shell 命令执行 (沙箱内) |
| `web.py` | `web_fetch`, `web_search` | HTTP 请求 + 网页内容提取 |
| `websearch/` | `search_brave`, `search_ddgs`, `search_exa`, `search_tavily` | 多搜索引擎 |
| `message.py` | `send_message` | 向通道发送消息 |
| `mcp.py` | `mcp_call` | 调用外部 MCP 工具 |
| `cron.py` | `cron_add`, `cron_list`, `cron_remove` | 定时任务管理 |
| `image.py` | `generate_image`, `analyze_image` | 图像生成/分析 |
| `spawn.py` | `spawn_subagent` | 创建子代理 |
| `ov_file.py` | `ov_search`, `ov_read`, `ov_browse`, `ov_grep` | OpenViking 上下文检索 |

#### 工具注册表

```python
class ToolRegistry:
    def register(tool: ToolBase)
    def get(name: str) -> ToolBase
    def list_all() -> List[ToolBase]
    def get_schemas() -> List[Dict]       # → OpenAI function schemas
```

#### 子代理 (spawn.py)

```python
class SubAgent:
    """隔离的子代理, 有限迭代 + 受限工具集"""
    async def run(prompt, tools, max_iterations=5) -> str
```

### 2.4 Web 搜索 (agent/tools/websearch/)

| 引擎 | 类 | 说明 |
|---|---|---|
| Brave | `BraveSearch` | Brave Search API |
| DuckDuckGo | `DuckDuckGoSearch` | 免费搜索 (ddgs) |
| Exa | `ExaSearch` | Exa AI 搜索 API |
| Tavily | `TavilySearch` | Tavily AI 搜索 API |

---

## 3. 通道系统 (channels/)

### 3.1 通道基类

```python
class ChannelBase(ABC):
    name: str
    
    @abstractmethod
    async def start(bus: MessageBus, config: Dict)
    @abstractmethod
    async def stop()
```

### 3.2 通道清单

| 通道文件 | 通道 | 依赖 |
|---|---|---|
| `telegram.py` | Telegram Bot | `python-telegram-bot` |
| `discord.py` | Discord Bot | `discord.py` |
| `slack.py` | Slack Bot | `slack-sdk` |
| `feishu.py` | 飞书 (Lark) | `lark-oapi` |
| `dingtalk.py` | 钉钉 | `dingtalk-stream` |
| `whatsapp.py` | WhatsApp | `bridge/` (Node.js) |
| `qq.py` | QQ | `qq-botpy` |
| `email.py` | Email | SMTP/IMAP |
| `openapi.py` | OpenAPI (HTTP) | FastAPI |
| `mochat.py` | MoChat | 内部 |
| `single_turn.py` | 单轮对话 | 无 |
| `botchannel.py` | Bot-to-Bot | 内部 |
| `chat.py` | CLI 交互式聊天 | prompt_toolkit |

### 3.3 通道管理器

```python
class ChannelManager:
    def add_channel(channel, config)
    async def start_all()
    async def stop_all()
    async def status() -> Dict[str, bool]
```

---

## 4. 沙箱系统 (sandbox/)

### 4.1 SandboxBackend 抽象

```python
class SandboxBackend(ABC):
    async def create_workspace(session_key) -> str
    async def exec_command(workspace, command, timeout) -> str
    async def read_file(workspace, path) -> bytes
    async def write_file(workspace, path, data) -> None
    async def delete_workspace(workspace) -> None
```

### 4.2 四种后端

| 后端 | 文件 | 隔离级别 | 说明 |
|---|---|---|---|
| `DirectBackend` | `direct.py` | 无 | 直接在主机执行 (仅开发) |
| `AioSandboxBackend` | `aiosandbox.py` | Docker 容器 | 基于 agent-sandbox SDK |
| `OpenSandboxBackend` | `opensandbox.py` | K8s Pod | 基于 opensandbox SDK, 支持 PVC 挂载 |
| `SRTBackend` | `srt.py` | 沙箱运行时 | 基于 @anthropic-ai/sandbox-runtime, Node.js JSON 协议 |

### 4.3 SandboxManager

```python
class SandboxManager:
    # 三种模式:
    # - shared: 所有会话共享一个沙箱
    # - per_channel: 每个通道一个沙箱
    # - per_session: 每个会话一个沙箱
    
    async def get_workspace(session_key) -> str
    async def ensure_session_workspace(session_key) -> None
    async def cleanup_session(session_key) -> None
```

---

## 5. LLM 提供商 (providers/)

### 5.1 提供商基类

```python
class BaseLLMProvider(ABC):
    async def chat(messages, tools, **kwargs) -> LLMResponse
    async def chat_stream(messages, tools, **kwargs) -> AsyncIterator[str]
```

### 5.2 LiteLLM 提供商

```python
class LiteLLMProvider(BaseLLMProvider):
    """通过 LiteLLM 支持 100+ 模型提供商"""
    # model 格式: "provider/model_name"
    # 自动检测: gpt→openai, claude→anthropic, gemini→gemini...
    # 环境变量透传
```

### 5.3 OpenAI 兼容提供商

```python
class OpenAICompatibleProvider(BaseLLMProvider):
    """OpenAI API 兼容的通用的提供商"""
    # 支持任何 OpenAI 兼容端点
    # 自定义 api_base, api_key, headers
```

---

## 6. OpenViking 挂载 (openviking_mount/)

### 6.1 挂载方式

```
FUSE 模式:           API 模式:
───────              ────────
POSIX 文件系统       HTTP API 代理
   │                    │
   ▼                    ▼
OpenVikingFUSE       OpenVikingMount
(Operations)         (同步客户端)
   │                    │
   ▼                    ▼
  OpenViking 服务器 ←────┘
```

### 6.2 五种 FUSE 实现

| 实现 | 文件 | 特点 |
|---|---|---|
| Standard | `fuse_simple.py` | 基础实现, PDF 自动上传 |
| Debug | `fuse_simple_debug.py` | 所有操作日志记录 |
| Finder | `fuse_finder.py` | 文件隐藏 (.DS_Store), PDF 目录表示 |
| Proxy | `fuse_proxy.py` | 反向代理到 `.original_files/` |
| Viking | `viking_fuse.py` | 完整 FUSE + FUSEMountManager (多进程) |

### 6.3 VikingClient - 代理 OpenViking 集成

```python
class VikingClient:
    """代理的 OpenViking API 集成入口"""
    
    # URI 构造 (含命名空间策略)
    def get_agent_space_name(user_id) -> str        # MD5 哈希
    def _memory_target_uri(user_id) -> str           # 用户记忆目标 URI
    def _agent_memory_target_uri(user_id) -> str     # Agent 记忆目标 URI
    
    # 上下文操作
    async def find(query, target_uri) -> List
    async def search(query, target_uri, limit) -> List
    async def list_resources(path, recursive) -> List
    async def read_content(uri, level) -> str
    async def grep(uri, pattern, ...) -> Dict
    async def search_memory(query, user_ids, agent_id) -> List
    async def search_experiences(query) -> List
    
    # 提交
    async def commit(session_id, messages, user_id) -> Dict
    # - 将消息转换为 Part (TextPart, ToolPart)
    # - 从 read_file 结果中提取 skill URIs
    # - 处理 root vs user API key 模式
    
    # 用户管理 (root 模式)
    async def _initialize_user(user_id, role) -> None
    async def _get_or_create_user_apikey(user_id) -> str
```

### 6.4 UserApiKeyManager

```python
class UserApiKeyManager:
    """用户 API Key 持久化管理器"""
    # 存储: {ov_path}/user_apikeys_{hash}.json
    # hash = MD5(server_url + account_id)
    # 方法: get_apikey, set_apikey, delete_apikey
```

---

## 7. 消息总线 (bus/)

```python
# 入站:  通道 → 总线 → 代理
# 出站:  代理 → 总线 → 通道

class MessageBus:
    _inbound: asyncio.Queue[InboundMessage]
    _outbound: asyncio.Queue[OutboundMessage]
    
    async def publish_inbound(msg)       # 通道发布消息
    async def consume_inbound() -> msg   # 代理消费消息
    async def publish_outbound(msg)      # 代理发布响应
    async def subscribe_outbound(channel_key, callback)  # 通道订阅响应
```

---

## 8. 会话管理 (session/)

```python
class SessionManager:
    """JSONL 持久化会话管理"""
    # 文件格式:
    # Line 1: {"_type": "metadata", "session_key": "...", "created_at": "...", "metadata": {...}}
    # Lines 2+: {"role": "user", "content": "...", "timestamp": "..."}
    
    async def get_or_create(key) -> Session
    async def save(session)             # 合并元数据, 写回 JSONL
    async def update_session(key, updater)  # 互斥: 重载-修改-持久化
    async def list_sessions() -> List   # 扫描 *.jsonl
    async def delete(key)               # 清理沙箱 + 删除文件
```

---

## 9. 调度 & 心跳

### 9.1 CronService

```python
class CronService:
    """定时任务调度器, JSON 持久化"""
    
    # 三种调度模式:
    # - at:    一次性 (at_ms 毫秒时间戳)
    # - every: 周期性 (every_ms 毫秒间隔)
    # - cron:  Cron 表达式 (croniter 解析)
    
    async def add_job(name, schedule, message, session_key) -> CronJob
    async def remove_job(job_id) -> bool
    async def enable_job(job_id, enabled) -> CronJob
    async def run_job(job_id, force) -> bool
    async def list_jobs(include_disabled) -> List[CronJob]
```

### 9.2 HeartbeatService

```python
class HeartbeatService:
    """定时唤醒代理检查 HEARTBEAT.md"""
    # 默认间隔: 30 分钟
    # 过期阈值: 2 天未更新的会话自动跳过
    # 检查 HEARTBEAT.md 是否有可操作内容
    # 如为空 → 回复 HEARTBEAT_OK
```

---

## 10. 可观测性 (observability/)

### 10.1 反馈统计

```python
def compute_feedback_stats(bot_data_path, ...) -> Dict:
    """离线反馈聚合, 31 个可排序指标"""
    # channels → sessions/*.jsonl → metadata.feedback_events
    # 输出: summary_rows, channel_rows, session_rows
    
    # 核心指标:
    # - responses_total, feedback_coverage, thumbs_up_rate
    # - one_turn_resolution_rate, reask_rate
    # - outcomes_total, positive_feedback_total
```

### 10.2 结果评估

```python
def evaluate_response_outcome(messages, response_id, ...) -> OutcomeEvaluation:
    """响应结果评估 (10 分钟重问窗口)"""
    # 结果标签 (优先级):
    # negative_feedback → positive_feedback → reasked →
    # resolved → follow_up_without_feedback → follow_up
```

### 10.3 Langfuse 集成

```python
class LangfuseClient:
    """Langfuse v3 LLM 可观测性"""
    # 单例模式 (Langfuse.get_instance/set_instance)
    # Trace/span/generation/tool_call 包装器
    # propagate_attributes 上下文管理器
    # 结果标签评分 (CATEGORICAL)
```

---

## 11. CLI (cli/commands.py)

```bash
# 网关模式 (多通道)
vikingbot gateway --port 8080

# 交互式聊天
vikingbot chat
vikingbot chat --message "Hello" --session-id test --markdown

# 通道管理
vikingbot channels status
vikingbot channels login    # WhatsApp QR 登录

# 定时任务
vikingbot cron list
vikingbot cron add --name "daily" --every 86400 --message "..."

# 反馈统计
vikingbot feedback-stats
vikingbot feedback-stats --sessions --sort-by thumbs_up_rate --top 10
```

---

## 12. 配置 (config/)

```python
# 分层配置结构:
VikingBotConfig
├── server: ServerConfig       # 网关端口/主机
├── channels: List[ChannelConfig]   # Telegram, Discord...
├── providers: List[ProviderConfig] # LLM 提供商
├── sandbox: SandboxConfig     # 沙箱类型/模式
├── agent: AgentConfig         # 代理行为
├── openviking: OVConfig       # OpenViking 连接
├── langfuse: LangfuseConfig   # 可观测性
├── cron: CronConfig           # 定时任务
└── heartbeat: HeartbeatConfig # 心跳设置
```
