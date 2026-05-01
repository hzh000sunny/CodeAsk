# API 与数据模型设计

## 1. 目标

API 与数据模型文档定义前后端、Agent 和持久化之间的稳定契约。

## 2. API 分组

一期 API：

- `/api/auth/me`
- `/api/auth/admin/login`
- `/api/auth/logout`
- `/api/sessions`
- `/api/sessions/{id}/messages`
- `/api/sessions/{id}/attachments`
- `/api/sessions/{id}/attachments/{attachment_id}`
- `/api/sessions/{id}/reports`
- `/api/sessions/bulk-delete`
- `/api/feedback`
- `/api/events`
- `/api/audit-log`
- `/api/reports`
- `/api/features`
- `/api/documents`
- `/api/skills`
- `/api/repos`
- `/api/me/llm-configs`
- `/api/admin/llm-configs`
- `/api/healthz`
- `/api/metrics`（历史草案名；当前 raw metrics API 拆为 `/api/feedback`、`/api/events`、`/api/audit-log`）

消息发送接口返回 SSE 流。

`/api/llm-configs` 是旧 UI 使用的全局配置端点。新 workbench 不再使用它暴露全局配置给普通用户；普通用户使用 `/api/me/llm-configs`，管理员使用 `/api/admin/llm-configs`。管理员不拥有个人 LLM 配置面，管理员 cookie 调用 `/api/me/llm-configs` 返回 403。

`/api/repos` 采用同一路径分角色控制：`GET /api/repos` 供会话和特性页面读取全局仓库池；`POST /api/repos`、`DELETE /api/repos/{id}` 和 `POST /api/repos/{id}/refresh` 仅管理员可调用。当前实现没有 `/api/admin/repos` 路径。

`POST /api/sessions/{id}/reports` 用于从会话生成问题定位报告草稿。请求必须包含 `feature_id` 和 `title`；`feature_id = null` 会被视为无效请求。后端只允许会话所有者调用，并要求会话中至少存在一轮非空用户消息和其后的非空 Agent 回答，否则返回 400，避免把没有调查内容的空会话沉淀成报告。成功响应返回 `ReportRead`，前端据此跳转到绑定特性的"问题报告" tab。

`/api/sessions/{id}/attachments` 用于会话临时数据管理。后端必须先按当前 `subject_id` 加载会话，所有附件操作都限定在该会话下：

| Method | Path | 说明 |
|---|---|---|
| `GET` | `/api/sessions/{id}/attachments` | 列出该会话已上传的数据 |
| `POST` | `/api/sessions/{id}/attachments` | 上传日志 / 图片 / 文档片段 |
| `PATCH` | `/api/sessions/{id}/attachments/{attachment_id}` | 修改附件展示名 `display_name` 和 / 或用途说明 `description` |
| `DELETE` | `/api/sessions/{id}/attachments/{attachment_id}` | 删除附件记录，并尽力删除物理文件 |

`AttachmentResponse` 字段：

| 字段 | 含义 |
|---|---|
| `id` | 附件 ID，物理文件名使用该 ID 避免同名冲突 |
| `session_id` | 所属会话 |
| `kind` | `log` / `image` / `doc` / `other` |
| `display_name` | 用户可编辑展示名，默认等于上传文件名 |
| `original_filename` | 上传时的原始文件名 |
| `aliases` | 用户可用于口语引用的名称历史，包含原始文件名和历次展示名 |
| `reference_names` | 稳定引用集合，包含 `id`、当前展示名、别名和物理文件名 |
| `description` | 用户补充的用途说明，例如“数据库节点 A 的服务日志” |
| `file_path` | 后端本地物理路径 |
| `mime_type` | 上传 MIME |
| `size_bytes` | 上传字节数；历史数据未知时可为 `0` 或 `null` |
| `created_at` / `updated_at` | 元数据时间 |

同一会话可上传多个同名日志；不同会话的附件目录和列表互不共享。

每个会话目录下还会生成一个 `manifest.json`，用于人工排查磁盘目录与 DB 记录的对应关系。DB 记录是附件映射主源；manifest 是每次上传、重命名、编辑说明和删除后的快照。清单文件至少包含 `session_id`、`storage_dir` 和附件数组；附件项记录 `id`、`display_name`、`original_filename`、`aliases`、`reference_names`、`description`、`stored_filename`、`file_path`、`mime_type`、`size_bytes`、`created_at`、`updated_at`。

删除会话时，后端必须在删除 DB 记录前收集该会话附件的真实 `file_path`，并清理这些文件所在的 `<data_dir>/sessions/<session_id>/` 目录；不能只依赖当前运行时的 `settings.data_dir` 重新拼路径。这样历史会话即使经历过数据目录配置调整，也不会留下旧的会话临时目录。批量删除同样遵循该规则。

`metrics-eval` 阶段新增 raw metrics API：

| Method | Path | 说明 |
|---|---|---|
| `POST` | `/api/feedback` | 对单次 Agent 回答写显式反馈；请求字段为 `session_turn_id`、`feedback = solved / partial / wrong`、可选 `note` |
| `POST` | `/api/events` | 写前端打点；`event_type` 必须在白名单内，`payload` 为 JSON |
| `GET` | `/api/audit-log?entity_type=&entity_id=&limit=` | 按实体查询审计日志，按 `at desc` 返回 |

当前前端会话页已接入回答反馈：用户点击“已解决 / 部分解决 / 没解决”后写 `/api/feedback`，同时写 `feedback_submitted` 前端事件。用户打开“强制代码调查”时写 `force_deeper_investigation` 前端事件。Maintainer Dashboard 的聚合视图仍是后续前端增强，本阶段只保证 raw data 写入与读取边界。

## 3. 核心表

