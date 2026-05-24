# 04 — API 端点系统

## 架构概览

服务的端点分为以下几个层级：
1. **主 API 路由** (`/api/*`) — 前端使用的内部 API
2. **开发者 API** (`/api/v1/*`) — 通过 API Key 认证的外部 API
3. **外部端点** — 嵌入组件、浏览器扩展、移动端的独立入口

## 主 API 端点（内部使用）

### Chat 端点
| 路由 | 方法 | 功能 |
|------|------|------|
| `/workspace/:slug/stream-chat` | POST | 工作区流式聊天（SSE） |
| `/workspace/:slug/thread/:threadSlug/stream-chat` | POST | 线程流式聊天（SSE） |

中间件: `validatedRequest`, `flexUserRoleValid`, `validWorkspaceSlug`
- 检查消息非空
- 检查每日聊天限制
- 调用 `streamChatWithWorkspace()` 处理 SSE 流
- 发送遥测和事件日志
- 线程模式自动重命名线程

### Workspace 端点
| 路由 | 方法 | 功能 |
|------|------|------|
| `/workspaces` | GET | 列出用户可访问的工作区 |
| `/workspace/new` | POST | 创建工作区 |
| `/workspace/:slug` | GET | 获取工作区详情 |
| `/workspace/:slug` | DELETE | 删除工作区 |
| `/workspace/:slug/update` | POST | 更新工作区设置 |
| `/workspace/:slug/update-embeddings` | POST | 添加/删除文档嵌入 |
| `/workspace/:slug/update-pin` | POST | 切换文档固定状态 |
| `/workspace/:slug/chat` | POST | 同步聊天 |
| `/workspace/:slug/vector-search` | POST | 向量相似度搜索 |
| `/workspace/:slug/manage-users` | POST | 管理工作区用户 |

### Document 端点
| 路由 | 方法 | 功能 |
|------|------|------|
| `/document/upload` | POST | 上传文档文件 |
| `/document/upload-link` | POST | 抓取 URL 为文档 |
| `/document/raw-text` | POST | 原始文本创建文档 |
| `/document/process/:filename` | POST | 处理上传的文件 |
| `/document/remove-and-remove-embeddings` | POST | 删除文档及嵌入 |
| `/documents` | GET | 列出所有文档 |
| `/document/create-folder` | POST | 创建文件夹 |
| `/document/move-files` | POST | 移动文件 |
| `/document/remove-folder` | DELETE | 删除文件夹 |
| `/document/accepted-file-types` | GET | 支持的文件类型 |
| `/document/metadata-schema` | GET | 文档元数据 Schema |

### Thread 端点
| 路由 | 方法 | 功能 |
|------|------|------|
| `/workspace/:slug/thread/new` | POST | 创建线程 |
| `/workspace/:slug/thread/:threadSlug/update` | POST | 更新线程 |
| `/workspace/:slug/thread/:threadSlug/delete` | POST | 删除线程 |
| `/workspace/:slug/thread/:threadSlug/chats` | GET | 获取线程聊天记录 |

### Admin 端点
| 路由 | 方法 | 功能 |
|------|------|------|
| `/admin/users` | GET | 列出用户 |
| `/admin/users/new` | POST | 创建用户 |
| `/admin/users/:id` | POST | 更新用户 |
| `/admin/users/:id` | DELETE | 删除用户 |
| `/admin/invites` | GET | 列出邀请码 |
| `/admin/invite/new` | POST | 创建邀请码 |
| `/admin/invite/:id` | DELETE | 停用邀请码 |
| `/admin/workspace-chats` | POST | 分页聊天记录 |
| `/admin/preferences` | POST | 系统偏好设置 |
| `/admin/workspaces` | GET | 列出工作区及用户信息 |

### System 端点
| 路由 | 方法 | 功能 |
|------|------|------|
| `/system` | GET | 获取系统设置 |
| `/system/env-dump` | GET | 导出环境变量 |
| `/system/update-env` | POST | 更新系统设置 |
| `/system/vector-count` | GET | 向量总数 |
| `/system/remove-documents` | DELETE | 删除文档 |
| `/system/export-chats` | GET | 导出聊天记录 |

### Agent 端点
| 路由 | 方法 | 功能 |
|------|------|------|
| `/agent-invocation/:uuid` | WS | Agent WebSocket 连接 |
| `/agent-flows/save` | POST | 创建/更新流程 |
| `/agent-flows/list` | GET | 列出流程 |
| `/agent-flows/:uuid` | GET | 获取流程 |
| `/agent-flows/:uuid` | DELETE | 删除流程 |
| `/agent-flows/:uuid/toggle` | POST | 切换流程启用 |
| `/agent-skills/whitelist/add` | POST | 添加到白名单 |
| `/agent-skills/generated-files/:filename` | GET | 下载生成的文件 |

