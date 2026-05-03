# LLM Wiki 工作台系统设计

> 本文档属于 v1.0.1 SDD，描述独立 LLM Wiki 工作台的模块边界、目录结构、数据模型、API、前端组件拆分和 Agent 接入设计。
>
> 产品契约见 `../prd/llm-wiki.md`。若本文与 PRD 冲突，以 PRD 为准。

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

## 2.1 架构重心修正

在研究 AnythingLLM 之后，CodeAsk 的 LLM Wiki 不应只被理解为“独立 Wiki 工作台”。更准确的定义是：

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

原始 v1.0.1 草稿更偏重 `formal wiki layer` 和 `retrieval layer`。AnythingLLM 的启发是：`source layer`、`ingest layer` 和 `operator layer` 也必须在架构上占据正式位置。

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
- Wiki 上传、编辑、移动、删除、版本历史、导入任务只在 `components/wiki` 内实现。
- `components/wiki` 不直接调用通用 `apiRequest` 以外的其它页面状态；跨页面跳转通过 URL state 表达。
- Markdown 渲染基础组件可以复用 `components/ui/MarkdownRenderer.tsx`，但 Wiki 专用资源解析和 heading 定位放在 `lib/wiki`。

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
wiki_import_jobs
  id
  target_parent_node_id
  actor_subject_id
  status: preflight_failed | pending | running | succeeded | failed
  original_root_name
  conflicts_json
  warnings_json
  result_json
  created_at
  finished_at
```

```text
wiki_import_items
  id
  job_id
  source_type
  source_path
  staging_path
  target_path
  item_kind: document | asset
  token_estimate
  status
  warnings_json
  result_json
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
- `wiki_import_jobs` 记录一次导入动作；`wiki_import_items` 记录每个待导入或已导入项的细节。
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
| `PUT` | `/api/wiki/nodes/{node_id}` | 重命名、移动、更新排序 |
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
| `POST` | `/api/wiki/imports/preflight` | 目录上传预检查，返回冲突和断链警告 |
| `POST` | `/api/wiki/imports` | 创建导入任务 |
| `GET` | `/api/wiki/imports/{job_id}` | 查看导入状态 |
| `GET` | `/api/wiki/imports/{job_id}/items` | 查看本次导入的 staging item 明细 |
| `POST` | `/api/wiki/imports/{job_id}/apply` | 确认执行已通过预检查的导入 |

导入任务必须能够表达：

- 成功导入文件数量。
- 跳过文件数量。
- 冲突路径。
- 断链警告。
- 资源引用关系。
- 索引结果。
- 每个 item 的 staging 状态、token estimate、目标路径和最终导入结果。

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
| `GET` | `/api/wiki/search?q=` | 全 Wiki 可读范围搜索，返回分组结果 |
| `GET` | `/api/wiki/reports?feature_id=&status=` | Wiki 报告投影列表 |
| `GET` | `/api/wiki/reports/{report_id}` | 在 Wiki 语义下读取报告 |
| `POST` | `/api/wiki/reports/{report_id}/verify` | 验证通过，更新报告状态和索引 |
| `POST` | `/api/wiki/reports/{report_id}/reject` | 标记未通过，更新报告状态和索引 |
| `POST` | `/api/wiki/reports/{report_id}/unverify` | 撤销验证，更新报告状态和索引 |

报告状态变更仍委托 `reports.service` 执行，Wiki API 只提供符合 Wiki 页面语义的入口。

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

### 7.5 导入服务

`wiki/imports/service.py` 负责目录导入流程：

```text
接收上传目录
→ 保留相对路径到 staging
→ preflight 检查冲突和断链
→ 用户确认
→ 记录 import items 和来源信息
→ 创建 node、document、version、asset
→ 批量索引
→ 记录导入结果
```

导入任务应是可查询的，因为目录导入可能超过普通请求的交互时间。

AnythingLLM 对 CodeAsk 最大的启发之一是：导入不是一个布尔成功与否的动作，而是一组 staging item 的状态机。CodeAsk 的导入服务应围绕这一点设计。

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

它不直接改变报告生命周期，生命周期动作调用 `reports/service.py`。

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
│       ├── WikiWorkbench.tsx               # 页面编排，不写业务细节
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
│       │   ├── useWikiImport.ts
│       │   └── useWikiPermissions.ts
│       └── wiki-ui-types.ts
├── lib/
│   └── wiki/
│       ├── api.ts
│       ├── query-keys.ts
│       ├── routing.ts
│       ├── permissions.ts
│       ├── markdown.ts
│       └── tree.ts
└── types/
    └── wiki.ts
```

### 8.2 组件职责

| 组件 | 职责 |
|---|---|
| `WikiWorkbench` | 根据 URL state 组织树、阅读态、编辑态、弹窗和抽屉 |
| `WikiTreePane` | 渲染目录树，处理展开、收起、选中和搜索定位 |
| `WikiNodeMenu` | 节点三点菜单，按权限和节点类型裁剪 |
| `WikiReader` | 阅读态正文布局，不包含编辑逻辑 |
| `WikiFloatingActions` | 详情、复制链接、编辑、更多 |
| `WikiDetailDrawer` | 元信息、索引状态、断链、引用、历史入口 |
| `WikiEditor` | 编辑态布局，组织 source editor 和 live preview |
| `WikiSourceEditor` | Markdown 源码输入，触发自动草稿 |
| `WikiLivePreview` | 实时预览，使用 Wiki 资源解析 |
| `WikiVersionDrawer` | 版本列表、diff、回滚 |
| `WikiImportDialog` | 上传 Markdown 或目录、preflight、冲突展示 |
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

### 8.4 UI 设计约束

Wiki 工作台采用偏专业、简洁、舒适的 SaaS 工具风格。UI 参考 `ui-ux-pro-max` 的 Minimalism & Swiss Style：

- 主色使用中性色和清晰蓝色行动点，不做单一紫蓝或重渐变。
- 阅读区保证正文宽度和行高，优先服务长文阅读。
- 操作入口轻量，不把管理按钮铺满正文顶部。
- hover 和展开动效保持 150-250ms，并尊重 `prefers-reduced-motion`。
- 目录树、搜索结果、版本列表等固定区域必须有明确滚动容器，不让页面无限撑高。
- 下拉菜单、悬浮操作、抽屉不能被卡片或滚动容器裁切。

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

编辑态：

```text
┌───────────────────────────────────────────────────────────────┐
│ 当前路径                         保存 / 发布 / 取消 / 版本入口 │
├───────────────────────────────┬───────────────────────────────┤
│ Markdown 源码编辑区             │ 实时 Markdown 预览             │
└───────────────────────────────┴───────────────────────────────┘
```

编辑态默认收起目录树，保留轻量展开按钮。

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
