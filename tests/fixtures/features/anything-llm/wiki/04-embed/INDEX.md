# 04 — Embed 嵌入组件

## 概述

Embed 是 AnythingLLM 的可嵌入聊天 Widget，允许第三方网站集成 AI 聊天功能。

## 目录结构

```
embed/
└── (嵌入组件前端代码)
```

## 功能特性

### 聊天模式
- `query` 模式：仅基于文档内容回答（默认）
- `chat` 模式：标准对话模式

### 配置项
| 配置 | 说明 |
|------|------|
| `uuid` | 公开唯一标识符 |
| `enabled` | 启用/禁用 |
| `workspace_id` | 关联的工作区 |
| `chat_mode` | query / chat |
| `allowlist_domains` | 域名白名单 |
| `max_chats_per_day` | 每日聊天限制 |
| `max_chats_per_session` | 每会话聊天限制 |
| `message_limit` | 历史消息数限制（默认 20） |

### 覆盖能力
- `allow_model_override`: 允许外部指定模型
- `allow_temperature_override`: 允许外部指定温度
- `allow_prompt_override`: 允许外部指定提示词

## API 端点（面向公众）

### 聊天
| 端点 | 方法 | 功能 |
|------|------|------|
| `/embed/:embedId/stream-chat` | POST | 流式聊天（SSE） |

### 历史管理
| 端点 | 方法 | 功能 |
|------|------|------|
| `/embed/:embedId/:sessionId` | GET | 获取会话历史 |
| `/embed/:embedId/:sessionId` | DELETE | 清除会话历史 |

## 安全控制

通过 `canRespond` 中间件：
- 检查嵌入是否启用
- 验证域名白名单
- 验证会话 ID
- 消息长度限制
- 每日/每会话速率限制

## 连接信息记录

`setConnectionMeta` 中间件自动记录：
- 请求来源
- 客户端 IP
- 用于审计和分析

## 聊天存储

嵌入聊天使用独立的 `EmbedChats` 模型，不与工作区聊天混合：
- `session_id`: 会话标识
- `embed_id`: 嵌入配置 ID
- `connection_information`: 连接信息（JSON）

## 数据库模型

### embed_configs
管理每个嵌入实例的配置，包括：
- UUID 作为公开标识
- 工作区关联
- 速率限制参数
- 域名白名单

### embed_chats
存储嵌入组件的聊天记录：
- 按 session_id 分区
- 按 embed_id 筛选
- JSON 格式存储响应（含来源和指标）
