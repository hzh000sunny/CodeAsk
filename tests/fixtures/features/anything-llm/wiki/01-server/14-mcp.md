# 14 — MCP (Model Context Protocol)

## 概述

MCP 系统允许 AnythingLLM 连接到外部 MCP 服务器，将其工具暴露为 Agent 技能。

## 架构

```
MCPCompatibilityLayer (单例, 继承 MCPHypervisor)
├── MCPHypervisor (服务器生命周期管理)
│   ├── 连接管理 (Client + Transport)
│   ├── 进程管理 (stdio 子进程)
│   └── 配置存储 (JSON 文件)
└── Agent 插件转换
    └── convertServerToolsToPlugins()
```

## MCPHypervisor 类

**文件**: `server/utils/MCP/hypervisor/index.js` (555 行)

### 配置存储
- 文件: `storage/plugins/anythingllm_mcp_servers.json`
- 格式: `{ "mcpServers": { "name": { serverConfig } } }`

### 传输类型支持

| 类型 | 协议 | 配置 | 特点 |
|------|------|------|------|
| stdio | 标准输入/输出 | command, args, env | 子进程管理，SIGTERM 终止 |
| http (streamable) | HTTP 流式 | url, type: "streamable/http" | StreamableHTTPClientTransport |
| sse | Server-Sent Events | url, type: "sse" | SSEClientTransport |

### 服务器生命周期
1. **验证**: 根据类型检查必需字段
2. **环境变量**: 合并系统 PATH + 用户自定义 env
3. **传输**: 创建对应 Transport 实例
4. **连接**: `mcp.connect(transport)` with 30 秒超时
5. **工具发现**: 连接后自动获取工具列表
6. **关闭**: `mcp.close()` + SIGTERM (stdio)

### 工具抑制
- 每个服务器维护 `suppressedTools` 列表
- 被抑制的工具不会暴露给 Agent

## MCPCompatibilityLayer 类

**文件**: `server/utils/MCP/index.js` (269 行)

### Agent 插件转换
`convertServerToolsToPlugins(serverName, aibitat)`:
1. 通过 `mcp.listTools()` 获取工具列表
2. 过滤抑制的工具
3. 为每个工具创建 aibitat 插件：
   - `isMCPTool: true` 标识
   - 注册函数（名称、描述、inputSchema 作为参数）
   - 处理函数创建新的 MCP 连接并调用 `callTool()`
   - 结果通过 `returnMCPResult()` 序列化

### 工具调用冷却
MCP 工具每次调用后进入冷却期（`mcpsCooldown`），防止重复调用。

### 结果序列化
`returnMCPResult()` 处理:
- BigInt → String
- 循环引用 → `"[Circular]"`
- 不可序列化对象 → `"[Unserializable: error]"`

### 服务器状态
`servers()` 方法返回:
- 工具列表及描述
- 运行状态
- 进程信息
- 连接错误
- Ping 检测在线状态

## API 端点

### MCP 服务器管理
| 端点 | 功能 |
|------|------|
| `GET /mcp-servers/force-reload` | 重新加载所有服务器 |
| `GET /mcp-servers/list` | 列出所有服务器状态 |
| `POST /mcp-servers/toggle` | 启动/停止单个服务器 |
| `POST /mcp-servers/delete` | 删除服务器配置 |
| `POST /mcp-servers/toggle-tool` | 切换工具抑制状态 |

## MCP SDK 集成

使用 `@modelcontextprotocol/sdk` v1.24.3:
- `Client`: MCP 客户端
- `StdioClientTransport`: 子进程传输
- `SSEClientTransport`: SSE 传输
- `StreamableHTTPClientTransport`: 流式 HTTP 传输
