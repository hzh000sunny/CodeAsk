# OpenViking RAG 调研记录 2026-05-20

> 状态：Research
> 版本归属：待定
> 目的：记录 CodeAsk 评估 OpenViking 作为 Wiki RAG / 代码仓 RAG 统一后端时的真实调研结果、命令验证、风险和下一步验证项。

> Superseded：本调研已经沉淀为 [docs/v1.0.5/](../v1.0.5/) 的 PRD、SDD、Phase 0 spike 和验收清单。本文继续保留原始调研记录；版本实现与测试口径以 v1.0.5 文档为准。

## 1. 背景

CodeAsk 后续准备增强 Wiki RAG 和代码仓 RAG。当前候选方向是：

- 优先使用 OpenViking 作为统一 Context Database / RAG 后端。
- AnythingLLM 作为文档处理、切分、向量化和召回治理参考。
- opencode 在会话中通过 OpenViking MCP 自主检索知识，通过 CodeAsk MCP 准备真实代码 worktree。

用户明确要求：

- 尽可能使用已有成熟能力，不重新写一套低质量检索。
- CodeAsk 使用 `uv` 管理 Python 环境，部署方案也应优先使用 `uv`。
- 本阶段先调研和记录，不进入实现。

## 2. 本地环境

调研机器：

```text
repo: /home/hzh/workspace/CodeAsk
OpenViking wiki: /home/hzh/wiki/OpenViking-docs
OpenViking code: /home/hzh/wiki/OpenViking
```

实测环境：

```text
Python: 3.12.3
uv: 0.11.8
OpenViking PyPI latest: 0.3.17
```

本机工具状态：

```text
docker: 未安装
ollama: 未安装
openviking-server: 未全局安装
openviking / ov: 未全局安装
rustc / cargo: 未安装
cmake / gcc / g++: 已安装
```

结论：

- 当前环境适合验证 PyPI wheel + `uvx` 路径。
- 不适合把 Docker 或 Ollama 当作默认方案。
- 不应要求普通 CodeAsk 用户准备 Rust/Cargo；只有当 PyPI wheel 不可用、落到源码构建时，才需要进入 native build 排查。

## 3. 实测命令

### 3.1 OpenViking server help

命令：

```bash
uvx --from openviking openviking-server --help
```

结果：

- 可通过 `uvx` 直接拉取并运行 OpenViking。
- 实测安装 `133` 个依赖包。
- 当前 PyPI 包暴露的 `openviking-server` 参数包括：
  - `--host`
  - `--port`
  - `--config`
  - `--workers`
  - `--bot`
  - `--with-bot`
  - `--bot-port`
  - `--enable-bot-logging`
  - `--disable-bot-logging`
  - `--bot-log-dir`

观察：

- 文档里出现过 `openviking-server init` / `openviking-server doctor`，但当前 `--help` 没有展示这两个子命令。
- `uvx --from openviking openviking-server doctor --help` 实际进入了 doctor 检查流程，并因为缺少配置失败。
- 后续接入必须锁定 OpenViking 版本，并以真实 CLI 行为为准。

### 3.2 OpenViking CLI help

命令：

```bash
uvx --from openviking openviking --help
```

结果：CLI 可用，核心命令包括：

```text
add-resource
ls / tree / mkdir / rm / mv / stat / read
abstract / overview
find / search / grep / glob
session / add-memory
privacy / relations / link / unlink
export / backup / import / restore
tui / chat
wait / task / status / observer / health / config / version
admin / system / reindex
```

对 CodeAsk 最关键的命令：

- `add-resource`：导入 Wiki、报告、代码仓等资源。
- `find`：轻量语义检索。
- `search`：带 session 的上下文检索。
- `grep`：精确文本搜索。
- `glob`：按路径模式匹配。
- `read`：读取 L2 内容。
- `abstract` / `overview`：读取 L0 / L1 语义层。
- `wait` / `task` / `status` / `health`：索引任务和健康状态。

### 3.3 add-resource 参数

命令：

```bash
uvx --from openviking openviking add-resource --help
```

结果摘要：

```text
Usage: ov add-resource [OPTIONS] <PATH>

<PATH> 支持 local path 或 URL

关键参数：
--to
--parent
--parent-auto-create / -p
--reason
--instruction
--wait
--timeout
--strict
--ignore-dirs
--include
--exclude
--no-directly-upload-media
--watch-interval
--account
--user
--agent-id
--sudo
```

对 CodeAsk 的意义：

- CodeAsk 后台同步本地 Wiki 目录、本地报告目录、本地代码仓目录时，可以使用 CLI/SDK，不需要走 MCP。
- `--parent-auto-create` 可以对齐 CodeAsk 的 Feature 一级目录结构。
- `--include` / `--exclude` / `--ignore-dirs` 可以保留未来过滤规则入口。
- `--wait` 适合 E2E 或手动重建时使用；后台增量同步可异步执行并记录任务状态。

