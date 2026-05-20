# 01 架构总览

## 1. 项目定位

OpenViking 是一个**上下文数据库** (Context Database)，专为 AI Agent 设计。它提供统一的文件系统范式来管理 Agent 的记忆、资源和技能。

### 核心设计理念

1. **文件系统范式** → 解决碎片化: 所有上下文以 `viking://` URI 组织为虚拟文件系统
2. **三层分级加载** → 减少 Token 消耗: L0(Abstract) / L1(Overview) / L2(Detail)
3. **目录递归检索** → 提升检索效果: 先定位高分区目录，再递归精细化搜索
4. **可视化检索轨迹** → 可观测上下文: 保留完整检索路径便于调试
5. **自动会话管理** → 上下文自迭代: 会话结束后自动提取长期记忆

---

## 2. 项目构成

```
OpenViking/
├── openviking/              # 核心 Python 包 (服务端 + 客户端 + 业务逻辑)
│   ├── core/                # 核心概念 (URI, Context, Directory, Namespace, Skill)
│   ├── server/              # FastAPI HTTP 服务器 (路由, 认证, OAuth, MCP)
│   ├── service/             # 业务服务层
│   ├── client/              # Python 客户端 SDK
│   ├── storage/             # 存储层 (VikingFS, vectordb, queuefs, ovpack, transaction)
│   ├── models/              # ML 模型接口 (VLM, Embedder, Reranker)
│   ├── parse/               # 内容解析 (20+ 文件格式, 9 种语言 AST)
│   ├── session/             # 会话管理 + 记忆提取
│   ├── retrieve/            # 层次化检索系统
│   ├── metrics/             # 指标收集与导出 (Prometheus, OTel)
│   ├── telemetry/           # 操作遥测
│   ├── observability/       # 可观测性 (事件总线, 使用审计)
│   ├── crypto/              # 加密 (信封加密, AES-256-GCM)
│   ├── privacy/             # 隐私配置
│   ├── prompts/             # 提示词模板系统
│   ├── integrations/        # LangChain/LangGraph 集成
│   ├── eval/                # RAGAS 评估 + IO 录制回放
│   ├── console/             # Web 控制台 BFF
│   ├── pyagfs/              # AGFS Python SDK (Rust 绑定)
│   └── resource/            # 资源监控 (Watch)
│
├── openviking_cli/          # Python CLI 工具
│   ├── client/              # HTTP/SyncHTTP 客户端
│   ├── utils/config/        # 分层配置管理 (20+ 配置类)
│   ├── utils/               # LLM 调用, 提取器, 下载器
│   ├── server_bootstrap.py  # 服务器启动入口
│   └── setup_wizard.py      # 交互式设置向导
│
├── bot/                     # VikingBot 代理框架
│   └── vikingbot/
│       ├── agent/           # ReAct 代理循环 + 工具系统
│       ├── channels/        # 12 种通道 (Telegram, Discord, Feishu, WhatsApp...)
│       ├── providers/       # LLM 提供商
│       ├── sandbox/         # 沙箱 (Docker, K8s, SRT)
│       ├── hooks/           # 钩子系统
│       ├── openviking_mount/# FUSE 文件系统挂载
│       ├── bus/             # 消息总线
│       ├── session/         # 会话管理
│       ├── cron/            # 定时任务
│       ├── heartbeat/       # 心跳服务
│       ├── observability/   # 反馈统计 + 结果评估
│       └── integrations/    # Langfuse 集成
│
├── crates/                  # Rust 组件
│   ├── ov_cli/              # Rust CLI 工具 (TUI + 30+ 命令)
│   ├── ragfs/               # 虚拟文件系统 (插件架构, HTTP 服务器)
│   └── ragfs-python/        # Python 绑定 (PyO3)
│
├── src/                     # C++ 向量引擎
│   ├── abi3_engine_backend.cpp  # Python abi3 扩展
│   └── abi3_x86_caps.cpp         # CPU 特性检测
│
├── tests/                   # Python 测试套件
├── benchmark/               # 基准测试
├── deploy/                  # Helm Charts
├── examples/                # 示例与插件
└── docs/                    # VitePress 文档
```

---

## 3. 数据流概览

### 3.1 资源摄入流程

```
外部来源 (URL/Git/Feishu/本地)
    │
    ▼
DataAccessor (下载/克隆/获取)
    │
    ▼
Parser (解析为文档树)
    │
    ▼
TreeBuilder (映射到 VikingFS URI)
    │
    ▼
SemanticQueue → SemanticProcessor → SemanticDagExecutor
    │                               │
    │                               ├── 生成 L0 Abstract (.abstract.md)
    │                               ├── 生成 L1 Overview (.overview.md)
    │                               └── 为每个文件创建 EmbeddingMsg
    │
    ▼
EmbeddingQueue → TextEmbeddingHandler → VikingVectorIndexBackend
```

