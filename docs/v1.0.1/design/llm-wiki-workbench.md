# LLM Wiki 工作台系统设计

> 本文档属于 v1.0.1 SDD，描述独立 LLM Wiki 工作台的模块边界、目录结构、数据模型、API、前端组件拆分和 Agent 接入设计。
>
> 产品契约见 `../prd/llm-wiki.md`。若本文与 PRD 冲突，以 PRD 为准。

> 当前版本覆写：v1.0.1 第一版暂不启用 Wiki 写权限隔离，前后端保留权限通道，但当前所有用户都可执行 Wiki 写操作。

## 1. 设计目标

v1.0.1 的核心目标是把 Wiki 从“特性页内的文档上传面板”升级为独立、有目录树、有版本、有草稿、有软删除、有报告投影、有 Agent 回源能力的一级工作台。

设计必须提前切清楚模块边界，避免继续出现单文件、单组件无限增长：

- 后端把 Wiki 作为独立 bounded context，不再把 feature、document、report 的所有路由堆在 `api/wiki.py`。
- 前端新增独立 Wiki 页面和组件目录，不把完整 Wiki 管理塞进 `FeatureWorkbench`。
- 数据模型新增 Wiki 原生模型，不继续给 `documents` 表补字段承载目录树、版本、草稿和资源。
- `/api/wiki/*` 成为新 Wiki 的主 API；旧 `/api/documents` 仅作为短期兼容层。
- Wiki 不只是一棵树和一个编辑器，还必须覆盖来源、导入、索引、治理、临时证据和正式知识之间的生命周期。

## 2. 现有问题

v1.0 已具备基础文档上传、切块检索和报告回流，但它不是完整 Wiki。

当前主要问题：

| 区域 | 问题 |
|---|---|
| 后端 API | `src/codeask/api/wiki.py` 同时承担特性、仓库关联、文档、报告，边界混乱 |
| 后端模型 | `documents.feature_id` 是扁平结构，无法表达目录树、版本、草稿、资源和软删除恢复 |
| 后端服务 | 上传、索引、报告、搜索散落在 `codeask/wiki/*` 中，但缺少目录和生命周期领域层 |
| 前端 | Wiki 功能嵌在特性详情 tab，无法承载完整目录管理和编辑体验 |
| Agent | 检索偏 snippet，缺少可见 Wiki 范围解析和最终回答回源引用 |
| 权限 | 当前只有 admin cookie 和 subject id，缺少可替换的权限接口 |

v1.0.1 的设计目标不是重写整个系统，而是把新 Wiki 能力独立出来，同时保留 v1.0 API 的兼容路径。

## 2.2 当前实现快照

截至 2026-05-05，后端已经完成第一批可工作的 Wiki 原生骨架，作为 v1.0.1 的落地起点：

- 旧 `src/codeask/api/wiki.py` 已拆分为 `api/features.py`、`api/reports.py`、`api/documents_compat.py` 和 `api/wiki/` 包。
- `/api/wiki/spaces/by-feature/{feature_id}` 与 `/api/wiki/tree` 已可用，支持首次访问时的懒初始化。
- 创建 feature 时，会自动创建 `current` wiki space，并生成两个系统根目录：`知识库`、`问题定位报告`。
- 旧 `/api/documents` 上传的 Markdown，会同步映射成原生 `wiki_nodes` + `wiki_documents` + `wiki_document_versions`。
- 旧 `/api/reports` 创建的报告，会同步映射成原生 `wiki_report_refs`。
- 对旧库中的 feature / document / report，当前采用“首次访问 Wiki 时懒回填”的策略，而不是在 migration 中一次性重写全量历史数据。
- 当前已实现 `GET/POST/PUT/DELETE /api/wiki/nodes*` 的最小读写能力，并接入 owner/admin 写权限和系统目录保护。
- 当前已实现原生 Markdown 文档的最小 API：读取当前正文、按用户保存草稿、发布正式版本、列出历史版本。
- 当前已补上版本详情、版本 diff 和回滚接口，支持从历史版本生成新正式版本，不破坏旧版本链。
- 当前已补上 Markdown 相对引用解析的第一批后端能力：文档详情会返回 `resolved_refs_json` 和 `broken_refs_json`，用于前端渲染内部链接和展示断链。
- 当前已补上原生 Wiki asset 的第一批后端能力：支持上传图片等资源、按 node 读取资源内容，并让 Markdown 相对图片引用解析到对应 asset node。
- 当前已补上 import preflight 的第一批后端能力：支持通过 `multipart files[]` 上传目录文件集，以上传文件名承载相对路径，并返回 target path、路径冲突和 Markdown 断链警告。
- 当前已补上 import job staging 的第一批后端能力：支持创建 import job、把上传文件写入 `data_dir/wiki/imports/job_{id}/`、并查询 job summary 与 item 明细。
- 当前已补上 import apply 的第一批后端能力：支持把 staged 内容正式落成 native wiki nodes / documents / assets，并沿用现有文档发布链路生成版本和引用解析结果。
- 当前已确认 v1.0.1 导入体验需要从“preflight + apply”前端交互切换为“导入会话 + 文件队列”模型：preflight 保留为内部校验能力，不再作为用户可感知的独立阶段。
- 当前已补上导入会话后端的第一批能力：`wiki_import_sessions` / `wiki_import_session_items` 已落地，支持 `create / get / scan / list items / upload item`，并在最小链路上实现“逐文件上传后自动落库”。
- 当前目录导入的 `root_strip_segments=1` 已在导入会话模型中生效，`ops/Guide.md` 这类目录上传路径会导入到目标目录下的 `guide`，不会再多创建一层本地上传目录名。
- 当前已补上独立 Wiki 页的树面板可用性修正：目录树支持显式拖拽拉伸，节点长名称支持完整 title，节点右侧三点菜单已补入 `导入 Wiki` 入口。
- 当前已补上树内排序第一版：普通目录和 Markdown 文档支持三点菜单 `上移 / 下移`，普通目录和 Markdown 文档支持树内拖拽重排，Markdown 文档支持拖入目录。
- 当前前端上传实现已从“仅等待最终响应”切到“可汇报进度的请求层”，导入会话队列会在单文件上传过程中实时更新 `uploading + progress_percent`，顶部摘要同步反映总进度和当前处理文件。
- 当前已补上独立 `wiki/index` 和 `wiki/maintenance` 第一版边界：`WikiIndexService` 负责刷新 native wiki document 的派生状态，`POST /api/wiki/maintenance/nodes/{node_id}/reindex` 负责 owner/admin 手动 repair subtree。
- 当前 `publish / rollback / import apply` 已通过 `WikiIndexService` 收口正式文档状态刷新，不再把这部分逻辑继续散落到多个 service 内。