### 3.4 find / search 参数

命令：

```bash
uvx --from openviking openviking find --help
uvx --from openviking openviking search --help
```

`find` 关键参数：

```text
query
--uri
--node-limit
--threshold
--level
--after
--before
--account / --user / --agent-id
```

`search` 关键参数：

```text
query
--uri
--session-id
--node-limit
--threshold
--level
--after
--before
--account / --user / --agent-id
```

对 CodeAsk 的意义：

- `find` 适合普通语义召回。
- `search` 适合和当前会话上下文相关的深度召回，但需要后续验证 OpenViking session_id 是否应与 CodeAsk session_id 映射。
- `--level` 支持按 L0/L1/L2 层级过滤，未来可用于控制召回粗细。

### 3.5 grep / glob / read / ls 参数

命令：

```bash
uvx --from openviking openviking grep --help
uvx --from openviking openviking glob --help
uvx --from openviking openviking read --help
uvx --from openviking openviking list --help
```

结果摘要：

- `grep <PATTERN> --uri <URI> --ignore-case --node-limit --level-limit`
- `glob <PATTERN> --uri <URI> --node-limit`
- `read <URI>`
- `ls [URI] --recursive --simple --node-limit --abs-limit`

对 CodeAsk 的意义：

- OpenViking 能提供语义搜索之外的确定性检索。
- opencode 不必只依赖向量召回，可以先 `glob` / `grep` 精确定位，再 `read` 展开。
- 这符合 CodeAsk 用户要求的“让模型自己判断，而不是后端写死检索路径”。

## 4. MCP 能力

OpenViking server 内置 `/mcp` 端点，与 REST API 同进程、同端口，源码入口：

```text
/home/hzh/wiki/OpenViking/openviking/server/mcp_endpoint.py
```

当前源码暴露 10 个工具：

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

注意文档差异：

- `docs/zh/guides/06-mcp-integration.md` 里写的是 9 个工具，并包含 `store`。
- 当前源码实际是 10 个工具，并使用 `remember`，不是 `store`。
- 未来 CodeAsk 接入时必须按锁定版本的源码和实际 MCP tool list 验证，不应照抄文档。

对 CodeAsk 的建议：

- opencode 会话中可以直接挂 OpenViking `/mcp`。
- OpenViking 工具名保持原生，不额外加 `viking_` 前缀。
- CodeAsk 不重新封装 `search_wiki` / `search_reports` / `search_code`。
- CodeAsk 只负责在上下文中告诉模型：有哪些 OpenViking 根 URI、哪些报告是 verified、何时需要用 CodeAsk MCP 准备真实 worktree。

## 5. opencode 示例观察

OpenViking 仓库中存在两个 opencode 相关示例：

```text
/home/hzh/wiki/OpenViking/examples/opencode/plugin/
/home/hzh/wiki/OpenViking/examples/opencode-plugin/
```

### 5.1 早期 skill + CLI 示例

`examples/opencode/plugin/` 的模式：

- 自动安装 `skills/openviking/SKILL.md` 到 opencode skill 目录。
- 在系统提示中注入已索引仓库列表。
- 要求模型通过 shell 执行 `ov search`、`ov grep`、`ov glob`、`ov read`。
- 如果 OpenViking server 不健康，插件尝试执行 `openviking-server > /tmp/openviking.log 2>&1 &` 自动启动。
- repo 列表有 60 秒缓存。

对 CodeAsk 的参考价值：

- “先注入可检索仓库列表，再让模型自主选择搜索工具”这个思路是可借鉴的。
- “缩小 URI scope 后继续检索”的提示策略可借鉴。

不适合直接照搬的点：

- 使用 `~/.openviking` 和 `/tmp/openviking.log`，不符合 CodeAsk 数据目录规范。
- 让模型直接执行 shell `ov` 命令，会绕过 CodeAsk 的事件流、权限和审计。
- 自动启动 OpenViking 的逻辑应由 CodeAsk 后端进程管理，而不是 opencode 插件在会话中临时拉起。

### 5.2 新版 opencode plugin 示例

`examples/opencode-plugin/` 的模式：

- 不安装 skill。
- 通过 opencode tool hooks 暴露工具。
- 通过 HTTP API 调 OpenViking。
- 支持 repo search / grep / glob / read / browse / add / remove / queue status。
- 支持把 OpenCode session 映射到 OpenViking session。
- 支持自动记忆召回和 session commit。

工具名包括：

```text
memsearch
memread
membrowse
memcommit
memgrep
memglob
memadd
memremove
memqueue
```

对 CodeAsk 的参考价值：

- HTTP API 方式比 shell `ov` 更适合产品化。
- queue status、session map、自动 recall、工具返回结构都值得参考。
- `memremove` 要求 `confirm: true` 的删除保护可以借鉴。