### MCP 端点
| 路由 | 方法 | 功能 |
|------|------|------|
| `/mcp-servers/force-reload` | GET | 重新加载 MCP 服务器 |
| `/mcp-servers/list` | GET | 列出 MCP 服务器 |
| `/mcp-servers/toggle` | POST | 启动/停止服务器 |
| `/mcp-servers/delete` | POST | 删除服务器 |
| `/mcp-servers/toggle-tool` | POST | 切换工具抑制 |

### Embed 管理端点
| 路由 | 方法 | 功能 |
|------|------|------|
| `/embed` | GET | 列出嵌入配置 |
| `/embed/new` | POST | 创建嵌入 |
| `/embed/:uuid` | POST | 更新嵌入 |
| `/embed/:uuid` | DELETE | 删除嵌入 |

### 扩展端点（代理到 Collector）
| 路由 | 功能 |
|------|------|
| `/ext/:repo_platform/branches` | 获取仓库分支 |
| `/ext/:repo_platform/repo` | 导入仓库 |
| `/ext/youtube/transcript` | YouTube 字幕 |
| `/ext/confluence` | Confluence 导入 |
| `/ext/website-depth` | 网站深度抓取 |
| `/ext/drupalwiki` | DrupalWiki 导入 |
| `/ext/obsidian/vault` | Obsidian 导入 |
| `/ext/paperless-ngx` | Paperless-NGX 导入 |

### Community Hub 端点
| 路由 | 方法 | 功能 |
|------|------|------|
| `/community-hub/settings` | GET | 获取 Hub 连接设置 |
| `/community-hub/settings` | POST | 更新 Hub 连接设置 |
| `/community-hub/explore` | GET | 浏览社区资源 |
| `/community-hub/item` | POST | 获取资源详情 |
| `/community-hub/apply` | POST | 应用资源（斜杠命令/提示词） |
| `/community-hub/import` | POST | 导入资源包（Agent技能/流程） |
| `/community-hub/items` | GET | 获取用户发布的资源 |
| `/community-hub/:type/create` | POST | 发布新资源到社区 |

### Telegram 端点
| 路由 | 方法 | 功能 |
|------|------|------|
| `/telegram/config` | GET | 获取 Telegram 配置 |
| `/telegram/connect` | POST | 验证 Token 并启动 Bot |
| `/telegram/disconnect` | POST | 停止 Bot |
| `/telegram/status` | GET | 获取运行状态 |
| `/telegram/pending-users` | GET | 待批准用户列表 |
| `/telegram/approved-users` | GET | 已批准用户列表 |
| `/telegram/approve-user` | POST | 批准用户 |
| `/telegram/deny-user` | POST | 拒绝用户 |
| `/telegram/revoke-user` | POST | 撤销用户 |
| `/telegram/update-config` | POST | 更新配置（语音模式等） |

语音响应模式: `text_only` / `mirror` / `always_voice`

### Web Push 端点
| 路由 | 方法 | 功能 |
|------|------|------|
| `/web-push/subscribe` | POST | 注册推送订阅 |
| `/web-push/pubkey` | GET | 获取 VAPID 公钥 |

### 其他端点
| 路由 | 方法 | 功能 |
|------|------|------|
| `/utils/global-models` | GET | 全局模型列表 |
| `/utils/provider-models` | GET | 提供商模型列表 |
| `/utils/available-models` | GET | 可用模型配置 |
| `/utils/total-disk-space` | GET | 磁盘空间 |
| `/invite/:code` | GET | 验证邀请码 |
| `/invite/accept` | POST | 接受邀请 |
| `/scheduled-jobs/*` | CRUD | 定时任务管理 |

## 开发者 API (v1)

所有 `/api/v1/*` 路由需要 `Authorization: Bearer <API_KEY>` 认证。

### Auth
| 路由 | 方法 | 功能 |
|------|------|------|
| `/v1/auth` | GET | 验证 API 密钥 |

### Workspace
| 路由 | 方法 | 功能 |
|------|------|------|
| `/v1/workspace/new` | POST | 创建工作区 |
| `/v1/workspaces` | GET | 列出工作区 |
| `/v1/workspace/:slug` | GET/DELETE | 获取/删除工作区 |
| `/v1/workspace/:slug/update` | POST | 更新工作区 |
| `/v1/workspace/:slug/chats` | GET | 获取聊天记录 |
| `/v1/workspace/:slug/chat` | POST | 同步聊天 |
| `/v1/workspace/:slug/stream-chat` | POST | 流式聊天（SSE） |
| `/v1/workspace/:slug/vector-search` | POST | 向量搜索 |
| `/v1/workspace/:slug/update-embeddings` | POST | 更新嵌入 |
| `/v1/workspace/:slug/update-pin` | POST | 切换文档固定 |

