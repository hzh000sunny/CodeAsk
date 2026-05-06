# LLM Wiki 工作台实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 v1.0 主链路不变的前提下，新增独立 LLM Wiki 工作台，并把它落成一个完整的工程知识生命周期系统，支持 Markdown-only 目录树、来源追踪、导入 staging、阅读、编辑、版本、报告投影、权限通道、搜索索引和 Agent 回源引用。

**Architecture:** 采用独立 Wiki bounded context。后端新增 Wiki 原生模型和 `/api/wiki/*` 主 API，旧 `/api/documents` 仅做兼容；同时引入来源、导入 item、临时证据晋级的架构预留。前端新增 `components/wiki` 和 `lib/wiki`，特性页只保留当前特性的树和预览入口。

**Tech Stack:** FastAPI、SQLAlchemy async、Alembic、SQLite FTS5、React、TypeScript、TanStack Query、Lucide、MarkdownRenderer。

---

## 0. 执行原则

- 每个阶段都先补测试，再实现，再跑对应测试。
- 不把新 Wiki 功能继续堆进 `src/codeask/api/wiki.py` 或 `FeatureWorkbench.tsx`。
- 新增模块优先小文件拆分；单个 service 目标不超过约 350 行，单个 React 组件目标不超过约 250 行。
- 前端 URL 必须能保持当前一级页面和 Wiki node，刷新不能回到会话页。
- v1.0 的会话、特性、设置和报告 API 保持兼容，除非计划明确迁移。

## 0.1 当前进度

- 已完成：Phase 1 路由拆分。
- 已完成：Phase 2 原生模型、迁移、feature 自动建 space、系统目录初始化。
- 已完成：旧 Markdown 文档和旧报告到原生 Wiki 的同步桥，以及首次访问 Wiki 时的懒回填。
- 已完成：Phase 3 的最小可用版本，包括 actor、权限判断、路径规范化、node detail、node create/update/delete、系统目录保护。
- 已完成：Phase 4 的当前后端能力，包括原生文档读取、草稿保存/删除、正式发布、版本列表、diff、回滚、基础相对引用解析和断链返回。
- 已完成：Phase 7A 的第一批资源能力，包括原生 asset 上传、内容读取，以及 Markdown 对同目录 asset 的原生引用解析。
- 已完成：Phase 7A 的第一批导入能力，包括 import preflight、路径冲突检测和 Markdown 断链告警。
- 已完成：Phase 7A 的第二批导入能力，包括 import job 创建、staged 文件落盘、job/items 查询。
- 已完成：Phase 7A 的第三批导入能力，包括 apply 导入、文档版本生成、asset 落盘和引用解析统一。
- 已完成：Phase 7B 的导入会话主链路收口，已补齐逐文件进度、忽略折叠区、目录剥壳、冲突不中断、失败重试、后台继续上传和导入完成自动打开首篇文档的前后端与浏览器级验证。
- 已完成：Phase 5 的第一批前端工作，包括独立 Wiki 一级入口、hash 路由恢复、目录树、默认首篇文档打开、阅读态正文和详情/版本/导入抽屉。
- 已完成：Phase 6 的第一批前端工作，包括编辑态双栏、进入编辑态默认收起目录树、自动草稿、发布、diff、回滚。
- 已完成：Phase 8 的第一版报告投影，包括投影读取 API、前端状态分组注入、报告正文预览，以及特性页 KnowledgePanel 轻量入口化。
- 已完成：Phase 9 的第一版 Wiki 搜索，包括 `/api/wiki/search`、当前特性文档/报告分组展示，以及独立 Wiki 工作台搜索交互。
- 已完成：独立 Wiki 搜索全局分桶收口，支持 `current_feature_id` 上下文分组、大小写不敏感匹配，以及 `当前特性 / 问题定位报告 / 其它当前特性 / 历史特性` 固定排序。
- 已完成：编辑态离开确认、多节点管理菜单和文档节点重命名标题同步。
- 已完成：独立 Wiki 页的全局目录树切换，`/api/wiki/tree` 已支持 `当前特性 / 历史特性` 虚拟根，同时保留 `feature_id` 单特性模式给特性页预览复用。
- 已完成：特性页 `KnowledgePanel` 预览收口，包括默认只展开 `知识库` 根目录、下层目录可展开 / 收起，以及右侧预览区去掉文档名头部和特性级报告计数，只保留正文。
- 已完成：v1.0.1 当前版本权限覆写，Wiki 写操作已对所有用户放开，同时保留 owner/admin 权限通道供后续恢复。
- 已完成：独立 Wiki 页目录树可用性收口，包括显式拉伸、长名称 title、节点右侧三点菜单导入入口、带父目录语义的导入抽屉，以及目录树 `上移 / 下移` 与拖拽排序第一版。
- 已完成：特性归档流转，删除特性后会从默认特性列表移除，并迁移到 Wiki 的 `历史特性` 虚拟根；归档特性仍可通过 `#/wiki?feature=<id>&node=<id>` 访问其历史文档。
- 已完成：最小 `wiki_sources` 来源注册表接口，包括列表、创建、编辑和手动同步入口。
- 已完成：30 天软删除清理任务，当前会物理清理过期软删除节点并联动清理资源文件，同时保留历史特性和版本链路不受影响。
- 已完成：最小 `session attachment -> wiki` promotion 边界，当前已支持把会话附件直接晋级为正式 Wiki 文档或资源节点，并记录 `session_promotion` provenance/source。
- 已完成：普通 Wiki 节点的软删除恢复链路，当前已支持 `POST /api/wiki/nodes/{node_id}/restore` 恢复目录子树，并在路径冲突时阻断。
- 已完成：历史特性恢复链路，当前管理员可通过 `POST /api/wiki/spaces/{space_id}/restore` 将归档特性恢复回 `当前特性`。
- 已完成：formal Wiki content 的 provenance/source 扩充，当前手工 asset 上传、import job、import session 物化以及 session attachment promotion 都会创建或绑定 `wiki_sources` 记录，并把 `source_id` 写入正式 document / asset 的 `provenance_json`。
- 已完成：导入任务、来源刷新和 session promotion 的最小审计事件补齐，当前会写入 `audit_log` 并同时输出结构化审计日志。
- 已完成：native wiki 的独立 `index + maintenance` 边界第一版，当前 `WikiIndexService` 负责正式文档派生状态刷新，`POST /api/wiki/maintenance/nodes/{node_id}/reindex` 负责 owner/admin 手动 repair subtree。
- 已完成：导入抽屉的当前 UI 收口，双入口卡片已改为固定紧凑宽度，空队列占位会填满剩余区域，不再与文件队列错误平分空间。

