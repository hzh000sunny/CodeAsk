# LLM Wiki v1.0.1 Tail Execution Checklist

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不破坏现有 Wiki 主链路的前提下，补齐 v1.0.1 剩余的治理与运维入口，包括来源管理、恢复通道、会话附件晋级、手动修复入口和对应的浏览器回归覆盖。

**Architecture:** 延续现有独立 Wiki bounded context，不改动会话、特性、设置的既有主链路。前端继续按 `components/wiki/* + hooks/* + lib/wiki/*` 拆分，后端继续沿 `/api/wiki/*` 现有边界扩展，只补前端入口、状态编排和必要的只读/动作型接口复用。

**Tech Stack:** FastAPI、SQLAlchemy async、React、TypeScript、TanStack Query、Vitest、Playwright。

---

## 0. 目标范围

本清单只覆盖 `v1.0.1` 当前还没收口的四类工作：

1. `wiki_sources` 来源治理前端 UI
2. 恢复 / 晋级 / 手动 repair 的前端入口
3. Agent 侧 Wiki 范围解析的小幅增强
4. 对上述能力的浏览器级回归补齐

明确不在本轮内扩散：

- 不重做现有导入会话主链路
- 不重做会话主界面布局
- 不引入新的权限模型
- 不重做 Wiki 搜索的底层索引结构

## 1. 任务拆分原则

- 每个任务必须有独立前端入口、后端依赖边界、自动化测试和手动验收口径。
- 每个任务完成后，我会单独告诉你：
  - 改了哪些文件
  - 跑了哪些测试
  - 你该怎么手动验收
- 没有进入当前任务边界的模块，不允许顺手重构。

## 2. 组件拆分总览

### 2.1 前端新增/扩展组件

| 组件 / Hook | 责任 |
|---|---|
| `components/wiki/WikiSourcesDrawer.tsx` | 来源列表、同步状态、入口容器 |
| `components/wiki/WikiSourceList.tsx` | 来源列表渲染 |
| `components/wiki/WikiSourceFormDialog.tsx` | 新建 / 编辑来源 |
| `components/wiki/WikiSourceSyncResult.tsx` | 最近同步结果和错误摘要 |
| `components/wiki/WikiNodeRestoreDialog.tsx` | 恢复软删除目录/文档 |
| `components/wiki/WikiSpaceRestoreDialog.tsx` | 历史特性恢复 |
| `components/wiki/WikiMaintenanceActions.tsx` | 手动 reindex repair 入口 |
| `components/wiki/WikiPromotionDialog.tsx` | 会话附件晋级为 Wiki |
| `components/wiki/hooks/useWikiSources.ts` | 来源查询、创建、编辑、同步 |
| `components/wiki/hooks/useWikiRestoreActions.ts` | 节点恢复、历史特性恢复 |
| `components/wiki/hooks/useWikiMaintenance.ts` | 手动 reindex repair |
| `components/session/useSessionWikiPromotion.ts` | 会话附件晋级动作编排 |

### 2.2 后端复用/扩展边界

| 边界 | 说明 |
|---|---|
| `/api/wiki/sources*` | 已有接口为主，只补前端实际需要的返回字段时才扩展 |
| `/api/wiki/nodes/{id}/restore` | 复用现有恢复接口 |
| `/api/wiki/spaces/{id}/restore` | 复用现有历史特性恢复接口 |
| `/api/wiki/maintenance/nodes/{id}/reindex` | 复用现有 repair 接口 |
| `/api/wiki/promotions/session-attachment` | 复用现有晋级接口 |

### 2.3 集成位置

| 页面 | 接入点 |
|---|---|
| 独立 Wiki 页 | 来源治理、恢复、repair 主入口 |
| 特性页知识库轻量预览 | 只保留“跳转到独立 Wiki”入口，不新增复杂治理动作 |
| 会话页附件区 | 附件晋级为 Wiki 的入口 |
| 历史特性根 / 节点三点菜单 | 历史特性恢复、节点恢复等动作 |

## 3. Checklist

### [x] Task 1: 来源治理 UI

**目标**

把后端已有的 `wiki_sources` 接口变成用户可管理的前端功能，支持查看来源、创建来源、编辑来源、手动同步、查看同步状态。

**前端边界**

- 新增 `WikiSourcesDrawer.tsx`
- 新增 `WikiSourceList.tsx`
- 新增 `WikiSourceFormDialog.tsx`
- 新增 `WikiSourceSyncResult.tsx`
- 新增 `useWikiSources.ts`
- 修改 `WikiFloatingActions.tsx` 或 `WikiWorkbenchDialogs.tsx`，挂载来源治理入口

**后端边界**

