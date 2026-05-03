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
- 已完成：Phase 4 的当前后端能力，包括原生文档读取、草稿保存/删除、正式发布、版本列表、diff、回滚。
- 未完成：历史特性虚拟根、完整文档编辑/草稿/版本 API、导入 staging、前端独立 Wiki 工作台。

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
- [ ] 实现 `GET /api/wiki/tree`，返回 `当前特性` 和默认折叠的 `历史特性` 虚拟根。
- [x] 实现 `GET /api/wiki/nodes/{node_id}`，返回节点元信息和权限。
- [x] 实现 `POST /api/wiki/nodes` 创建普通目录和空 Markdown 节点。
- [x] 实现 `PUT /api/wiki/nodes/{node_id}` 重命名和移动。
- [x] 实现 `DELETE /api/wiki/nodes/{node_id}` 软删除。
- [x] 写 API 测试覆盖普通用户不可写、owner 可写、admin 可写。

**验收：**

- 普通用户能读树但不能写。
- owner 和 admin 可以管理普通目录和 Markdown 节点。
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
- [ ] 实现 Markdown 相对图片和相对 `.md` 链接解析。
- [ ] 在文档详情中返回 broken refs。

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
- 手动验证 `/?section=wiki&node=...` 刷新后仍在 Wiki。
- 手动验证 Markdown 正文不溢出页面边界。

**步骤：**

- [ ] Sidebar 增加 `Wiki` 一级导航，顺序为 `会话 / 特性 / Wiki / 设置`。
- [ ] AppShell 支持 `section=wiki` URL 状态，刷新后不回到会话页。
- [ ] 实现 Wiki tree 数据加载和展开状态。
- [ ] 实现阅读态右侧 Markdown 预览。
- [ ] 实现右上轻量操作 `详情 / 复制链接 / 编辑 / 更多`。
- [ ] 实现详情抽屉，展示路径、更新时间、索引状态、断链、版本入口。
- [ ] 确保 tree、预览、详情抽屉都有明确滚动容器。

**验收：**

- Wiki 是独立一级页面。
- 阅读态是左树右 Markdown，不出现常驻第三栏。
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

- [ ] 编辑态默认收起目录树，仅保留展开目录按钮。
- [ ] 源码区变更后节流自动保存草稿。
- [ ] 保存 / 发布调用正式保存 API。
- [ ] 取消时如果有未保存草稿，提示继续编辑、丢弃草稿或保存正式版本。
- [ ] 版本抽屉展示版本列表。
- [ ] 支持查看历史版本、diff 和回滚。
- [ ] 回滚成功后刷新当前文档和版本列表。

**验收：**

- 草稿不会污染正式预览和检索。
- 保存后生成版本，版本 UI 可见。
- 编辑态源码和预览布局稳定，不挤压到不可用。

## 8. Phase 7: 上传目录、资源和断链

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

- [ ] 实现 import preflight，列出同名冲突和断链警告。
- [ ] 冲突时阻断导入，不覆盖、不重命名、不跳过。
- [ ] 实现目录 staging，保留相对路径。
- [ ] 为导入任务写入 `wiki_import_items`，记录 source path、staging path、target path、token estimate 和 warnings。
- [ ] 为导入生成 provenance，并在正式 document / asset 上保留来源摘要。
- [ ] 实现 Markdown 引用资源入库。
- [ ] 实现资源读取 API，让 Markdown 图片能渲染。
- [ ] 导入成功后批量创建版本并触发索引。
- [ ] 提供最小 `wiki_sources` 读写接口，为后续 repo docs 或外部来源刷新预留结构。
- [ ] 前端导入弹窗展示冲突、警告和导入结果。

**验收：**

- 上传目录能保留结构。
- 相对图片能在预览中显示。
- 断链可见但不阻断。
- 冲突阻断且提示清晰。
- 导入结果可追溯到 item 级别，正式文档具备来源摘要。

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

- [ ] 报告生成后确保存在 `wiki_report_ref`。
- [ ] 根据 report status 计算虚拟路径 `草稿 / 已验证 / 未通过`。
- [ ] 验证通过后进入报告索引。
- [ ] 标记未通过、撤销验证、删除后从默认报告索引下架。
- [ ] 特性页 KnowledgePanel 只展示当前特性目录树和预览。
- [ ] 特性页上传、编辑、移动、删除、历史版本入口跳转到独立 Wiki 页面。
- [ ] 预留“会话附件 / 会话产物晋级为 wiki 内容”的服务边界，哪怕首版先不做完整 UI。

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

- [ ] 实现 `GET /api/wiki/search`，默认搜索全 Wiki 可读范围。
- [ ] 搜索结果按当前特性、问题定位报告、其它当前特性、历史特性分组。
- [ ] 实现 `resolve_wiki_path`，支持口语化路径解析。
- [ ] 实现 `search_wiki` 和 `read_wiki_node` Agent 工具。
- [ ] Agent 运行事件展示 Wiki 范围解析。
- [ ] Agent 最终回答引用 Wiki node、heading 和可点击 URL。
- [ ] MarkdownRenderer 支持 Wiki evidence 链接跳转。

**验收：**

- Agent 不只依赖 snippet，能回源读取 Markdown 原文。
- 运行事件能解释参考了哪些 Wiki 路径。
- 最终回答中的 Wiki 证据能跳转到对应文档和 heading。

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

- [ ] 加入 30 天软删除清理任务，保留历史版本和历史特性。
- [ ] 实现手动重新索引 repair API，限制 owner/admin。
- [ ] 为导入任务、来源刷新、session promotion 预留或补齐审计事件。
- [ ] 标记旧 `/api/documents` 兼容层，不在其上增加新能力。
- [ ] 更新 README 和 v1.0.1 文档的落地状态。
- [ ] 跑全量后端测试。
- [ ] 跑前端 build。
- [ ] 手动验证会话、特性、Wiki、设置四个一级页面刷新保持正确页面。

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
