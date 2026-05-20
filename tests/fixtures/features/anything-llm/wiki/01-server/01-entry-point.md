# 01 — 入口与启动流程

## 文件位置
`server/index.js`

## 启动流程

### 1. 环境变量加载
```
开发模式 → .env.development
生产模式 → .env
```
使用 `dotenv` 包加载环境变量。

### 2. 日志系统初始化
启动时立即调用 `require("./utils/logger")()` 初始化 Winston 日志系统，覆盖全局 `console.log/error/info`。

### 3. Express 应用创建
```javascript
const app = express();
const apiRouter = express.Router();
```

### 4. 中间件注册（按顺序）

| 中间件 | 条件 | 用途 |
|--------|------|------|
| `httpLogger` | 仅开发模式 + `ENABLE_HTTP_LOGGER=true` | HTTP 请求日志 |
| `cors({ origin: true })` | 始终 | 跨域资源共享 |
| `bodyParser.text({ limit: "3GB" })` | 始终 | 文本请求体解析 |
| `bodyParser.json({ limit: "3GB" })` | 始终 | JSON 请求体解析 |
| `bodyParser.urlencoded({ limit: "3GB", extended: true })` | 始终 | URL 编码请求体解析 |

### 5. SSL/HTTP 引导

**HTTPS 模式** (`ENABLE_HTTPS=true`):
- 调用 `bootSSL(app, port)` 创建 HTTPS 服务器
- 自动加载 SSL 证书

**HTTP 模式** (默认):
- 使用 `@mintplex-labs/express-ws` 加载 WebSocket 支持
- 最后调用 `bootHTTP(app, port)` 启动 HTTP 监听

### 6. API 路由挂载

所有端点挂载在 `/api` 路径下：

```javascript
app.use("/api", apiRouter);
```

挂载顺序（在 `apiRouter` 上）：

| 顺序 | 端点模块 | 功能域 |
|------|----------|--------|
| 1 | `systemEndpoints` | 系统设置、环境变量 |
| 2 | `extensionEndpoints` | 扩展功能 |
| 3 | `workspaceEndpoints` | 工作区 CRUD |
| 4 | `workspaceThreadEndpoints` | 工作区线程 |
| 5 | `chatEndpoints` | 聊天（流式 SSE） |
| 6 | `adminEndpoints` | 管理员功能 |
| 7 | `inviteEndpoints` | 邀请码 |
| 8 | `embedManagementEndpoints` | 嵌入组件管理 |
| 9 | `utilEndpoints` | 工具端点（模型列表等） |
| 10 | `documentEndpoints` | 文档上传/管理 |
| 11 | `agentWebsocket` | Agent WebSocket |
| 12 | `agentSkillWhitelistEndpoints` | Agent 技能白名单 |
| 13 | `agentFileServerEndpoints` | Agent 文件服务 |
| 14 | `experimentalEndpoints` | 实验性功能 |
| 15 | `developerEndpoints` (app, apiRouter) | 开发者 API v1 |
| 16 | `communityHubEndpoints` | 社区中心 |
| 17 | `agentFlowEndpoints` | Agent 流程 |
| 18 | `mcpServersEndpoints` | MCP 服务器 |
| 19 | `mobileEndpoints` | 移动端 API |
| 20 | `webPushEndpoints` | Web Push 通知 |
| 21 | `telegramEndpoints` | Telegram 机器人 |
| 22 | `scheduledJobEndpoints` | 定时任务 |
| 23 | `outlookAgentEndpoints` | Outlook Agent |
| 24 | `googleAgentSkillEndpoints` | Google Agent 技能 |
| 25 | `embeddedEndpoints` | 外部嵌入组件 API |
| 26 | `browserExtensionEndpoints` | 浏览器扩展 API |

### 7. 生产环境特殊路由

**静态文件服务**: `express.static("public")`
- 移除 `X-Powered-By` 响应头
- 设置 `X-Frame-Options: DENY` 防止 iframe 嵌入

**robots.txt**: 禁止所有爬虫
```
User-agent: *
Disallow: /
```

**manifest.json**: 通过 `MetaGenerator` 动态生成 PWA 清单

**SPA 回退路由**: 所有非 API 路径返回 index.html（由 MetaGenerator 处理）

### 8. 开发环境调试路由

开发模式下提供 `/api/v/:command` POST 路由：
- 直接调用 Vector DB 的任意方法
- 用于调试和测试向量数据库接口

### 9. 404 处理
```javascript
app.all("*", function(_, response) {
  response.sendStatus(404);
});
```

## 关键依赖

- `@mintplex-labs/express-ws`: 支持 SSL 模式下的 WebSocket
- `express`: Web 框架
- `cors`: 跨域支持
- `body-parser`: 请求体解析
- `dotenv`: 环境变量加载