## 0.3 收口结论

v1.0.1 的 Wiki 收尾已经完成：

- 来源治理、恢复/修复、会话附件晋级三组尾项已具备前端入口、自动化覆盖和真实服务浏览器证据。
- 真实浏览器回归已补齐主要 live 证据；导入目录、来源治理、恢复/重新索引、会话附件晋级、目录树排序和编辑/预览切换都已有真实服务覆盖。
- README、SDD、验收清单和关闭清单的版本口径已经统一。
- LLM agent 的进一步优化已从本版本剥离，后移到后续版本处理，不再计入 v1.0.1 Wiki 封板条件。

## 0.2 已确认的前端执行顺序

前端 Wiki 工作台按两个连续阶段执行，不把报告和搜索一开始混入第一版：

- `A1 + A2`：先完成独立 Wiki 工作台的阅读态与编辑态主链路，并完成前后端联调压实。
- `B1`：在 `A` 稳定后，紧接着补上问题定位报告投影。
- `B2`：随后补上 Wiki 搜索和结果分组。

当前明确不采用“一次把 Wiki / 报告 / 搜索全部塞进首版”的做法，避免第一轮交互和联调边界失控。

## 1. 目标目录结构

后端：

```text
src/codeask/api/wiki/
src/codeask/db/models/wiki/
src/codeask/features/
src/codeask/reports/
src/codeask/wiki/spaces/
src/codeask/wiki/tree/
src/codeask/wiki/documents/
src/codeask/wiki/assets/
src/codeask/wiki/imports/
src/codeask/wiki/index/
src/codeask/wiki/reports/
```

前端：

```text
frontend/src/components/wiki/
frontend/src/components/wiki/hooks/
frontend/src/lib/wiki/
frontend/src/types/wiki.ts
```

详细职责以 `../design/llm-wiki-workbench.md` 为准。

## 2. Phase 1: 后端模块骨架和兼容拆分

**目标：** 先切开路由和服务边界，不改变现有行为。

**主要文件：**

- 创建：`src/codeask/api/wiki/__init__.py`
- 创建：`src/codeask/api/wiki/router.py`
- 创建：`src/codeask/api/wiki/deps.py`
- 创建：`src/codeask/api/features.py`
- 创建：`src/codeask/api/reports.py`
- 创建：`src/codeask/api/documents_compat.py`
- 修改：`src/codeask/app.py`
- 迁移：`src/codeask/api/wiki.py` 内现有路由

**测试：**

- `tests/integration/test_wiki_features_api.py`
- `tests/integration/test_wiki_documents_api.py`
- `tests/integration/test_wiki_reports_api.py`
- `tests/integration/test_feature_repos_api.py`

**步骤：**

- [x] 新建 `src/codeask/api/wiki/` 包，并让 `from codeask.api.wiki import router` 继续可用。
- [x] 把 `/api/features/*` 路由迁移到 `api/features.py`，保持路径和 response model 不变。
- [x] 把 `/api/reports/*` 路由迁移到 `api/reports.py`，保持路径和状态变更行为不变。
- [x] 把 `/api/documents/*` 路由迁移到 `api/documents_compat.py`，明确标注为兼容层。
- [x] `api/wiki/router.py` 建立 `/api/wiki/*` 新入口，并开始挂载原生子路由。
- [x] 更新 `app.py` include_router 顺序，确保旧 API 测试不变。
- [x] 跑现有 Wiki、feature repo、report API 测试，确认只是结构迁移。

**验收：**

- 旧 API 路径全部可用。
- `src/codeask/api/wiki.py` 不再是大文件。
- 新 `/api/wiki/*` 入口已存在但不承载旧 `/api/documents` 语义。

## 3. Phase 2: Wiki 原生模型和迁移