这批实现的目标是先建立稳定的后端边界和数据归属，而不是一次完成整个 Wiki 工作台。

## 2.1 架构重心修正

CodeAsk 的 LLM Wiki 不应只被理解为“独立 Wiki 工作台”。更准确的定义是：

> 一个围绕特性空间组织的工程知识系统，覆盖来源接入、导入预处理、正式知识沉淀、会话证据交互、报告回流、检索索引和 Agent 回源引用。

因此，架构上至少要明确六层：

| 层 | 职责 |
|---|---|
| source layer | 外部来源、本地目录、手工 Markdown、会话附件、未来可同步连接器 |
| ingest layer | 预检查、staging、导入任务、引用解析、冲突处理、结果记录 |
| formal wiki layer | spaces、nodes、documents、assets、versions、drafts、permissions |
| session and report layer | 会话附件、临时证据、问题定位报告、报告投影 |
| retrieval layer | chunk、signals、索引、搜索、回源读取 |
| operator layer | 重新索引、软删除清理、失败修复、来源刷新、审计与观测 |

原始 v1.0.1 草稿更偏重 `formal wiki layer` 和 `retrieval layer`。当前版本明确要求：`source layer`、`ingest layer` 和 `operator layer` 也必须在架构上占据正式位置。

## 3. 模块边界

### 3.1 后端 bounded context

后端按领域拆分：

| 领域 | 职责 |
|---|---|
| `features` | 特性本体、owner、描述、关联仓库、分析策略；负责触发 Wiki space 创建和归档 |
| `wiki` | Wiki 空间、目录树、Markdown 文档、版本、草稿、资源、导入、搜索、索引、权限检查 |
| `reports` | 问题定位报告生命周期；Wiki 只引用和投影报告 |
| `sessions` | 会话、附件、消息、运行轨迹；会话生成报告后调用 reports/wiki 服务 |
| `code_index` | 仓库同步和代码检索；不直接管理 Wiki 内容 |
| `agent` | 解析 Wiki 范围、调用 Wiki 工具、回源读取证据 |

边界规则：

- `features` 可以创建、归档、恢复 Wiki space，但不直接改 Wiki 文档内容。
- `wiki` 可以读取 feature 元信息做权限和展示，但不拥有 feature 生命周期。
- `reports` 拥有报告状态；`wiki_report_refs` 只负责树中投影。
- `agent` 只能通过 Wiki service/tool API 访问 Wiki，不直接读 Wiki 表。
- `sessions` 持有临时证据和上传附件，但不直接写正式 Wiki 文档；正式沉淀必须经过 wiki/import 或 wiki/promotion 边界。

### 3.2 前端 bounded context

前端按一级页面和业务能力拆分：

| 目录 | 职责 |
|---|---|
| `components/layout` | 全局 TopBar、Sidebar、Shell，不包含 Wiki 业务逻辑 |
| `components/session` | 会话工作台 |
| `components/features` | 特性列表、特性设置、轻量 Wiki 预览入口 |
| `components/wiki` | 独立 Wiki 工作台完整 UI |
| `components/settings` | 用户设置和全局设置 |
| `lib/wiki` | Wiki API client、query key、路径工具、权限工具 |
| `types/wiki.ts` | Wiki 前端类型 |

边界规则：

- `FeatureWorkbench` 只渲染当前特性的 Wiki 子树预览和跳转入口。
- `KnowledgePanel` 只承担轻量阅读入口：左侧是当前特性的局部目录树，右侧只渲染正文，不复刻独立 Wiki 页的详情头、报告计数或完整管理操作。
- Wiki 上传、编辑、移动、删除、版本历史、导入任务只在 `components/wiki` 内实现。
- `components/wiki` 不直接调用通用 `apiRequest` 以外的其它页面状态；跨页面跳转通过 URL state 表达。
- Markdown 渲染基础组件可以复用 `components/ui/MarkdownRenderer.tsx`，但 Wiki 专用资源解析和 heading 定位放在 `lib/wiki`。
- 当前版本不在前端基于 `owner/admin/member` 隐藏 Wiki 写入口；按钮显示与后端行为保持一致，统一按 v1.0.1 全员可写处理。

## 4. 后端目录结构

### 4.1 目标结构

后端目标结构如下：

```text
src/codeask/
├── api/
│   ├── features.py                         # 特性 API，从旧 wiki router 中拆出
│   ├── reports.py                          # 报告生命周期 API，从旧 wiki router 中拆出
│   ├── documents_compat.py                 # 旧 /api/documents 兼容层
│   └── wiki/
│       ├── __init__.py                     # 导出 router
│       ├── router.py                       # 汇总 /api/wiki 子路由
│       ├── deps.py                         # session、actor、权限依赖
│       ├── schemas.py                      # API 输入输出 schema 汇总或 re-export
│       ├── spaces.py                       # /api/wiki/spaces
│       ├── tree.py                         # /api/wiki/tree, /api/wiki/nodes
│       ├── documents.py                    # Markdown 文档读写
│       ├── drafts.py                       # 自动草稿
│       ├── versions.py                     # 历史版本和回滚
│       ├── assets.py                       # 图片等资源
│       ├── imports.py                      # 目录上传和导入任务
│       ├── search.py                       # Wiki 搜索
│       ├── reports.py                      # Wiki 报告投影和虚拟分组
│       └── maintenance.py                  # 重新索引、软删除清理等修复入口
├── db/
│   └── models/
│       └── wiki/
│           ├── __init__.py
│           ├── space.py
│           ├── node.py
│           ├── document.py
│           ├── asset.py
│           ├── import_job.py
│           └── event.py
├── features/
│   ├── __init__.py
│   ├── service.py                          # 特性创建、归档、恢复
│   └── repo.py                             # feature DB 访问
├── reports/
│   ├── __init__.py
│   ├── service.py                          # 报告生命周期
│   ├── repo.py
│   └── projections.py                      # 报告状态到 Wiki 虚拟分组的映射
└── wiki/
    ├── __init__.py
    ├── actor.py                            # 当前操作者模型，后续接 AuthProvider
    ├── permissions.py                      # can_read/can_write/can_admin
    ├── paths.py                            # node path、slug、冲突检测
    ├── events.py                           # wiki_node_events 记录
    ├── spaces/
    │   ├── service.py
    │   └── repo.py
    ├── tree/
    │   ├── service.py
    │   ├── repo.py
    │   └── virtual_nodes.py                # 当前特性/历史特性/报告状态虚拟节点
    ├── documents/
    │   ├── service.py
    │   ├── repo.py
    │   ├── drafts.py
    │   ├── versions.py
    │   └── renderer.py
    ├── assets/
    │   ├── service.py
    │   ├── repo.py
    │   └── storage.py
    ├── imports/
    │   ├── service.py
    │   ├── repo.py
    │   ├── preflight.py
    │   ├── unpacker.py
    │   └── references.py
    ├── index/
    │   ├── service.py
    │   ├── chunker.py
    │   ├── tokenizer.py
    │   ├── signals.py
    │   └── search.py
    ├── reports/
    │   ├── service.py
    │   └── repo.py
    └── cleanup.py                          # 30 天软删除清理任务
```

