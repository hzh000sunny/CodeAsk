# OpenCode HTTP API Server

## 概述

OpenCode 的 HTTP API Server 是整个系统的 Web 服务层，基于 Effect-TS 构建，负责将 OpenCode 的所有核心功能暴露为 RESTful HTTP API。Server 整合了路由、中间件、WebSocket、mDNS 服务发现、CORS、认证等能力，并提供优雅关闭机制。

Server 的核心入口位于 `packages/opencode/src/server/server.ts`，对外暴露四个主要 API：

| 导出 | 说明 |
|------|------|
| `Default()` | 获取默认的 HTTP API 处理器（`fetch` / `request` 双接口） |
| `openapi()` | 生成 OpenAPI 规范文档，基于 `PublicApi` |
| `listen(opts)` | 启动服务器并监听端口，返回 `Listener` |
| `url` | 模块级导出的当前服务器 URL |

---

## 架构总览

```
 请求
  │
  ▼
┌──────────────────────────────────────────────────────────────────────┐
│  HttpRouter.serve()                                                  │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │ ROUTER MIDDLEWARE (disposeMiddleware)                        │     │
│  │   - 请求/响应生命周期管理                                      │     │
│  │   - Instance 销毁在响应发送后执行                               │     │
│  └─────────────────────────────────────────────────────────────┘     │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │ ROUTE LAYERS (createRoutes)                                  │     │
│  │                                                              │     │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────┐ ┌───────┐  │     │
│  │  │rootApi   │ │eventApi  │ │instance  │ │doc   │ │ui     │  │     │
│  │  │Routes    │ │Routes    │ │Routes    │ │Route │ │Route  │  │     │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────┘ └───────┘  │     │
│  └─────────────────────────────────────────────────────────────┘     │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │ SHARED MIDDLEWARE LAYERS                                     │     │
│  │  errorLayer → compressionLayer → corsVaryFix → fenceLayer   │     │
│  │  → corsLayer → runtime (观测性注解)                           │     │
│  └─────────────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────────────┘
  │
  ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Layer.provideMerge() ─ 运行平台层                                    │
│                                                                      │
│  ┌───────────────────┐                                               │
│  │ WebSocketTracker  │  WebSocket 连接追踪与批量关闭                 │
│  └───────────────────┘                                               │
│  ┌───────────────────┐                                               │
│  │ HttpApiServer     │  HTTP 服务器运行时 (Bun / Node 实现)          │
│  └───────────────────┘                                               │
└──────────────────────────────────────────────────────────────────────┘
  │
  ▼
┌──────────────────────────────────────────────────────────────────────┐
│ ConfigProvider.layer(ConfigProvider.fromEnv())                        │
│   - 每个 listen() 调用使用全新的 ConfigProvider                        │
│   - 确保 process.env 变更可被后续 port 解析感知                       │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 启动流程

### 1. ListenOptions 参数

```typescript
type ListenOptions = CorsOptions & {
  port: number          // 监听端口，0 表示自动选择
  hostname: string      // 绑定主机名
  mdns?: boolean        // 是否启用 mDNS 服务发现 (默认 false)
  mdnsDomain?: string   // 自定义 mDNS 域名 (默认 "opencode.local")
}
```

CORS 相关参数由 `CorsOptions` 混入提供，支持自定义允许的 origin 列表。

### 2. 启动流程详解

```
listen(opts)
  │
  ├─ 1. 定义 buildLayer(port)
  │    ├─ HttpRouter.serve(createRoutes(opts), { middleware: disposeMiddleware })
  │    ├─ Layer.provideMerge(WebSocketTracker.layer)
  │    ├─ Layer.provideMerge(HttpApiServer.layer({ port, hostname }))
  │    └─ Layer.provide(ConfigProvider.layer(ConfigProvider.fromEnv()))
  │
  ├─ 2. 端口解析策略
  │
  │    opts.port === 0 ?
  │    │
  │    ├─ YES ──► start(4096) ──► 成功? ──► 使用 port 4096
  │    │                │
  │    │                └─ 失败 ──► start(0) ──► 系统分配任意可用端口
  │    │
  │    └─ NO  ──► start(opts.port) ──► 直接使用指定端口
  │
  ├─ 3. 创建 Scope + 构建 Effect Layer
  │    ├─ Effect.runPromise(Layer.buildWithMemoMap(layer, memoMap, scope))
  │    └─ 获取 HttpServer HttpApiServer WebSocketTracker 上下文
  │
  ├─ 4. 提取端口号
  │    ├─ Context.get(ctx, HttpServer.HttpServer)
  │    ├─ 验证地址类型为 TcpAddress
  │    └─ 提取 port
  │
  ├─ 5. 构造 URL
  │    └─ new URL(`http://${hostname}:${port}`)
  │
  ├─ 6. mDNS 发布 (条件触发)
  │    ├─ mdns 已启用?     ──► 否 ──► 跳过
  │    ├─ 端口有效?        ──► 否 ──► 跳过
  │    └─ hostname 非回环?  ──► 否 ──► 跳过 (记录警告)
  │                           └─ 是 ──► MDNS.publish(port, mdnsDomain)
  │
  └─ 7. 返回 Listener { hostname, port, url, stop(close?) }