SQLite 主库包含：

- `features`
- `repos`
- `feature_repos`
- `documents`
- `document_references`
- `reports`
- `skills`
- `sessions`
- `session_features`
- `session_repo_bindings`
- `session_turns`
- `session_attachments`
- `feedback`
- `frontend_events`
- `audit_log`
- `llm_configs`
- `auth_sessions`
- `system_settings`

`llm_configs.protocol` 一期支持：

```text
openai
anthropic
```

新 workbench 的消息接口协议下拉只展示 OpenAI 和 Anthropic；后端历史兼容层仍可识别 `openai_compatible`，但不作为当前配置页面的可选项。Agent 不直接读取供应商协议字段。LLM 网关根据该字段选择适配器，并向 Agent 暴露统一事件流。

## 3.1 身份与权限

请求身份解析优先级：

1. 有效管理员 cookie → `role = admin`
2. `X-Subject-Id` 自报身份 → `role = member`
3. 无效或缺失自报身份 → 后端生成匿名 subject id，仅用于该请求

管理员 cookie 由 `POST /api/auth/admin/login` 写入，`POST /api/auth/logout` 清除。内置管理员默认用户名 / 密码为 `admin` / `admin`，可通过 `CODEASK_ADMIN_USERNAME` 和 `CODEASK_ADMIN_PASSWORD` 覆盖。

`GET /api/auth/me` 返回：

```json
{
  "subject_id": "client_xxx",
  "display_name": "client_xxx",
  "role": "member",
  "authenticated": false
}
```

管理员返回：

```json
{
  "subject_id": "admin",
  "display_name": "Admin",
  "role": "admin",
  "authenticated": true
}
```

## 3.2 LLM Config Scope

`llm_configs` 新增语义字段：

| 字段 | 类型 | 含义 |
|---|---|---|
| `scope` | `user` / `global` | 配置归属 |
| `owner_subject_id` | nullable string | `scope=user` 时所属用户 |
| `enabled` | bool | 是否参与运行时选择 |
| `max_tokens` | int | 后端默认 `200 * 1024`，配置页不展示 |
| `temperature` | float | 后端默认 `0.2`，配置页不展示 |
| `rpm_limit` | nullable int | 保留字段；当前配置页不展示，也不参与调度 |
| `quota_remaining` | nullable float | 保留字段；当前配置页不展示，也不参与调度 |

当前实现为兼容已有数据仍保留 `name` 全局唯一约束；默认配置唯一性按作用域隔离：

- global config：最多一个 `scope = global AND is_default = true`
- user config：每个 `owner_subject_id` 最多一个 `scope = user AND is_default = true`

后续如果需要同名的个人 / 全局配置，应通过迁移把 `name` 唯一约束调整为 `scope + owner_subject_id + name`。

运行时选择顺序：

1. 当前用户启用的个人 LLM 配置。
2. 启用的全局 LLM 配置。
3. 如果都没有，Agent 返回配置缺失错误。

新 workbench 不提供"设为默认配置"操作；多配置选择按启用状态和创建时间稳定选择。RPM、剩余额度暂不配置，供应商调用失败时直接向会话返回错误。

## 3.3 Session Attachments

`session_attachments` 保存会话临时数据元信息：

| 字段 | 类型 | 含义 |
|---|---|---|
| `id` | string | 附件 ID |
| `session_id` | string | 所属会话，外键到 `sessions.id` |
| `kind` | string | 附件类型 |
| `display_name` | string | 用户可编辑展示名 |
| `original_filename` | string | 上传时原始文件名 |
| `aliases_json` | JSON list | 附件名称历史，用于把用户口语中的旧名 / 新名映射回同一个附件 ID |
| `description` | text nullable | 用户补充的用途说明 |
| `file_path` | string | 本地物理路径 |
| `mime_type` | string | MIME 类型 |
| `size_bytes` | int nullable | 文件大小 |
| `created_at` / `updated_at` | datetime | 时间戳 |

物理路径必须包含 `session_id`：

```text
<data_dir>/sessions/<session_id>/<attachment_id>.<ext>
```

因此相同文件名（例如多个节点都上传 `service.log`）不会互相覆盖；展示层通过 `display_name`、`original_filename`、附件短 ID 和用途说明区分。Agent 构造 prompt 时必须以 `attachment_id` 为稳定键，同时把 `display_name`、`original_filename`、`aliases_json`、`reference_names` 和 `description` 注入附件摘要，确保用户说“刚才那个 service.log 是节点 A 的数据库日志”之后，后续重命名为 `db-node-a.log` 仍能映射回同一个物理文件。

## 4. FTS5

全文检索表方向：

- `docs_fts`
- `docs_ngram_fts`
- `reports_fts`

报告只有验证后写入 `reports_fts`。

Wiki 文档建议增加 `document_chunks`，保存 chunk 原文、heading path、分词文本、n-gram 文本和研发信号。`docs_fts` 负责分词/BM25 召回，`docs_ngram_fts` 负责分词失败时的字符 n-gram 兜底召回。

## 5. 文件目录

默认数据根目录：

```text
~/.codeask/
├── data.db
├── wiki/
├── skills/
├── sessions/        # 会话级临时数据，按 sessions/<session_id>/ 隔离
├── repos/
├── index/
└── logs/
```

## 6. Migration

使用 Alembic 管理 schema 版本。启动时自动迁移到 head。迁移失败时服务启动失败，不能进入半迁移状态。

当前 head 到 `0016`：

```text
0001 foundation
0002-0005 wiki-knowledge
0006 code-index
0007-0012 agent-runtime
0013-0015 frontend-workbench admin/session attachment corrections
0016 metrics-eval feedback/frontend_events/audit_log
```
