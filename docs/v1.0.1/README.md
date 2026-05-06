# CodeAsk 文档 — v1.0.1

| 字段 | 值 |
|---|---|
| 版本 | v1.0.1 |
| 状态 | Completed |
| 主题 | LLM Wiki 专项 |
| 基线版本 | `../v1.0/` |
| 目标 | 补齐 v1.0 已后置的完整 LLM Wiki 能力 |

## 版本定位

v1.0.1 是一个聚焦版本，专门用于建设 CodeAsk 的独立 LLM Wiki 工作台。

从严格语义化版本角度看，完整 Wiki 工作台属于显著能力增强，放到 `v1.1` 也成立。但在 CodeAsk 当前路线中，完整 LLM Wiki 是 v1.0 已明确后置的核心缺口，不改变产品主链路，而是补齐“知识库 + 代码调查 + 报告回流”中的知识管理基础设施。因此本版本采用 `v1.0.1`，语义是：

> 在 v1.0 主链路不变的前提下，补齐 LLM Wiki 这个关键短板。

## 当前记录

| 文件 | 说明 |
|---|---|
| `prd/llm-wiki.md` | LLM Wiki 产品契约：定位、范围、权限、生命周期、Agent 接入和验收标准 |
| `design/llm-wiki-workbench.md` | 独立 Wiki 工作台 SDD：前后端模块边界、目标目录结构、数据模型、API 和测试策略 |
| `plans/llm-wiki-workbench.md` | v1.0.1 LLM Wiki 分阶段实施计划，明确目录结构和落地顺序 |
| `plans/closure-checklist.md` | v1.0.1 版本关闭清单：明确哪些必须在本版本收口，哪些正式后移 |
| `specs/llm-wiki-brainstorm.md` | 头脑风暴记录和决策快照；正式实现以 PRD / SDD / Plan 为准 |

## 当前实现进度

截至 2026-05-06，v1.0.1 后端已经具备以下原生能力：

- Wiki space、目录树和节点 CRUD。
- v1.0.1 当前版本的 Wiki 写权限覆写：普通文档/目录写操作默认对所有用户开放，同时保留系统目录保护，以及未来 `owner / admin` 或管理员治理动作的权限通道。
- Markdown 正式内容读取、草稿、发布、版本、diff、回滚。
- Markdown 相对 `.md` 链接和图片引用解析，返回 resolved refs 和 broken refs。
- 原生 Wiki asset 上传与内容读取：
  - `POST /api/wiki/assets`
  - `GET /api/wiki/assets/{node_id}/content`
- 目录导入内部 preflight 能力：
  - `POST /api/wiki/imports/preflight`
  - 支持 `multipart files[]`
  - 以上传文件名承载相对路径
  - 返回路径冲突和 Markdown 断链警告
- 导入任务 staging：
  - `POST /api/wiki/imports`
  - `GET /api/wiki/imports/{job_id}`
  - `GET /api/wiki/imports/{job_id}/items`
  - 在 `data_dir/wiki/imports/job_{id}/` 按原相对路径保存 staged 文件
  - `POST /api/wiki/imports/{job_id}/apply` 会把 staged 文件落成原生 Wiki node / document / asset
- Markdown 中引用同目录 asset 时，可解析到原生 Wiki asset node。
- Wiki 报告投影读取：
  - `GET /api/wiki/reports/projections?feature_id=...`
  - `GET /api/wiki/reports/by-node/{node_id}`
- Wiki 原生搜索第一版：
  - `GET /api/wiki/search?q=...&feature_id=...`
  - 当前覆盖正式 Wiki 文档和问题报告正文
  - 当前按工作台前端需要返回分组键和值

截至 2026-05-06，v1.0.1 前端已经落地以下独立 Wiki 工作台能力：

- Sidebar 新增 `Wiki` 一级入口，URL 采用 `#/wiki?feature=...&node=...&mode=...&drawer=...`。
- 独立 Wiki 页面已接通特性选择、目录树、默认首篇文档打开和空态。
- 阅读态已实现左树右正文、纯正文阅读容器、详情抽屉、历史版本抽屉。
- 阅读态已支持复制当前 Wiki 链接。
- 编辑态已实现源码/预览双栏、进入编辑态默认收起目录树、自动草稿、发布、diff、回滚。
- 导入抽屉已切到“导入会话 + 文件队列”模型，内部复用 preflight / materialize 能力，但用户不再感知独立 preflight 阶段。
- Wiki Markdown 代码块已支持复制。
- 已落地报告投影视图：
  - `问题定位报告` 根目录下按 `草稿 / 已验证 / 未通过` 展开
  - 报告正文支持独立预览和 Markdown 渲染
- 已落地 Wiki 搜索第一版：
  - 左侧搜索直接走后端 `/api/wiki/search`
  - 当前支持“当前特性文档 / 当前特性问题报告”的分组展示
- 已落地编辑退出确认、多节点管理菜单和特性页轻量 KnowledgePanel 预览入口。
- 已落地导入会话第一版：
  - 单文件上传进度、顶部总进度、当前处理文件
  - 冲突不中断、失败重试、忽略文件折叠区、后台继续上传
  - 导入完成后自动打开目标一级目录下的第一篇 Markdown
- 已落地目录树排序第一版：
  - 普通目录和 Markdown 文档支持 `上移 / 下移`
  - 普通目录和 Markdown 文档支持树内拖拽重排
  - Markdown 文档支持拖入普通目录或 `知识库` 根目录
