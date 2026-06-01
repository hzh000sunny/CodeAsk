# RAG 与知识处理增强路线

> 状态：Draft
> 版本归属：待定
> 主题：CodeAsk 未来的本地 RAG、文本处理、向量处理和召回能力增强
> 最新补充：2026-05-19，新增 AnythingLLM / OpenViking 参考后的候选主架构判断

> Superseded：本文件作为 v1.0.5 前的设计前史保留。OpenViking 统一后端方案已进入并落地到 [docs/v1.0.5/](../v1.0.5/)；后续实现和验收以 v1.0.5 PRD / SDD / plans 为准。

## 1. 背景

当前 CodeAsk 已具备：

- Wiki、问题报告、会话附件、代码仓库等多类知识入口。
- 基于 `retrieval_context` 的轻量候选注入。
- 会话级 Agent runtime、工具调用、上下文预算和行动轨迹。

但当前内置 RAG 仍是过渡实现，后续需要把知识处理能力提升到更稳定、更系统的层级。

本文件记录未来增强方向，避免以下共识在后续版本中丢失：

- 早期方向曾倾向本地 LanceDB；在接入 opencode 后，RAG 主后端需要重新评估，当前更优先评估 **OpenViking 作为统一 Context Database / RAG 后端**。
- 可以认真评估是否引入 **LangChain** 作为文本处理、切分和检索编排的基础设施，但如果采用 OpenViking，则 LangChain 更偏参考或局部工具，而不是主 runtime。
- 目标不是照搬 AnythingLLM，而是让 CodeAsk 在**文本处理、向量处理、召回质量**上，至少对齐 AnythingLLM 的基础能力；AnythingLLM 更适合作为文档处理链路参考，而不是直接作为 CodeAsk Wiki RAG 的主服务。
- 在当前没有明显错误的前提下，**暂不优先做会话收敛策略强化**，避免引入新的行为劣化。

## 2. 已确认方向

### 2.1 主后端候选：OpenViking 优先

在 CodeAsk v1.0.4 引入 opencode 后，Agent 主链路已经变成：

```text
CodeAsk 准备会话环境、特性目录、Wiki 文件、代码 worktree 和 MCP 工具
    ↓
opencode 在该环境内自主调查
    ↓
CodeAsk 展示事件流、证据、报告和会话沉淀
```

在这个模式下，RAG 不应只考虑“文档向量库”，而应考虑“Agent 可使用的统一上下文数据库”。当前更推荐优先评估 OpenViking：

- OpenViking 的定位是 Context Database，天然面向 Agent。
- OpenViking 使用 `viking://` URI、L0 Abstract / L1 Overview / L2 Detail、目录层次检索和 MCP 工具，更适合 opencode 自主选择检索路径。
- OpenViking 对代码仓的处理更贴合 CodeAsk 多仓库、多特性、按需深入源码调查的目标。
- Wiki、问题报告、代码仓如果进入同一套 OpenViking 资源空间，opencode 只需要面对一套 MCP 和 URI 语义。

这会替代早期“CodeAsk 自建 LanceDB 主索引”的默认倾向。LanceDB 仍可作为参考或备选，但不再作为当前优先主方案。

### 2.2 CodeAsk 保留主数据权

即使采用 OpenViking，也不能把 CodeAsk 的业务模型交给 OpenViking 管理。

CodeAsk 仍然负责：

- Feature / Wiki / Report / Repo / Session / Permission 的主数据。
- 特性管理员、权限、Wiki 树、报告 verified / draft 状态。
- 会话绑定特性、问题报告生成、代码仓配置和 worktree 准备。
- 前端证据展示、行动轨迹、审计和版本升级兼容。

OpenViking 负责：

- 对 CodeAsk 派生出的 Wiki / 报告 / 代码仓资源进行解析、摘要、向量化和检索。
- 通过 MCP 提供 `find/search/read/list/grep/glob` 等 Agent 可用能力。
- 保留检索 URI、层次摘要和召回轨迹，供 CodeAsk 回填引用和调试。

