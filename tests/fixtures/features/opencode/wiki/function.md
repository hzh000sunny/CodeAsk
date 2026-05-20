# Function 包

Function 包 (`@opencode-ai/function`) 是一个部署在 Cloudflare Workers 上的函数服务，提供会话同步、分享管理和 GitHub App 集成等能力。它使用 Durable Objects 实现有状态的 WebSocket 实时同步。

## 技术栈

| 技术 | 用途 |
|------|------|
| Hono | HTTP 路由框架 |
| Cloudflare Workers | 无服务器运行时平台 |
| Durable Objects | 有状态、长期存活的同步服务 |
| WebSocket | 实时双向通信 |
| R2 Bucket | 对象存储持久化 |
| @octokit/rest | GitHub REST API 客户端 |
| @octokit/auth-app | GitHub App 安装令牌认证 |
| jose | JWT/JWK 验证（OIDC 令牌） |
| SST | 基础设施编排和密钥管理 |

## 架构总览

```
┌──────────────────────────────────────────────────────────┐
│                    Cloudflare Workers                      │
│                                                           │
│  ┌────────────────────────────────────────────────────┐  │
│  │                  Hono Router                         │  │
│  │  /                    → Hello World                 │  │
│  │  /share_create        → 创建分享                     │  │
│  │  /share_delete        → 删除分享                     │  │
│  │  /share_delete_admin  → 管理员强制删除               │  │
│  │  /share_sync          → 同步数据                     │  │
│  │  /share_poll          → WebSocket 升级 (实时订阅)    │  │
│  │  /share_data          → 获取分享数据                  │  │
│  │  /feishu              → 飞书消息转发                  │  │
│  │  /exchange_github_app_token      → OIDC 令牌交换     │  │
│  │  /exchange_github_app_token_with_pat → PAT 令牌交换  │  │
│  │  /get_github_app_installation     → 查询安装状态     │  │
│  └──────────────────────┬─────────────────────────────┘  │
│                         │                                  │
│  ┌──────────────────────┴─────────────────────────────┐  │
│  │           Durable Object: SyncServer                 │  │
│  │  ┌──────────┐  ┌──────────┐  ┌─────────────────┐   │  │
│  │  │ WebSocket │  │ Storage  │  │ R2 Persistence  │   │  │
│  │  │ 实时推送  │  │ (内存K/V) │  │ (对象存储持久化) │   │  │
│  │  └──────────┘  └──────────┘  └─────────────────┘   │  │
│  └────────────────────────────────────────────────────┘  │
│                                                           │
│  ┌────────────────────────────────────────────────────┐  │
│  │              外部服务集成                             │  │
│  │  GitHub Actions (OIDC)  │  飞书  │  Discord        │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

## Durable Objects 同步服务 (SyncServer)

`SyncServer` 是一个 Durable Object 类，每个分享实例对应一个独立的 DO 实例，通过 DO 的全局唯一标识符实现路由和隔离。

### DO 标识机制

```typescript
// 使用 sessionID 后 8 位作为 DO 名称
static shortName(id: string) {
  return id.substring(id.length - 8)
}

// 通过 shortName 获取 DO 实例
const id = c.env.SYNC_SERVER.idFromName(SyncServer.shortName(sessionID))
const stub = c.env.SYNC_SERVER.get(id)
```

相同 `shortName` 的请求会被路由到同一个 DO 实例，保证会话状态的一致性。

### WebSocket 实时同步

**连接建立** (`fetch`)：

```
客户端请求 GET /share_poll?id={shortName}
  → Worker 检查 Upgrade 头 = "websocket"
  → 创建 DO stub，调用 stub.fetch()
  → DO 创建 WebSocketPair
  → server 端 acceptWebSocket
  → 回放所有已存储的 session 数据给新订阅者
  → 返回 101 状态码 + client WebSocket
