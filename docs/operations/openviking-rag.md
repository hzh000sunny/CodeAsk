# OpenViking RAG 运维说明

> 范围：CodeAsk v1.0.5 的 OpenViking Wiki RAG 使用、配置和排障。
> 状态：Active

本文面向部署者和管理员，避免为了理解 OpenViking RAG 去阅读 v1.0.5 的开发计划文档。

## 当前范围

v1.0.5 的 OpenViking 只负责 **Wiki 语义召回**：

- opencode 会话可以通过 OpenViking MCP 检索 Wiki 候选。
- Wiki UI 搜索框仍走 SQL ILIKE，不调用 OpenViking。
- Report 不进入 OpenViking，只维护本地 `problem-reports/` 文件视图。
- 代码仓内容不进入 OpenViking；源码证据仍通过 CodeAsk `prepare_worktree` 后读取真实 worktree。

OpenViking 是增强能力，不是 CodeAsk 的事实源。Wiki、Report、Repo、权限和审计仍由 CodeAsk 管理。

## 资源布局

CodeAsk 按 feature 同步 Wiki 目录：

```text
wiki_workspace/current/<feature_slug>/knowledge-base
```

对应 OpenViking URI：

```text
viking://resources/codeask/wiki/<feature_slug>
```

预留但当前不导入：

```text
viking://resources/codeask/code/<repo_slug>
```

## 运行方式

OpenViking 作为 CodeAsk 依赖随 `uv sync` 安装。CodeAsk 后端负责：

- 生成 `$CODEASK_DATA_DIR/openviking/ov.conf`
- 拉起 `openviking-server` 子进程
- keepalive 守护和健康检查
- 把 OpenViking MCP endpoint 注入 opencode 会话配置
- 维护同步任务、事件流和运行指标

常用路径：

```text
$CODEASK_DATA_DIR/openviking/
├── ov.conf
├── workspace/
├── models/
└── logs/
```

CodeAsk 不使用用户默认 `~/.openviking` 作为运行目录。

注意：上面的 `models/` 是 CodeAsk 预留的 OpenViking 运行目录。默认 local embedding 的 GGUF 模型缓存使用 OpenViking 自身规则，路径是 `~/.cache/openviking/models/`。

## Embedding 和 VLM

默认 embedding provider 是 OpenViking local：

- 依赖由 `openviking[local-embed]>=0.3.22,<0.4` 提供。
- 默认模型是 `local/bge-small-zh-v1.5-f16`。
- 首次使用 local 模型时，OpenViking 会按自身缓存规则下载模型。
- 模型文件不随 CodeAsk 仓库提交。

管理员可以在设置页切换 embedding provider，例如 Ollama、OpenAI-compatible 或其他 OpenViking 支持的 provider。

规则：

- 点击“测试”只使用用户数据目录下的临时 `ov.conf` 调 OpenViking doctor。
- 测试不会保存 DB、不会覆盖正式 `ov.conf`、不会重启、不会清索引。
- 点击“保存”才会持久化配置。
- 保存 embedding 配置需要破坏性确认，会重启 OpenViking、清理索引并重新同步 Wiki。
- VLM 默认关闭；保存 VLM 配置只重启 OpenViking，不清索引。

### local 模型手动下载

如果首次启用 local embedding 时自动下载失败，通常是网络、代理或 Hugging Face 访问问题。可以手动把默认模型放到 OpenViking 的默认缓存路径。

默认模型：

```text
local/bge-small-zh-v1.5-f16
```

默认文件路径：

```text
~/.cache/openviking/models/bge-small-zh-v1.5-f16.gguf
```

手动下载命令：

```bash
mkdir -p "$HOME/.cache/openviking/models"
curl -L \
  "https://huggingface.co/CompendiumLabs/bge-small-zh-v1.5-gguf/resolve/main/bge-small-zh-v1.5-f16.gguf?download=true" \
  -o "$HOME/.cache/openviking/models/bge-small-zh-v1.5-f16.gguf"
```

下载后确认文件存在：

```bash
ls -lh "$HOME/.cache/openviking/models/bge-small-zh-v1.5-f16.gguf"
```

文件放好后，在管理员界面重新测试 embedding 配置，或重启 CodeAsk 后端让 OpenViking 重新加载。

如果管理员配置里指定了自定义 `model_path`，模型文件必须放在该精确路径；如果指定了自定义 `model_cache_dir`，则把 `bge-small-zh-v1.5-f16.gguf` 放到该目录下。