- 已落地多处 Wiki 显示层修正：
  - 用户可见路径统一显示为展示路径，不再暴露 `knowledge-base`、`reports` 等内部存储路径
  - 特性页知识库树默认只展开 `知识库` 根目录，下层目录可展开 / 收起
  - 特性页知识库右侧预览只保留 Markdown 正文，不显示文档名头部和特性级报告计数
  - 导入抽屉首屏已收口为紧凑双入口卡片；上方入口不再平分整屏高度，空队列占位会填满剩余空间
- 已落地 Wiki 收尾治理入口：
  - 来源治理抽屉：列表、创建、编辑、手动同步、同步结果反馈
  - 软删除节点恢复、历史特性恢复、手动重新索引入口
  - 会话附件晋级为正式 Wiki 文档或资源，并支持从会话直接跳转到目标 Wiki 节点
- 已补齐一轮浏览器级收尾回归：
  - `frontend/e2e/wiki-tail.spec.ts` 覆盖来源治理、恢复/重新索引和会话附件晋级的浏览器工作流
  - `frontend/e2e/wiki-tail-live.spec.ts` 覆盖真实前后端服务下的来源治理、节点恢复/重新索引和会话附件晋级
  - `frontend/e2e/wiki-import-live.spec.ts` 覆盖真实前后端服务下的目录导入成功与冲突覆盖链路

v1.0.1 已经完成收口。下列事项明确后移到后续版本，不再计入本版本：

- 来源治理的更深 provenance 展示和长期治理细节继续增强。
- 更大范围的版本级人工 blocker sweep 和发布流程沉淀继续完善。

不再纳入 v1.0.1 的事项：

- 恢复 `owner / admin / member` 的真实写权限隔离
- 接入 AuthProvider 或企业级统一登录
- PDF / DOCX 等非 Markdown 文档格式导入
- 企业级外部来源连接器和跨空间治理策略
- LLM agent 的进一步优化，包括更强的范围理解、复杂口语化推理和更深的运行时策略调整

版本关闭标准见 [plans/closure-checklist.md](./plans/closure-checklist.md)。

## 当前已确认的前端路线

v1.0.1 前端 Wiki 不采用“一次把知识库、报告投影、搜索全部塞进首版”的方案，而是分两段连续执行：

1. `A1 + A2`
   - 独立 Wiki 一级页
   - 左树右正文阅读态
   - 编辑态双栏
   - 抽屉式详情 / 历史版本
   - 导入、草稿、发布、版本回滚联调
2. `B1 + B2`
   - 紧接着补问题定位报告投影
   - 随后补全 Wiki 搜索与结果分组

当前状态：

- `A1 + A2` 已完成并稳定。
- `B1` 已完成，报告投影已进入独立 Wiki 工作台。
- `B2` 已完成第一版，已打通后端搜索接口和前端分组展示，但还不是最终的全 Wiki/Agent 一体化搜索形态。

其中已明确的默认交互包括：

- 当前特性有 Wiki 时，默认打开该特性的第一篇 Wiki。
- 当前特性没有 Wiki 时，显示空态。
- 左侧默认只展开 `知识库`。
- 特性页知识库预览树同样默认只展开 `知识库` 根目录；其下层目录默认收起，但可以逐层展开 / 收起。
- 阅读态默认是纯正文，不保留常驻元信息栏；辅助信息全部通过抽屉进入。
- 特性页知识库右侧预览区只承担正文阅读，不额外显示文档标题和特性级报告计数，避免与正文层级混淆。
- 编辑态默认收起目录树，只保留位于中间分界线的悬浮展开按钮。
- 目录树节点的管理操作通过三点菜单进入，系统目录只保留允许的创建动作，报告投影节点不提供直接修改。

## 文档状态

当前已经从头脑风暴收敛出正式 PRD、SDD 和实施计划。后续讨论如改变产品契约，必须先更新 `prd/llm-wiki.md`；如只改变实现方式，更新 `design/llm-wiki-workbench.md` 和 `plans/llm-wiki-workbench.md`。

## 模块设计原则

v1.0.1 明确采用独立 Wiki bounded context：

- 后端新增 `/api/wiki/*` 主 API，并把现有 feature、document compatibility、report lifecycle 从旧 `api/wiki.py` 中拆出。
- 后端新增 Wiki 原生模型，不继续在旧 `documents` 表上追加目录树、草稿、版本和资源语义。
- 前端新增 `components/wiki/` 和 `lib/wiki/`，Wiki 作为一级页面实现。
- 特性页只保留当前特性的 Wiki 树和预览，上传、编辑、移动、删除、版本历史等操作跳转到独立 Wiki 页面。
- 特性页中的 KnowledgePanel 是轻量阅读入口，不承载完整管理动作，也不承载独立于正文的文档元信息头部。
- Agent 通过 Wiki service/tool API 解析、检索、回源和引用 Wiki 内容，不直接访问 Wiki 表。

## 与 v1.0 的关系

v1.0 已有的 Wiki 能力是 MVP 骨架：

- 特性维度的文档上传。
- 文档切块和 FTS5 / n-gram 检索。
- 问题报告生成、验证、撤销、未通过和删除。
- 已验证报告进入检索。
- 特性页中有轻量知识库入口。

v1.0.1 的目标不是在特性页里继续堆功能，而是把 Wiki 升级为独立一级工作台，并让它成为 Agent 可稳定引用的知识基础设施。

## 推荐阅读顺序

1. `prd/llm-wiki.md`
2. `design/llm-wiki-workbench.md`
3. `plans/llm-wiki-workbench.md`
4. `specs/llm-wiki-brainstorm.md`
5. `../v1.0/design/wiki-search.md`
6. `../v1.0/design/evidence-report.md`
7. `../v1.0/design/frontend-workbench.md`
8. `../v1.0/prd/codeask.md`
