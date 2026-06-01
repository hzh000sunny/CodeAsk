# OpenViking 知识库

> OpenViking 是一个开源的 **AI Agent 上下文数据库** (Context Database)，由字节跳动/火山引擎开发。
> 它采用**文件系统范式**统一管理 Agent 的记忆(Memories)、资源(Resources)和技能(Skills)，
> 通过 L0/L1/L2 三层分级加载、目录递归检索、会话自动记忆提取等机制，
> 解决 AI Agent 开发中的上下文碎片化、Token 消耗过高、检索效果差等问题。

---

## 仓库概览

| 属性 | 值 |
|---|---|
| **仓库地址** | `github.com/volcengine/OpenViking` |
| **主语言** | Python 3.10+ (核心), Rust (CLI + RAGFS), C++ (向量引擎) |
| **构建系统** | setuptools + maturin + CMake |
| **核心依赖** | FastAPI, Pydantic, httpx, OpenAI SDK, LiteLLM, tree-sitter, OpenTelemetry |

---

## 模块索引

### [01 架构总览](01-architecture-overview/architecture-overview.md)
整体架构设计、核心设计哲学、数据流概览、部署拓扑

### [02 核心包](02-core-package/core-package.md)
- Viking URI 体系 (`viking://resources/`, `viking://user/`, `viking://agent/`)
- 上下文类型 (ContextType: memory/resource/skill)
- 三层分级 (L0 Abstract / L1 Overview / L2 Detail)
- 目录结构与命名空间 (user/agent 隔离策略)
- 技能加载器 (SkillLoader)
- MCP 协议转换器

### [03 服务器 & API](03-server-api/server-api.md)
- FastAPI 应用工厂与生命周期
- 路由体系 (resources, filesystem, search, sessions, admin, metrics, system, bot, console, tasks, relations, pack, debug, observer, webdav, stats, privacy)
- 认证体系 (API Key, OAuth2, OTP)
- MCP 端点 (Model Context Protocol)
- 请求上下文与身份模型
- 错误映射与本地输入守卫

### [04 服务层](04-service-layer/service-layer.md)
- 核心服务 (资源/文件系统/搜索/会话/关系/打包/重索引/调试/任务)
- 任务追踪器
- 服务间依赖关系

### [05 客户端 SDK](05-client-sdks/client-sdks.md)
- AsyncOpenViking (单例嵌入式客户端)
- SyncOpenViking (同步外观)
- LocalClient (进程内直接调用)
- HTTP 客户端 (AsyncHTTPClient / SyncHTTPClient)
- Session 对象 (面向对象会话操作)
- 消息模型 (Message / TextPart / ContextPart / ToolPart)
- Web 控制台 (代理 BFF + 静态前端)

### [06 存储层](06-storage-layer/storage-layer.md)
- **VikingFS**: 虚拟文件系统抽象 (read/write/mkdir/rm/mv/grep/find/search/tree/stat/link)
- **向量数据库引擎**: 集合管理, 本地/HTTP/Volcengine/VikingDB 适配器
- **C++ 引擎后端**: IndexEngine (向量搜索), PersistStore/VolatileStore (KV 存储), BytesRow/Schema (二进制序列化)
- **QueueFS**: 语义处理管道 (SemanticQueue → SemanticProcessor → SemanticDagExecutor → EmbeddingQueue)
- **OVPack**: 导出/导入/备份/恢复 (v2 格式, 增量向量快照)
- **事务**: 分布式文件锁 (PathLockEngine), 锁管理器 (LockManager), 崩溃恢复 (RedoLog)
- **观察者**: 文件系统/锁/模型/队列/检索/VikingDB 健康监控

### [07 模型 & 嵌入](07-models-embeddings/models-embeddings.md)
- **VLM 后端**: Volcengine, OpenAI/Azure, Codex (OAuth), Kimi, GLM, LiteLLM
- **嵌入器**: OpenAI, Volcengine, Jina, Cohere, Voyage, DashScope, MiniMax, Gemini, LiteLLM, VikingDB, Local (llama-cpp)
- **重排序器**: Volcengine (VikingDB), Cohere, LiteLLM, OpenAI
- **Token 使用追踪器**
- **结构化 VLM 输出** (JSON Schema 约束)
- **故障转移 VLM**