边界原则：

> CodeAsk 管理业务对象，OpenViking 管理可检索上下文。

### 2.3 AnythingLLM 的定位

AnythingLLM 不建议作为 CodeAsk Wiki RAG 的直接运行时依赖。原因：

- AnythingLLM 的核心抽象是 workspace / document / vector / chat，CodeAsk 的核心抽象是 feature / wiki / report / session / repo / evidence。
- 如果 Wiki 用 AnythingLLM，代码仓用 OpenViking，opencode 会面对两套 RAG 后端、两套 MCP / URI / 来源治理语义。
- verified report、draft report、特性权限、报告绑定、CodeAsk 来源引用都需要额外映射。
- 长期看容易形成“双 RAG 后端拼接”，增加调试、排序、上下文预算和审计成本。

AnythingLLM 应作为参考实现，重点吸收：

- 文档上传解析、标准化和生命周期设计。
- Recursive text splitting、chunk size、chunk overlap 和 metadata header。
- `document -> chunk -> vector` 映射。
- 向量缓存、重复 embedding 避免、来源去重和 context window 治理。
- LanceDB、rerank、source window 等成熟经验。

但这些经验应落到 CodeAsk + OpenViking 的架构中，而不是把 AnythingLLM 服务直接嵌入 CodeAsk 主链路。

### 2.4 框架评估

需要认真评估是否引入 LangChain，但要坚持“按需吸收，不被框架绑架”：

- 可以利用其现成的文本切分、文档抽象、部分检索管线能力。
- 不应该把 CodeAsk runtime、工具边界、版本化 Wiki 模型和前端证据展示全部交给 LangChain 接管。
- 如果引入，应限定在知识处理层，而不是产品主流程层。

评估重点：

- `Document` 抽象是否有助于统一 Wiki、报告、附件、外部资料。
- `TextSplitter` 能力是否足够适配 Markdown、日志、代码、报告等多种内容。
- Retrieval 组件是否利于做可审计、可解释、可裁剪的召回。
- 是否会给当前数据模型、索引更新和调试链路带来额外复杂度。

### 2.5 对齐 AnythingLLM 的能力下限

CodeAsk 后续在知识处理层，至少要补齐 AnythingLLM 这类成熟项目的基础能力：

1. 上传资料先解析、标准化，再进入索引。
2. 文本切分要有稳定策略，不是简单全文塞入。
3. 向量入库要有清晰的 `document -> chunk -> vector` 映射。
4. 查询时要有候选召回、去重、截断、引用和来源治理。
5. 知识对象要带明确 provenance，而不是只有内容本身。

## 3. 推荐候选架构

当前推荐候选方案：

> 全部使用 OpenViking 作为 Wiki RAG 和代码仓 RAG 的统一后端；AnythingLLM 作为文档处理与召回治理参考。

### 3.1 总体结构

```text
CodeAsk
├── Feature / Wiki / Report / Repo / Session / Permission
│   └── 仍由 CodeAsk 数据库和现有 UI 管理
│
├── Wiki Workspace Exporter
│   └── 导出稳定 Markdown 文件树
│
├── OpenViking Sync Adapter
│   ├── 同步 Wiki
│   ├── 同步 verified reports / draft reports
│   ├── 同步代码仓资源
│   ├── 触发 reindex / build_index
│   └── 记录同步状态和错误
│
└── opencode Runtime
    ├── CodeAsk MCP：特性绑定、准备 worktree、附件等平台能力
    └── OpenViking MCP：语义检索、读取、grep、glob
```

### 3.2 OpenViking URI 建议

建议将 CodeAsk 派生资源组织为：

```text
viking://resources/codeask/
├── features/
│   ├── <feature_slug>/
│   │   ├── README.md
│   │   ├── knowledge-base/
│   │   ├── problem-reports/
│   │   │   ├── verified/
│   │   │   └── drafts/
│   │   └── repos.md
│   └── ...
│
├── repos/
│   ├── <repo_id_or_slug>/
│   └── ...
│
└── global/
    ├── feature-index.md
    ├── repo-index.md
    └── report-index.md
```