### 3.2 检索流程

```
用户查询 (query)
    │
    ▼
IntentAnalyzer (LLM 意图分析 → TypedQuery 列表)
    │
    ▼
HierarchicalRetriever
    │
    ├── 全局向量搜索 (top-K 候选目录)
    ├── 合并起点
    ├── 递归搜索 (BFS 优先队列)
    │   ├── 搜索当前目录子项
    │   ├── 分数传播 (parent × α + child × (1-α))
    │   └── 收敛检测 (3 轮无变化)
    └── 结果聚合 (热度混合)
```

### 3.3 会话记忆提取流程

```
Session.commit()
    │
    ▼
Phase 1: 消息归档 (LockContext 下)
    ├── 保留尾部最近消息
    ├── 归档旧消息到 archive_NNN/
    └── 生成 Working Memory v2 (.overview.md)
    │
    ▼
Phase 2: 后台记忆提取
    ├── MemoryExtractor (LLM → 8 类候选记忆)
    ├── MemoryDeduplicator (向量预过滤 + LLM 去重决策)
    ├── MemoryUpdater (写入/合并/删除 + 向量化)
    └── 生成 memory_diff.json
```

---

## 4. 部署拓扑

```
                   ┌──────────────┐
                   │   AI Agent   │
                   │  (Claude,    │
                   │   OpenClaw,  │
                   │   Codex...)  │
                   └──────┬───────┘
                          │ HTTP / MCP / FUSE
                          ▼
     ┌────────────────────────────────────────┐
     │         OpenViking Server              │
     │  ┌──────────┐  ┌────────────────────┐  │
     │  │ FastAPI   │  │ VikingBot Gateway  │  │
     │  │ :1933     │  │ :8080              │  │
     │  └────┬─────┘  └────────┬───────────┘  │
     │       │                 │               │
     │  ┌────▼─────────────────▼────────────┐  │
     │  │         Service Layer             │  │
     │  └────┬──────────────────────────────┘  │
     │       │                                 │
     │  ┌────▼──────────────────────────────┐  │
     │  │       Storage Layer               │  │
     │  │  ┌─────────┐  ┌────────────────┐  │  │
     │  │  │ VikingFS │  │ Vector Engine  │  │  │
     │  │  │ (RAGFS)  │  │ (C++ / LevelDB)│  │  │
     │  │  └─────────┘  └────────────────┘  │  │
     │  └───────────────────────────────────┘  │
     └────────────────────────────────────────┘
```

---

## 5. 关键技术栈

| 层次 | 技术 |
|---|---|
| HTTP 框架 | FastAPI + Uvicorn |
| 数据验证 | Pydantic v2 |
| HTTP 客户端 | httpx (Python), reqwest (Rust) |
| 向量存储 | 自研 C++ 引擎 (HNSW) + LevelDB |
| 文件系统 | RAGFS (Rust, 插件架构) |
| 异步 | asyncio (Python), tokio (Rust) |
| 可观测性 | OpenTelemetry + Prometheus + Langfuse |
| 加密 | AES-256-GCM, HKDF-SHA256, Argon2 |
| 代码解析 | tree-sitter (9 种语言) |
| 构建 | setuptools + maturin + CMake |

---

## 6. 单例模式

整个代码库中广泛使用模块级单例 (init_* / get_* 模式):

| 单例 | 位置 | 用途 |
|---|---|---|
| `AsyncOpenViking` | `openviking/async_client.py` | 全局嵌入式客户端 |
| `VikingFS` | `openviking/storage/viking_fs.py` | 虚拟文件系统 |
| `QueueManager` | `openviking/storage/queuefs/queue_manager.py` | 消息队列管理 |
| `LockManager` | `openviking/storage/transaction/lock_manager.py` | 分布式锁 |
| `VikingVectorIndexBackend` | `openviking/storage/viking_vector_index_backend.py` | 向量索引 |
| `IORecorder` | `openviking/eval/recorder/recorder.py` | IO 录制 |
| `PromptManager` | `openviking/prompts/manager.py` | 提示词管理 |
| `RetrievalStatsCollector` | `openviking/retrieve/retrieval_stats.py` | 检索统计 |
| `EmbeddingTaskTracker` | `openviking/storage/queuefs/embedding_tracker.py` | 嵌入追踪 |