```

### 3. Layer 组合层次

Server 的 Layer 组合是一个自上而下的效应系统构建过程，大致分为四个层次：

**第一层：路由层 (Route Layers)**
由 `createRoutes(opts)` 生成，包含五组路由：

| 路由组 | 说明 | 包含的 API 组 |
|--------|------|---------------|
| `rootApiRoutes` | 全局路由，无需 workspace 上下文 | ControlApi, GlobalApi |
| `eventApiRoutes` | 事件流路由 (SSE) | /event, /global/event |
| `instanceRoutes` | 实例级路由，需要 workspace 上下文 | Config, Experimental, File, Instance, MCP, Project, Pty, Question, Permission, Provider, Session, Sync, V2, Tui, Workspace |
| `docRoute` | OpenAPI 文档路由 | GET /doc |
| `uiRoute` | 前端 UI 服务 | 静态资源 + 上游代理转发 |

**第二层：共享中间件层 (Shared Middleware Layers)**
从外到内依次应用：

| 中间件 | 功能 |
|--------|------|
| `errorLayer` | 捕获效应异常，将缺陷转为 HTTP 错误响应 (400/404/500)，对已类型化的 HTTP API 错误不做干预 |
| `compressionLayer` | HTTP 响应压缩 |
| `corsVaryFix` | 修复 CORS Vary 头 |
| `fenceLayer` | 工作空间隔离：在 `OPENCODE_WORKSPACE_ID` 标志开启时，对比请求前后的状态变更并通过响应头传递增量数据 |
| `cors(corsOptions)` | CORS 跨域处理，通过 `isAllowedCorsOrigin` 校验请求来源 |
| `runtime` | 注入观测性 Span 注解 (`opencode.server.backend: effect-httpapi`) |

**第三层：基础设施层 (Infrastructure Layers)**
提供完整的依赖注入图：

- **领域服务**: Account, Agent, Auth, Command, Config, File, FileWatcher, Ripgrep, Format, LSP, MCP, Permission, Installation, Plugin, Project, Provider, ProviderAuth, ModelsDev, Pty, PtyTicket, Question, Session, SessionCompaction, SessionPrompt, SessionRevert, SessionShare, SessionRunState, SessionStatus, SessionSummary, ShareNext, Snapshot, SyncEvent, Skill, Todo, ToolRegistry, Vcs, Workspace, Worktree
- **基础设施**: Bus (事件总线), AppFileSystem (文件系统), FetchHttpClient (HTTP 客户端), HttpServer.layerServices
- **实例层**: InstanceLayer, Observability, CorsConfig

**第四层：外部提供层 (External Providers)**

| Layer | 功能 |
|-------|------|
| `WebSocketTracker.layer` | WebSocket 连接生命周期追踪 |
| `HttpApiServer.layer({port, hostname})` | 平台级 HTTP 服务器 (Node: `node:http.createServer`，Bun: Bun.serve) |
| `ConfigProvider.layer(ConfigProvider.fromEnv())` | 每个 listener 使用全新的 ConfigProvider，确保 `process.env` 的变更在每次 `listen()` 调用中都能被正确读取，避免 Effect 默认的模块级缓存导致的状态不一致 |

---

## 端口解析策略

Server 的端口解析模仿了旧版适配器的行为，具体逻辑：

```
port 参数值      行为
─────────────────────────────────────────────
> 0             直接使用指定端口
                失败 → 抛出异常