说明：

- Feature 是一级语义边界，和 CodeAsk 当前产品模型保持一致。
- `knowledge-base/` 是正式 Wiki。
- `problem-reports/verified/` 是已验证问题报告，证据权重高。
- `problem-reports/drafts/` 是草稿报告，只能作为弱背景。
- `repos.md` 描述该特性关联代码仓、仓库用途、主要路径和当前版本提示。
- `global/feature-index.md` 和 `global/repo-index.md` 用于帮助模型先理解有哪些特性和仓库，不替模型做强制选择。

### 3.3 MCP 边界

CodeAsk MCP 只保留平台动作：

```text
codeask_get_feature_info
codeask_bind_session_features
codeask_list_feature_repos
codeask_prepare_worktree
codeask_list_session_attachments
codeask_read_session_attachment
```

OpenViking MCP 承接知识检索：

```text
find      语义快速召回
search    带会话上下文的深度召回
read      读取 viking:// URI 内容
list      列目录
grep      精确文本搜索
glob      文件名匹配
health    健康检查
```

不建议重新在 CodeAsk 中封装 `search_wiki`、`search_reports`、`search_code_rag` 等工具。过去的封装检索命中质量弱，容易把模型上下文带偏。OpenViking 接入后，应让 opencode 面向 OpenViking 原生工具做检索。

OpenViking MCP 返回代码仓候选时，应返回 `viking://` URI 和 CodeAsk 可理解的来源元数据，例如 `repo_id`、`repo_name`、`path`、`symbol`、`line_range`。如果该候选可以映射到 session workspace，也可以附带 `workspace_relative_path`，但不能要求模型直接访问宿主机绝对路径。

### 3.4 代码仓 RAG 与真实源码读取

代码仓 RAG 不应替代真实源码读取。

建议职责拆分：

- OpenViking code RAG：用于定位候选 repo、目录、文件、符号和相关上下文。
- CodeAsk `prepare_worktree`：用于准备当前会话可读取的真实源码 worktree。
- opencode 原生 `grep/read/glob`：用于最终读取真实文件，形成可审计源码证据。

也就是说：

```text
OpenViking 负责“可能在哪里”
CodeAsk worktree 负责“真实文件是什么”
opencode 原生工具负责“最终证据确认”
```

因此必须在 opencode 的动态上下文中明确说明：

- 当 OpenViking 返回的是代码仓候选、代码文件候选、符号候选或 repo/path 线索时，如果模型想读取真实源码文件，必须先调用 CodeAsk MCP 的 `codeask_prepare_worktree`。
- `codeask_prepare_worktree` 成功后，模型才能使用 opencode 原生 `grep/read/glob` 读取 session workspace 下的相对路径。
- OpenViking 的 `read(uri)` 可用于读取 OpenViking 维护的摘要、overview、chunk、skeleton 或资源内容；但如果回答需要“源码中确实如此”的证据，最终应回到准备好的 worktree 读取真实文件。
- 后端不应把所有代码仓预先全量挂载到每个 session。代码仓应由模型基于 OpenViking 召回和用户问题，自主决定是否按需准备。
- Wiki live view 可以继续通过 `workspace/wiki` 零复制挂载作为兜底；代码仓不采用全量只读挂载。

### 3.5 opencode 上下文提示建议

后续接入 OpenViking 时，动态上下文和 `AGENTS.md` 应提供资源布局和证据原则，而不是固定流程。

建议核心提示：