## Ollama 可选路径

默认 local provider 不要求安装 Ollama。

只有在管理员选择 Ollama provider 时，部署者才需要准备：

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull <embedding-model>
```

检查：

```bash
curl -sf http://127.0.0.1:11434/api/version
curl -sf http://127.0.0.1:11434/api/tags | python3 -m json.tool
```

Ollama CPU 模式通常建议把 embedding 并发设为 `1`，避免本地模型队列被并发请求拖慢。

## 同步触发

这些操作会让对应 feature 的 Wiki 目录进入 OpenViking 同步队列：

- 上传 legacy Markdown / 文本 / PDF 后落到 Wiki。
- 发布 Wiki 文档。
- 回滚 Wiki 文档。
- 移动、重命名、删除或恢复 Wiki 节点。
- 创建、重命名、删除或恢复 feature。
- 管理员手动重同步。
- 定时 sweep 发现本地 feature 与远端 OpenViking 不一致。

这些操作不会进入 OpenViking：

- 保存或删除 Wiki 草稿。
- Report verify / unverify / reject / delete。
- 仓库 ready / refresh。

## 定时 sweep

CodeAsk 会定时执行 OpenViking sweep，当前默认每 1 小时一次。

sweep 做三件事：

1. 扫描 active feature 的已发布 Wiki。
2. 对比本地 hash 与同步任务记录，变化的 feature 入队 `add_resource`。
3. 对比 OpenViking 远端 `wiki/` 根目录，远端存在但 CodeAsk active feature 不存在的资源入队删除。

如果当前已有 running sync job，本轮 sweep 会跳过新增 `add_resource`，避免重叠提交。

## 管理员界面怎么看

在 admin 设置页的 OpenViking 面板中关注：

- **健康状态**：OpenViking 是否 running、PID、端口、版本、配置路径。
- **索引构建**：embedding 队列、处理速度、预计剩余时间。
- **运行指标**：近期吞吐、请求延迟、breaker 事件。
- **同步任务**：pending / running / failed / cancelled / indexed。
- **事件流**：同步触发、模型切换、进程重启、失败重试和远端对账。
- **Embedding/VLM 配置**：当前 provider、模型、维度、并发和测试结果。

判断“可召回”的关键不是只看任务是否创建，而是看同步任务进入 indexed，且 embedding 队列已经 drain。

## 模型在会话里怎么用

当 OpenViking 可用时，CodeAsk 会在 opencode 会话上下文中提示：

- 先从 `viking://resources/codeask/wiki` 根目录做宽召回。
- 如果已经知道 feature，再收窄到 `viking://resources/codeask/wiki/<feature_slug>`。
- OpenViking 结果是 Wiki 候选，不是源码事实。
- 需要源码证据时必须调用 CodeAsk `prepare_worktree`，再读真实 worktree 文件。

OpenViking 不可用时，会话仍可以通过 `workspace/wiki` symlink 使用 native read/grep/glob 读取 Wiki 文件。

## 常见问题

| 问题 | 说明 |
|---|---|
| UI Wiki 搜索为什么没有用 OpenViking | UI 搜索是导航功能，直接走 SQL ILIKE，避免受 embedding 队列和模型切换影响 |
| Report 为什么不进 OpenViking | v1.0.5 release 范围已收敛，Report 只作为本地文件视图给 opencode 读取 |
| 代码仓为什么搜不到 | 代码仓 OpenViking 内容同步已延后；源码证据走 `prepare_worktree` |
| local 模型是否需要手动下载 | 默认由 OpenViking 首次使用时按自身缓存规则下载；自动下载失败时按上面的手动下载命令放到 `~/.cache/openviking/models/` |
| 切换 embedding 为什么要重建索引 | 不同 provider/model/dimension 的向量不兼容，需要清索引并重新同步 |
| add_resource 重复提交是不是全量重建 | OpenViking 对同一路径会按自身逻辑处理增量；CodeAsk 侧定时 sweep 会避免在 running job 期间重复提交 |
| 同步任务 running 但 embedding 队列空了怎么办 | 以同步任务和 OpenViking task 状态为准；队列空只是一个信号，后台还可能在完成后处理或状态刷新 |

## 相关文档

- [INSTALL.md](../../INSTALL.md)：安装入口。
- [docs/operations/troubleshooting.md](./troubleshooting.md)：通用排障。
- [docs/v1.0.5/README.md](../v1.0.5/README.md)：当前版本范围。