```

连接建立时，DO 会遍历 `ctx.storage` 中所有以 `session/` 为前缀的 key，将它们作为历史数据回放给新连接的客户端，确保客户端获得完整状态。

**消息广播** (`publish`)：

```typescript
async publish(key: string, content: any) {
  // 1. 校验 key 是否属于当前 session
  // 2. 写入 R2: share/{key}.json
  // 3. 写入 DO 内存存储
  // 4. 向所有 WebSocket 客户端广播
}
```

Key 校验规则（防止跨 session 写入）：
- 必须以 `session/info/{sessionID}` 开头
- 或以 `session/message/{sessionID}/` 开头
- 或以 `session/part/{sessionID}/` 开头

### 数据存储层次

```
┌─────────────────────────┐
│  ctx.storage (DO 内存)   │  ← 热数据，实时读取
│  - secret                │
│  - sessionID             │
│  - session/info/{id}     │
│  - session/message/{id}/ │
│  - session/part/{id}/    │
├─────────────────────────┤
│  R2 Bucket (持久化)       │  ← 冷数据，持久化备份
│  - share/{key}.json      │
└─────────────────────────┘
```

DO 内存存储保证低延迟读取，R2 作为持久化备份防止 DO 重启后数据丢失。

### 分享管理 API

| 方法 | 说明 |
|------|------|
| `share(sessionID)` | 初始化分享，生成随机 secret，存储 sessionID |
| `getData()` | 获取所有 session 数据 |
| `assertSecret(secret)` | 校验 secret，不匹配时抛出异常 |
| `clear()` | 清除 DO 内存存储和 R2 中对应 session 的所有数据 |
| `publish(key, content)` | 写入数据并广播给订阅者 |

### 安全模型

- 每个分享实例由一个 `secret` 保护（`crypto.randomUUID()`）
- 写操作（`share_sync`、`share_delete`）需要提供匹配的 secret
- 管理员可通过 `share_delete_admin` 使用全局 `ADMIN_SECRET` 强制删除
- DO 实例间完全隔离，不同 session 的数据不会混淆

## HTTP API 端点

### 分享相关

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| `POST` | `/share_create` | 创建分享，返回 secret 和 URL | 无 |
| `POST` | `/share_delete` | 删除分享 | secret |
| `POST` | `/share_delete_admin` | 管理员强制删除 | ADMIN_SECRET |
| `POST` | `/share_sync` | 同步数据到分享 | secret |
| `GET` | `/share_poll` | WebSocket 实时订阅 | Upgrade 头 |
| `GET` | `/share_data` | 查询分享数据 | 无 |

**创建分享响应**：
```json
{
  "secret": "uuid-string",
  "url": "https://{WEB_DOMAIN}/s/{shortName}"
}
```

**share_poll -- WebSocket 升级流程**：

1. 客户端发送 `GET /share_poll?id={shortName}`
2. 请求必须包含 `Upgrade: websocket` 头，否则返回 `426 Upgrade Required`
3. Worker 将请求转发给对应 DO 的 `fetch()` 方法
4. DO 建立 WebSocket 连接，回放历史数据
5. 后续通过 `publish()` 实时推送新数据

**share_data -- 数据查询**：

```
GET /share_data?id={shortName}
→ DO stub.getData()
→ 分类整理: info / messages (含 parts)
→ 返回 { info, messages }
```

### GitHub 集成

**令牌交换 -- OIDC 模式** (`POST /exchange_github_app_token`)：

用于 GitHub Actions 工作流中获取 GitHub App 安装令牌：

```
GitHub Actions Runner
  → 携带 OIDC JWT (Audience: "opencode-github-action")
  → 验证 JWT (Issuer: token.actions.githubusercontent.com)
  → 提取 sub 中的 owner/repo (格式: repo:my-org/my-repo:ref:...)
  → 使用 GitHub App 私钥生成 App JWT
  → 查询仓库的 App 安装信息
  → 生成 Installation Access Token
  → 返回 { token }