**目标：** 新增 Wiki 数据模型，并从现有 feature/document/report 初始化 Wiki 树，同时补上来源与导入谱系的结构基础。

**主要文件：**

- 创建：`src/codeask/db/models/wiki/space.py`
- 创建：`src/codeask/db/models/wiki/node.py`
- 创建：`src/codeask/db/models/wiki/document.py`
- 创建：`src/codeask/db/models/wiki/asset.py`
- 创建：`src/codeask/db/models/wiki/source.py`
- 创建：`src/codeask/db/models/wiki/import_job.py`
- 创建：`src/codeask/db/models/wiki/import_item.py`
- 创建：`src/codeask/db/models/wiki/event.py`
- 修改：`src/codeask/db/models/__init__.py`
- 创建：`alembic/versions/*_wiki_native_models.py`
- 创建：`src/codeask/wiki/spaces/service.py`
- 创建：`src/codeask/wiki/spaces/repo.py`

**测试：**

- 新增：`tests/integration/test_wiki_native_models.py`
- 新增：`tests/integration/test_wiki_space_migration.py`

**步骤：**

- [x] 新增 `wiki_spaces`、`wiki_nodes`、`wiki_documents`、`wiki_document_versions`、`wiki_document_drafts`、`wiki_assets`、`wiki_sources`、`wiki_report_refs`、`wiki_node_events`、`wiki_import_jobs`、`wiki_import_items`。
- [x] 定义 active path 唯一约束、version 唯一约束、space-feature 唯一约束。
- [x] 为 document 和 asset 设计 provenance 字段，至少能表达 `manual_upload`、`directory_import`、`session_promotion` 这几类来源。
- [x] 写 migration 测试，验证空库升级成功。
- [x] 写已有 feature 初始化测试：每个 feature 生成一个 active current space。
- [x] 写系统目录测试：每个 space 自动创建 `知识库` 和 `问题定位报告`。
- [x] 写 document 迁移测试：旧 document 进入 `知识库` 并生成第一个正式版本。
- [x] 写 report ref 迁移测试：旧 report 投影到 `问题定位报告` 虚拟状态分组。
- [x] 实现幂等 bootstrap / lazy backfill，保证重复访问不会重复创建同一 space 和系统目录。
- [x] 为旧 `documents` 填充默认 provenance，避免新架构下出现无来源的正式知识。

**验收：**

- 新表可迁移、可回放、可幂等初始化。
- 旧数据不会丢失。
- 新模型具备完整 Wiki 树、来源信息和导入谱系的基本表达能力。

## 4. Phase 3: 权限、路径和目录树 API

**目标：** 建立 Wiki 的读写权限、路径冲突规则和目录树读取能力。

**主要文件：**

- 创建：`src/codeask/wiki/actor.py`
- 创建：`src/codeask/wiki/permissions.py`
- 创建：`src/codeask/wiki/paths.py`
- 创建：`src/codeask/wiki/tree/service.py`
- 创建：`src/codeask/wiki/tree/repo.py`
- 创建：`src/codeask/wiki/tree/virtual_nodes.py`
- 创建：`src/codeask/api/wiki/tree.py`
- 创建：`src/codeask/api/wiki/spaces.py`

**测试：**

- 新增：`tests/unit/test_wiki_permissions.py`
- 新增：`tests/unit/test_wiki_paths.py`
- 新增：`tests/integration/test_wiki_tree_api.py`

**步骤：**

- [x] 定义 `actor`：subject id、is_admin、未来 auth user 占位字段。
- [x] 实现 viewer、owner、admin 权限矩阵。
- [x] 实现路径规范化、展示路径生成、同级冲突检测。
- [x] 实现移动循环检测，防止目录移动到自己的子树下。
- [x] 实现 `GET /api/wiki/tree`，返回 `当前特性` 和默认折叠的 `历史特性` 虚拟根；同时保留 `feature_id` 单特性树模式。
- [x] 实现 `GET /api/wiki/nodes/{node_id}`，返回节点元信息和权限。
- [x] 实现 `POST /api/wiki/nodes` 创建普通目录和空 Markdown 节点。
- [x] 实现 `PUT /api/wiki/nodes/{node_id}` 重命名和移动。
- [x] 实现 `DELETE /api/wiki/nodes/{node_id}` 软删除。
- [x] 写 API 测试覆盖当前 v1.0.1 全员可写，以及系统目录保护仍然生效。

**验收：**

- 当前 v1.0.1 第一版所有用户都能读写普通目录和 Markdown 节点。
- 系统目录不能改名、移动、删除。
- 路径冲突阻断并返回可读错误。

## 5. Phase 4: Markdown 文档、草稿和版本

**目标：** 实现 Markdown-only 的阅读、编辑、自动草稿、正式版本和回滚。

**主要文件：**

- 创建：`src/codeask/wiki/documents/service.py`
- 创建：`src/codeask/wiki/documents/repo.py`
- 创建：`src/codeask/wiki/documents/drafts.py`
- 创建：`src/codeask/wiki/documents/versions.py`
- 创建：`src/codeask/wiki/documents/renderer.py`
- 创建：`src/codeask/api/wiki/documents.py`
- 创建：`src/codeask/api/wiki/drafts.py`
- 创建：`src/codeask/api/wiki/versions.py`

