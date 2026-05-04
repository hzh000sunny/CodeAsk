# CodeAsk 文档 — v1.0.1

| 字段 | 值 |
|---|---|
| 版本 | v1.0.1 |
| 状态 | Draft |
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
| `specs/llm-wiki-brainstorm.md` | 头脑风暴记录和决策快照；正式实现以 PRD / SDD / Plan 为准 |

## 当前实现进度

截至 2026-05-04，v1.0.1 后端已经具备以下原生能力：

- Wiki space、目录树和节点 CRUD。
- owner / admin 写权限和系统目录保护。
- Markdown 正式内容读取、草稿、发布、版本、diff、回滚。
- Markdown 相对 `.md` 链接和图片引用解析，返回 resolved refs 和 broken refs。
- 原生 Wiki asset 上传与内容读取：
  - `POST /api/wiki/assets`
  - `GET /api/wiki/assets/{node_id}/content`
- 目录导入 preflight：
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

截至 2026-05-04，v1.0.1 前端已经落地第一批独立 Wiki 工作台能力：

- Sidebar 新增 `Wiki` 一级入口，URL 采用 `#/wiki?feature=...&node=...&mode=...&drawer=...`。
- 独立 Wiki 页面已接通特性选择、目录树、默认首篇文档打开和空态。
- 阅读态已实现左树右正文、纯正文阅读容器、详情抽屉、历史版本抽屉。
- 阅读态已支持复制当前 Wiki 链接。
- 编辑态已实现源码/预览双栏、进入编辑态默认收起目录树、自动草稿、发布、diff、回滚。
- 导入抽屉已接通 preflight、job、apply 的前后端联调。
- Wiki Markdown 代码块已支持复制。

当前仍未完成的重点能力：

- provenance 扩充和完整来源追踪。
- 历史特性虚拟根。
- 报告投影页签和结果视图。
- Wiki 搜索与结果分组。
- 编辑态离开确认、多节点管理菜单、复制链接等细节交互收尾。

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

其中已明确的默认交互包括：

- 当前特性有 Wiki 时，默认打开该特性的第一篇 Wiki。
- 当前特性没有 Wiki 时，显示空态。
- 左侧默认只展开 `知识库`。
- 阅读态默认是纯正文，不保留常驻元信息栏；辅助信息全部通过抽屉进入。
- 编辑态默认收起目录树，只保留位于中间分界线的悬浮展开按钮。

## 文档状态

当前已经从头脑风暴收敛出正式 PRD、SDD 和实施计划。后续讨论如改变产品契约，必须先更新 `prd/llm-wiki.md`；如只改变实现方式，更新 `design/llm-wiki-workbench.md` 和 `plans/llm-wiki-workbench.md`。

## 模块设计原则

v1.0.1 明确采用独立 Wiki bounded context：

- 后端新增 `/api/wiki/*` 主 API，并把现有 feature、document compatibility、report lifecycle 从旧 `api/wiki.py` 中拆出。
- 后端新增 Wiki 原生模型，不继续在旧 `documents` 表上追加目录树、草稿、版本和资源语义。
- 前端新增 `components/wiki/` 和 `lib/wiki/`，Wiki 作为一级页面实现。
- 特性页只保留当前特性的 Wiki 树和预览，上传、编辑、移动、删除、版本历史等操作跳转到独立 Wiki 页面。
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
