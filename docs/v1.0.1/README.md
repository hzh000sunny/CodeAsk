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
| `specs/llm-wiki-brainstorm.md` | 当前头脑风暴结论、已确认约束、缺口分析、待讨论问题 |

## 后续文档计划

待头脑风暴继续收敛后，本版本应补齐：

| 文件 | 作用 |
|---|---|
| `prd/llm-wiki.md` | LLM Wiki 产品契约：为谁、为什么、做什么、不做什么 |
| `design/llm-wiki-workbench.md` | 独立 Wiki 工作台、数据模型、索引、权限和 Agent 接入设计 |
| `plans/llm-wiki-workbench.md` | 可执行开发计划，按 TDD task 拆分 |

## 与 v1.0 的关系

v1.0 已有的 Wiki 能力是 MVP 骨架：

- 特性维度的文档上传。
- 文档切块和 FTS5 / n-gram 检索。
- 问题报告生成、验证、撤销、未通过和删除。
- 已验证报告进入检索。
- 特性页中有轻量知识库入口。

v1.0.1 的目标不是在特性页里继续堆功能，而是把 Wiki 升级为独立一级工作台，并让它成为 Agent 可稳定引用的知识基础设施。

## 推荐阅读顺序

1. `specs/llm-wiki-brainstorm.md`
2. `../v1.0/design/wiki-search.md`
3. `../v1.0/design/evidence-report.md`
4. `../v1.0/design/frontend-workbench.md`
5. `../v1.0/prd/codeask.md`