```md
## CodeAsk Knowledge Layout

CodeAsk provides two knowledge surfaces:

1. Feature knowledge and reports are indexed in OpenViking under:
   viking://resources/codeask/features/

2. Source repositories are indexed in OpenViking under:
   viking://resources/codeask/repos/

For product, workflow, troubleshooting, or historical issue questions, prefer searching feature knowledge first.
For implementation details, exact function behavior, API contracts, or code evidence, inspect repositories after you have identified the related feature or repository.

Use OpenViking semantic search to locate candidate Wiki/report/code resources.
Use read/list/grep/glob to inspect exact files.
Use CodeAsk MCP tools when you need to bind the session to features, prepare a live worktree, inspect attachments, or update CodeAsk session state.

When OpenViking returns code repository candidates, file candidates, symbols, or repo/path hints, do not assume the real source file already exists in the session workspace.
Before reading real repository files with native grep/read/glob, call CodeAsk MCP `codeask_prepare_worktree` for the relevant repository.
After the worktree is prepared, inspect the workspace-relative repository path returned by CodeAsk.
OpenViking `read(uri)` is suitable for OpenViking-managed abstracts, overviews, chunks, skeletons, and resource content; source-code conclusions should be confirmed from the prepared worktree whenever practical.

Problem reports are reference material:
- verified reports are stronger evidence
- draft reports are weak background
- only treat a report as the same issue when symptoms, error, scenario, and root cause match closely
```

这里的重点是：提示模型资源分层和证据强弱，但不由后端强制“先 Wiki 后代码”。用户明确要求看源码时，模型可以直接进入代码调查。

### 3.6 OpenViking 部署调研

当前调研结论：CodeAsk 后续接入 OpenViking 时，不建议把 Docker 作为默认路径。CodeAsk 项目本身使用 `uv` 管理 Python 环境，因此默认部署也应基于 `uv`，Docker / Helm 只作为可选部署方式。

已验证的本地环境与命令：

- 当前机器 Python：`3.12.3`，满足 OpenViking `>=3.10` 要求。
- 当前机器 `uv`：`0.11.8`。
- 当前机器未安装 `docker`、`ollama`、`openviking-server`、`rustc`、`cargo`。
- 当前机器有 `cmake`、`gcc`、`g++`，但不应把本地编译工具链作为普通用户部署前置条件。
- `uvx --from openviking openviking-server --help` 可直接拉取 PyPI 包并运行，实测安装 OpenViking `0.3.17`，一次拉取约 133 个依赖包。
- `uvx --from openviking openviking --help` 可运行 CLI，命令包含 `add-resource`、`tree`、`read`、`abstract`、`overview`、`find`、`search`、`grep`、`glob`、`session`、`status`、`health` 等能力。

注意：OpenViking 文档中存在部分命令形态和当前 PyPI 包不完全一致的情况。文档描述过 `openviking-server init` / `openviking-server doctor`，但当前实测 `openviking-server --help` 只展示 server 启动参数；`uvx --from openviking openviking-server doctor --help` 会进入 doctor 检查并提示缺少配置文件。后续正式接入前，必须以目标锁定版本的真实 CLI 行为为准，不能只按文档推断。

#### 3.6.1 推荐安装方式

上游 README 以 `pip install openviking` 为主，但 CodeAsk 应保持 `uv` 体系：

```bash
# Spike / 调研期：不污染 CodeAsk 当前 venv
uvx --from openviking openviking --help
uvx --from openviking openviking-server --help

# 正式接入期：建议做成可选依赖，避免默认安装变重
uv sync --extra openviking

# 如果启用本地 GGUF embedding，再单独启用 native extra
uv sync --extra openviking-local-embed
```

建议未来在 `pyproject.toml` 中拆分可选依赖，而不是直接塞进默认依赖：

```toml
[project.optional-dependencies]
openviking = ["openviking==0.3.17"]
openviking-local-embed = ["openviking[local-embed]==0.3.17"]
```

原因：

- OpenViking 默认依赖较多，包含文档解析、PDF、LiteLLM、Volcengine SDK、native engine 等组件。
- 本地 embedding 需要 `llama-cpp-python`，这类 native 依赖在不同系统上更容易遇到编译或 wheel 兼容问题。
- CodeAsk 的 RAG 能力应允许显式启用，不能让普通安装无感变重。

如果后续希望完全隔离 OpenViking runtime，也可以采用独立 venv：