```

OIDC 令牌验证使用 `jose` 库：
- `createRemoteJWKSet` -- 从 GitHub 的 JWKS 端点获取公钥
- `jwtVerify` -- 验证令牌的签发者、受众和签名

**令牌交换 -- PAT 模式** (`POST /exchange_github_app_token_with_pat`)：

用于本地测试（`opencode github run` 本地执行），允许用户使用 Personal Access Token 换取 Installation Token：

1. 验证 PAT 对目标仓库的权限（需要 `admin` / `push` / `maintain` 之一）
2. 使用 GitHub App 私钥生成 Installation Token
3. 返回 token

**查询安装状态** (`GET /get_github_app_installation`)：

```
GET /get_github_app_installation?owner={owner}&repo={repo}
→ 查询 GitHub App 是否已安装到目标仓库
→ 返回 { installation } 或 { installation: undefined }
```

CLI 端使用此端点检查 App 安装状态，决定是否需要引导用户授权。

### 飞书集成 (`/feishu`)

将飞书消息转发到 Discord 支持频道：

1. 处理飞书 Event Callback（URL 验证：返回 `challenge`）
2. 解析消息内容（支持 JSON 格式和纯文本）
3. 去除 @mention 前缀
4. 将消息通过 Discord Bot API 发送到指定频道

消息格式处理：
- 移除 `@_user_数字` 形式的 @提及
- 替换 `aiden,` 前缀为 Discord 用户 ID
- 在消息末尾附上飞书线程 ID `[threadId]`（用于追溯）

## WebSocket 通信协议

### 连接流程

```
Client                           DO (SyncServer)
  │                                     │
  │  GET /share_poll?id=xxx             │
  │  Upgrade: websocket                 │
  │─────────────────────────────────────>
  │                                     │  acceptWebSocket
  │                                     │  回放历史数据
  │  ← { key, content }                 │
  │  ← { key, content }                 │
  │  ← ... (所有 session/* 数据)         │
  │                                     │
  │  (后续实时推送)                       │
  │  ← { key, content }                 │  publish() 广播
  │  ← { key, content }                 │
```

### 消息格式

所有 WebSocket 消息为 JSON 格式：

```json
{
  "key": "session/info/abc123",
  "content": { /* 任意 JSON 数据 */ }
}
```

客户端根据 `key` 的路径结构解析数据类型：
- `session/info/{id}` -- 会话元信息
- `session/message/{id}` -- 消息数据
- `session/part/{id}` -- 消息片段

### 关闭处理

当 WebSocket 连接关闭时，DO 会发送关闭帧并附带原因说明 `"Durable Object is closing WebSocket"`。客户端可以处理断线重连逻辑。

## 部署与基础设施

### Cloudflare Workers 绑定

Worker 的 `Env` 类型定义了运行时绑定：

```typescript
type Env = {
  SYNC_SERVER: DurableObjectNamespace<SyncServer>  // DO 命名空间
  Bucket: R2Bucket                                   // R2 存储桶
  WEB_DOMAIN: string                                 // Web 应用域名
}
```

### SST 资源管理

项目使用 SST 进行基础设施编排，通过 `Resource` 对象访问密钥和配置：

| 资源 | 用途 |
|------|------|
| `GITHUB_APP_ID` | GitHub App ID |
| `GITHUB_APP_PRIVATE_KEY` | GitHub App 私钥 |
| `ADMIN_SECRET` | 管理员密钥 |
| `DISCORD_SUPPORT_BOT_TOKEN` | Discord Bot Token |
| `DISCORD_SUPPORT_CHANNEL_ID` | Discord 支持频道 ID |
| `Bucket` | R2 存储桶（通过 Cloudflare 绑定） |

`sst-env.d.ts` 文件由 SST 自动生成，提供所有资源的类型定义。

## 运行方式

此包不包含独立的启动脚本，作为 Cloudflare Worker 部署到 Cloudflare 平台。Worker 由 Cloudflare 的运行时自动调用，Durable Object 由平台按需创建和管理。

```bash
# 类型检查
tsgo --noEmit
```