=== 0           策略:
                1. 首先尝试端口 4096 (历史默认端口)
                2. 如果 4096 不可用，尝试 0
                   (操作系统分配任意可用端口)
                3. 如果两次均失败 → 抛出异常
```

每个端口尝试都会独立创建新的 Scope 和 Layer，保证失败后资源被正确清理。

---

## mDNS 服务发现

mDNS（Multicast DNS）用于在同一局域网内自动发现 OpenCode 服务，实现 "零配置" 的服务访问。底层使用 `bonjour-service` 库。

### 发布条件

mDNS 发布需要同时满足以下所有条件：
1. `opts.mdns` 为 `true`
2. 端口号有效（非 0）
3. hostname 不是回环地址：`127.0.0.1`、`localhost`、`::1`

如果 `mdns` 开启了但 hostname 是回环地址，会记录一条 warning 日志但不会发布。

### 发布行为

```
MDNS.publish(port, domain?)
  │
  ├─ 检查当前是否已经有相同端口的服务在运行
  │    └─ 如有，先执行 unpublish()
  │
  ├─ 创建 Bonjour 实例
  │
  ├─ 发布 mDNS 服务:
  │    ├─ name:  "opencode-{port}"        (例: opencode-4096)
  │    ├─ type:  "http"
  │    ├─ host:  domain ?? "opencode.local"   (默认域名)
  │    ├─ port:  服务端口号
  │    └─ txt:   { path: "/" }
  │
  ├─ 监听事件:
  │    ├─ "up":    记录服务发布成功
  │    └─ "error": 记录 mDNS 服务错误
  │
  └─ 失败降级: 销毁 Bonjour 实例并清理状态
```

### 取消发布

```
MDNS.unpublish()
  ├─ 如果 Bonjour 实例存在:
  │   ├─ bonjour.unpublishAll()  — 取消所有发布的服务
  │   └─ bonjour.destroy()       — 销毁 Bonjour 实例
  └─ 重置内部状态 (currentPort = undefined)
