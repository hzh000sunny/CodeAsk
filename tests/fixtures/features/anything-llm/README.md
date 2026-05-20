# Test Feature — anything-llm

## 元信息

| 字段 | 值 |
|---|---|
| 特性 slug | `anything-llm` |
| 显示名 | AnythingLLM |
| 上游仓库 | `https://github.com/Mintplex-Labs/anything-llm` |
| Git URL | `git@github.com:Mintplex-Labs/anything-llm.git` |
| 上游许可证 | MIT |
| 上游主语言 | JavaScript / Node.js |
| wiki 抓取日期 | 2026-05-20 |
| wiki 抓取来源 | `/home/hzh/wiki/anything-llm-docs` |

## Wiki 内容

`wiki/` 目录包含上游 AnythingLLM 的模块化结构文档 dump：

- `01-server` —— 后端 API、AI providers、embedding、向量库、agent、文档管理、TextSplitter 等
- `02-frontend` —— React 工作台、路由、Agent 工具、国际化
- `03-collector` —— 文档摄取微服务（PDF / DOCX / Confluence / GitHub 等）
- `04-embed` / `05-browser-extension` / `06-deployment` / `07-extras`

可作为 CodeAsk Wiki 文档批量导入。AnythingLLM 是 v1.0.5 RAG 设计的"处理管线参考"（chunk header、vector cache、document sync queue、source dedup），其 wiki 文档可作为：

- RAG 召回测试真实样本（query 例："anythingllm 的 chunk 默认大小是多少"、"document sync 失败重试机制"）
- 与 OpenViking RAG 召回结果做对照基线
- 真实"特性下挂多模块文档"场景验证 Wiki 树同步

## 源码

```bash
git clone git@github.com:Mintplex-Labs/anything-llm.git $CODEASK_REFERENCES_DIR/anything-llm
```

`references/anything-llm/` 已在 `.gitignore`，源码不进仓库。代码仓注册到 CodeAsk 时使用上述上游 URL。

## 使用入口

- `docs/rules/test-features.md` — 全局使用约定
- `docs/v1.0.5/plans/phase-0-spike.md` §4 — 第二类样本（含 verified report 与代码仓导入）
- `docs/v1.0.5/design/openviking-integration.md` —— "AnythingLLM 处理管线参考"段落