```bash
uv venv "$CODEASK_DATA_DIR/runtimes/openviking/.venv"
"$CODEASK_DATA_DIR/runtimes/openviking/.venv/bin/python" -m pip install "openviking==0.3.17"
```

但这会引入额外环境管理复杂度。第一版更建议使用 CodeAsk 项目的 `uv sync --extra openviking`，由 CodeAsk 进程管理 OpenViking server 生命周期。

#### 3.6.2 数据目录与启动方式

OpenViking 的配置文件是 JSON 格式 `ov.conf`。CodeAsk 不应使用用户默认的 `~/.openviking`，而应落在 CodeAsk 数据目录内，便于备份、迁移和升级：

```text
$CODEASK_DATA_DIR/openviking/
├── ov.conf
├── workspace/
├── models/
└── logs/
```

建议配置入口：

```bash
export OPENVIKING_CONFIG_FILE="$CODEASK_DATA_DIR/openviking/ov.conf"
uv run --extra openviking openviking-server \
  --config "$CODEASK_DATA_DIR/openviking/ov.conf" \
  --host 127.0.0.1 \
  --port 1933
```

建议 `ov.conf` 的基础结构：

```json
{
  "storage": {
    "workspace": "<CODEASK_DATA_DIR>/openviking/workspace",
    "vectordb": {
      "name": "context",
      "backend": "local"
    },
    "agfs": {
      "backend": "local"
    }
  },
  "server": {
    "host": "127.0.0.1",
    "port": 1933,
    "auth_mode": "trusted",
    "cors_origins": ["http://127.0.0.1:5173", "http://localhost:5173"],
    "temp_upload": {
      "default_mode": "local"
    }
  }
}
```

认证建议：

- Spike 阶段可以只绑定 `127.0.0.1`，使用本机访问，不暴露公网。
- 正式接入时优先评估 `trusted` 模式，由 CodeAsk 作为受信上游注入 `X-OpenViking-Account` / `X-OpenViking-User`，避免把 OpenViking 直接暴露给浏览器。
- 如果后续需要直接开放 OpenViking API，改用 `api_key` 模式，并由 CodeAsk 管理 root key / user key。

健康检查建议：

```bash
curl http://127.0.0.1:1933/health
uv run --extra openviking openviking health
uv run --extra openviking openviking status
```

如果目标版本提供 doctor 能力，再追加：

```bash
uv run --extra openviking openviking-server doctor
```

但由于当前实测 CLI 形态和文档存在差异，doctor 命令必须在锁定版本后重新确认。

#### 3.6.3 Embedding 与 VLM 要求

OpenViking 的语义检索核心依赖 embedding。没有 embedding，就无法达到 CodeAsk 希望的 Wiki RAG / 代码 RAG 质量目标。

可选 embedding 方向：

1. 云端或私有网关 embedding：
   - 支持 `openai`、`azure`、`volcengine`、`vikingdb`、`jina`、`ollama`、`gemini`、`voyage`、`dashscope`、`minimax`、`cohere`、`litellm`、`local` 等 provider。
   - 如果使用 OpenAI 兼容网关，必要时可设置 `encoding_format: "float"`，避免部分网关无法处理 base64 embedding payload。
   - 这是生产质量更稳定的第一候选，但是否免费取决于用户自己的模型服务。

2. 本地 GGUF embedding：
   - OpenViking 的本地方案默认模型是 `bge-small-zh-v1.5-f16`，维度 `512`。
   - 需要安装 `openviking[local-embed]`，底层依赖 `llama-cpp-python`。
   - 默认模型来源是 HuggingFace，离线环境需要提前缓存或提供模型文件。
   - 优点是调用成本为零；风险是安装、模型下载、CPU 性能和平台兼容性需要实测。

3. Ollama embedding：
   - OpenViking 支持 `provider: "ollama"`。
   - 不需要远程 API key，但需要用户本机或服务器已部署 Ollama 和 embedding 模型。
   - 当前机器未安装 `ollama`，后续只能作为可选路径，不应作为 CodeAsk 默认依赖。

VLM / LLM 的作用是生成 L0 Abstract / L1 Overview 等语义层内容：

