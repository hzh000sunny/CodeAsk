# API 与数据模型设计

## 1. 目标

API 与数据模型文档定义前后端、Agent 和持久化之间的稳定契约。

## 2. API 分组

一期 API：

- `/api/sessions`
- `/api/sessions/{id}/messages`
- `/api/sessions/{id}/attachments`
- `/api/reports`
- `/api/features`
- `/api/documents`
- `/api/skills`
- `/api/repos`
- `/api/llm-configs`
- `/api/healthz`
- `/api/metrics`

消息发送接口返回 SSE 流。

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
- `llm_configs`
- `system_settings`

`llm_configs.protocol` 一期支持：

```text
openai
openai_compatible
anthropic
```

Agent 不直接读取供应商协议字段。LLM 网关根据该字段选择适配器，并向 Agent 暴露统一事件流。

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
├── sessions/
├── repos/
├── index/
└── logs/
```

## 6. Migration

使用 Alembic 管理 schema 版本。启动时自动迁移到 head。迁移失败时服务启动失败，不能进入半迁移状态。
