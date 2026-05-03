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
- Markdown 中引用同目录 asset 时，可解析到原生 Wiki asset node。

当前仍未完成的重点能力：

- staging import job / item 明细。
- 批量导入和来源追踪。
- 独立 Wiki 前端工作台。

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
