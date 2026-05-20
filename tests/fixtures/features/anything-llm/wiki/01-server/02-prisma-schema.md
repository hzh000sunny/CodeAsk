# 02 — 数据库模式 (Prisma)

## 概述

使用 Prisma 5.3.1 ORM，默认使用 SQLite（`file:../storage/anythingllm.db`），可选 PostgreSQL。

## 数据表清单（共 25 张表）

### 用户与认证

#### `users` — 用户表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Int (PK, auto) | 用户 ID |
| username | String? (unique) | 用户名（Unix 风格：小写字母开头，2-32字符） |
| password | String (hashed) | bcrypt 哈希密码 |
| pfpFilename | String? | 头像文件名 |
| role | String (default: "default") | 角色：default/admin/manager |
| suspended | Int (0/1) | 是否被暂停 |
| seen_recovery_codes | Boolean? | 是否查看过恢复码 |
| dailyMessageLimit | Int? | 每日聊天限制 |
| bio | String? | 个人简介 |
| web_push_subscription_config | String? | Web Push 订阅配置 |

关联关系：workspace_chats, workspace_users, embed_configs, embed_chats, threads, recovery_codes, password_reset_tokens, workspace_agent_invocations, slash_command_presets, browser_extension_api_keys, temporary_auth_tokens, system_prompt_variables, prompt_history, desktop_mobile_devices, workspace_parsed_files

#### `recovery_codes` — 账户恢复码
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Int (PK) | |
| user_id | Int (FK → users) | 关联用户 |
| code_hash | String | bcrypt 哈希的恢复码 |

#### `password_reset_tokens` — 密码重置令牌
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Int (PK) | |
| user_id | Int (FK → users) | |
| token | String (unique) | 重置令牌 |
| expiresAt | DateTime | 过期时间 |

#### `temporary_auth_tokens` — 临时认证令牌
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Int (PK) | |
| token | String (unique) | 临时令牌 |
| userId | Int (FK → users) | |
| expiresAt | DateTime | 过期时间 |

#### `api_keys` — API 密钥
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Int (PK) | |
| name | String? | 密钥名称 |
| secret | String? (unique) | 密钥 |
| createdBy | Int? | 创建者 ID |

#### `browser_extension_api_keys` — 浏览器扩展密钥
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Int (PK) | |
| key | String (unique) | API 密钥 |
| user_id | Int? (FK → users) | |

### 工作区

#### `workspaces` — 工作区表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Int (PK) | |
| name | String | 工作区名称 |
| slug | String (unique) | URL 友好的唯一标识 |
| vectorTag | String? | 向量标签 |
| openAiTemp | Float? | LLM 温度参数 |
| openAiHistory | Int (default: 20) | 聊天历史消息数 |
| openAiPrompt | String? | 系统提示词 |
| similarityThreshold | Float? (default: 0.25) | 相似度阈值 |
| chatProvider | String? | LLM 提供商 |
| chatModel | String? | LLM 模型 |
| topN | Int? (default: 4) | 检索 Top N |
| chatMode | String? (default: "chat") | 聊天模式：chat/query/automatic |
| pfpFilename | String? | 工作区头像 |
| agentProvider | String? | Agent 提供商 |
| agentModel | String? | Agent 模型 |
| queryRefusalResponse | String? | 查询拒绝回复 |
| vectorSearchMode | String? (default: "default") | 向量搜索模式：default/rerank |

#### `workspace_threads` — 工作区线程
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Int (PK) | |
| name | String | 线程名称 |
| slug | String (unique) | |
| workspace_id | Int (FK → workspaces, Cascade) | |
| user_id | Int? (FK → users, Cascade) | |

#### `workspace_users` — 工作区-用户关联
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Int (PK) | |
| user_id | Int (FK → users, Cascade) | |
| workspace_id | Int (FK → workspaces, Cascade) | |

#### `workspace_suggested_messages` — 建议消息
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Int (PK) | |
| workspaceId | Int (FK → workspaces, Cascade) | |
| heading | String | 标题 |
| message | String | 消息内容 |

### 聊天

#### `workspace_chats` — 工作区聊天记录
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Int (PK) | |
| workspaceId | Int | 工作区 ID |
| prompt | String | 用户提问 |
| response | String (JSON) | LLM 响应（含 sources, metrics, type 等） |
| include | Boolean (default: true) | 是否包含在历史中 |
| user_id | Int? (FK → users) | |
| thread_id | Int? | 线程 ID（无外键约束） |
| api_session_id | String? | API 会话标识 |
| feedbackScore | Boolean? | 用户反馈评分 |

#### `workspace_agent_invocations` — Agent 调用记录
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Int (PK) | |
| uuid | String (unique) | 调用唯一 ID |
| prompt | String | Agent 指令文本 |
| closed | Boolean (default: false) | 是否已关闭 |
| user_id | Int? (FK → users) | |
| thread_id | Int? | |
| workspace_id | Int (FK → workspaces) | |

#### `prompt_history` — 提示词历史
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Int (PK) | |
| workspaceId | Int (FK → workspaces, Cascade) | |
| prompt | String | 历史提示词 |
| modifiedBy | Int? (FK → users) | |
| modifiedAt | DateTime | 修改时间 |

#### `slash_command_presets` — 斜杠命令预设
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Int (PK) | |
| command | String | 触发命令 |
| prompt | String | 替换提示词 |
| description | String | 描述 |
| uid | Int (default: 0) | 0 = 系统级 |
| userId | Int? (FK → users) | |