- 优先复用：
  - `GET /api/wiki/sources`
  - `POST /api/wiki/sources`
  - `PUT /api/wiki/sources/{source_id}`
  - `POST /api/wiki/sources/{source_id}/sync`
- 仅在前端缺字段时扩展 `schemas.py`

**不允许影响**

- 导入会话抽屉
- 目录树排序
- Markdown 阅读/编辑

**自动化验证**

- 前端新增来源抽屉测试
- 后端沿用 / 补充 `tests/integration/test_wiki_sources_api.py`

**你完成后怎么手动验收**

1. 打开某个特性的独立 Wiki 页面
2. 打开“来源治理”入口
3. 能看到已有来源列表
4. 新建一个来源，保存后出现在列表
5. 编辑来源显示名，刷新页面仍保留
6. 点击同步，能看到成功或失败状态反馈

### [x] Task 2: 恢复与修复入口

**目标**

把现有后端恢复/repair 能力接进前端，让用户可以在 Wiki 工作台内完成：

- 恢复软删除节点
- 恢复历史特性
- 手动触发 reindex repair

**前端边界**

- 新增 `WikiNodeRestoreDialog.tsx`
- 新增 `WikiSpaceRestoreDialog.tsx`
- 新增 `WikiMaintenanceActions.tsx`
- 新增 `useWikiRestoreActions.ts`
- 新增 `useWikiMaintenance.ts`
- 修改 `WikiNodeMenu.tsx`
- 修改 `WikiTreeNode.tsx`
- 修改 `WikiWorkbenchDialogs.tsx`

**后端边界**

- 复用：
  - `POST /api/wiki/nodes/{node_id}/restore`
  - `POST /api/wiki/spaces/{space_id}/restore`
  - `POST /api/wiki/maintenance/nodes/{node_id}/reindex`

**不允许影响**

- 当前删除逻辑
- 当前历史特性浏览逻辑
- 当前目录树拖拽排序逻辑

**自动化验证**

- 前端新增恢复/repair 行为测试
- 后端沿用：
  - `tests/integration/test_wiki_nodes_api.py`
  - `tests/integration/test_wiki_tree_api.py`
  - `tests/integration/test_wiki_maintenance_api.py`

**你完成后怎么手动验收**

1. 删除一个普通 Wiki 目录或文档
2. 通过前端入口执行恢复
3. 恢复后目录树立即回到原位置，内容可正常预览
4. 找一个历史特性，点击恢复到当前特性
5. 恢复后它从 `历史特性` 消失，重新出现在 `当前特性`
6. 触发一次手动 reindex，看到成功反馈，没有破坏当前预览

**当前实现备注**

- 来源治理抽屉改为惰性加载，只有打开抽屉时才请求 `wiki_sources`，避免普通阅读 / 编辑路径被无关查询干扰。
- 目录导入不再在“创建导入会话”时立刻写入 `wiki_source`；只有真正 materialize 成功后，才会创建或复用来源记录，避免来源治理被未完成导入污染。
- 历史遗留的空壳目录来源（如 `导入会话 N` 且对应导入未完成）会在来源列表里自动隐藏，避免继续干扰用户。
- 成功导入后的目录来源名称优先取上传目录根名，例如 `ops` / `Xiaomi`，不再暴露无意义的会话流水号。
- 目录树会自动展开当前路由节点所在祖先链，因此历史特性恢复入口在直达 `#/wiki?feature=x&node=y` 时也能稳定显示。
- `当前特性 / 历史特性` 两个虚拟根分组不再暴露不合理的“新建 / 导入 / 重新索引”菜单项，恢复和修复动作只保留在真实特性或真实目录节点上。

### [x] Task 3: 会话附件晋级为 Wiki

**目标**

把会话附件从“仅会话临时材料”提升成“可沉淀到正式 Wiki”的前端可操作能力。

**前端边界**

- 新增 `WikiPromotionDialog.tsx`
- 新增 `useSessionWikiPromotion.ts`
- 修改 `SessionWorkspaceDialogs.tsx`
- 修改 `SessionConversationPanel.tsx` 或附件列表组件
- 复用 Wiki 特性/目录选择能力，不另造一套树

**后端边界**

- 复用 `POST /api/wiki/promotions/session-attachment`
- 必要时补充前端所需的目标选择辅助字段

**不允许影响**

- 现有会话附件上传/重命名/删除
- 会话生成报告主链路
- 当前 Wiki 导入会话链路

**自动化验证**

- 前端新增会话附件晋级工作流测试
- 后端沿用 / 补充 `tests/integration/test_wiki_promotions_api.py`

**你完成后怎么手动验收**