- 文本场景下，VLM 不是最小可运行的硬前置；配置缺失时，OpenViking 可以退化为直接基于内容生成较弱的 L0/L1。
- 但为了达到 AnythingLLM 级别以上的检索质量，生产环境应配置 VLM / LLM。
- 对图片、复杂 PDF、多模态材料，VLM 基本是必要能力。
- 未来可以考虑由 CodeAsk 复用已有全局 LLM 配置生成 OpenViking `vlm` 配置，但这需要单独处理 provider 协议、base url、api key、reasoning 参数和失败降级，不能直接拼接。

#### 3.6.4 后续接入风险

需要在正式版本开发前验证：

- PyPI wheel 是否覆盖 CodeAsk 常见部署平台；如果落到源码构建，是否需要 Rust / Cargo / C++ / CMake。
- `openviking-server` 的 CLI 参数和文档差异需要锁版本后重新确认。
- 本地 embedding 在中文 Wiki、代码注释、问题报告上的召回质量和耗时。
- 大型代码仓导入时的索引耗时、磁盘占用、增量更新和失败恢复。
- OpenViking MCP 返回的 URI / path / repo metadata 能否稳定映射回 CodeAsk 的 feature、wiki node、report、repo、path。
- CodeAsk 切换版本时，`$CODEASK_DATA_DIR/openviking` 的配置、索引和模型缓存如何升级兼容。
- OpenViking 不可用时，CodeAsk 是否允许降级为当前的 `workspace/wiki` + `prepare_worktree` + opencode 原生 grep/read。

### 3.7 OpenViking MCP 与同步边界

当前锁定前调研以 OpenViking PyPI `0.3.17` 和本地源码为准。实测 / 源码显示，OpenViking server `/mcp` 已提供以下通用工具：

```text
find
search
read
list
remember
add_resource
grep
glob
forget
health
```

其中：

- `find` 是轻量语义检索。
- `search` 是 session-aware / deep search，可带 `session_id`。
- `read` 读取一个或多个 `viking://` 文件 URI。
- `list` 列出 `viking://` 目录。
- `grep` / `glob` 提供精确文本搜索和路径匹配。
- `add_resource` 在 MCP 场景下只接受 remote URL / Git URL，不支持本地路径。
- `forget` 是危险删除能力，CodeAsk 接入时需要考虑是否暴露给 opencode，或通过权限/提示约束要求用户明确授权。

注意：OpenViking 文档中存在“9 个工具 / `store` 工具”的旧描述，但当前源码是“10 个工具 / `remember` 工具”。正式接入时必须锁定 OpenViking 版本，并通过真实 MCP tool list 做验收。

CodeAsk 的同步边界应明确拆开：

```text
CodeAsk 后台同步本地资源：
  Wiki / 报告 / 本地代码仓 / Git 代码仓
  ↓
  OpenViking CLI / SDK / REST temp_upload / add_resource
  ↓
  OpenViking 维护 viking:// 资源、L0/L1/L2、向量索引

opencode 会话中检索资源：
  OpenViking MCP find/search/grep/glob/read/list
  ↓
  如果需要真实源码证据，再调用 CodeAsk MCP codeask_prepare_worktree
  ↓
  opencode 原生 grep/read/glob 读取 session workspace 相对路径
```

这意味着：

- 不让模型通过 OpenViking MCP 导入 CodeAsk 本地路径。
- 不把宿主机绝对路径暴露到 Agent 工具面。
- 不在 CodeAsk 中重新封装低质量 `search_wiki` / `search_reports` / `search_code`。
- CodeAsk 负责同步状态、权限、来源映射、失败恢复和 UI 展示。
- OpenViking 负责检索、摘要、向量、`viking://` URI 和工具调用。

## 4. 未来目标能力

### 4.1 统一知识对象

需要逐步收敛出统一内部抽象，例如：

```text
KnowledgeDocument
KnowledgeChunk
KnowledgeSource
KnowledgeReference
```

它们应覆盖：