**测试：**

- 新增：`tests/unit/test_wiki_markdown_refs.py`
- 新增：`tests/integration/test_wiki_documents_native_api.py`
- 新增：`tests/integration/test_wiki_drafts_versions_api.py`

**步骤：**

- [x] 实现读取当前正式 Markdown。
- [x] 实现保存正式版本：写 version、更新 current_version_id、清理当前用户草稿。
- [x] 实现自动保存草稿：只写 draft，不触发索引。
- [x] 实现丢弃草稿。
- [x] 实现版本列表和历史版本读取。
- [x] 实现版本 diff API。
- [x] 实现回滚：把历史版本内容保存为新的正式版本。
- [x] 实现 Markdown 相对图片和相对 `.md` 链接解析。
- [x] 在文档详情中返回 broken refs。

**验收：**

- 刷新后可以恢复未发布草稿。
- 正式保存才进入版本历史和索引流程。
- 回滚不破坏历史链。
- Markdown-only 边界明确，非 Markdown 文档不能作为 Wiki 文档创建。

## 6. Phase 5: 前端 Wiki 一级入口和阅读态

**目标：** 新增独立 Wiki 页面，完成树和 Markdown 预览。

**主要文件：**

- 修改：`frontend/src/components/layout/Sidebar.tsx`
- 修改：`frontend/src/components/layout/AppShell.tsx`
- 创建：`frontend/src/types/wiki.ts`
- 创建：`frontend/src/lib/wiki/api.ts`
- 创建：`frontend/src/lib/wiki/query-keys.ts`
- 创建：`frontend/src/lib/wiki/routing.ts`
- 创建：`frontend/src/components/wiki/WikiWorkbench.tsx`
- 创建：`frontend/src/components/wiki/WikiTreePane.tsx`
- 创建：`frontend/src/components/wiki/WikiTreeNode.tsx`
- 创建：`frontend/src/components/wiki/WikiNodeMenu.tsx`
- 创建：`frontend/src/components/wiki/WikiReader.tsx`
- 创建：`frontend/src/components/wiki/WikiFloatingActions.tsx`
- 创建：`frontend/src/components/wiki/WikiDetailDrawer.tsx`
- 创建：`frontend/src/components/wiki/hooks/useWikiTree.ts`
- 创建：`frontend/src/components/wiki/hooks/useWikiDocument.ts`

**测试：**

- 前端 build。
- 手动验证 `#/wiki?feature=...&node=...` 刷新后仍在 Wiki。
- 手动验证 Markdown 正文不溢出页面边界。

**步骤：**

- [x] Sidebar 增加 `Wiki` 一级导航，顺序为 `会话 / 特性 / Wiki / 设置`。
- [x] AppShell 支持 `#/wiki?...` URL 状态，刷新后不回到会话页。
- [x] 实现 Wiki tree 数据加载和展开状态。
- [x] 进入某个特性时，若该特性已有 Wiki 文档，则默认打开该特性的第一篇 Wiki；若没有，则显示空态。
- [x] 左侧目录树默认只展开 `知识库`，`问题定位报告` 与自定义目录默认收起。
- [x] 实现阅读态右侧 Markdown 预览。
- [x] 实现右上轻量操作 `详情 / 复制链接 / 编辑 / 更多`，并把 `历史版本 / 导入 Wiki` 收进 `更多` 浮层。
- [x] 实现详情抽屉，展示路径、更新时间、索引状态、断链、版本入口。
- [x] 确保 tree、预览、详情抽屉都有明确滚动容器。

**验收：**

- Wiki 是独立一级页面。
- 阅读态是左树右 Markdown，不出现常驻第三栏，也不出现常驻信息条。
- 来源、更新时间、索引状态、断链、历史版本等辅助信息默认全部通过抽屉进入。
- 普通用户只看到阅读动作。
- 刷新和复制链接能回到同一个 node。

## 7. Phase 6: 前端编辑态和版本 UI

**目标：** 完成 Markdown 源码编辑、实时预览、自动草稿和版本历史交互。

**主要文件：**

- 创建：`frontend/src/components/wiki/WikiEditor.tsx`
- 创建：`frontend/src/components/wiki/WikiSourceEditor.tsx`
- 创建：`frontend/src/components/wiki/WikiLivePreview.tsx`
- 创建：`frontend/src/components/wiki/WikiVersionDrawer.tsx`
- 创建：`frontend/src/components/wiki/hooks/useWikiDraftAutosave.ts`
- 创建：`frontend/src/lib/wiki/markdown.ts`

**测试：**

- 前端 build。
- 手动验证编辑中刷新后草稿可恢复。
- 手动验证源码区和实时预览同屏，目录树默认收起。

**步骤：**

- [x] 编辑态默认收起目录树，仅保留位于内容分界线中部的悬浮展开按钮，交互风格与现有一级/二级侧边栏收起逻辑一致。
- [x] 源码区变更后节流自动保存草稿。
- [x] 保存 / 发布调用正式保存 API。
- [x] 取消时如果有未保存草稿，提示继续编辑、保留草稿离开、丢弃草稿或发布正式版本。
- [x] 版本抽屉展示版本列表，版本只表示正式发布快照，不包含自动草稿。
- [x] 支持查看历史版本、diff 和回滚。
- [x] 回滚成功后刷新当前文档和版本列表。