### [08 内容解析](08-content-parsing/content-parsing.md)
- **数据访问器**: HTTP (URL 下载), Git (仓库克隆), Feishu/Lark (云文档), Local (本地文件)
- **文档解析器**: Markdown, HTML, PDF (pdfplumber + MinerU), Word, Excel, PowerPoint, EPub, 旧版 DOC, ZIP, 目录, Feishu, 纯文本
- **代码解析器**: 仓库解析 + 9 种语言 AST 骨架提取 (Python, JS/TS, Java, C/C++, Rust, Go, C#, PHP, Lua)
- **媒体解析器**: 图像 (VLM 描述 + OCR), 音频 (ASR), 视频
- **资源检测器**: 访问类型/大小/递归分类
- **TreeBuilder**: 解析树转 VikingFS URI 映射
- **VLM 文档处理器**: 图像/表格/页面批处理分析

### [09 检索系统](09-retrieval-system/retrieval-system.md)
- **层次化检索器**: BFS 优先队列搜索, 分数传播, 收敛检测
- **意图分析器**: LLM 驱动的查询计划生成
- **记忆生命周期**: 热度评分函数 (sigmoid × 指数衰减)
- **检索统计**: 线程安全的指标收集器

### [10 会话 & 记忆](10-session-memory/session-memory.md)
- **会话核心**: 消息生命周期, 两阶段提交, 存档管理, Working Memory v2
- **记忆提取**: 8 类分类, LLM 提取 + 向量预过滤 + LLM 去重决策
- **记忆模板系统 v2**: ReAct 编排器, YAML Schema 定义, 动态 Pydantic 模型生成
- **合并操作**: PATCH (搜索替换), REPLACE, SUM, IMMUTABLE
- **记忆更新器**: 写入/编辑/删除/向量化/概览生成
- **Agent 记忆**: 轨迹提取 → 经验整合 (两阶段)
- **会话压缩器**: v1 (传统 8 类) / v2 (模板化)
- **记忆归档器**: 冷热分离, 自动归档

### [11 VikingBot 代理框架](11-vikingbot/vikingbot.md)
- **代理核心**: ReAct 循环, 并行工具执行, 上下文构建器
- **工具系统**: 文件系统, Shell, Web 搜索 (Brave/DuckDuckGo/Exa/Tavily), 消息, MCP, Cron, 图像, 子代理
- **通道系统**: Telegram, Discord, Slack, Feishu, DingTalk, WhatsApp, QQ, Email, OpenAPI, MoChat, 单轮
- **沙箱**: Direct / AioSandbox (Docker) / OpenSandbox (K8s) / SRT (Anthropic)
- **LLM 提供商**: LiteLLM + OpenAI 兼容
- **OpenViking 挂载**: FUSE 文件系统 (5 种实现), API 挂载, 会话集成
- **可观测性**: Langfuse 集成, 响应结果评估, 反馈统计
- **调度与心跳**: CronService (at/every/cron), HeartbeatService (定时唤醒)
- **会话管理**: JSONL 持久化, 工作区沙箱集成

### [12 指标 & 可观测性](12-metrics-observability/metrics-observability.md)
- **指标核心**: 注册表, 运行时, 刷新调度器, 账户维度
- **数据源**: HTTP, 队列, 会话, 缓存, VLM, 嵌入, 重排序, 任务, 加密, 资源, 检索, 观察者状态, 模型使用, 遥测桥
- **收集器**: 对应每个数据源的 Prometheus 指标收集器 (Counter/Gauge/Histogram)
- **导出器**: Prometheus (/metrics 端点), OpenTelemetry (OTLP gRPC/HTTP)
- **遥测**: 操作跨度模型, 执行上下文, 快照, 请求等待追踪器, 内存后端
- **可观测性**: HTTP 中间件, 事件总线, 使用审计 (SQLite 存储, 投影, 订阅者)

### [13 加密 & 隐私](13-crypto-privacy/crypto-privacy.md)
- **信封加密**: AES-256-GCM, HKDF 密钥派生
- **密钥提供者**: LocalFile, HashiCorp Vault, Volcengine KMS
- **隐私配置**: 版本化用户隐私设置 (upsert/activate/list), 技能敏感值提取与占位符替换

### [14 Rust CLI](14-rust-cli/rust-cli.md)
- 基于 Clap 的 30+ 命令 CLI 工具
- TUI 模式 (ratatui + crossterm): 文件树浏览器, 内容预览, 向量记录查看, 图片预览
- 交互式聊天 (SSE 流式)
- 动态超时, 进度条, 目录 zip 上传

### [15 RAGFS 虚拟文件系统](15-ragfs/ragfs.md)
- 核心抽象: FileSystem trait, MountableFS (radix_trie 路由), ServicePlugin
- 内置插件: MemFS, KVFS, LocalFS (ripgrep 集成), QueueFS, SQLFS, S3FS, ServerInfoFS
- HTTP 服务器 (axum): REST API, 动态挂载
- Python 绑定 (PyO3): RAGFSBindingClient

### [16 C++ 向量引擎](16-cpp-engine/cpp-engine.md)
- abi3 Python 扩展 (Python 3.10+ 稳定 ABI)
- IndexEngine: 向量搜索 (HNSW), 标量过滤, 混合检索
- PersistStore/VolatileStore: LevelDB 持久化 KV 存储
- BytesRow/Schema: 二进制行序列化
- x86 CPU 特性检测: SSE3/AVX2/AVX512 多变体编译

### [17 Python CLI](17-python-cli/python-cli.md)
- 配置体系: 服务器/存储/嵌入/VLM/日志/加密/OAuth/内存/解析/重排序/检索/遥测/事务/向量数据库
- 服务器引导 (init/doctor/start)
- 设置向导 (交互式配置)
- HTTP 客户端 (异步/同步)
- 检索类型定义

### [18 集成](18-integrations/integrations.md)
- **LangChain**: 客户端, 检索器, 工具, 存储 (LangGraph BaseStore), 上下文后端, 消息历史, 中间件, 测试内存客户端
- **LangGraph**: Agent 工作流, 中间件模式

### [19 部署](19-deployment/deployment.md)
- Docker (多阶段构建, docker-compose)
- Helm Charts (K8s 部署, PVC, Ingress)
- Caddy 反向代理
- ECS / VKE 部署脚本

### [20 基准测试 & 评估](20-benchmarks-eval/benchmarks-eval.md)
- LoCoMo 长期对话基准
- RAG 基准 (FinanceBench, QASPER, SyllabusQA)
- SkillsBench / Tau2 / Vaka
- RAGAS 评估框架
- IO 录制与回放
- 自定义会话竞争基准