### Thread
| 路由 | 方法 | 功能 |
|------|------|------|
| `/v1/workspace/:slug/thread/new` | POST | 创建线程 |
| `/v1/workspace/:slug/thread/:threadSlug/update` | POST | 更新线程 |
| `/v1/workspace/:slug/thread/:threadSlug` | DELETE | 删除线程 |
| `/v1/workspace/:slug/thread/:threadSlug/chats` | GET | 获取线程聊天 |
| `/v1/workspace/:slug/thread/:threadSlug/chat` | POST | 线程同步聊天 |
| `/v1/workspace/:slug/thread/:threadSlug/stream-chat` | POST | 线程流式聊天 |

### Document
| 路由 | 方法 | 功能 |
|------|------|------|
| `/v1/document/upload` | POST | 上传文件 |
| `/v1/document/upload/:folderName` | POST | 上传到文件夹 |
| `/v1/document/upload-link` | POST | URL 抓取 |
| `/v1/document/raw-text` | POST | 原始文本 |
| `/v1/documents` | GET | 列出文档 |
| `/v1/document/:docName` | GET | 获取文档 |
| `/v1/document/accepted-file-types` | GET | 支持的文件类型 |
| `/v1/document/create-folder` | POST | 创建文件夹 |
| `/v1/document/remove-folder` | DELETE | 删除文件夹 |
| `/v1/document/move-files` | POST | 移动文件 |

### OpenAI Compatible
| 路由 | 方法 | 功能 |
|------|------|------|
| `/v1/openai/models` | GET | 列出模型（工作区） |
| `/v1/openai/chat/completions` | POST | 聊天完成 |
| `/v1/openai/embeddings` | POST | 嵌入 |
| `/v1/openai/vector_stores` | GET | 向量存储列表 |

### Admin (v1)
| 路由 | 方法 | 功能 |
|------|------|------|
| `/v1/admin/users` | GET | 列出用户 |
| `/v1/admin/users/new` | POST | 创建用户 |
| `/v1/admin/users/:id` | POST | 更新用户 |
| `/v1/admin/users/:id` | DELETE | 删除用户 |
| `/v1/admin/invites` | GET | 列出邀请 |
| `/v1/admin/invite/new` | POST | 创建邀请 |
| `/v1/admin/invite/:id` | DELETE | 停用邀请 |
| `/v1/admin/workspace-chats` | POST | 分页聊天 |

### System (v1)
| 路由 | 方法 | 功能 |
|------|------|------|
| `/v1/system` | GET | 系统设置 |
| `/v1/system/env-dump` | GET | 环境导出 |
| `/v1/system/update-env` | POST | 更新设置 |
| `/v1/system/vector-count` | GET | 向量计数 |
| `/v1/system/export-chats` | GET | 导出聊天 |
| `/v1/system/remove-documents` | DELETE | 删除文档 |

### Embed (v1)
| 路由 | 方法 | 功能 |
|------|------|------|
| `/v1/embed` | GET | 列出嵌入 |
| `/v1/embed/new` | POST | 创建嵌入 |
| `/v1/embed/:embedUuid` | POST | 更新嵌入 |
| `/v1/embed/:embedUuid` | DELETE | 删除嵌入 |
| `/v1/embed/:embedUuid/chats` | GET | 获取嵌入聊天 |

### User Management (v1)
| 路由 | 方法 | 功能 |
|------|------|------|
| `/v1/users` | GET | 列出用户 |
| `/v1/users/:id/issue-auth-token` | GET | 签发临时令牌 |

## 外部端点

### Embedded Chat（无需认证）
| 路由 | 方法 | 功能 |
|------|------|------|
| `/embed/:embedId/stream-chat` | POST | 嵌入流式聊天 |
| `/embed/:embedId/:sessionId` | GET | 获取历史 |
| `/embed/:embedId/:sessionId` | DELETE | 清除历史 |

中间件: `validEmbedConfig`, `canRespond`, `setConnectionMeta`
- 速率限制: max_chats_per_day, max_chats_per_session
- 域名白名单检查
- 支持模型/温度/提示覆盖

### Mobile API
| 路由 | 方法 | 功能 |
|------|------|------|
| `/mobile/auth` | GET | 验证设备令牌 |
| `/mobile/register` | POST | 注册设备 |
| `/mobile/send/:command` | POST | 发送移动命令 |
| `/mobile/devices` | GET | 列出设备（管理员） |

支持的命令: `workspaces`, `workspace-content`, `model-tag`, `reset-chat`, `new-thread`, `stream-chat`, `unregister-device`

### Browser Extension
| 路由 | 方法 | 功能 |
|------|------|------|
| `/browser-extension/save-page` | POST | 保存页面 |

## SSE 流式响应格式

所有流式端点使用 Server-Sent Events 格式：
```
data: {"id":"uuid","type":"textResponseChunk","textResponse":"...","close":false}
data: {"id":"uuid","type":"finalizeResponseStream","close":true,"chatId":123}
```

事件类型: `textResponseChunk`, `textResponse`, `abort`, `finalizeResponseStream`, `action`