说明：

- `src/codeask/api/wiki.py` 应迁移为 `src/codeask/api/wiki/` 包。`codeask.api.wiki.router` 仍向外导出 `router`，让 `app.py` 的导入变化最小。
- 当前已经实际落地 `api/wiki/router.py`、`api/wiki/spaces.py`、`api/wiki/tree.py`、`api/wiki/nodes.py`，后续再继续补 documents/drafts/versions/imports 等子路由。
- 旧 `src/codeask/wiki/chunker.py`、`search.py`、`signals.py`、`tokenizer.py` 可以先移动到 `src/codeask/wiki/index/`，保留兼容 re-export，避免一次性破坏现有测试。
- 旧 `src/codeask/wiki/reports.py` 应拆到 `reports/service.py` 和 `wiki/reports/service.py`，明确报告生命周期和 Wiki 投影的差异。
- 每个 service 文件只承载一个聚合根的业务规则。超过约 350 行时应继续拆分，不继续堆方法。

### 4.2 API router 拆分

`api/wiki/router.py` 只负责汇总子路由：

```python
router.include_router(spaces.router, prefix="/wiki/spaces", tags=["wiki-spaces"])
router.include_router(tree.router, prefix="/wiki", tags=["wiki-tree"])
router.include_router(documents.router, prefix="/wiki/documents", tags=["wiki-documents"])
router.include_router(drafts.router, prefix="/wiki/documents", tags=["wiki-drafts"])
router.include_router(versions.router, prefix="/wiki/documents", tags=["wiki-versions"])
router.include_router(assets.router, prefix="/wiki/assets", tags=["wiki-assets"])
router.include_router(imports.router, prefix="/wiki/imports", tags=["wiki-imports"])
router.include_router(search.router, prefix="/wiki/search", tags=["wiki-search"])
router.include_router(reports.router, prefix="/wiki/reports", tags=["wiki-reports"])
router.include_router(maintenance.router, prefix="/wiki/maintenance", tags=["wiki-maintenance"])
```

旧 API 拆分：

| 当前路由 | v1.0.1 归属 | 策略 |
|---|---|---|
| `/api/features/*` | `api/features.py` | 保持路径，迁出 `api/wiki.py` |
| `/api/documents/*` | `api/documents_compat.py` | 兼容旧前端和测试，不增加新能力 |
| `/api/reports/*` | `api/reports.py` | 保持报告生命周期 API |
| `/api/wiki/*` | `api/wiki/` | 新 Wiki 主 API |

## 5. 数据模型

v1.0.1 采用 Wiki 原生模型，不继续在 `documents` / `reports` 上补丁。

当前已落地的关键补充：

- `wiki_documents.legacy_document_id` 用于稳定绑定旧 `documents.id`，避免只依赖 `provenance_json` 做弱映射。
- `wiki_nodes(space_id, path)` 当前使用“仅对 `deleted_at IS NULL` 生效”的唯一约束，满足软删除后的路径重建需求。
- 旧 document/report 到 Wiki 原生树的同步由 `src/codeask/wiki/sync/service.py` 负责，不把兼容层逻辑直接堆进 API handler。
- 原生 Markdown 正式内容采用 `wiki_document_versions` 追加式保存，`wiki_documents.current_version_id` 只指向当前正式版本。
- 草稿采用 `wiki_document_drafts(document_id, subject_id)` 存储，当前设计是“每个用户对同一文档只有一份活动草稿”。
- 版本对比使用统一 diff 文本输出，回滚会新增版本而不是改写历史版本。
- 当前相对引用解析范围已覆盖 Markdown 内部链接和图片链接的路径标准化、相对路径折叠与断链识别；手工 asset 上传和图片内容服务化已经落地，目录级导入和 staging 仍在后续阶段。

### 5.1 核心表

```text
wiki_spaces
  id
  feature_id
  scope: current | history
  display_name
  slug
  status: active | archived
  archived_at
  archived_by
```

```text
wiki_nodes
  id
  space_id
  parent_id
  type: folder | document | asset | report_ref
  name
  path
  system_role
  sort_order
  deleted_at
  deleted_by
```

```text
wiki_documents
  node_id
  title
  current_version_id
  summary
  index_status
  broken_refs_json
  provenance_json
```

```text
wiki_document_versions
  id
  document_node_id
  version_no
  content_markdown
  rendered_cache
  saved_by
  saved_at
  change_summary
```

```text
wiki_document_drafts
  document_node_id
  draft_markdown
  updated_by
  updated_at
```

```text
wiki_assets
  node_id
  raw_file_path
  mime_type
  size
  content_hash
  provenance_json
```

```text
wiki_report_refs
  node_id
  report_id
  status_snapshot
```

```text
wiki_node_events
  id
  node_id
  event_type
  actor_subject_id
  before_json
  after_json
  created_at
```

```text
wiki_sources
  id
  space_id
  source_type: manual_upload | directory_import | session_promotion | repo_docs | external_link
  display_name
  source_ref
  sync_enabled
  sync_status
  last_synced_at
  next_sync_at
  config_json
```

```text
wiki_import_sessions
  id
  space_id
  target_parent_node_id
  actor_subject_id
  mode: markdown | directory
  root_strip_segments
  status: running | completed | cancelled
  total_count
  pending_count
  uploading_count
  uploaded_count
  conflict_count
  failed_count
  ignored_count
  skipped_count
  options_json
  summary_json
  created_at
  updated_at
  finished_at
```

```text
wiki_import_session_items
  id
  session_id
  source_name
  relative_path
  normalized_relative_path
  staging_path
  target_path
  item_kind: document | asset | ignored
  status: pending | uploading | uploaded | conflict | failed | ignored | skipped
  progress_percent
  ignore_reason
  conflict_reason
  error_message
  result_node_id
  content_hash
  warnings_json
  result_json
  created_at
  updated_at
```

### 5.2 约束

关键唯一性和完整性约束：

- `wiki_spaces.feature_id` 唯一。
- 同一 `space_id + path` 下 active node 唯一。
- 同一 `document_node_id + version_no` 唯一。
- 系统目录 `知识库` 和 `问题定位报告` 每个 space 只能各有一个。
- `wiki_report_refs.report_id` 对同一 feature space 唯一，避免报告重复投影。
- `wiki_sources.space_id + source_ref` 在启用状态下应可唯一约束，避免同一来源被重复注册为可同步来源。