不适合直接照搬的点：

- CodeAsk 已经有自己的 opencode runtime、MCP server、Agent 事件流和权限体系。
- 如果直接装这个插件，工具事件和权限会绕过 CodeAsk 后端，不利于统一审计。
- 它的 memory 能力和 CodeAsk 的 Feature/Wiki/Report/RAG 目标不完全一致。

### 5.3 CodeAsk 建议路线

第一版不直接安装 OpenViking opencode plugin，也不让模型执行 `ov` shell 命令作为主路径。

建议：

- CodeAsk 后端进程管理 OpenViking server。
- CodeAsk 后台 adapter 用 OpenViking CLI / SDK / HTTP API 同步本地资源。
- opencode 会话通过 OpenViking 原生 `/mcp` 使用 `find/search/read/list/grep/glob/health`。
- CodeAsk 自己展示 OpenViking 工具事件、URI、耗时、错误和证据。
- OpenViking 示例插件只作为提示词、工具命名、queue 状态和错误处理参考。

## 6. 本地路径、Wiki 和代码仓导入

OpenViking 的资源导入有两条路径：

1. CLI / SDK：
   - 支持本地文件、本地目录、URL、Git URL。
   - 本地目录扫描遵守 `.gitignore`。
   - 适合 CodeAsk 后台同步 Wiki / 报告 / 本地代码仓。

2. REST / MCP：
   - 远端 URL / Git URL 可以直接传 `path`。
   - 本地文件需要先 `temp_upload`，再调用 `add_resource`。
   - 本地目录裸 HTTP 需要先 zip 再上传。
   - MCP `add_resource` 当前只支持 remote URL / Git URL，不支持本地 path。

因此 CodeAsk 的设计应是：

```text
CodeAsk 后台同步：
  使用 SDK / CLI / REST temp_upload 导入本地 Wiki、报告、代码仓

opencode 会话中：
  使用 OpenViking MCP 检索 / 读取已经同步好的资源
  不让模型通过 MCP 导入 CodeAsk 本地路径
```

这可以避免把宿主机本地路径暴露给模型，也避免 MCP local path 限制。

## 7. 代码仓解析观察

源码入口：

```text
/home/hzh/wiki/OpenViking/openviking/parse/parsers/code/code.py
/home/hzh/wiki/OpenViking/openviking/parse/parsers/upload_utils.py
/home/hzh/wiki/OpenViking/openviking_cli/utils/config/parser_config.py
```

关键观察：

- `CodeRepositoryParser` 处理 Git / Zip 代码仓。
- 网络获取在 Accessor 层完成，Parser 本身只接收已经准备好的本地目录。
- Git 仓库路径会被浅克隆，上传到 VikingFS temp URI。
- 代码仓解析保留目录结构，不在 parser 阶段做 LLM 生成。
- 上传目录时会应用 `.gitignore`，并跳过 `.git`、`node_modules` 等常见无效目录。
- 文件上传默认最大文件大小是 `10 MiB`。
- 目录上传并发是 `8`。
- `source_meta` 中会保留 `repo_name`、`repo_ref`、`repo_commit`。
- 如果 `repo_name` 缺失，会尝试从原始 GitHub / GitLab URL 提取 `org/repo`。
- 如果 source_path 退化为本地临时路径，后续 TreeBuilder 的 repo name 解析可能失败；这说明 CodeAsk 同步时需要尽量给 OpenViking 明确、稳定的 repo source metadata。

代码解析配置支持：

```text
code_summary_mode: ast | llm | ast_llm，默认 ast
extract_functions: true
extract_classes: true
extract_imports: true
include_comments: true
max_token_limit: 50000
truncation_strategy: head | tail | balanced，默认 head
```

对 CodeAsk 的影响：

- 本地目录仓库可以作为同步来源，但 CodeAsk 必须维护自己的 repo_id / repo_name / ref / commit 映射，不应完全依赖 OpenViking 从路径猜。
- 对 Git URL 仓库，OpenViking 自身能处理 URL 和 metadata；但 CodeAsk 仍应保留当前的 worktree 准备机制，确保回答源码证据时读的是可控版本。
- 对本地目录仓库，建议同步时写入 `reason` / `instruction` 或 metadata 文件，明确这是哪个 CodeAsk repo、归属哪些 feature、当前 ref / commit / snapshot 是什么。
- 大仓库同步前要配置 `ignore_dirs`、`include`、`exclude`，避免把构建产物、依赖目录、二进制资产送入 RAG。

## 8. Embedding 与 VLM

### 8.1 Embedding

OpenViking 的语义检索需要 embedding。当前配置支持：

```text
openai
azure
volcengine
vikingdb
jina
ollama
gemini
voyage
dashscope
minimax
cohere
litellm
local
```