- Wiki 正式文档
- 问题定位报告
- 会话附件和解析结果
- 外部导入资料
- 未来可能的同步来源

最低要求：

- 能标识来源类型。
- 能标识 feature / repo / session / import job 归属。
- 能回到原始文档或原始文件。
- 能支撑删除、重建、重新索引和引用展示。

### 4.2 文本处理

文本处理能力应覆盖至少四类内容：

1. Markdown / Wiki
2. 问题报告
3. 日志 / 会话附件
4. 代码与代码说明材料

不同类型不应使用同一套粗糙切分规则。

重点要求：

- Markdown 保留 heading 层级和段落结构。
- 报告保留结论、证据、验证状态等结构字段。
- 日志保留文件名、重命名名、原始文件名、时间线或行范围。
- 代码相关知识保留 repo、path、symbol、line range、commit 等元数据。

### 4.3 向量处理

向量处理能力需要补齐以下环节：

- chunk 级 embedding 生成。
- 批量写入目标 RAG 后端；若采用 OpenViking，则由 OpenViking 负责资源索引、摘要、向量化和检索。
- `document_id -> chunk_id -> vector_id` 的稳定映射。
- 重命名、移动、删除、归档后的索引更新。
- 重新索引和增量更新能力。

### 4.4 召回与重排

召回能力至少应补齐：

- query 标准化
- 多来源候选召回
- 同源去重
- snippet 裁剪
- heading / path / metadata 保留
- 召回结果排序和必要的 rerank 钩子

后续可考虑：

- 关键词检索 + 向量检索混合召回
- 多路召回融合
- 可插拔 rerank
- 外部 RAG 服务替换入口

## 5. 对 CodeAsk 产品的约束

后续即使增强 RAG，也不能破坏当前已经明确的产品原则：

- RAG 召回结果是**候选证据**，不是后端替模型做的业务结论。
- 不允许把“是否需要继续查代码”“是否知识足够”固化成 RAG 服务自己的判定结果。
- Agent 是否继续调用工具，仍由模型基于上下文、RAG 候选和用户问题自行判断。
- 召回层必须可审计、可追踪、可解释。

## 6. 候选实现路径

### 路径 A：OpenViking 统一后端（当前推荐）

特点：

- Wiki、报告、代码仓都进入 OpenViking 统一资源空间。
- opencode 只面对 OpenViking MCP + CodeAsk 平台 MCP 两类工具。
- CodeAsk 保留主数据权，OpenViking 作为派生索引和上下文数据库。
- AnythingLLM 只作为文档处理和检索治理参考。

适合：

- 当前 v1.0.4 之后的 opencode 主链路。
- 多特性、多代码仓、跨 Wiki / 报告 / 代码的复杂研发问答。
- 需要清晰行动轨迹、召回 URI、证据引用和同步状态的长期架构。

风险：

- 需要建设 CodeAsk -> OpenViking 同步适配层。
- 需要验证 OpenViking 对真实 CodeAsk Wiki、报告、代码仓的召回质量。
- 需要明确 OpenViking server 生命周期、索引重建、升级和数据目录策略。

### 路径 B：AnythingLLM + OpenViking 双后端

特点：

- AnythingLLM 负责 Wiki 文档 RAG。
- OpenViking 负责代码仓 RAG。
- CodeAsk 同时适配两个外部检索后端。

适合：

- 需要快速借用 AnythingLLM 文档处理能力做 spike。
- 需要单独比较 AnythingLLM 和 OpenViking 在 Wiki 文档上的召回质量。

风险：

- 两套 RAG 后端导致工具、URI、来源治理、排序和上下文预算复杂化。
- Feature / Report / Permission / Evidence 需要双向映射。
- opencode 的工具面会变复杂，模型更容易误用。
- 长期维护成本高。

当前不推荐作为主架构，只建议作为短期对比 spike。

### 路径 C：延续当前自研内核，局部吸收 LangChain / LanceDB

特点：