路径原则：

- 内部引用使用稳定 `node_id`。
- UI 展示中文路径。
- URL 优先使用 `node_id`，例如 `/wiki?node=123`。
- 保存分析策略时尽量把路径解析为 `node_id`，目录重命名后策略不失效。

来源原则：

- 正式 wiki document 和 asset 应可追溯其来源，不论来源是手工上传、目录导入、会话晋级还是未来的连接器同步。
- `wiki_sources` 是长期来源注册表；不是所有文档都必须有 source，但所有导入型或可同步型文档都应该能绑定 source。
- `wiki_import_sessions` 记录一次用户可感知的导入会话；`wiki_import_session_items` 记录每个文件的逐项状态、进度、冲突与结果。
- provenance 不应只存在于审计日志；它应成为文档详情、导入结果和后续刷新逻辑可直接读取的数据。

### 5.3 迁移策略

迁移分三层：

1. 创建新表和 service，不改变旧 API 行为。
2. 从现有 `features`、`documents`、`reports` 初始化 Wiki spaces、nodes、versions 和 report refs。
3. 前端切到新 `/api/wiki/*` 后，旧 `/api/documents` 保留为兼容层。

迁移规则：

- 每个 feature 创建一个 `wiki_space(status=active, scope=current)`。
- 每个 space 自动创建系统目录 `知识库` 和 `问题定位报告`。
- 现有 `documents` 迁移到 `知识库` 下，创建 document node、document current state 和第一个正式 version。
- 现有 reports 通过 `wiki_report_refs` 投影到 `问题定位报告`。
- verified report 显示在虚拟 `已验证`，rejected 显示在 `未通过`，其它显示在 `草稿`。
- 迁移后的现有 documents 默认视为 `manual_upload` provenance；后续新架构落地后，再逐步支持更细粒度来源。

## 6. API 契约

### 6.1 Space 和目录树

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/wiki/tree` | 获取全 Wiki 目录树，含 `当前特性` 和 `历史特性` 虚拟根 |
| `GET` | `/api/wiki/spaces` | 获取 Wiki space 列表 |
| `GET` | `/api/wiki/spaces/{space_id}` | 获取 space 详情和权限 |
| `POST` | `/api/wiki/spaces/{space_id}/restore` | 管理员恢复历史特性 |
| `GET` | `/api/wiki/nodes/{node_id}` | 获取节点元信息 |
| `POST` | `/api/wiki/nodes` | 新建目录或 Markdown 文档节点 |
| `PUT` | `/api/wiki/nodes/{node_id}` | 重命名、兼容性父节点更新、直接写入排序值 |
| `POST` | `/api/wiki/nodes/{node_id}/move` | 树排序第一版专用接口；按目标父节点和目标索引执行同级重排或拖入目录 |
| `DELETE` | `/api/wiki/nodes/{node_id}` | 软删除节点 |
| `POST` | `/api/wiki/nodes/{node_id}/restore` | 恢复软删除节点 |

节点响应必须包含权限：

```json
{
  "id": 123,
  "type": "document",
  "name": "订单提交失败.md",
  "path": "订单中心 / 知识库 / 错误码 / 订单提交失败.md",
  "permissions": {
    "can_read": true,
    "can_write": false,
    "can_delete": false,
    "can_admin": false,
    "reason": "viewer"
  }
}
```

### 6.2 文档、草稿和版本

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/wiki/documents/{node_id}` | 读取当前正式 Markdown、渲染信息、引用状态 |
| `PUT` | `/api/wiki/documents/{node_id}` | 保存正式版本，触发索引 |
| `GET` | `/api/wiki/documents/{node_id}/draft` | 读取当前用户草稿 |
| `PUT` | `/api/wiki/documents/{node_id}/draft` | 自动保存草稿，不触发索引 |
| `DELETE` | `/api/wiki/documents/{node_id}/draft` | 丢弃草稿 |
| `GET` | `/api/wiki/documents/{node_id}/versions` | 查看版本列表 |
| `GET` | `/api/wiki/documents/{node_id}/versions/{version_id}` | 查看历史版本 |
| `GET` | `/api/wiki/documents/{node_id}/diff?from=&to=` | 查看版本 diff |
| `POST` | `/api/wiki/documents/{node_id}/versions/{version_id}/rollback` | 回滚并生成新版本 |

文档响应除正文、版本和断链信息外，还应返回来源摘要：

- 手工上传还是目录导入
- 是否来自会话晋级
- 是否绑定长期 source
- 最近一次导入或同步状态