**验收：**

- 草稿不会污染正式预览和检索。
- 保存后生成版本，版本 UI 可见。
- 编辑态源码和预览布局稳定，不挤压到不可用。
- 历史版本语义明确为“正式发布快照”，查看、对比、回滚都从抽屉进入。

## 8. Phase 7A: 上传目录、资源和断链骨架

**目标：** 支持上传 Markdown 和目录，保留相对路径和图片资源，并让导入过程具备 staging item、来源信息和结果明细。

**主要文件：**

- 创建：`src/codeask/wiki/imports/service.py`
- 创建：`src/codeask/wiki/imports/repo.py`
- 创建：`src/codeask/wiki/imports/preflight.py`
- 创建：`src/codeask/wiki/imports/unpacker.py`
- 创建：`src/codeask/wiki/imports/references.py`
- 创建：`src/codeask/wiki/sources/service.py`
- 创建：`src/codeask/wiki/sources/repo.py`
- 创建：`src/codeask/wiki/assets/service.py`
- 创建：`src/codeask/wiki/assets/storage.py`
- 创建：`src/codeask/api/wiki/imports.py`
- 创建：`src/codeask/api/wiki/sources.py`
- 创建：`src/codeask/api/wiki/assets.py`
- 创建：`frontend/src/components/wiki/WikiImportDialog.tsx`
- 创建：`frontend/src/components/wiki/hooks/useWikiImport.ts`

**测试：**

- 新增：`tests/integration/test_wiki_imports_api.py`
- 新增：`tests/integration/test_wiki_assets_api.py`

**步骤：**

- [x] 实现 import preflight，列出同名冲突和断链警告。
- [x] 冲突时阻断导入，不覆盖、不重命名、不跳过。
- [x] 实现目录 staging，保留相对路径。
- [x] 为导入任务写入 `wiki_import_items`，记录 source path、staging path、target path、token estimate 和 warnings。
- [x] 为导入生成 provenance，并在正式 document / asset 上保留来源摘要。
- [x] 实现原生 asset 手工上传入库。
- [x] 实现资源读取 API，让 Markdown 图片能渲染。
- [x] 让 Markdown 相对图片引用可解析到同目录原生 asset node。
- [x] 对断链图片和运行时加载失败图片提供正文内可见占位反馈。
- [x] 约定 preflight 使用 `multipart files[]`，相对路径通过上传文件名传递。
- [x] 实现 `POST /api/wiki/imports` 创建 import job，并把上传文件按原相对路径写入 staging 目录。
- [x] 实现 `GET /api/wiki/imports/{job_id}` 与 `/items`，返回 summary 和 item 明细。
- [x] 实现 `POST /api/wiki/imports/{job_id}/apply`，把 staged 内容落成 native wiki nodes / documents / assets。
- [x] 导入成功后批量创建版本并触发索引。
- [x] 提供最小 `wiki_sources` 读写接口，为后续 repo docs 或外部来源刷新预留结构。
- [x] 前端导入弹窗展示冲突、警告和导入结果，并拆分 Markdown / 目录两类选择入口。

**验收：**

- 上传目录能保留结构。
- 相对图片能在预览中显示。
- 断链可见但不阻断。
- 冲突阻断且提示清晰。
- 导入结果可追溯到 item 级别，正式文档具备来源摘要。

## 8A. Phase 7B: 导入会话、文件队列和逐文件冲突处理

**目标：** 在保留现有 staging / apply 内部能力的前提下，把用户可见导入流程升级为“导入会话 + 文件队列”，支持逐文件进度、冲突不中断、全部覆盖/全部跳过、失败重试和后台继续上传。

**主要文件：**

- 创建：`src/codeask/api/wiki/import_sessions.py`
- 创建：`src/codeask/wiki/imports/session_service.py`
- 创建：`src/codeask/wiki/imports/session_repo.py`
- 创建：`src/codeask/wiki/imports/upload_service.py`
- 修改：`src/codeask/api/wiki/router.py`
- 修改：`src/codeask/api/wiki/schemas.py`
- 修改：`src/codeask/db/models/wiki/import_job.py`
- 修改：`alembic/versions/*`
- 修改：`frontend/src/components/wiki/WikiImportDialog.tsx`
- 修改：`frontend/src/components/wiki/WikiWorkbench.tsx`
- 创建：`frontend/src/components/wiki/WikiImportQueue.tsx`
- 创建：`frontend/src/components/wiki/WikiImportQueueItem.tsx`
- 创建：`frontend/src/components/wiki/WikiImportConflictActions.tsx`
- 创建：`frontend/src/components/wiki/hooks/useWikiImportSession.ts`
- 修改：`frontend/src/lib/wiki/api.ts`
- 修改：`frontend/src/types/wiki.ts`

**测试：**

- 新增：`tests/integration/test_wiki_import_sessions_api.py`
- 修改：`tests/integration/test_wiki_imports_api.py`
- 新增：`frontend/tests/wiki/import-session-dialog.test.tsx`
- 新增：`frontend/tests/wiki/import-session-workflow.test.tsx`
- 修改：`frontend/tests/wiki/import-files.test.ts`