- 保留现有数据模型和 runtime 边界。
- 用 LangChain / LanceDB / 自研组件承载文本切分、向量化、召回和重排。
- 不依赖 OpenViking。

风险：

- 需要自研大量 OpenViking 已具备的上下文数据库、MCP、代码仓解析和层次检索能力。
- 和 opencode 主链路的结合不如 OpenViking 自然。
- 研发成本更高。

当前只作为备选，不作为优先方案。

## 7. 暂不在本阶段优先推进的事项

以下方向先记录，不作为当前近期实现优先级：

- 为了追求“更聪明”而提前强化会话收敛策略。
- 过早接入外部托管向量库。
- 把当前 Agent runtime 再次改造成新的重型状态机。
- 因引入框架而改写现有 Wiki、报告和附件模型。
- 同时上线 AnythingLLM 和 OpenViking 两套主 RAG runtime。
- 让 RAG 后端替模型判断“是否需要继续查代码”或“哪个特性一定相关”。

## 8. 建议版本拆分

当这条路线正式排入某个版本时，至少需要补齐：

1. 版本归属和目标范围。
2. OpenViking server 生命周期和数据目录策略。
3. CodeAsk -> OpenViking 同步状态表和失败恢复策略。
4. OpenViking URI 组织和 metadata schema。
5. Wiki、报告、代码仓导入、重建、删除、迁移、重新索引的生命周期设计。
6. opencode 同时接入 CodeAsk MCP 和 OpenViking MCP 的工具契约。
7. RAG 质量与 E2E 验收清单。

建议分三步推进：

### 8.1 Phase 0：OpenViking 可用性 Spike

- 启动 OpenViking server。
- 导入一个真实 CodeAsk Feature Wiki。
- 导入一个 verified report。
- 导入一个真实代码仓。
- 用 OpenViking MCP 完成 `find/search/read/list/grep/glob`。
- 验证 opencode 在同一会话里同时使用 CodeAsk MCP 和 OpenViking MCP。
- 记录召回质量、耗时、失败场景、行动轨迹展示要求。

### 8.2 Phase 1：OpenViking Sync Adapter

- 新增独立模块，例如 `src/codeask/rag/openviking_adapter/`。
- 维护 OpenViking server 连接、健康检查和状态展示。
- 新增同步状态表，记录 source object、viking URI、hash、status、indexed_at、error。
- Wiki / 报告 / 代码仓变更后触发同步或标记待同步。
- 提供手动重建和后台重建任务。

### 8.3 Phase 2：opencode 主链路接入

- 会话动态上下文注入 OpenViking 资源入口和工具使用原则。
- opencode 可通过 OpenViking MCP 查 Wiki / 报告 / 代码候选。
- 需要精确源码证据时仍通过 CodeAsk `prepare_worktree` 准备 live worktree。
- Agent 行动轨迹展示 OpenViking 工具调用、命中 URI、耗时、错误和证据引用。
- 保留 `workspace/wiki` 文件挂载作为兜底和人工排查入口。

## 9. 进入实现前的验收问题

正式开发前需要先回答：

1. OpenViking 是否支持 CodeAsk 目标环境的一键启动、健康检查、数据目录配置和升级兼容。
2. OpenViking 对本地路径、Git 仓库、本地目录仓库、私有仓库的支持边界是什么。
3. CodeAsk Wiki / Report 更新后，OpenViking 增量同步和删除是否可靠。
4. OpenViking MCP 工具参数是否足够简单，模型是否稳定调用。
5. OpenViking 检索结果能否回填到 CodeAsk 原始 Wiki node、report id、repo id、path、line range。
6. opencode 同时接入 CodeAsk MCP 和 OpenViking MCP 后，工具选择是否稳定。
7. OpenViking 的检索耗时、失败重试、索引任务状态能否进入 Agent 行动轨迹和后台日志。
8. 当 OpenViking 不可用时，CodeAsk 是否允许降级为 `workspace/wiki` 文件 grep + worktree grep。
9. 是否需要保留 AnythingLLM 文档处理 spike，用于和 OpenViking Wiki RAG 质量做对比。
