# Server 后端服务 — 模块索引

> AnythingLLM 的核心后端，基于 Express.js 框架，提供 REST API、WebSocket、SSE 流式响应。

## 架构概览

```
server/
├── index.js              # 入口文件，Express 应用初始化
├── prisma/schema.prisma  # 数据库模式定义 (40+ 表)
├── models/               # 数据模型层 (ORM 封装)
├── endpoints/            # API 端点路由
│   ├── api/              # 开发者 API (v1)
│   ├── embed/            # 嵌入组件 API
│   ├── experimental/     # 实验性功能
│   ├── extensions/       # 扩展端点
│   ├── mobile/           # 移动端 API
│   └── utils/            # 端点工具函数
├── middleware/            # Express 中间件
├── utils/                # 核心工具模块
│   ├── AiProviders/      # 35+ LLM 提供商
│   ├── EmbeddingEngines/ # 15 个嵌入模型引擎
│   ├── vectorDbProviders/# 10 个向量数据库
│   ├── agents/           # Agent 系统 (aibitat)
│   ├── agentFlows/       # Agent 流程执行器
│   ├── chats/            # 聊天处理管线
│   ├── MCP/              # Model Context Protocol
│   ├── DocumentManager/  # 文档管理
│   ├── TextSplitter/     # 文本分割
│   ├── BackgroundWorkers/# 后台任务
│   ├── telegramBot/      # Telegram 机器人
│   └── ...               # 更多工具
├── jobs/                 # 后台 Job 定义
├── swagger/              # API 文档
└── storage/              # 文件存储
```

## 模块导航

### [01 — 入口与启动流程](./01-entry-point.md)
Express 应用初始化、中间件注册、路由挂载、SSL/HTTP 引导启动。

### [02 — 数据库模式 (Prisma)](./02-prisma-schema.md)
40+ 张数据表的完整定义：用户、工作区、聊天、文档、Agent、定时任务等。

### [03 — 数据模型层](./03-models.md)
ORM 封装层，提供业务逻辑方法：CRUD、验证、关联查询、权限控制。

### [04 — API 端点系统](./04-endpoints.md)
REST API + WebSocket + SSE 流式端点：聊天、工作区、文档、Admin、API v1。

### [05 — LLM 提供商系统](./05-ai-providers.md)
35+ 个 AI 提供商集成：OpenAI, Anthropic, Gemini, Ollama, Azure, Bedrock 等。

### [06 — 嵌入引擎系统](./06-embedding-engines.md)
15 个嵌入模型提供商：支持本地模型 (Xenova/Transformers) 及云端服务。

### [07 — 向量数据库系统](./07-vector-db-providers.md)
10 个向量数据库支持：LanceDB, Pinecone, Chroma, Qdrant, Milvus, Weaviate 等。

### [08 — Agent 系统 (aibitat)](./08-agent-system.md)
多 Agent 协作框架：Agent 编排、插件系统、工具调用、提供商抽象。

### [09 — Agent 插件系统](./09-agent-plugins.md)
20+ 种 Agent 工具插件：文件操作、Gmail、Google Calendar、SQL、网页浏览等。

### [10 — Agent 流程执行器](./10-agent-flows.md)
预定义的 Agent 工作流：社区中心导入的 Flow 定义与执行。

### [11 — 聊天处理管线](./11-chat-system.md)
多模式聊天系统：chat/query/automatic 模式、RAG 检索增强、流式响应。

### [12 — 文档管理系统](./12-document-management.md)
文档上传、解析、向量化、缓存、同步、去重的完整管线。

### [13 — 文本分割系统](./13-text-splitters.md)
基于 LangChain 的递归字符分割器，支持元数据头、嵌入前缀。

### [14 — MCP (Model Context Protocol)](./14-mcp.md)
MCP 协议实现：服务器管理、工具发现、连接超visor。

### [15 — 后台任务系统](./15-jobs.md)
基于 Bree 的后台任务调度：嵌入 Worker、文档同步、定时清理、Telegram 处理。

### [16 — Telegram 机器人](./16-telegram-bot.md)
完整的 Telegram Bot 集成：命令系统、导航、聊天流式响应。

### [17 — 移动端 API](./17-mobile-api.md)
移动应用连接接口：设备注册、Token 管理、消息推送。

### [18 — 中间件系统](./18-middleware.md)
Express 中间件：认证、授权、多用户保护、请求验证。

### [19 — 工具函数集](./19-utilities.md)
辅助工具：加密、日志、文件管理、HTTP 工具、推送通知等。

### [20 — Swagger API 文档](./20-swagger.md)
OpenAPI 规范文档自动生成。

### [21 — 测试系统](./21-tests.md)
Jest 测试套件：模型测试、工具函数测试、Agent 测试。
