# 03 — 数据模型层

## 概述

数据模型层位于 `server/models/`，封装了 Prisma ORM 操作，提供业务逻辑方法、字段验证、权限控制和关联查询。

## 模型清单

### User（用户模型）
**文件**: `models/user.js`

- `usernameRegex`: Unix 风格（小写字母开头，2-32 字符，支持 `._@-`）
- **角色**: `default`, `admin`, `manager`
- `create()`: bcrypt 密码哈希（10 轮）
- `update()`: 字段验证 + 密码复杂度检查（joi-password-complexity）
- `canSendChat()`: 每日消息限制检查（24 小时窗口）
- `filterFields()`: 移除敏感字段（password, web_push_subscription_config）
- `checkPasswordComplexity()`: 可配置的密码策略（min, max, lowerCase, upperCase, numeric, symbol, requirementCount）

### Workspace（工作区模型）
**文件**: `models/workspace.js`

- `VALID_CHAT_MODES`: chat, query, automatic
- `writable` 字段白名单
- 每个字段的验证函数（openAiTemp, similarityThreshold, topN, chatMode, vectorSearchMode）
- **Slugify 扩展**: `+`, `!`, `@`, `*`, `.` 等特殊字符映射
- `new()`: 默认系统提示词继承、自动 slug 生成（冲突时添加随机后缀）
- `update()`: 验证字段 + `chatProvider: "default"` → 清除 provider/model
- `getWithUser()`: 角色感知（admin/manager 无视限制）
- `_getContextWindow()`: 动态获取上下文窗口大小
- `_getCurrentContextTokenCount()`: 计算工作区/线程的文件 Token 总数
- `trackChange()`: 提示词变更跟踪 → PromptHistory + EventLogs + Telemetry
- `supportsNativeToolCalling()`: 检查模型是否支持原生工具调用
- `isAgentCommandAvailable()`: Agent 命令是否需要显式 `@agent`

### WorkspaceChats（聊天记录模型）
**文件**: `models/workspaceChats.js`

- `new()`: 创建聊天（JSON 序列化响应）
- `forWorkspaceByUser()`: 按用户获取（默认线程）
- `forWorkspaceByApiSessionId()`: 按 API 会话获取
- `forWorkspace()`: 获取工作区聊天（排除线程和 API 会话）
- `markThreadHistoryInvalidV2()`: 灵活的标记无效
- `updateFeedbackScore()`: 用户反馈评分（true/false/null）
- `bulkCreate()`: 批量创建（因 SQLite 不支持 createMany）

### Document（文档模型）
**文件**: `models/documents.js`

- `parseDocumentTypeAndSource()`: 解析 `chunkSource` 格式（`type://source`）
- `addDocuments()`: 完整的文档嵌入管道（fileData → VectorDb.addDocumentToNamespace → DB 记录）
- `removeDocuments()`: 删除向量 + DB 记录 + document_vectors 清理
- `forWorkspace()`: 获取工作区文档列表
- `_stripSource()`: 清理 confluence/github 源的敏感参数
- `api.uploadToWorkspace()`: API 文档上传后嵌入到多个工作区

### WorkspaceThread（线程模型）
**文件**: `models/workspaceThread.js`

- `new()`: 创建线程（基于工作区和用户）
- `update()`/`delete()`: 线程 CRUD
- `autoRenameThread()`: 基于聊天内容自动重命名线程
- 支持 slug 生成和冲突检测

### SystemSettings（系统设置模型）
**文件**: `models/systemSettings.js`

- 键值对存储（label → value）
- `currentSettings()`: 获取所有设置
- `updateSettings()`: 批量更新
- `saneDefaultSystemPrompt`: 合理的默认系统提示词
- 功能标志管理（通过 label 值 `"enabled"/"disabled"`）

### Invite（邀请码模型）
**文件**: `models/invite.js`

- 邀请码生成、验证、使用
- 支持工作区限制（`workspaceIds`）
- 状态管理（pending/claimed）

### ApiKeys & BrowserExtensionApiKey
**文件**: `models/apiKeys.js`, `models/browserExtensionApiKey.js`

- API 密钥管理
- 浏览器扩展密钥验证

### EmbedConfig & EmbedChats
**文件**: `models/embedConfig.js`, `models/embedChats.js`

- 嵌入组件配置 CRUD
- 嵌入聊天历史管理
- `canRespond()`: 速率限制检查

### ScheduledJob & ScheduledJobRun
**文件**: `models/scheduledJob.js`, `models/scheduledJobRun.js`

- 定时任务的定义和执行记录
- `markRunning()`: 原子状态转换（queued → running）
- `complete()`, `fail()`, `timeout()`, `kill()`: 终端状态管理
- `start()`: 防并发创建执行记录

### DocumentSyncQueue & DocumentSyncRun
**文件**: `models/documentSyncQueue.js`, `models/documentSyncRun.js`

- 文档同步队列管理
- `staleDocumentQueues()`: 获取过期队列
- `calcNextSync()`: 计算下次同步时间
- `maxRepeatFailures`: 连续失败阈值
- `validFileTypes`: 支持的文件类型

### AgentSkillWhitelist
**文件**: `models/agentSkillWhitelist.js`

- Agent 技能白名单
- 工具名 + Agent 名唯一约束
- 自动批准配置

### 其他模型

| 模型 | 文件 | 用途 |
|------|------|------|
| PromptHistory | `models/promptHistory.js` | 提示词变更历史 |
| SystemPromptVariables | `models/systemPromptVariables.js` | 提示词变量管理 |
| EventLogs | `models/eventLogs.js` | 审计日志 |
| Telemetry | `models/telemetry.js` | 遥测数据上报 |
| CacheData | `models/cacheData.js` | 通用缓存 |
| PasswordRecovery | `models/passwordRecovery.js` | 密码恢复 |
| TemporaryAuthToken | `models/temporaryAuthToken.js` | 临时认证令牌 |
| MobileDevice | `models/mobileDevice.js` | 移动设备管理 |
| WorkspaceParsedFiles | `models/workspaceParsedFiles.js` | 工作区解析文件 |
| CommunityHub | `models/communityHub.js` | 社区中心集成 |
| SlashCommandPresets | `models/slashCommandsPresets.js` | 斜杠命令预设 |
| ExternalCommunicationConnector | `models/externalCommunicationConnector.js` | 外部通信连接器 |

## 通用 CRUD 模式

所有模型遵循一致的 CRUD 模式：
- `get(clause)`: 查找单条记录
- `where(clause, limit, orderBy)`: 查找多条记录
- `new(data)`: 创建记录
- `update(id, data)`: 更新记录
- `delete(clause)`: 删除记录
- `count(clause)`: 计数

特殊方法：
- `_update`: 直接更新（无验证，内部使用）
- `_get`: 获取完整记录（包含敏感字段）
- `_where`: 无过滤查询
- `_findMany`/`_findFirst`: 原始 Prisma 查询