**步骤：**

- [x] 为导入会话补失败测试，覆盖“创建会话、登记完整文件列表、逐文件上传、冲突决策、失败重试、取消会话”主链路。
- [x] 新增 `wiki_import_sessions` / `wiki_import_session_items` 或在现有导入表上迁移到等价结构，明确记录逐文件状态、进度、忽略原因、冲突原因和失败原因。
- [x] 实现 `POST /api/wiki/import-sessions`，创建导入会话并绑定 `space_id`、`parent_id`、`mode`、`root_strip_segments=1`。
- [x] 实现 `POST /api/wiki/import-sessions/{session_id}/scan`，登记完整文件清单，包括有效上传项和忽略项。
- [x] 实现 `POST /api/wiki/import-sessions/{session_id}/items/{item_id}/upload`，按单文件处理上传；目录导入时剥掉最外层目录名，仅保留内部相对结构。
- [x] 实现冲突即时判定和单文件 `resolve` API，支持 `overwrite`、`skip`、`overwrite_all`、`skip_all`。
- [x] 实现单文件重试和失败批量重试 API。
- [x] 实现会话查询和 item 列表查询，保证抽屉关闭后仍能恢复现场。
- [x] 实现取消会话 API；取消未完成项，不回滚已成功项。
- [x] 前端导入抽屉移除独立 preflight 区块，替换为顶部摘要 + 文件队列 + 忽略文件折叠区。
- [x] 文件队列默认按选择顺序渲染；支持“全部 / 仅看进行中与失败”过滤。
- [x] 每行显示文件名、相对路径、状态、进度条；冲突在当前行内直接展开操作按钮。
- [x] 顶部摘要显示目标目录、总进度、成功 / 冲突 / 失败 / 忽略 / 跳过计数，以及当前正在处理的文件名。
- [x] 关闭抽屉或切页时，若导入未结束，弹确认框让用户选择继续后台上传或取消。
- [x] 导入完成后关闭抽屉、刷新目录树，并自动打开目标一级目录下的第一篇 Markdown 预览。

**当前进度补充：**

- 已新增两条集成测试，覆盖导入会话的 `create + scan + items` 与 `upload + auto materialize` 最小主链路。
- 导入会话后端已补齐冲突决策第一版：`upload -> conflict`、单项 `resolve`、批量 `bulk-resolve` 都已有集成测试覆盖。
- 导入会话后端已补上 `cancel` API；已验证“部分上传后取消，不自动落库未完成队列”。
- 导入会话后端已补上 `retry item / retry session`；已验证“落库失败 -> failed -> retry 后完成导入”主链路。
- 前端已切到第一版导入会话抽屉：`选择 Markdown / 选择目录` 会进入 `import session + queue` 流程，抽屉可展示状态计数、队列项、进度条与 ignored 折叠区。
- 前端已完成一次结构拆分：`WikiPage / WikiWorkbench / WikiWorkspacePane / WikiWorkbenchDialogs / useWikiImportSessionFlow / useWikiTreeLayout` 已落地，后续冲突处理和后台继续上传不再继续堆进单个页面组件。
- 前端已补上冲突行内操作：`覆盖 / 跳过 / 全部覆盖 / 全部跳过` 已接线到导入抽屉。
- 前端已补上失败重试第一版：失败行支持 `重试`，摘要区支持 `重试失败项`。
- 前端已补上导入摘要增强：顶部摘要区会展示 `总进度` 和 `当前处理文件`，进度按有效队列项聚合计算，忽略文件不计入总进度。
- 前端上传请求当前已改为可汇报进度的实现，`useWikiImportSessionFlow` 会把单文件上传中的本地进度实时回写到队列项，避免只能等待后端最终返回状态。
- 前端已补上“单项失败不阻断后续队列”：某个文件上传失败后，该项会留在 `failed` 状态，后续 `pending` 文件继续上传，便于最后统一回看和重试。
- 导入队列项当前已直接展示 `error_message`：冲突和失败原因不再只存在后端状态里，用户在抽屉内就能看到具体原因并决定下一步操作。
- 前端已补上队列过滤第一版：支持 `全部` 和 `仅看进行中与失败` 两个视图，忽略文件继续固定在列表最下方的折叠区。
- 前端已补上“关闭抽屉前确认”：当导入未完成时，关闭抽屉会提示 `继续后台 / 取消上传 / 继续留在此处`。
- `AppShell` 已补上“离开 Wiki 前确认”：当 import drawer 仍有 unfinished session 时，切换一级导航会提示 `继续后台 / 取消上传 / 继续留在 Wiki`，并保留后台 session 句柄用于回到 Wiki 后恢复。
- 导入完成后会自动关闭抽屉、刷新当前特性树和全局树，并优先打开本次导入结果中的第一篇 Markdown 文档预览。
- 已新增独立 Playwright 用例 `frontend/e2e/wiki-import.spec.ts`，覆盖目录导入忽略折叠、目录剥壳、冲突后续继续、批量重试失败项和导入完成自动打开文档。
- 已新增真实服务 Playwright 用例 `frontend/e2e/wiki-import-live.spec.ts`：测试会启动隔离的 Vite + FastAPI 服务，对真实后端执行目录导入成功链路和冲突覆盖链路，不再只依赖 `page.route` mock。