### 6.3 上传和导入

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/wiki/assets` | 上传单个 Wiki asset，创建原生 `asset` node |
| `GET` | `/api/wiki/assets/{node_id}/content` | 读取 asset 二进制内容，用于 Markdown 图片渲染 |
| `POST` | `/api/wiki/import-sessions` | 创建一次导入会话，绑定 target 目录、mode 和导入选项 |
| `POST` | `/api/wiki/import-sessions/{session_id}/scan` | 登记本次扫描出的完整文件列表，包括忽略项和目标路径草案 |
| `POST` | `/api/wiki/import-sessions/{session_id}/items/{item_id}/upload` | 上传单个文件并即时返回成功 / 冲突 / 失败 |
| `POST` | `/api/wiki/import-sessions/{session_id}/items/{item_id}/resolve` | 对单个冲突项执行 `overwrite` 或 `skip` |
| `POST` | `/api/wiki/import-sessions/{session_id}/bulk-resolve` | 对当前冲突项执行 `overwrite_all` 或 `skip_all` |
| `POST` | `/api/wiki/import-sessions/{session_id}/items/{item_id}/retry` | 重试单个失败文件 |
| `POST` | `/api/wiki/import-sessions/{session_id}/retry` | 重试全部失败文件 |
| `GET` | `/api/wiki/import-sessions/{session_id}` | 读取导入会话摘要，用于抽屉恢复和切页后回看 |
| `GET` | `/api/wiki/import-sessions/{session_id}/items` | 读取完整文件列表和逐文件状态 |
| `POST` | `/api/wiki/import-sessions/{session_id}/cancel` | 取消本次导入；已成功项不回滚，未完成项终止 |

导入任务必须能够表达：

- Markdown 入口与目录入口的差异。
- 目录导入时剥掉本地上传目录的最外层目录名，仅保留内部相对结构。
- 成功、冲突、失败、忽略、跳过数量。
- 当前正在处理的文件名。
- 每个 item 的相对路径、目标路径、逐项状态、进度、冲突原因、失败原因和最终导入结果。
- 失败重试、冲突单项处理与全部覆盖 / 全部跳过。
- 关闭抽屉后继续后台上传，以及重新打开抽屉后的状态恢复。

前端交互约束：

- 导入抽屉使用两个独立选择入口：`选择 Markdown` 与 `选择目录`。
- 目录选择入口只负责批量目录导入；Markdown 入口支持单文件和多文件补录。
- 导入抽屉首屏不再保留单独的说明横幅；可见内容只保留两个导入入口卡片和下方队列区。
- 两个导入入口卡片采用固定、紧凑宽度，不平分整个抽屉高度或宽度；多余空间优先留给文件队列。
- 用户完成选择后立即展示完整文件队列，而不是独立 preflight 面板。
- 顶部摘要除目标目录和计数外，还要显示聚合总进度，以及当前正在处理的文件名；忽略文件不计入总进度。
- 文件队列默认按选择顺序排列，并提供“仅看进行中/失败”过滤视图。
- 前端逐文件上传采用“本地顺序调度 + 单项失败继续后续项”的策略：某个 item 请求失败时，当前项转为 `failed` 并保留错误提示，队列继续推进到后面的 `pending` 项；整批导入是否最终可 materialize 仍由后端 session 状态决定。
- `wiki_import_session_items` 的读模型需要把 `error_message` 一并返回，前端队列行直接渲染冲突或失败原因，不额外设计隐藏式详情面板。
- 忽略文件固定放在列表底部，默认折叠。
- 冲突操作直接在当前文件行内展开：`覆盖 / 跳过 / 全部覆盖 / 全部跳过`。
- 当前前端队列采用顺序调度；单个冲突或失败文件不会阻塞后续 `pending` 文件继续上传。
- 关闭抽屉或切页时，如队列未完成，需要弹确认框让用户选择继续后台上传或取消。
- 导入完成后关闭抽屉、刷新目录树，并优先打开目标一级目录下的第一篇 Markdown 文档。
- 在尚未选择文件时，队列空状态占位卡片需要随着队列容器一起撑满剩余高度，不能只显示内容高度后留下大面积空白。

### 6.4 来源和晋级接口

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/wiki/sources?space_id=` | 获取某个 wiki space 的长期来源注册表 |
| `POST` | `/api/wiki/sources` | 注册一个长期来源，初期可只支持本地目录或 repo docs |
| `PUT` | `/api/wiki/sources/{source_id}` | 更新来源显示名、同步开关或配置 |
| `POST` | `/api/wiki/sources/{source_id}/sync` | 手动触发来源刷新 |
| `POST` | `/api/wiki/promotions/session-attachment` | 将会话附件或会话产物晋级为 wiki 导入项或正式文档 |

说明：

- `wiki/sources` 可以在 v1.0.1 只做最小可用注册与元数据返回，不要求一次实现完整连接器矩阵。
- `wiki/promotions/*` 不要求在 v1.0.1 落地完整 UI，但架构上必须预留“临时证据 -> 正式知识”的边界。