可选方案：

- 云端 / 私有网关 embedding：质量和稳定性较好，但是否免费取决于用户服务。
- OpenAI 兼容 embedding：必要时设置 `encoding_format: "float"`，兼容不支持 base64 embedding payload 的网关。
- Ollama embedding：本地免费，但需要单独安装 Ollama 和模型。
- OpenViking local embedding：默认 `bge-small-zh-v1.5-f16`，维度 512，依赖 `openviking[local-embed]` 和 `llama-cpp-python`，模型默认来自 HuggingFace。

第一版建议：

- 默认支持用户配置远程 / 私有 embedding。
- 本地 embedding 作为可选安装，不默认启用。
- 离线环境需要提供模型缓存导入说明。

### 8.2 VLM / LLM

OpenViking 的 VLM 用于 L0 Abstract / L1 Overview 语义提取。

结论：

- 对最小文本检索来说，VLM 可以不是硬前置；缺失时会退化为直接基于内容的较弱 L0/L1。
- 对生产质量、复杂 Wiki、代码仓导航、图片/PDF/多模态材料来说，VLM 很重要。
- 未来可考虑复用 CodeAsk 全局 LLM 配置生成 OpenViking `vlm` 配置，但不能简单拼接，需要单独处理 provider 协议、base url、api key、reasoning 参数和失败降级。

## 9. 对 CodeAsk 的候选落地方式

### 9.1 模块边界

未来新增模块建议：

```text
src/codeask/rag/openviking/
├── config.py
├── process.py
├── client.py
├── sync.py
├── uri.py
├── models.py
└── health.py
```

边界：

- 该模块只负责 OpenViking 兼容。
- 不和 opencode 模块抽公共 agent runtime。
- 不接管 CodeAsk 的 Feature / Wiki / Report / Repo 主数据。

### 9.2 同步方式

CodeAsk 维护主数据，OpenViking 维护派生索引。

建议同步对象：

```text
Feature Wiki -> viking://resources/codeask/features/<feature_slug>/knowledge-base/
Verified Reports -> viking://resources/codeask/features/<feature_slug>/problem-reports/verified/
Draft Reports -> viking://resources/codeask/features/<feature_slug>/problem-reports/drafts/
Repo Index -> viking://resources/codeask/features/<feature_slug>/repos.md
Code Repo RAG -> viking://resources/codeask/repos/<repo_slug>/
```

同步状态表应记录：

```text
source_type
source_id
source_hash
viking_uri
status
last_synced_at
last_indexed_at
error
task_id
```

### 9.3 会话上下文

opencode 动态上下文应告诉模型：

- OpenViking 中有 CodeAsk 的 Wiki、问题报告和代码仓 RAG。
- verified report 权重高，draft report 只能作为弱参考。
- 只有报错、场景、根因高度一致时，才能把历史报告当作同一问题。
- OpenViking 召回代码候选后，如果要读取真实源码证据，必须调用 CodeAsk `codeask_prepare_worktree`。
- `codeask_prepare_worktree` 返回 session workspace 相对路径后，再用 opencode 原生 `grep/read/glob` 读取真实文件。

## 10. 风险与待验证项

正式进入版本前必须验证：

1. OpenViking server 在 CodeAsk `uv` 环境中的启动、重启、日志、健康检查和异常恢复。
2. PyPI wheel 在目标部署环境是否稳定；源码构建是否会要求 Rust/Cargo。
3. CodeAsk 本地 Wiki 目录导入质量、耗时和增量更新行为。
4. CodeAsk 代码仓导入质量、`.gitignore` 行为、索引耗时和磁盘占用。
5. OpenViking MCP 在 opencode 中的真实工具调用稳定性。
6. `find` / `search` / `grep` / `glob` / `read` 返回结果能否映射回 CodeAsk 原始对象。
7. OpenViking 不可用时，CodeAsk 是否降级到当前 workspace 文件检索能力。
8. local embedding 在中文文档和代码场景下的质量与性能。
9. VLM 缺失时，L0/L1 质量是否足够支撑第一版使用。

## 11. 当前结论

当前调研足以支撑继续做 OpenViking 方案设计，但还不足以直接开发完整 RAG：

- OpenViking 适合作为统一 Wiki / 报告 / 代码仓 RAG 后端。
- CodeAsk 应通过 `uv` 可选依赖或独立 venv 管理 OpenViking，不使用 Docker 作为默认路径。
- CodeAsk 后台负责本地资源同步，opencode 只使用 OpenViking MCP 查询已经同步好的资源。
- OpenViking MCP 工具面满足第一版需求，但文档和源码存在差异，需要锁版本后做真实 MCP tool list 测试。
- Embedding 是核心依赖；本地免费 embedding 可行但需要额外 native 依赖和模型缓存策略。