**验收：**

- 用户不再需要理解独立 preflight 阶段。
- 文件队列能完整显示有效上传项和忽略项，忽略区默认折叠。
- 单个冲突文件不阻塞其它文件继续上传。
- 支持 `覆盖 / 跳过 / 全部覆盖 / 全部跳过`。
- 支持单文件重试和失败批量重试。
- 关闭抽屉后可继续后台上传，重新打开能恢复真实状态。
- 导入目录不会再额外创建一层本地上传目录名。

## 9. Phase 8: 报告投影和特性页轻量入口

**目标：** 把问题定位报告作为 Wiki 投影展示，并把特性页改成预览入口。

**主要文件：**

- 创建：`src/codeask/wiki/reports/service.py`
- 创建：`src/codeask/wiki/reports/repo.py`
- 创建：`src/codeask/reports/service.py`
- 创建：`src/codeask/reports/repo.py`
- 创建：`src/codeask/api/wiki/reports.py`
- 修改：`frontend/src/components/features/KnowledgePanel.tsx`
- 修改：`frontend/src/components/features/ReportsPanel.tsx`
- 创建：`frontend/src/components/wiki/WikiReportViewer.tsx`

**测试：**

- 新增：`tests/integration/test_wiki_reports_projection.py`
- 现有：`tests/integration/test_wiki_reports_lifecycle.py`

**步骤：**

- [x] 报告生成后确保存在 `wiki_report_ref`。
- [x] 根据 report status 计算虚拟路径 `草稿 / 已验证 / 未通过`。
- [x] 验证通过后进入报告索引。
- [x] 标记未通过、撤销验证、删除后从默认报告索引下架。
- [x] 报告状态变化和标题编辑后，同步刷新 Wiki 投影分组和 report_ref 标题。
- [x] 特性页 KnowledgePanel 只展示当前特性目录树和预览。
- [x] 特性页 KnowledgePanel 默认只展开 `知识库` 根目录，下层目录可展开 / 收起。
- [x] 特性页 KnowledgePanel 右侧只显示正文预览，不显示文档名头部和特性级报告计数。
- [x] 特性页上传、编辑、移动、删除、历史版本入口跳转到独立 Wiki 页面。
- [x] 预留“会话附件 / 会话产物晋级为 wiki 内容”的服务边界，哪怕首版先不做完整 UI。

补充说明：

- 当前 `草稿 / 已验证 / 未通过` 分组是前端在 `问题定位报告` 根下做的虚拟注入，底层 `report_ref` 仍保持原生节点语义。
- 当前报告预览已支持 Markdown 渲染和从独立 Wiki 页面回跳到特性页。
- 当前特性页知识库预览已刻意收缩为轻量阅读入口，不再复用独立 Wiki 页的详情头部结构。

说明：本阶段不是首个前端切面，而是紧接 `A1 + A2` 之后的下一段工作。

**验收：**

- 报告列表不再只有草稿标签。
- 报告状态动作来自生命周期 API，不允许拖拽改变。
- 特性页不承载完整 Wiki 管理，但入口完整。
- 会话、报告和正式 wiki 之间的边界在架构和服务层已清楚，不再只是概念描述。

## 10. Phase 9: 搜索、索引和 Agent 回源

**目标：** 完成全 Wiki 搜索、自动索引和 Agent 可点击证据链。

**主要文件：**

- 创建：`src/codeask/wiki/index/service.py`
- 迁移：`src/codeask/wiki/chunker.py` → `src/codeask/wiki/index/chunker.py`
- 迁移：`src/codeask/wiki/search.py` → `src/codeask/wiki/index/search.py`
- 创建：`src/codeask/api/wiki/search.py`
- 修改：`src/codeask/agent/tools.py`
- 修改：`src/codeask/agent/tool_schemas.py`
- 修改：`src/codeask/agent/tool_delegates.py`
- 修改：`src/codeask/agent/stages/knowledge_retrieval.py`
- 修改：`src/codeask/agent/stages/evidence_synthesis.py`
- 修改：`frontend/src/components/session/InvestigationPanel.tsx`
- 修改：`frontend/src/components/ui/MarkdownRenderer.tsx`

**测试：**

- 新增：`tests/integration/test_wiki_search_native.py`
- 新增：`tests/integration/test_wiki_agent_tools.py`
- 更新：`tests/integration/test_orchestrator_sufficient.py`
- 更新：`tests/integration/test_orchestrator_insufficient.py`

**步骤：**

- [x] 实现 `GET /api/wiki/search`，当前支持按特性范围搜索正式 Wiki 文档和问题报告。
- [x] 搜索结果按当前特性、问题定位报告、其它当前特性、历史特性分组。
- [x] 实现 `resolve_wiki_path`，支持口语化路径解析。
- [x] 实现 `search_wiki` 和 `read_wiki_node` Agent 工具。
- [x] Agent 运行事件展示 Wiki 范围解析。
- [x] Agent 最终回答引用 Wiki node 和可点击 URL。
- [x] MarkdownRenderer 支持 Wiki evidence 链接跳转。
- [x] Agent 最终回答补齐 Wiki heading 锚点级跳转。