```

---

## API 路由结构

### 路由树总览

API 路由使用 Effect 的 `HttpApi` 构建，分为三个主要 API 组：

```
HttpApi "opencode"
├── RootHttpApi "opencode-root"
│   ├── ControlApi     — 控制端点 (服务器管理)
│   └── GlobalApi      — 全局端点 (全局会话、事件等)
│
├── EventApi "event"
│   └── EventGroup     — 事件流端点 (/event SSE)
│
├── InstanceHttpApi "opencode-instance"
│   ├── ConfigApi      — 配置管理
│   ├── ExperimentalApi — 实验性功能
│   ├── FileApi        — 文件操作 (查找、读取、写入等)
│   ├── InstanceApi    — 实例管理
│   ├── McpApi         — MCP 工具集成
│   ├── ProjectApi     — 项目管理
│   ├── PtyApi         — 伪终端 (PTY)
│   ├── QuestionApi    — 提问交互
│   ├── PermissionApi  — 权限管理
│   ├── ProviderApi    — AI 提供商配置
│   ├── SessionApi     — 会话管理
│   ├── SyncApi        — 同步事件
│   ├── V2Api          — 实验性 v2 API (Message + Session)
│   ├── TuiApi         — 终端 UI 控制
│   └── WorkspaceApi   — 工作空间管理
│
└── PtyConnectApi      — PTY 连接 (原始 WebSocket 路由)
```

### 各路由组的认证与中间件

| 路由组 | 认证方式 | 关键中间件 |
|--------|---------|-----------|
| `rootApiRoutes` | `HttpApiMiddleware.Authorization` (Schema 级别) | `schemaErrorLayer` |
| `eventApiRoutes` | `authorizationRouterMiddleware` (Router 级别) | `instanceRouterMiddleware`, `workspaceRouterMiddleware`, `Socket.layerWebSocketConstructorGlobal` |
| `instanceRoutes` | `authorizationRouterMiddleware` (Router 级别) | `workspaceRoutingLayer`, `instanceContextLayer`, `schemaErrorLayer`, `Socket.layerWebSocketConstructorGlobal` |
| `docRoute` | `authorizationRouterMiddleware` | 延迟构建 OpenAPI 文档，缓存序列化结果 |
| `uiRoute` | `authorizationRouterMiddleware` | 静态 UI 路径可绕过认证 |

### API 处理器组织

每个 API Group 都有对应的 handler 层（位于 `handlers/` 目录），handler 负责将 API 定义绑定到具体的实现逻辑：

```
groups/                         handlers/
├── config.ts       ←→         config.ts
├── control.ts      ←→         control.ts
├── experimental.ts ←→         experimental.ts
├── file.ts         ←→         file.ts
├── global.ts       ←→         global.ts
├── instance.ts     ←→         instance.ts
├── mcp.ts          ←→         mcp.ts
├── permission.ts   ←→         permission.ts
├── project.ts      ←→         project.ts
├── provider.ts     ←→         provider.ts
├── pty.ts          ←→         pty.ts
├── question.ts     ←→         question.ts
├── session.ts      ←→         session.ts
├── sync.ts         ←→         sync.ts
├── tui.ts          ←→         tui.ts
├── workspace.ts    ←→         workspace.ts
└── v2/
    ├── ../v2.ts    ←→         ../v2.ts
    ├── message.ts  ←→         message.ts
    └── session.ts  ←→         session.ts
```

### OpenAPI 文档端点

`GET /doc` 端点返回 OpenAPI 规范文档。其实现采用了两个优化策略：

1. **延迟构造**: `OpenApi.fromApi` 的计算是非平凡的，使用 `lazy()` 确保只在首次访问 `/doc` 时执行，CLI 和脚本等不使用该端点的进程不会付出初始化代价
2. **响应缓存**: `HttpServerResponse.jsonUnsafe` 会立即执行 `JSON.stringify`，将序列化后的 `Uint8Array` 缓存，后续请求直接复用，避免重复序列化

PublicApi 对标准 OpenAPI 输出进行了向后兼容的转换（`matchLegacyOpenApi`），包括：
- 修复自引用组件 Schema
- 剥离 `Schema.optional` 引入的 `null` 联合类型
- 规范化组件命名（去除包路径前缀，合并重复 Schema）
- 添加旧版错误 Schema (`BadRequestError`, `NotFoundError`)
- 为 SSE 端点显式声明 `text/event-stream` 响应格式
- 适配旧版 SDK 的 query 参数类型（将 Effect 解码值映射为公开调用形式）

---

## WebSocket 支持

### WebSocketTracker

WebSocketTracker 是一个 Effect Service，负责追踪所有活跃的 WebSocket 连接，支持在服务器关闭时批量终止连接。

**接口定义** (`WebSocketTracker.Interface`):

| 方法 | 说明 |
|------|------|
| `add(close: Effect<void>)` | 注册一个 WebSocket 的关闭回调。如果服务器正在关闭中，返回 `false` 表示拒绝注册 |
| `remove(close: Effect<void>)` | 移除注册的关闭回调 |
| `closeAll: Effect<void>` | 关闭所有活跃的连接：设置 `closing` 标志阻止新连接，然后并发执行所有注册的关闭回调（超时 1 秒，异常被捕获忽略） |

**注册机制**:

```
WebSocket 连接建立
  │
  ├─ 调用 WebSocketTracker.register(closeCallback)
  │
  ├─ 检查 tracker service 是否存在 (Effect.serviceOption)
  │    └─ 如不存在 → 返回 true（无 tracker 环境）
  │
  ├─ 调用 tracker.add(closeCallback)
  │    └─ 返回 false → 服务器正在关闭，拒绝连接
  │
  └─ 注册成功 → 通过 Effect.addFinalizer 确保连接关闭时自动调用 tracker.remove()
