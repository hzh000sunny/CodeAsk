# AnythingLLM 知识库

> AnythingLLM v1.12.1 — 将私人文档转化为 AI 聊天机器人的全栈解决方案。
> 基于 MIT 许可证开源，由 Mintplex Labs 开发。

## 项目概述

AnythingLLM 是一个全栈应用程序，由以下核心组件构成：

| 组件 | 技术栈 | 用途 |
|------|--------|------|
| **Server** | Node.js + Express + Prisma | 后端 API 服务、LLM 编排、向量检索、Agent 系统 |
| **Frontend** | React 18 + Vite + TailwindCSS | 多用户 Web 管理界面 |
| **Collector** | Node.js + Express | 文档摄取微服务，处理各类文件格式 |
| **Embed** | 独立 Widget | 可嵌入第三方网站的聊天组件 |
| **Browser Extension** | Chrome 扩展 | 浏览器端数据抓取 |

## 模块索引

### [01 — Server 后端服务](./01-server/INDEX.md)

核心后端，包含 35+ 个模块：

- **入口与启动**: Express 应用初始化、中间件注册、SSL/HTTP 引导
- **数据库模型** (Prisma): 40+ 张数据表，涵盖用户、工作区、聊天、文档、Agent、定时任务等
- **API 端点**: REST API + WebSocket + SSE 流式响应
- **LLM 提供商系统**: 35+ 个 AI 提供商集成（OpenAI, Anthropic, Gemini, Ollama, 等）
- **Embedding 引擎**: 15 个嵌入模型提供商（含本地 Native 嵌入）
- **向量数据库**: 10 个向量数据库支持（LanceDB, Pinecone, Chroma, Qdrant, Milvus, 等）
- **Agent 系统 (aibitat)**: 多 Agent 协作框架，支持 20+ 种工具插件
- **聊天处理管线**: 多模式聊天（chat/query/automatic）、RAG 检索增强
- **文档管理**: 文档上传、解析、向量化、同步
- **后台任务**: 嵌入 Worker、文档同步、定时清理
- **Telegram Bot**: 完整的 Telegram 机器人集成
- **MCP**: Model Context Protocol 支持
- **移动端 API**: 移动应用连接接口

### [02 — Frontend 前端](./02-frontend/INDEX.md)

React 18 SPA 管理界面：

- **认证系统**: 登录、注册、密码恢复、多用户管理
- **工作区管理**: 创建/编辑工作区、文档管理、用户分配
- **聊天界面**: 流式聊天、多线程、Agent 模式、文件上传
- **系统设置**: LLM/Embedding/Vector/TTS 配置、用户管理
- **Agent 技能管理**: Agent 工具配置、技能白名单
- **国际化**: 多语言支持 (i18next)

### [03 — Collector 文档处理器](./03-collector/INDEX.md)

独立的文档摄取微服务：

- **文件处理**: 支持 PDF, DOCX, TXT, CSV, Markdown 等多种格式
- **链接处理**: URL 内容抓取、YouTube 字幕提取
- **原始文本**: 直接文本内容处理
- **扩展系统**: Confluence, GitHub, GitLab, DrupalWiki 等数据源连接器

### [04 — Embed 嵌入组件](./04-embed/INDEX.md)

可嵌入第三方网站的聊天 Widget。

### [05 — Browser Extension 浏览器扩展](./05-browser-extension/INDEX.md)

Chrome 浏览器扩展，支持网页数据抓取。

### [06 — 部署与运维](./06-deployment/INDEX.md)

- **Docker**: 容器化部署（docker-compose）
- **CloudFormation**: AWS 一键部署
- **Terraform**: DigitalOcean 部署
- **GCP Deployment**: Google Cloud 部署
- **Helm Charts**: Kubernetes 部署
- **OpenShift**: 红帽 OpenShift 部署

### [07 — 附加工具](./07-extras/INDEX.md)

- **Translator**: 多语言翻译工具
- **Scripts**: 构建与验证脚本
- **Cloud Deployment Generators**: 云部署配置生成器

---

## 架构总览

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Frontend   │────▶│    Server    │────▶│  Collector  │
│  (React)    │     │  (Express)   │     │  (Express)  │
│  Port: 3000 │     │  Port: 3001  │     │  Port: 8888 │
└─────────────┘     └──────┬───────┘     └─────────────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                 ▼
   ┌──────────┐   ┌──────────────┐   ┌──────────────┐
   │  SQLite  │   │  Vector DB   │   │  LLM/Embed  │
   │ (Prisma) │   │ (LanceDB等)  │   │  Providers  │
   └──────────┘   └──────────────┘   └──────────────┘
```

**数据流**: 用户通过 Frontend 上传文档 → Server 转发给 Collector 处理 → Server 进行文本分割和向量化 → 存入 Vector DB → 用户查询时进行相似度检索 → LLM 生成回答

**Agent 流**: 用户发送 @agent 指令 → Agent 系统 (aibitat) 接管 → 多 Agent 并发协作 → 调用工具插件 → 汇总结果返回

---

## 技术栈详情

- **运行时**: Node.js >= 18
- **后端框架**: Express.js 4.x
- **ORM**: Prisma 5.3.1 (默认 SQLite，可选 PostgreSQL)
- **前端**: React 18 + Vite 4 + TailwindCSS 3
- **Agent 框架**: 自研 aibitat 多 Agent 系统
- **AI SDK**: Anthropic SDK, OpenAI SDK, LangChain
- **任务调度**: @mintplex-labs/bree (基于 Bree)
- **WebSocket**: @mintplex-labs/express-ws
- **Web Push**: web-push
- **文档处理**: pdf-lib, cheerio, docx, exceljs, pptxgenjs, mdpdf
- **向量化**: @xenova/transformers (本地), 各云服务 SDK
- **向量数据库**: LanceDB (默认), Pinecone, Chroma, Qdrant, Milvus, Weaviate, AstraDB, PGVector
- **国际化**: i18next