说明：搜索作为 `B2`，排在报告投影之后，避免在首版 UI 中同时混入阅读、编辑、报告、搜索四套复杂状态。

当前进度补充：

- 已新增 `GET /api/wiki/resolve-path`，当前支持在单个特性的 current space 内解析 `知识库` / `问题报告` 根目录别名，以及按名称、路径尾段、token 包含关系返回候选节点。
- Agent Wiki facade 已从旧的 legacy search 切到 native wiki 模型，并补上 `search_wiki / search_reports / read_wiki_doc / read_wiki_node / read_report` 五个真实工具后端。
- `knowledge_retrieval` 阶段已补上 `wiki_scope_resolution` 运行事件，并在 trace 中持久化默认范围与显式命中目录。
- `scope_detection` 选中的 `feature_ids` 现已沿运行时上下文传递到 `knowledge_retrieval`，不再退回到“所有特性一起搜”的宽泛兜底。
- `answer_finalization` 阶段已把 `[ev_knowledge_*]` 这类 Wiki 证据引用改写为 `#/wiki?feature=..&node=..` 的可点击 Markdown 链接；当搜索命中能解析出 `heading_path` 时，会继续补上 `heading` 锚点参数。

当前第一版说明：

- 搜索结果当前已经在独立 Wiki 工作台可用。
- 搜索结果命中具体 Wiki 标题小节时，当前会显式展示 `heading_path`，并在点击后把 `heading` 一并写入 Wiki 路由。
- 当前分组已覆盖“当前特性文档”和“当前特性问题报告”。
- Agent 侧的 Wiki 检索与范围解析当前已支持多特性聚合：`describe_scope` 会汇总多个特性的默认目录和显式命中节点，`search_wiki / search_reports` 会跨选中特性合并命中结果并按相关性截断。
- 历史特性与跨特性更复杂的优先级策略仍保留在本阶段后续子任务中完成；当前先保证“被选中特性集合”不会在检索阶段丢失。

**验收：**

- Agent 不只依赖 snippet，能回源读取 Markdown 原文。
- 运行事件能解释参考了哪些 Wiki 路径。
- 最终回答中的 Wiki 证据能跳转到对应文档；Wiki 文档在命中 `heading_path` 时可直接落到对应标题。

## 11. Phase 10: 清理、兼容和稳定化

**目标：** 确保新旧 API 边界清楚，软删除清理可运行，来源和导入状态可观察，文档同步完成。

**主要文件：**

- 创建：`src/codeask/wiki/cleanup.py`
- 创建：`src/codeask/api/wiki/maintenance.py`
- 修改：`src/codeask/app.py`
- 修改：`docs/v1.0.1/*`

**测试：**

- 新增：`tests/integration/test_wiki_cleanup.py`
- 全量：`uv run pytest`
- 前端：`corepack pnpm --dir frontend build`

**步骤：**

- [x] 加入 30 天软删除清理任务，保留历史版本和历史特性。
- [x] 实现手动重新索引 repair API，限制 owner/admin。
- [x] 为导入任务、来源刷新、session promotion 预留或补齐审计事件。
- [x] 标记旧 `/api/documents` 兼容层，不在其上增加新能力。
- [x] 更新 README 和 v1.0.1 文档的落地状态。
- [x] 跑全量后端测试。
- [x] 跑前端 build。
- [x] 手动验证会话、特性、Wiki、设置四个一级页面刷新保持正确页面。

**验收：**

- 新 Wiki 功能由 `/api/wiki/*` 承载。
- 旧 API 测试通过。
- 软删除清理不误删历史版本和历史特性。
- 正式知识、导入任务和来源谱系都具备可检查状态。
- 文档、代码、测试三者一致。

## 12. 风险和处理

| 风险 | 处理 |
|---|---|
| 模型迁移影响旧数据 | 先写幂等迁移测试，保留旧表和兼容 API |
| Wiki 页面再次变成大组件 | 页面编排、树、阅读、编辑、导入、版本全部拆组件和 hook |
| 权限在无登录阶段被误解 | UI 和 API 都实现软权限，同时在文档中明确不是强安全边界 |
| 目录上传复杂度过高 | 先做 preflight + 手动处理冲突，不做自动合并策略 |
| Agent 引用不可追溯 | 工具必须 read back 原文，最终回答必须返回 node_id + path + heading |
| 索引遗漏 | 所有正式变更通过 service 层触发 index service，不让 UI 负责记住重建索引 |

## 13. 完成定义

v1.0.1 LLM Wiki 视为完成时，需要同时满足：

- PRD 中的验收标准全部完成。
- `../design/llm-wiki-workbench.md` 中的模块边界没有被破坏。
- 后端核心 API、迁移、权限、路径、文档、导入、报告、索引、Agent 工具有测试覆盖。
- 前端 Wiki 阅读态、编辑态、导入、版本、报告、搜索有可验证交互。
- 刷新页面不会丢失当前一级页面、当前 Wiki node 或编辑上下文。
- 全量后端测试和前端 build 通过。