```

### SSE 事件流

Server 提供了两个核心的 Server-Sent Events 端点：

**`/event` (实例级事件)**:

```
eventResponse(bus)
  │
  ├─ 订阅 Bus 上的所有事件 (bus.subscribeAll)
  │    └─ 监听至 Bus.InstanceDisposed 事件后自动终止
  │
  ├─ 心跳流: 每 10 秒发送一次 server.heartbeat
  │
  ├─ 合并事件流与心跳流 (haltStrategy: "left")
  │
  ├─ 以 server.connected 事件开头
  │
  ├─ 编码为 SSE 格式:
  │    ├─ Stream.pipeThroughChannel(Sse.encode())
  │    └─ Stream.encodeText
  │
  └─ 响应头:
       ├─ Content-Type: text/event-stream
       ├─ Cache-Control: no-cache, no-transform
       ├─ X-Accel-Buffering: no
       └─ X-Content-Type-Options: nosniff
```

SSE 事件 Schema 由 `BusEvent.effectPayloads()` 和 `SyncEvent.effectPayloads()` 动态构建，所有事件类型都通过 Effect Schema 的 `Union` 组合。

---

## 认证

### 服务器端认证

Server 支持基于 HTTP Basic Auth 的认证机制，配置通过环境变量控制：

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| `OPENCODE_SERVER_PASSWORD` | 服务器访问密码 | 无 (密码为空时认证被禁用) |
| `OPENCODE_SERVER_USERNAME` | 服务器访问用户名 | `opencode` |

**认证逻辑**:
- 如果未设置密码 → 认证被旁路，所有请求均可通过
- 如果设置了密码 → 请求必须携带正确的 Authorization 头
- 支持两种方式传递凭证：
  1. HTTP `Authorization: Basic ...` 头
  2. URL 查询参数 `?auth_token=...` (query string 形式)

**认证配置类**:
```typescript
class Config extends ConfigService.Service {
  password: Config.string("OPENCODE_SERVER_PASSWORD").option()
  username: Config.string("OPENCODE_SERVER_USERNAME").withDefault("opencode")
}
```

**认证中间件分为两层**:

| 层级 | 实现 | 适用场景 |
|------|------|---------|
| `authorizationLayer` | `HttpApiMiddleware.Service` (Schema 级别) | 类型化 HTTP API 路由，通过 Effect HttpApi 的 middleware 机制在 handler 之前拦截 |
| `authorizationRouterMiddleware` | `HttpRouter.middleware` (Router 级别) | 原始路由 (raw routes)、事件路由、文档路由、UI 路由，在路由器层面进行检查 |

### 免认证路径

以下路径类型可绕过认证：
- **公共 UI 路径** (`isPublicUIPath`): 静态资源如 JS/CSS/图片等
- **PTY 连接票据** (`hasPtyConnectTicketURL`): 带有效票据的 PTY WebSocket 连接

---

## CORS 跨域策略

CORS 中间件配置了以下默认允许的来源 (origin)：

| 允许的 Origin | 说明 |
|---------------|------|
| `http://localhost:*` | 本地开发 (任意端口) |
| `http://127.0.0.1:*` | 本地开发 (IPv4 环回) |
| `oc://renderer` | OpenCode 桌面应用自定义协议 |
| `tauri://localhost` | Tauri 桌面应用 |
| `http://tauri.localhost` | Tauri 桌面应用 |
| `https://tauri.localhost` | Tauri 桌面应用 |
| `https://*.opencode.ai` | OpenCode 官方域名 |
| `cors` 选项中的自定义列表 | 用户自定义允许的 origin |

CORS 预检缓存设置为 `maxAge: 86400` (24 小时)。

此外，`isAllowedRequestOrigin` 额外允许与当前服务器 hostname 相同的同源请求 (same-host check)。