1. 在会话里上传一个 Markdown 或图片附件
2. 通过附件操作入口选择“晋级为 Wiki”
3. 选择目标特性和目标目录
4. 提交后跳转或刷新到对应 Wiki 目录
5. 能看到新文档或新资源节点
6. 打开详情能看到它来自 `session_promotion`

**当前实现备注**

- 会话附件区新增 `晋级为 Wiki` 入口，和重命名 / 删除并列，不改动原有上传、描述、删除链路。
- 晋级弹窗按独立 session 子模块拆分，包含特性选择、目录选择和文档标题输入；文本类附件默认晋级为文档，图片等二进制附件默认晋级为资源。
- 目标目录默认优先选中 `知识库` 根目录；晋级成功后可以直接从会话跳转到新写入的 Wiki 节点。
- 成功写入后会同时刷新 Wiki 目录树和搜索相关缓存，避免用户切到 Wiki 页面时看不到刚晋级的内容。

### [x] Task 4: Agent 范围解析小幅增强

**目标**

在不重写 Agent 主链路的前提下，增强现有 Wiki 范围解析，让自然语言指定目录时更稳定。

**边界**

- 修改 `src/codeask/wiki/path_resolver.py`
- 保持 `/api/wiki/resolve-path` 和 `agent/wiki_tools.py` 现有调用面不变
- 仅补口语噪音清洗、特性别名剥离和现有候选打分前的 query 归一化

**不允许影响**

- 现有 `scope_detection -> knowledge_retrieval` 主流程
- 现有证据链接结构

**自动化验证**

- 补路径解析和 Agent facade 测试

**你完成后怎么手动验收**

1. 在会话里用口语化方式提到某个特性下的目录
2. 查看运行事件中的 Wiki 范围解析结果
3. 结果里应出现正确的特性和目录候选
4. 最终回答里的 Wiki 证据链接应跳到正确目录/文档

**当前实现备注**

- `path_resolver` 现在会在 `feature_id` 已确定时，先剥离当前特性的常见别名：`Feature.name`、`Feature.slug`、`WikiSpace.display_name`、`WikiSpace.slug`。
- 对 `这个特性 / 当前特性 / 目录下 / 里面的` 等口语填充词做了统一清洗，避免整句被当成脏短语导致零命中。
- `/api/wiki/resolve-path` 与 Agent 工具层不需要改协议，现有调用就能直接吃到更稳定的解析结果。
- 已补并通过定向回归：
  - `tests/integration/test_wiki_path_resolver_api.py`
  - `tests/integration/test_wiki_agent_tools.py`

### [x] Task 5: 浏览器回归补齐

**目标**

给前面 1~4 的新增能力补真实浏览器级回归，防止后续改动互相污染。

**测试边界**

- 新增 `frontend/e2e/wiki-tail.spec.ts`
- 覆盖三条浏览器链路：
  - 来源治理抽屉：查看 / 创建 / 编辑 / 同步
  - 恢复与修复：删除后恢复、重新索引、历史特性恢复
  - 会话附件晋级：从会话进入晋级弹窗并跳转到目标 Wiki
- 暂不新增 live E2E；本轮优先保证 mocked browser regression 稳定可重复

**你完成后怎么手动验收**

1. 跑新的 Playwright 用例
2. 人工按 Task 1~4 的手动步骤再走一遍
3. 确认新功能不影响：
   - 导入会话
   - 树排序
   - 阅读态
   - 编辑态

**当前实现备注**

- 新增的 Playwright 用例采用独立 mock 夹具，不依赖真实外部数据，能稳定覆盖这轮新增的治理入口。
- 浏览器测试只覆盖本轮新增的前端入口和路由跳转，不修改现有生产逻辑。
- 已通过：
  - `cd frontend && npx playwright test e2e/wiki-tail.spec.ts`
  - `cd frontend && npm run typecheck`

## 4. 执行顺序

推荐顺序固定为：

1. Task 1 来源治理 UI
2. Task 2 恢复与修复入口
3. Task 3 会话附件晋级
4. Task 4 Agent 范围解析增强
5. Task 5 浏览器回归补齐

原因：

- Task 1 / 2 完全在 Wiki 边界内，最容易隔离修改
- Task 3 首次跨到会话侧，风险更高，放在 Wiki 面板稳定后做
- Task 4 属于运行时增强，依赖前面治理语义稳定
- Task 5 最后收口，防止边做边写脆弱测试

## 5. 当前执行承诺

从下一步开始，我会按上面的顺序逐项实现。每完成一项，我都会固定给你四类信息：

1. 本项改了哪些文件
2. 跑了哪些自动化测试
3. 你该怎么手动验收
4. 这项是否影响了任何现有功能，如果有，影响在哪里