唯一约束：`(uid, command)`

### 文档与向量

#### `workspace_documents` — 工作区文档
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Int (PK) | |
| docId | String (unique) | 文档 UUID |
| filename | String | 文件名 |
| docpath | String | 文件路径 |
| workspaceId | Int (FK → workspaces) | |
| metadata | String? (JSON) | 元数据 |
| pinned | Boolean? | 是否固定 |
| watched | Boolean? | 是否监视同步 |

#### `document_vectors` — 文档向量记录
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Int (PK) | |
| docId | String | 关联文档 UUID |
| vectorId | String | 向量存储中的 ID |

#### `document_sync_queues` — 文档同步队列
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Int (PK) | |
| staleAfterMs | Int (default: 604800000 = 7天) | 过期时间 |
| nextSyncAt | DateTime | 下次同步时间 |
| lastSyncedAt | DateTime | 上次同步时间 |
| workspaceDocId | Int (unique, FK → workspace_documents) | |

#### `document_sync_executions` — 同步执行记录
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Int (PK) | |
| queueId | Int (FK → document_sync_queues) | |
| status | String (default: "unknown") | 状态 |
| result | String? | 结果详情 |

#### `workspace_parsed_files` — 解析文件
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Int (PK) | |
| filename | String (unique) | |
| workspaceId | Int (FK → workspaces, Cascade) | |
| userId | Int? (FK → users, Cascade) | |
| threadId | Int? (FK → workspace_threads, Cascade) | |
| metadata | String? (JSON) | |
| tokenCountEstimate | Int? | Token 数估计 |

### 嵌入组件

#### `embed_configs` — 嵌入配置
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Int (PK) | |
| uuid | String (unique) | 公开 UUID |
| enabled | Boolean | 是否启用 |
| chat_mode | String (default: "query") | |
| allowlist_domains | String? | 域名白名单 |
| allow_model_override | Boolean? | |
| allow_temperature_override | Boolean? | |
| allow_prompt_override | Boolean? | |
| max_chats_per_day | Int? | |
| max_chats_per_session | Int? | |
| message_limit | Int? (default: 20) | |
| workspace_id | Int (FK → workspaces, Cascade) | |
| createdBy | Int? | |
| usersId | Int? (FK → users) | |

#### `embed_chats` — 嵌入聊天记录
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Int (PK) | |
| prompt | String | |
| response | String (JSON) | |
| session_id | String | 会话 ID |
| connection_information | String? (JSON) | 连接信息 |
| embed_id | Int (FK → embed_configs, Cascade) | |
| usersId | Int? (FK → users) | |

### 定时任务

#### `scheduled_jobs` — 定时任务
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Int (PK) | |
| name | String | 任务名称 |
| prompt | String | Agent 提示词 |
| tools | String? (JSON数组) | 工具限制（null=使用所有启用的技能） |
| schedule | String | Cron 表达式 |
| enabled | Boolean (default: true) | |
| lastRunAt | DateTime? | |
| nextRunAt | DateTime? | |

#### `scheduled_job_runs` — 任务执行记录
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Int (PK) | |
| jobId | Int (FK → scheduled_jobs, Cascade) | |
| status | String (default: "queued") | queued/running/completed/failed/timed_out |
| result | String? (JSON) | 执行结果 |
| error | String? | 错误信息 |
| startedAt | DateTime | 开始时间 |
| completedAt | DateTime? | 完成时间 |
| readAt | DateTime? | 已读时间（null=未读） |

### 其他

#### `system_settings` — 系统设置（键值对）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Int (PK) | |
| label | String (unique) | 设置键名 |
| value | String? | 设置值 |

#### `system_prompt_variables` — 系统提示变量
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Int (PK) | |
| key | String (unique) | 变量名 |
| value | String? | 变量值 |
| description | String? | 描述 |
| type | String (default: "system") | system/user/dynamic |
| userId | Int? (FK → users) | |

#### `invites` — 邀请码
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Int (PK) | |
| code | String (unique) | 邀请码 |
| status | String (default: "pending") | pending/claimed |
| claimedBy | Int? | |
| workspaceIds | String? | 限制的工作区 ID |
| createdBy | Int | |

#### `cache_data` — 缓存数据
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Int (PK) | |
| name | String | 缓存名称 |
| data | String | 缓存数据 |
| belongsTo | String? | 所属 |
| byId | Int? | 关联 ID |
| expiresAt | DateTime? | 过期时间 |

#### `event_logs` — 事件日志
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Int (PK) | |
| event | String (indexed) | 事件类型 |
| metadata | String? (JSON) | 事件数据 |
| userId | Int? | 触发用户 |

#### `external_communication_connectors` — 外部通信连接器
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Int (PK) | |
| type | String (unique) | 连接器类型 |
| config | String (default: "{}") | JSON 配置 |
| active | Boolean | 是否激活 |

#### `desktop_mobile_devices` — 移动/桌面设备
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Int (PK) | |
| deviceOs | String | 操作系统 |
| deviceName | String | 设备名称 |
| token | String (unique) | 设备 Token |
| approved | Boolean | 是否已批准 |
| userId | Int? (FK → users) | |

## 数据源配置

```prisma
datasource db {
  provider = "sqlite"
  url      = "file:../storage/anythingllm.db"
}
```

PostgreSQL 备选方案已在 schema 中注释提供。

## 迁移历史

共有 30+ 个 Prisma 迁移，从 `20230921191814_init` 到 `20260423191158_init`，覆盖了从项目初始到最新版本的模式演进。