---

## 优雅关闭流程

Graceful shutdown 通过 `Listener.stop(close?: boolean)` 方法实现，支持两种模式：

### 标准关闭 (`stop()` 或 `stop(false)`)

```
stop()
  │
  ├─ 1. 取消 mDNS 发布 (如果已发布)
  │    └─ MDNS.unpublish()
  │
  └─ 2. 关闭 Effect Scope
       └─ Scope.close(scope, Exit.void)
          └─ 所有注册的 finalizer 按注册顺序反向执行
             ├─ WebSocketTracker 的 cleanup
             ├─ HttpApiServer 的优雅关闭
             └─ 其他资源的释放
```

### 强制关闭 (`stop(true)`)

```
stop(true)
  │
  ├─ 1. 取消 mDNS 发布
  │
  ├─ 2. forceStop() — 先关闭活跃连接:
  │    ├─ HttpApiServer.Service.closeAll
  │    │   └─ Node 实现: 设置 forceStop 标志，如果 close 已启动则调用
  │    │      server.closeAllConnections() 强制断开所有 HTTP 连接
  │    │
  │    └─ WebSocketTracker.Service.closeAll
  │        └─ 并发执行所有已注册的 WebSocket close 回调
  │           (超时 1 秒，异常被忽略)
  │
  └─ 3. 关闭 Effect Scope
```

### Node 平台的 close 增强

在 `httpapi-server.node.ts` 中，Node.js 的 HTTP server 的 `close` 方法被代理增强：

```
server.close() 被代理为:
  ├─ 设置 closeStarted = true
  ├─ 调用原始 close(callback)
  │   └─ NodeHttpServer 配置了 gracefulShutdownTimeout: "1 second"
  │       (在 1 秒内完成当前请求的处理)
  │
  └─ 如果 forceStop 标志被设置:
      └─ server.closeAllConnections() 强制关闭所有 socket
```

### 生命周期中间件 (disposeMiddleware)

```
disposeMiddleware
  │
  ├─ 1. 执行请求处理 (yield* effect)，获取 response
  │
  ├─ 2. 从 disposeAfterResponse WeakMap 中查找标记的 instance
  │    └─ key: Request.source (原始请求对象)
  │
  ├─ 3. 如果找到标记:
  │    ├─ 从 WeakMap 中移除
  │    └─ 通过 EffectBridge 在隔离的 fiber 中执行 dispose
  │       └─ InstanceStore.dispose(instanceContext)
  │          └─ 捕获异常并记录警告 (不向上传播)
  │
  └─ 4. 返回原始 response (此时响应已发送)
```

---

## 默认 HTTP 处理器

`Default()` 返回一个 memoized 的单例处理器，提供两种调用方式：

```typescript
type ServerApp = {
  fetch(request: Request): Response | Promise<Response>
  request(input: string | URL | Request, init?: RequestInit): Response | Promise<Response>
}
```

- `fetch`: 接收标准 Request 对象，返回 Response
- `request`: 兼容 RequestInit 格式，自动将字符串/URL 转为 Request

---

## 事件系统

Server 通过 `Bus` (事件总线) 实现事件驱动架构：

| 事件端点 | URL | 说明 |
|----------|-----|------|
| 实例事件流 | `GET /event` | 当前工作空间实例的事件流 |
| 全局事件流 | `GET /global/event` | 跨工作空间的全局事件流 |

**事件数据流**:
```
Bus.publish(event)
  │
  ▼
Bus.subscribeAll()
  │
  ▼
Stream.merge(heartbeat, { haltStrategy: "left" })
  │  └─ heartbeat 在 event 流结束 (InstanceDisposed) 时自动停止
  ▼
Sse.encode() → Stream.encodeText → HttpServerResponse.stream()
```

支持的事件类型包括（但不限于）：
- `server.connected` / `server.heartbeat` — 服务端心跳/连接状态
- Session 更新、Message 增量、Diff 变更
- Instance 生命周期事件
- Error 事件

---

## 可观测性

Server 集成了 OpenTelemetry 观测性支持：