### 6.5 搜索和报告投影

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/wiki/search?q=&feature_id=&current_feature_id=` | Wiki 搜索第一版；当前覆盖正式 Wiki 文档和问题报告 |
| `GET` | `/api/wiki/resolve-path?q=&feature_id=` | 口语化路径解析第一版；返回当前特性范围内的候选 Wiki 节点 |
| `GET` | `/api/wiki/reports/projections?feature_id=` | 获取某个特性的报告投影列表 |
| `GET` | `/api/wiki/reports/by-node/{node_id}` | 在 Wiki 语义下按投影节点读取报告正文 |

说明：

- 报告生命周期状态变更仍委托现有 `/api/reports/*` API 和 `reports.service` 执行。
- Wiki API 当前负责“如何在 Wiki 工作台里读取和展示报告”，而不是复制一套新的报告生命周期入口。
- `feature_id` 仍保留为硬过滤参数，兼容特性页或未来局部搜索场景。
- `current_feature_id` 用于全局 Wiki 搜索的上下文分组，不收窄搜索范围。
- 搜索第一版当前返回 `group_key/group_label` 供前端直接渲染，已覆盖 `当前特性 / 问题定位报告 / 其它当前特性 / 历史特性` 四个分组，匹配规则大小写不敏感。
- 路径解析第一版只覆盖当前特性的 current space，支持 `知识库` / `问题报告` 根目录别名，以及按名称、路径尾段和 token 包含关系返回候选节点。

## 7. 服务设计

### 7.1 权限服务

`wiki/permissions.py` 提供统一权限判断：

```text
resolve_actor(request)
can_read(actor, space)
can_write(actor, space)
can_delete(actor, node)
can_admin(actor)
```

`actor` 当前由 admin cookie 和 subject id 组成，后续替换为 AuthProvider。

所有写 API 必须在服务层校验权限。前端隐藏按钮只是体验优化，不是权限边界。

### 7.2 路径和冲突服务

`wiki/paths.py` 负责：

- 规范化路径。
- 构造展示路径。
- 检查同级命名冲突。
- 检查移动是否造成循环。
- 批量重算目录下节点路径。
- 将口语化路径候选解析为 node。

当前实现补充：

- `wiki/path_resolver.py` 已作为独立服务落地，不再把口语化路径解析混进 `search` 或 `tree` 服务。
- 第一版 resolver 只做候选返回，不做强制单结果判定，供后续 Agent scope 解析继续叠加。

路径冲突一律阻断，不自动覆盖或重命名。

### 7.3 文档服务

`wiki/documents/service.py` 负责：

- 新建 Markdown。
- 读取当前正式版本。
- 自动保存草稿。
- 正式保存并生成版本。
- 回滚历史版本。
- 解析 Markdown 引用。
- 触发索引更新。
- 记录 node event。

文档服务不直接处理目录上传，目录上传由 `wiki/imports/service.py` 编排。

### 7.4 来源服务

`wiki/sources/service.py` 负责：

- 注册和更新可长期追踪的来源。
- 判断某来源是否支持刷新。
- 记录来源的最近刷新状态。
- 为导入任务和正式文档提供 provenance 装配。

v1.0.1 不要求完成全连接器生态，但来源服务必须存在，这样手工目录导入、repo docs 导入和未来可同步来源才不会混在一起。

### 7.4A 资源服务

`wiki/assets/service.py` 负责：

- 校验上传者对目标 feature space 的写权限。
- 创建原生 `asset` node，并保留资源在目录树中的路径语义。
- 生成去重后的目标路径，避免同目录资源名冲突。
- 存储资源文件，并记录 `mime_type`、原始文件名、文件大小和 provenance。
- 按 `node_id` 回读资源内容，供 Markdown 预览直接请求。

当前这层只覆盖单文件手工上传和内容读取。目录批量导入、统一 staging 和来源刷新仍由 `wiki/imports/*`、`wiki/sources/*` 继续扩展。

### 7.5 导入服务

`wiki/imports/service.py` 负责目录导入流程：

```text
创建 import session
→ 前端登记完整文件列表
→ 过滤有效导入项并保留忽略项
→ 逐文件上传到 staging
→ 即时执行冲突判断和导入
→ 记录 import session items 的逐项状态
→ 对冲突项等待用户决策
→ 对成功项创建 node、document、version、asset
→ 批量或增量索引
→ 更新会话摘要和最终结果
```

导入会话必须可查询，因为目录导入会跨越多个前端请求，并且需要支持抽屉关闭后的后台继续上传。

CodeAsk 的导入不是一个布尔成功与否的动作，而是一组 staging item 的状态机。导入服务应围绕这一点设计。

当前已经落地的 preflight 子集：

- 接收 `space_id`、可选 `parent_id` 和 `multipart files[]`。
- 将上传文件名视为相对路径来源，而不是只看叶子文件名。
- 规范化目标 node path，并识别上传集内部冲突与现有 Wiki 路径冲突。
- 解析 Markdown 相对 `.md` / 图片引用，优先在上传集内部解析，其次回看现有 Wiki node。
- 对断链返回 warning，不阻断 preflight；对路径冲突返回 error，并把整次 preflight 标记为 `ready=false`。

当前已经落地的 import job staging 子集：

- `POST /api/wiki/imports` 内部复用同一套 preflight 规则。
- 若 preflight 包含 conflict，则返回 `409`，不创建 job。
- 若 preflight 可通过，则创建 `wiki_import_jobs`、`wiki_import_items`，并将原文件内容按相对路径写入 `data_dir/wiki/imports/job_{id}/`。
- `GET /api/wiki/imports/{job_id}` 返回 job 级 summary。
- `GET /api/wiki/imports/{job_id}/items` 返回 item kind、target path、warnings 和 staging path。
- `POST /api/wiki/imports/{job_id}/apply` 会把 staged 内容正式落库：
  - Markdown 文件创建 document node + document row + version。
  - 资源文件创建 asset node + wiki asset row。
  - 版本生成后，引用解析复用现有文档发布逻辑。
- Markdown 引用解析必须与 node path 规范化规则一致，folder / document leaf 都要走统一小写规范化，否则导入后的引用会误判为断链。
- 下一阶段需要把这些内部能力迁移到导入会话模型下复用，而不是继续直接暴露给前端作为独立 preflight/apply 流程。

### 7.6 索引服务

`wiki/index/service.py` 是 Wiki 索引唯一入口：

```text
index_document(node_id)
remove_document(node_id)
reindex_subtree(node_id)
index_report(report_id)
remove_report(report_id)
search(query, scope)
```

任何正式内容、路径、报告状态或资源引用变化都通过该服务自动更新索引。

### 7.7 报告投影服务

`wiki/reports/service.py` 负责：

- 确保报告在对应 feature space 下有 `wiki_report_ref`。
- 根据 report status 计算虚拟展示路径。
- 为 Wiki 页面读取报告内容和权限。
- 状态变更后触发报告索引更新或下架。

当前实现补充：

- 底层仍保存真实 `report_ref` 节点。
- `草稿 / 已验证 / 未通过` 分组当前由前端在 `问题定位报告` 根目录下做虚拟注入，避免第一轮就把“展示分组”和“存储结构”绑定死。
- 它不直接改变报告生命周期，生命周期动作调用 `reports/service.py`。

### 7.8 会话晋级服务

`wiki/promotions/service.py` 负责：

- 接收会话附件、会话生成产物或人工整理后的文本。
- 生成 import item 或直接生成正式 wiki document。
- 记录 provenance，标记其来源自 session 或 report。
- 触发索引和事件记录。

这部分不必在 v1.0.1 一次做完整，但架构上必须明确存在，否则会话、报告和 wiki 仍会各自割裂。

## 8. 前端目录结构

### 8.1 目标结构

```text
frontend/src/
├── components/
│   ├── layout/
│   │   ├── AppShell.tsx
│   │   ├── Sidebar.tsx                     # 新增 Wiki 一级导航
│   │   └── TopBar.tsx
│   ├── features/
│   │   ├── KnowledgePanel.tsx              # 轻量树和预览，不承载完整管理
│   │   └── ReportsPanel.tsx                # 报告预览和跳转
│   └── wiki/
│       ├── WikiPage.tsx                    # Wiki 页面入口，承接 AppShell 路由
│       ├── WikiWorkbench.tsx               # 页面编排，不写业务细节
│       ├── WikiWorkspacePane.tsx           # 阅读态 / 编辑态 / 报告态主工作区
│       ├── WikiWorkbenchDialogs.tsx        # 抽屉、确认框、导入弹层宿主
│       ├── WikiTreePane.tsx                # 当前特性/历史特性树
│       ├── WikiTreeNode.tsx
│       ├── WikiNodeMenu.tsx
│       ├── WikiSearchBar.tsx
│       ├── WikiSearchResults.tsx
│       ├── WikiReader.tsx                  # 阅读态容器
│       ├── WikiFloatingActions.tsx
│       ├── WikiDetailDrawer.tsx
│       ├── WikiEditor.tsx                  # 编辑态容器
│       ├── WikiSourceEditor.tsx
│       ├── WikiLivePreview.tsx
│       ├── WikiVersionDrawer.tsx
│       ├── WikiImportDialog.tsx
│       ├── WikiMoveDialog.tsx
│       ├── WikiDeleteDialog.tsx
│       ├── WikiReportViewer.tsx
│       ├── WikiEmptyState.tsx
│       ├── hooks/
│       │   ├── useWikiTree.ts
│       │   ├── useWikiDocument.ts
│       │   ├── useWikiDraftAutosave.ts
│       │   ├── useWikiSearch.ts
│       │   ├── useWikiImportSessionFlow.ts
│       │   ├── useWikiTreeLayout.ts
│       │   └── useWikiPermissions.ts
│       └── wiki-ui-types.ts
├── lib/
│   └── wiki/
│       ├── api.ts
│       ├── query-keys.ts
│       ├── routing.ts
│       ├── permissions.ts
│       ├── markdown.ts
│       ├── tree.ts
│       └── tree-selectors.ts
└── types/
    └── wiki.ts
```

### 8.2 组件职责

| 组件 | 职责 |
|---|---|
| `WikiPage` | 作为独立 Wiki 页面入口，承接 AppShell 与 URL 路由状态 |
| `WikiWorkbench` | 只做页面编排，串联树、工作区、弹窗和导入状态 |
| `WikiWorkspacePane` | 承接阅读态、编辑态、报告态和空态，不直接管理路由与导入流程 |
| `WikiWorkbenchDialogs` | 集中挂载详情、历史、导入、离开编辑、节点管理等弹层 |
| `AppShell` | 拦截离开 Wiki 的一级导航切换，并保留后台导入会话句柄用于回到 Wiki 后恢复 |
| `WikiTreePane` | 渲染目录树，处理展开、收起、选中和搜索定位 |
| `WikiNodeMenu` | 节点三点菜单，按权限和节点类型裁剪 |
| `WikiReader` | 阅读态正文布局，不包含编辑逻辑 |
| `WikiFloatingActions` | 详情、复制链接、编辑、更多 |
| `WikiDetailDrawer` | 元信息、索引状态、断链、引用、历史入口 |
| `WikiEditor` | 编辑态布局，组织 source editor 和 live preview |
| `WikiSourceEditor` | Markdown 源码输入，触发自动草稿 |
| `WikiLivePreview` | 实时预览，使用 Wiki 资源解析 |
| `WikiVersionDrawer` | 版本列表、diff、回滚 |
| `WikiImportDialog` | 上传 Markdown 或目录、文件队列、逐文件进度、冲突决策和失败重试 |
| `useWikiImportSessionFlow` | 管理导入会话创建、scan、队列上传、刷新树和自动打开首篇文档 |
| `useWikiTreeLayout` | 管理目录树收起、编辑态自动切换、宽度拖拽 |
| `WikiReportViewer` | 报告 Markdown 渲染和状态操作 |

拆分原则：

- 页面编排组件不直接写 API 细节。
- hooks 负责数据读取、状态保存和 mutation。
- `lib/wiki` 负责纯函数和 API client。
- 单个 React 组件目标不超过 250 行；超过时优先拆 UI 子组件或 hook。

### 8.3 路由状态

当前项目还没有完整 router。v1.0.1 可继续使用 AppShell 内部 section state，但必须把 Wiki 状态写入 URL query，支持刷新后保持页面：

```text
/?section=wiki&node=123
/?section=wiki&node=123&mode=edit
/?section=wiki&parent=456&action=upload-directory
/?section=wiki&node=789&drawer=history
```

如果后续引入 React Router，这些参数可以平滑迁移为：

```text
/wiki/nodes/123
/wiki/nodes/123/edit
/wiki/nodes/789/history
```

### 8.3A 已确认的前端默认行为

本轮头脑风暴已确认以下默认行为，后续实现以此为准：

- 用户进入某个特性对应的 Wiki 工作台时：
  - 如果该特性还没有任何 Wiki 文档，右侧显示空态。
  - 如果该特性已有 Wiki 文档，默认打开该特性目录下的第一篇可读 Wiki。
- 左侧目录树默认只展开 `知识库`。
- 特性页 `KnowledgePanel` 也遵循相同的默认展开原则：只展开 `知识库` 根目录，其下层目录默认收起，用户可以逐层展开 / 收起。
- `问题定位报告` 与用户自定义目录默认收起。
- 阅读态不使用“最近访问文档优先”的全局策略，而是优先遵循当前特性的上下文。

### 8.4 UI 设计约束

Wiki 工作台采用偏专业、简洁、舒适的 SaaS 工具风格。UI 参考 `ui-ux-pro-max` 的 Minimalism & Swiss Style：

- 主色使用中性色和清晰蓝色行动点，不做单一紫蓝或重渐变。
- 阅读区保证正文宽度和行高，优先服务长文阅读。
- 操作入口轻量，不把管理按钮铺满正文顶部。
- hover 和展开动效保持 150-250ms，并尊重 `prefers-reduced-motion`。
- 目录树、搜索结果、版本列表等固定区域必须有明确滚动容器，不让页面无限撑高。
- 下拉菜单、悬浮操作、抽屉不能被卡片或滚动容器裁切。
- 阅读态默认不展示导入任务状态栏，也不展示常驻元信息条；来源、更新时间、索引状态、断链、历史版本都通过抽屉或轻量浮层进入。导入相关状态只在导入抽屉内部展示。
- 特性页知识库右侧预览继续收缩为“正文优先”：不显示文档名头部，不显示特性级报告计数。
- 编辑态目录展开/收起按钮不放在右上角工具区，而是放在目录树与主内容交界线的中部，沿用当前工作台侧边栏的悬浮箭头交互语言。
- 阅读态顶部动作固定为 `详情 / 复制链接 / 编辑 / 更多`，`历史版本 / 导入 Wiki` 收入 `更多` 浮层，避免正文上方工具栏继续膨胀。
- Markdown 相对图片若断链或运行时加载失败，正文区需要显示可见占位块，不能只保留浏览器原生破图图标。

当前实现快照（2026-05-05）：

- 已落地独立 `Wiki` 一级入口和 hash 路由恢复。
- 已落地左树右正文阅读态、详情抽屉、历史版本抽屉、导入抽屉。
- 已落地编辑态双栏、进入编辑态默认收起目录树、自动草稿、发布、diff、回滚。
- 已落地报告投影阅读态，支持在 `问题定位报告` 根下按状态分组查看报告。
- 已落地 Wiki 搜索第一版，当前支持全局搜索并按 `当前特性 / 问题定位报告 / 其它当前特性 / 历史特性` 分组展示结果，且匹配大小写不敏感。
- 已落地编辑态离开确认和目录树节点三点菜单，支持新建目录、新建 Wiki、重命名、删除。
- 已落地 native wiki repair API：owner/admin 可对节点子树触发手动 reindex，用于修复正式文档派生状态。
- 当前详情抽屉仍未完整展示路径和更新时间；README 落地状态整理、一级页面刷新手工联调仍待补。

阅读态：

```text
┌───────────────────────────────────────────────────────────────┐
│ Wiki 搜索 / 当前路径                                   操作区 │
├───────────────┬───────────────────────────────────────────────┤
│ 目录树         │ Markdown 渲染预览                              │
│ 当前特性       │                                               │
│ 历史特性       │                                               │
└───────────────┴───────────────────────────────────────────────┘
```

说明：

- 默认阅读态是“纯正文阅读态”，正文上方不保留来源、更新时间、导入任务等常驻辅助栏。
- `详情`、`历史版本`、`断链`、`索引状态` 等全部从抽屉进入。
- 报告投影节点进入右侧时，正文区直接切换为报告预览视图，不复用文档编辑态。
- Markdown 内部 `.md` 链接在阅读态中直接写回 `#/wiki?feature=...&node=...`，点击后无额外中转页。

编辑态：

```text
┌───────────────────────────────────────────────────────────────┐
│ 当前路径                         保存 / 发布 / 取消 / 版本入口 │
├───────────────────────────────┬───────────────────────────────┤
│ Markdown 源码编辑区             │ 实时 Markdown 预览             │
└───────────────────────────────┴───────────────────────────────┘
```

编辑态默认收起目录树，保留轻量展开按钮。

补充说明：

- `历史版本` 表示正式发布后的历史快照，不包含自动草稿。
- 用户可以查看任意历史快照、做 diff、以及回滚到某一正式版本；回滚本身仍生成新的正式版本。
- 取消编辑不会再用文本 prompt；当前通过确认弹窗选择“继续编辑 / 保留草稿离开 / 丢弃草稿 / 发布并离开”。

## 9. Agent 接入设计

### 9.1 工具接口

Agent 使用的 Wiki 工具应由 Wiki 服务提供，不直接访问表：

```text
resolve_wiki_path(description, feature_hint?)
list_wiki_children(node_id)
search_wiki(query, scope)
read_wiki_node(node_id)
search_wiki_reports(query, scope)
read_wiki_report(report_id)
```

`scope` 支持：

- 当前特性默认范围。
- 分析策略指定目录。
- 用户问题口语化引用目录。
- 历史特性显式引用范围。
- 会话上传附件范围。

当前实现补充：

- Agent 运行时已通过 `agent/wiki_tools.py` 接入 native wiki 数据面，不再依赖旧的 legacy documents search。
- 当前已提供 `search_wiki`、`search_reports`、`read_wiki_doc`、`read_wiki_node`、`read_report` 五个运行时工具后端；其中 `read_wiki_doc` 作为兼容别名保留，后续 prompt 和文档统一使用 `read_wiki_node`。
- 当前已提供 `describe_scope` 能力，`knowledge_retrieval` 阶段会把默认系统目录和口语化路径命中的候选节点写入 `wiki_scope_resolution` 运行事件。
- `scope_detection` 阶段选中的 `feature_ids` 已通过运行时 metadata 显式传递到 `knowledge_retrieval`，避免知识检索阶段重新退回到所有 feature digest。
- `AgentWikiToolService` 当前已支持多特性输入：`describe_scope` 会在多个 feature 间聚合默认目录和匹配节点，`search_wiki / search_reports` 会跨 feature 合并 native search 命中并去重后再按 score 截断。

### 9.2 运行事件

会话运行事件必须展示 Wiki 范围解析结果：

```text
Wiki 目录解析

识别到：
- 订单中心 / Prompt 上下文
- 订单中心 / 客户环境

检索范围：
- 订单中心 / 知识库（默认）
- 订单中心 / 问题定位报告 / 已验证（默认）
- 订单中心 / Prompt 上下文（策略指定）
- 订单中心 / 客户环境（用户问题指定）
```

如果引用历史特性，需要提示历史性质。如果解析失败，需要展示失败原因。

当前实现补充：

- 第一版运行事件已展示两类信息：
  - 默认检索范围，如 `知识库 / 问题定位报告`
  - 显式命中目录，如用户问题中提到的具体 Wiki 路径候选
- 前端运行事件弹层已支持 Markdown 渲染，可直接点击跳转到对应 Wiki node。

### 9.3 证据回源

Agent 最终回答中的 Wiki 引用必须是可点击路径。实现上应返回：

```json
{
  "type": "wiki_document",
  "node_id": 123,
  "path": "订单中心 / 知识库 / 错误码 / 订单提交失败.md",
  "heading": "ERR_ORDER_CONTEXT_EMPTY",
  "url": "/?section=wiki&node=123&heading=ERR_ORDER_CONTEXT_EMPTY"
}
```

前端 Markdown 渲染器应把该引用渲染为可点击链接。

当前实现补充：

- 当前已完成 Wiki 文档的 node + heading 级证据回链：回答阶段会把 `[ev_knowledge_*]` 改写成 `#/wiki?feature=..&node=..&heading=..` 的 Markdown 链接。
- 独立 Wiki 路由已支持 `heading` 参数，阅读器会把 Markdown 标题渲染成稳定锚点，并在进入页面时直接滚动到对应标题。
- 问题报告当前仍以 node 级跳转为主，不附带 heading 锚点。

## 10. 测试策略

后端测试：

- `tests/unit/test_wiki_paths.py`：路径规范化、冲突检测、循环移动阻断。
- `tests/unit/test_wiki_permissions.py`：viewer、owner、admin 权限矩阵。
- `tests/unit/test_wiki_markdown_refs.py`：相对图片和 Markdown 链接解析。
- `tests/integration/test_wiki_spaces_api.py`：space 创建、归档、恢复。
- `tests/integration/test_wiki_tree_api.py`：目录树、虚拟根、系统目录。
- `tests/integration/test_wiki_documents_api.py`：新建、读取、保存、软删除。
- `tests/integration/test_wiki_drafts_versions_api.py`：草稿、版本、diff、回滚。
- `tests/integration/test_wiki_imports_api.py`：preflight、冲突阻断、断链警告。
- `tests/integration/test_wiki_reports_projection.py`：报告虚拟状态分组和索引资格。
- `tests/integration/test_wiki_agent_tools.py`：路径解析、检索、回源。

前端测试：

- Wiki 刷新后保持 `section=wiki` 和当前 node。
- 阅读态 Markdown 不溢出，正文容器可滚动。
- 编辑态源码和预览同屏，目录树默认收起。
- 节点菜单不被滚动容器裁切。
- 无写权限时写操作不可见；直接调用写 mutation 失败后有消息提示。
- 自动草稿在刷新后可恢复。
- 版本历史可查看、对比、回滚。
- 导入冲突列表可读，不自动覆盖。

## 11. 实施顺序

推荐顺序：

1. 后端模型和迁移骨架。
2. provenance、source、import item 模型补齐。
3. Wiki 权限、路径、tree service。
4. `/api/wiki/tree` 和 node CRUD。
5. Markdown document、draft、version service。
6. 前端 Wiki 一级导航和阅读态。
7. 前端编辑态和自动草稿。
8. 上传导入任务、staging item 和资源引用。
9. 报告投影和虚拟状态分组。
10. 搜索、索引和 Agent 回源。
11. 特性页轻量 Wiki 预览改造。
12. 兼容 API 整理、来源刷新入口和旧路径降级。

## 12. 明确不做

v1.0.1 不做：

- 完整 AuthProvider。
- Git-backed Wiki。
- 富文本编辑器。
- PDF / DOCX / TXT 原生内容。
- 独立回收站页面。
- 历史特性永久删除。
- 向量库优先替代目录和回源。

这些能力如后续需要，应进入 v1.1 或更高版本单独设计。
