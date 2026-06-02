# Test Feature — OpenViking

## 元信息

| 字段 | 值 |
|---|---|
| 特性 slug | `openviking` |
| 显示名 | OpenViking |
| 上游仓库 | `https://github.com/volcengine/OpenViking` |
| Git URL | `git@github.com:volcengine/OpenViking.git` |
| 上游主语言 | Python 3.10+（核心）/ Rust / C++ |
| 当前支持依赖范围 | `>=0.3.22,<0.4` |
| 当前锁文件版本 | `0.3.22` |
| wiki 抓取基准版本 | `0.3.17`（与 `docs/future/openviking-rag-research-2026-05-20.md` 实测一致） |
| wiki 抓取日期 | 2026-05-20 |
| wiki 抓取来源 | `/home/hzh/wiki/OpenViking-docs` |

## Wiki 内容

`wiki/` 目录包含上游 OpenViking 的 20 个模块结构化文档：

- 架构总览、core 包、server / API、服务层、客户端 SDK
- 存储层（VikingFS / VectorDB / C++ 引擎 / QueueFS / OVPack）
- 模型与 embedding、内容解析（含 9 语言 AST 代码解析器）
- 检索系统（HierarchicalRetriever / IntentAnalyzer）
- 会话与记忆、VikingBot、指标、加密
- Rust CLI / RAGFS / C++ 向量引擎 / Python CLI
- LangChain 集成、部署、benchmarks

可作为 CodeAsk Wiki 文档批量导入。本特性同时是 v1.0.5 自身实现的"反查参考"——CodeAsk 集成 OpenViking 时遇到 URI / MCP / embedding 行为疑问，可以让模型直接通过 OpenViking RAG 检索该特性下的 wiki 自我解答。

## 源码

```bash
git clone git@github.com:volcengine/OpenViking.git $CODEASK_REFERENCES_DIR/OpenViking
```

`references/OpenViking/` 已在 `.gitignore`。

> 重要：CodeAsk 不修改、不内嵌 OpenViking 源码。代码仓注册时只作为只读检索目标。

## 使用入口

- `docs/rules/test-features.md` — 全局使用约定
- `docs/v1.0.5/plans/phase-0-spike.md` §4 — 第三类样本（代码仓导入与 grep/glob 实测）
- `docs/v1.0.5/design/openviking-integration.md` —— OpenViking 自身集成的实现参考