- 运行时中间件 (`runtime`) 为每个请求注入 Span 注解 `opencode.server.backend: "effect-httpapi"`
- `Observability.layer` 通过 `Layer.provideMerge` 提供到整棵服务依赖树
- 日志通过结构化 Logger (`@opencode-ai/core/util/log`) 输出，使用 `{ service: "server" }` 标识

同时，Server 在模块初始化时禁用了 AI SDK 的日志警告：
```typescript
globalThis.AI_SDK_LOG_WARNINGS = false
```

---

## 文件索引

| 文件路径 | 说明 |
|----------|------|
| `packages/opencode/src/server/server.ts` | Server 入口，listen/Default/openapi 导出 |
| `packages/opencode/src/server/httpapi-server.ts` | HttpApiServer Service 接口定义 |
| `packages/opencode/src/server/httpapi-server.node.ts` | Node.js 平台 HTTP Server 实现 |
| `packages/opencode/src/server/mdns.ts` | mDNS 服务发现 (bonjour-service) |
| `packages/opencode/src/server/cors.ts` | CORS 配置与 origin 校验 |
| `packages/opencode/src/server/auth.ts` | 服务端认证配置 |
| `packages/opencode/src/server/event.ts` | 事件定义 |
| `packages/opencode/src/server/routes/instance/httpapi/server.ts` | 路由构建核心 (createRoutes, webHandler) |
| `packages/opencode/src/server/routes/instance/httpapi/api.ts` | 顶层 HttpApi 定义 (RootHttpApi, InstanceHttpApi) |
| `packages/opencode/src/server/routes/instance/httpapi/public.ts` | PublicApi 与 OpenAPI 向后兼容转换 |
| `packages/opencode/src/server/routes/instance/httpapi/event.ts` | SSE 事件流端点实现 |
| `packages/opencode/src/server/routes/instance/httpapi/lifecycle.ts` | disposeMiddleware 生命周期管理 |
| `packages/opencode/src/server/routes/instance/httpapi/websocket-tracker.ts` | WebSocket 连接追踪器 |
| `packages/opencode/src/server/routes/instance/httpapi/middleware/authorization.ts` | 认证中间件 |
| `packages/opencode/src/server/routes/instance/httpapi/middleware/error.ts` | 错误处理中间件 |
| `packages/opencode/src/server/routes/instance/httpapi/middleware/fence.ts` | 工作空间隔离/增量中间件 |
| `packages/opencode/src/server/routes/instance/httpapi/middleware/compression.ts` | 响应压缩中间件 |
| `packages/opencode/src/server/routes/instance/httpapi/middleware/cors-vary.ts` | CORS Vary 头修正 |
| `packages/opencode/src/server/routes/instance/httpapi/middleware/instance-context.ts` | 实例上下文注入中间件 |
| `packages/opencode/src/server/routes/instance/httpapi/middleware/workspace-routing.ts` | 工作空间路由中间件 |
| `packages/opencode/src/server/routes/instance/httpapi/middleware/schema-error.ts` | Schema 验证错误中间件 |
| `packages/opencode/src/server/routes/instance/httpapi/middleware/proxy.ts` | 代理中间件 |
| `packages/opencode/src/server/routes/instance/httpapi/groups/*.ts` | API Group 定义 (Schema + 端点声明) |
| `packages/opencode/src/server/routes/instance/httpapi/handlers/*.ts` | API Handler 实现 |
| `packages/opencode/src/server/shared/ui.ts` | UI 服务 (嵌入式/上游代理) |
| `packages/opencode/src/server/shared/fence.ts` | Fence 共享逻辑 |
| `packages/opencode/src/server/shared/pty-ticket.ts` | PTY 连接票据验证 |
| `packages/opencode/src/server/shared/public-ui.ts` | 公共 UI 路径判断 |
| `packages/opencode/src/server/proxy-util.ts` | 代理请求工具 |
| `packages/opencode/src/server/projectors.ts` | projections 初始化 |
| `packages/opencode/src/server/global-lifecycle.ts` | 全局生命周期管理 |
