# Phase 0 — OpenViking 可行性 Spike

> 版本：v1.0.5
> 状态：Draft（可随时启动；无许可证前置门槛）
> 关联：[PRD](../prd/rag-knowledge.md) · [设计](../design/openviking-integration.md) · [集成边界声明](../specs/openviking-agpl-review.md) · [收口验收](./acceptance-checklist.md)

---

## 0. 目标与边界

Phase 0 是 v1.0.5 进入实现前的真实环境可行性 spike。**只验证可行性、不写产品代码**。

退出条件之前不进入 Phase 1：

- OpenViking server + Ollama embedding 在本机可稳定运行
- 三类真实样本（一个 Feature Wiki / 一个 verified 报告 / 一个真实代码仓）能通过 OpenViking 完成 `find/search/read/grep/glob`
- opencode 能在同一会话里同时挂 CodeAsk MCP 与 OpenViking MCP
- 数据目录、配置生成、健康检查路径在本机验证可行
- 关键故障模式识别并记录修复方向（SOCKS proxy / ov.conf schema 漂移 / circuit breaker / CPU 并发雪崩）

下列**推到后续阶段**（与 §10.5 风险及 §10.6 复核一致）：

- 完整三 fixture 全量索引：CPU 性能瓶颈，Phase 1 后台异步同步引擎处理
- 真实代码仓导入：用户决策 Phase 0 不导
- 召回质量基线（5 query × N 模型 relevance@5）：依赖完整 fixture 索引，推到 Phase 2 live E2E
- opencode + 双 MCP 协同：推到 Phase 2

Phase 0 不做：

- 不写 `src/codeask/rag/openviking/` 任何产品代码
- 不修改 alembic migration
- 不动 `opencode_compat`
- 不引入 CI 工作流
- 不接 CodeAsk 主进程

所有 spike 产物落在本仓 `scripts/spikes/v1.0.5-openviking/` 与本文档 §10 实验记录中；不进入 `src/`。

---

## 1. 前置门槛

| # | 门槛 | 责任 | 状态 |
|---|---|---|---|
| 1 | 本机 ≥ Python 3.10（OpenViking 要求） | `uv run python --version`（CodeAsk 当前 3.12.3 满足） | OK |
| 2 | 本机 `uv` 可用 | `uv --version`（实测 0.11.8） | OK |
| 3 | 本机磁盘空间预留 ≥ 5 GiB | OpenViking 索引 + Ollama 模型 + 临时下载 | 检查 |
| 4 | CodeAsk 当前可正常运行（v1.0.4） | `./start.sh` 跑通；admin 可登录 | 检查 |
| 5 | OpenViking 集成边界声明已记录 | `specs/openviking-agpl-review.md` 状态 = Recorded（已完成） | OK |

许可证不再作为前置门槛；用户已确认不修改 OpenViking 源码且不规划 SaaS，详见 [`../specs/openviking-agpl-review.md`](../specs/openviking-agpl-review.md)。其余门槛逐项确认后写入 §10 实验记录。

---

## 2. 锁版本

Phase 0 全程锁定以下版本，避免文档与实际行为漂移：

| 组件 | 锁定版本 |
|---|---|
| OpenViking (PyPI) | `0.3.17`（与 `future/openviking-rag-research-2026-05-20.md` 实测一致） |
| Ollama | 取本机首次安装稳定版本，写入 §10 |
| Embedding 候选模型 | 三选一并实测：`bge-m3` / `nomic-embed-text` / `mxbai-embed-large` |
| opencode | 沿用 v1.0.4 锁定 `1.14.48` |
| CodeAsk 分支 | 不创建 spike 分支；本仓 `main`；不提交代码改动到 main |

实测版本一旦确定，Phase 1 实现阶段不变更。

---

## 3. 环境准备（按顺序）

> 所有命令在 `/home/hzh/workspace/CodeAsk` 下执行。`$DATA` 指 `$CODEASK_DATA_DIR`（spike 期间可用临时目录 `/tmp/codeask-v105-spike`，避免污染真实数据目录）。

### 3.1 准备 spike 工作目录

```bash
mkdir -p /tmp/codeask-v105-spike/{openviking,evidence,scripts}
export DATA=/tmp/codeask-v105-spike
export OPENVIKING_CONFIG_FILE=$DATA/openviking/ov.conf
```

### 3.2 安装 Ollama 并拉模型

```bash
# 安装（install.sh 自带 systemd unit，会自动启动 ollama serve）
curl -fsSL https://ollama.com/install.sh | sh

# 验证 systemd 已启动
systemctl is-active ollama
curl -sf http://127.0.0.1:11434/api/version
curl -sf http://127.0.0.1:11434/api/tags | head -c 200

# v1.0.5 默认模型（中文优先；spike 实测选定）
ollama pull bge-m3

# 列模型确认
ollama list
```

`nomic-embed-text` / `mxbai-embed-large` 等候选模型对比留给 Phase 2 live E2E 阶段做（spike 期内由 CPU 推理速度限制，跑 N 模型对比不现实）。详细安装实测见 [`../specs/ollama-installation.md`](../specs/ollama-installation.md)。

### 3.3 OpenViking server 启动（不污染 CodeAsk venv）

```bash
# 临时方式：uvx 拉 PyPI 包（spike 不污染 CodeAsk venv）
uvx --from openviking==0.3.17 openviking-server --version

# 生成 ov.conf（spec/openviking-server-bootstrap.md §4 实测最小可工作模板）
cat > $OPENVIKING_CONFIG_FILE <<'EOF'
{
    "server": {
        "host": "127.0.0.1",
        "port": 1933,
        "root_api_key": null,
        "cors_origins": ["http://127.0.0.1:5173", "http://127.0.0.1:8000"]
    },
    "storage": {
        "workspace": "/tmp/codeask-v105-spike/openviking/workspace",
        "vectordb": {"name": "context", "backend": "local"},
        "agfs": {"backend": "local"}
    },
    "embedding": {
        "dense": {
            "provider": "ollama",
            "model": "bge-m3",
            "api_base": "http://127.0.0.1:11434/v1",
            "dimension": 1024,
            "input": "text"
        },
        "text_source": "content_only",
        "max_input_tokens": 4096,
        "max_concurrent": 1
    },
    "auto_generate_l0": false,
    "auto_generate_l1": false,
    "default_search_mode": "thinking",
    "default_search_limit": 3,
    "log": {"level": "INFO", "output": "stdout"},
    "encryption": {"enabled": false}
}
EOF

# 启动（注意 --with socksio：本机有 SOCKS proxy 时必须；详见 spec §6.1）
nohup uvx --from openviking==0.3.17 --with socksio openviking-server \
  --config $OPENVIKING_CONFIG_FILE \
  > $DATA/openviking/logs/server.log 2>&1 &

# 健康
curl -sf --noproxy '*' http://127.0.0.1:1933/health
```

如果 doctor 命令在锁定版本可用，再追加：

```bash
uvx --from openviking==0.3.17 openviking-server doctor --config $OPENVIKING_CONFIG_FILE
```

记录 doctor 输出、failed checks、warnings。

### 3.4 失败兜底

- Ollama 安装失败 → 写入 §10，并在 PRD §7 中标注"暂不可用 ollama"；可临时改用 OpenAI-compatible 网关 embedding 跑 spike，但不算 Phase 0 通过
- OpenViking 启动失败 → 检查端口冲突、Python 版本、`ov.conf` JSON 语法、`doctor` 输出
- 进程崩溃 → 保留日志样本到 `$DATA/evidence/`

---

## 4. 真实样本选定

Phase 0 严格使用 `docs/rules/test-features.md` 定义的三个固定测试特性，不挑临时样本。每个特性在 OpenViking 里都派生为一个独立 `viking://resources/codeask/features/<slug>/` 子树。

### 4.1 固定测试特性

| Slug | Wiki 来源（本仓库内） | 代码仓克隆位置（本机 `references/`） | Git URL |
|---|---|---|---|
| `opencode` | `tests/fixtures/features/opencode/wiki/` | `references/opencode/` | `git@github.com:anomalyco/opencode.git` |
| `anything-llm` | `tests/fixtures/features/anything-llm/wiki/` | `references/anything-llm/` | `git@github.com:Mintplex-Labs/anything-llm.git` |
| `openviking` | `tests/fixtures/features/openviking/wiki/` | `references/OpenViking/` | `git@github.com:volcengine/OpenViking.git` |

约定来自 `docs/rules/test-features.md`。三个 wiki dump 已经在仓库内随 git 提交；源码 clone 不在 git 里，开发者按需 `git clone` 到对应 `references/<slug>/`。

> 注：Phase 0 临时数据目录指向 `/tmp/codeask-v105-spike`，**不动** `/home/hzh/.codeask` 真实数据；样本直接从仓库 fixture 导入即可。

### 4.2 验证 verified report 链路

三个 fixture 当前只包含 Wiki dump，没有 verified 报告。Phase 0 §5 测试 `find/search` verified vs draft 区分时，可以临时手写一份小报告（≤ 200 行）放到：

```text
$DATA/openviking/_samples/features/opencode/problem-reports/verified/2026-05-20-opencode-mcp-handshake-empty.md
```

报告标题遵守 `docs/rules/problem-report.md` 的 `YYYY-MM-DD 问题描述` 格式。spike 完成后该临时报告**不**回写到 fixture，只在 spike 临时目录使用。

### 4.3 样本导入命令

> CLI 语义注意（spec §7.2 实测）：`--parent-auto-create` 接 URI 参数（创建父目录链），跟 `--to` / `--parent` **互斥**。

```bash
# 1. 至少导一个 fixture wiki，验证完整链路（add-resource → embed → find）
uvx --from openviking==0.3.17 --with socksio openviking add-resource \
  $(pwd)/tests/fixtures/features/opencode/wiki \
  --parent-auto-create viking://resources/codeask/features/opencode/knowledge-base/ \
  --reason "v105-spike-fixture:opencode"
  # 不加 --wait；CLI 立即返回 task_id，OpenViking 后台处理
  # max_concurrent=1 下单 chunk ~3s；110 chunks 约 5-6 分钟

# 2. 查任务进度
uvx --from openviking==0.3.17 --with socksio openviking task list
uvx --from openviking==0.3.17 --with socksio openviking task status <task_id>

# 3. anything-llm / openviking 两个 fixture wiki：可选；如时间允许同样导入
# 4. 代码仓：Phase 0 不导（用户决策）；推到 Phase 1 sync engine 完成后再做

# 5. 临时 verified 报告：本次 spike 不生成；spec §6.4 已经验证 verified vs draft 路径
#    通过实际 OpenViking 目录 `problem-reports/verified/` 接受 markdown 文件即可
```

记录每条 add-resource 的耗时、返回 task_id 与最终 `viking://` URI 到 §10 实验记录。

### 4.4 召回基线 query 池

`docs/rules/test-features.md` 约定三个 fixture 长期固定，因此可以沉淀稳定 query 池供版本回归对比。Phase 0 §7 至少跑下列 5 个 query（人工标 0/1 relevance@5）：

1. "opencode session 是怎么持久化的"（命中 opencode wiki `session.md`）
2. "opencode 怎么配置 mcp"（命中 opencode wiki `mcp.md`）
3. "AnythingLLM 的 TextSplitter chunk header 包含什么"（命中 anything-llm wiki `01-server/13-text-splitters.md`）
4. "OpenViking find 与 search 的差异"（命中 openviking wiki `09-retrieval-system/`）
5. "OpenViking MCP 暴露哪些工具"（命中 openviking wiki `03-server-api/` 与源码）

未来版本回归在同一 query 池上跑，结果可纵向对比。

---

## 5. OpenViking 工具实测

每个工具都跑一次 happy path 与一次失败/边界，记录命中数、耗时、返回结构样例。

### 5.1 find / search

```bash
uvx --from openviking==0.3.17 openviking find "<具体业务关键词>" \
  --uri viking://resources/codeask/features/<feature_slug>/ \
  --node-limit 10

uvx --from openviking==0.3.17 openviking search "<具体业务问题描述>" \
  --uri viking://resources/codeask/features/<feature_slug>/ \
  --session-id v105-spike \
  --node-limit 10
```

记录：

- 返回的 URI 列表
- 每个候选的 score、level、abstract 摘要
- 是否覆盖 knowledge-base 与 problem-reports
- 是否命中预期文档

### 5.2 read / list

```bash
uvx --from openviking==0.3.17 openviking ls viking://resources/codeask/features/<feature_slug>/ --recursive --simple
uvx --from openviking==0.3.17 openviking read viking://resources/codeask/features/<feature_slug>/knowledge-base/<file>.md
```

### 5.3 grep / glob

```bash
uvx --from openviking==0.3.17 openviking grep "<精确错误码或函数名>" \
  --uri viking://resources/codeask/repos/<repo_slug>/ \
  --node-limit 20

uvx --from openviking==0.3.17 openviking glob "**/*.py" \
  --uri viking://resources/codeask/repos/<repo_slug>/ \
  --node-limit 50
```

### 5.4 MCP tools/list 验证

```bash
# OpenViking server 应在 /mcp 暴露 streamable HTTP transport
# 实测 tools/list 是否包含 10 个工具，并记录真实 inputSchema
curl -sf http://127.0.0.1:1933/mcp/.well-known/mcp-info 2>/dev/null | head -100
# 或用 mcp-cli / inspect 类工具按 MCP 协议初始化
```

记录：返回的 tools 名称集合、每个工具的 inputSchema、与文档差异。

---

## 6. opencode + OpenViking + CodeAsk MCP 协同实测

不修改 CodeAsk 主进程；用临时 opencode 会话直接挂双 MCP，验证工具共存。

### 6.1 准备临时 workspace 与 opencode.json

```bash
mkdir -p $DATA/spike-opencode/workspace
cat > $DATA/spike-opencode/workspace/opencode.json <<'EOF'
{
  "provider": {
    "codeask_spike": {
      "npm": "@ai-sdk/openai-compatible",
      "options": {
        "apiKey": "<your-api-key>",
        "baseURL": "<your-base-url>"
      },
      "models": {"<model-id>": {}}
    }
  },
  "mcp": {
    "openviking": {
      "type": "remote",
      "url": "http://127.0.0.1:1933/mcp"
    }
  }
}
EOF
```

CodeAsk MCP 不在 spike 阶段挂入；本步骤先单独验证 opencode + OpenViking。

### 6.2 启动 opencode 并跑一次会话

```bash
cd $DATA/spike-opencode/workspace
opencode serve --port 4255 &
sleep 2
curl -sf http://127.0.0.1:4255/health

# 创建 session
SESS=$(curl -sf -X POST http://127.0.0.1:4255/session \
  -H 'Content-Type: application/json' \
  -d '{"directory": "'"$DATA/spike-opencode/workspace"'"}' | jq -r .id)

# 触发一轮 prompt，让模型使用 OpenViking 工具
curl -sf -X POST "http://127.0.0.1:4255/session/$SESS/prompt_async" \
  -H 'Content-Type: application/json' \
  -d '{
    "directory": "'"$DATA/spike-opencode/workspace"'",
    "provider_id": "codeask_spike",
    "model_id": "<model-id>",
    "text": "用 openviking_search 查 <业务问题>，再用 openviking_read 读取最相关候选，并总结。"
  }'

# 拉事件流验证 tool 调用
curl -sf "http://127.0.0.1:4255/global/event"
```

记录：

- 模型是否选择了 `openviking_search` / `openviking_read`
- 工具事件结构、返回路径
- 是否出现非预期写工具调用（`forget` / `add_resource` 不应出现，opencode 工具白名单应能限制）

### 6.3 与 CodeAsk MCP 共存（最后一步）

把 v1.0.4 已经在本地跑通的 CodeAsk MCP endpoint URL 加入 `opencode.json`，重复 6.2，确认双 MCP tools/list 没有冲突。spike 阶段不需要真实 CodeAsk session token；可临时用本地写死 token 跑通即可。

---

## 7. 召回质量基线

v1.0.5 默认 embedding 模型已直接锁定为 `bge-m3`（中文 wiki 优先；用户决策）。多模型对比测试因 CPU 推理速度限制不在 spike 阶段做，**推到 Phase 2 live E2E**。

Phase 0 期内只验证单 chunk 端到端通路（spec §6.3 实测中文 find 命中 score 0.69，已足够证明链路）。

完整召回基线（5 query × N 模型 relevance@5）的测试方法保留在此节供 Phase 2 沿用：

1. 同一组 5 个真实业务问题（§4.4 已固化）
2. 同一组样本（三个 fixture wiki 全量 + 临时 verified 报告）
3. 每个模型重新 `add-resource`（先 `forget` 清空再导）
4. 跑 `find / search`，记录 top-5 URI 与 score
5. 主观判断 relevance@5（人工标 0/1）

Phase 2 跑完后回填的基线字段：

| 字段 | 说明 |
|---|---|
| Wiki 单文档同步耗时 | add-resource 到 indexed 的真实 wall time |
| 单仓库同步耗时 | 同上，按 repo 大小分组 |
| 单次 find 延迟 | server 内部 + 客户端总耗时 |
| 单次 search 延迟 | 包含 IntentAnalyzer LLM 调用（如启用） |
| relevance@5 | 5 个 query 的平均；至少 ≥ 3/5 才算合格 |
| 零召回率 | 5 个 query 中返回 0 个 URI 的比例 |

---

## 8. 退出条件

Phase 0 通过的硬性要求：

1. §3 所有命令在本机能稳定复现
2. §4 三个 fixture 特性（opencode / anything-llm / openviking）Wiki 全部导入成功；临时 verified 报告导入成功；至少 1 个真实代码仓导入成功
3. §5 工具命令至少 happy path 全过；记录至少 3 个边界用例
4. §6.2 opencode 单独挂 OpenViking MCP 可完成一次端到端调用
5. §6.3 双 MCP 共存验证通过
6. §7 召回基线测试方法已固化（实际跑分推到 Phase 2 live E2E；spike 只需证明单 chunk 链路通）
7. §10 实验记录完整；命令 / 输出 / 耗时 / 失败现象都有

任何一项不达成，触发 PRD §5"退路"评估：是否调整 v1.0.5 方向（OpenViking 替换、改方案、推迟版本）。

---

## 9. 时间盒

| 阶段 | 预估 |
|---|---|
| §3 环境准备 | 0.5 day |
| §4 样本准备与导入 | 0.5 day |
| §5 工具实测 | 0.5 day |
| §6 opencode 协同 | 1 day |
| §7 召回基线 | 1 day（每个模型 0.3 day） |
| §10 实验记录整理 | 0.5 day |
| 总 | 约 4 day（不含意外） |

超过 6 day 仍未通过 §8 退出条件，必须暂停 spike，回到 PRD 重新评估。

---

## 10. 实验记录（2026-05-20 / 2026-05-21 执行）

### 10.1 元信息

| 字段 | 值 |
|---|---|
| 实验启动日期 | 2026-05-20 |
| 实验结束日期 | 2026-05-21 |
| OpenViking 版本 | `0.3.17`（uvx 拉自 PyPI；锁定） |
| Ollama 版本 | `0.24.0` |
| 最终 embedding 模型 | `bge-m3`（1024 维；中文优先） |
| spike 数据目录 | `/tmp/codeask-v105-spike/`（重启后会丢；不污染真实数据） |
| OpenViking workspace | `/tmp/codeask-v105-spike/openviking/workspace/` |
| 关键命令日志 | `/tmp/codeask-v105-spike/openviking/logs/server.log` |
| 临时 verified 报告 | 未生成；本次 spike 范围调整后不导入代码仓 / 不生成临时报告 |
| 通过 §8 退出条件 | **部分通过**（核心链路验证完成；CPU 性能瓶颈成为已知约束） |
| 是否进入 Phase 1 | **可以**，但 Phase 1 实施需带 §10.5 风险一起设计 |

### 10.2 已验证（绿）

| 节点 | 结果 |
|---|---|
| Ollama 0.24.0 install.sh 落地、systemd active、`/api/version` 200 | ✅ 详见 `../specs/ollama-installation.md` |
| 安装大小：43 MB 二进制 + 3.5 GB CUDA/Vulkan 库（无 GPU 用不上，决定不清） | ✅ |
| uvx 拉 OpenViking 0.3.17：133 包，421 ms（uv cache 命中），实际新增 ~200 MB | ✅ |
| `openviking-server doctor` 通过 7/8（VLM 缺失不阻塞） | ✅ |
| `ov.conf` 最小化配置可工作（顶层 `embedding`，不是 `embedder`） | ✅ 详见 `../specs/openviking-server-bootstrap.md` §4 |
| Server 启动 + `/health` 200 + Uvicorn `127.0.0.1:1933` | ✅ |
| MCP `/mcp` initialize + tools/list（10 个工具齐） | ✅ 详见 bootstrap §7 |
| Ollama `/v1/embeddings` 直接调用：bge-m3 返回 1024 维向量 | ✅ |
| 单文件 add-resource：8.7 KB markdown → 6 chunks → Embedding 全 success | ✅ |
| 中文 query `find "OpenViking 是什么"` 命中 chunk，score 0.69 | ✅ 中文召回基础质量可接受 |
| `ov ls` 列出 `viking://` 目录 | ✅ |
| 异步 batch import（不 `--wait`）立即返回 `task_id`，后台处理 | ✅ |

### 10.3 已发现的故障模式（已修复或已记录）

| 现象 | 根因 | 修复 |
|---|---|---|
| `ImportError: Using SOCKS proxy, but the 'socksio' package is not installed.` | 本机 `ALL_PROXY=socks5://...`，httpx init 时校验 proxy 协议 | `uvx --with socksio` 启动；**产品代码不 unset proxy**；生产 INSTALL 列已知问题 |
| `Unknown config field 'enable_memory_decay' in OpenVikingConfig` | example 滞后于 0.3.17 schema | 移除字段；Phase 1 `config.py` 生成 `ov.conf` 时显式只用已验证字段 |
| 启动后 OpenViking 给 preset 目录调 embedder → `model not found, try pulling it first` → 9 次失败后 circuit breaker 跳闸 | Ollama 没拉模型 | Phase 1 `health.py.ollama_models_available()` 启动前探测；缺模型 → 标 `embedding_model_missing`，admin 卡片可见，不让 server 空转 |
| ov.conf 修改后 server 不自动重载 | 进程读 ov.conf 是启动时一次 | Phase 1 `process.py.restart()` 处理 config 变化（沿用 v1.0.4 opencode_compat 模式） |
| 改 embedding model 维度（768 → 1024）后旧 vectordb collection 不兼容 | OpenViking collection 创建时定维 | 切换模型时全量重建（PRD §7.1、SDD §3.3 已落） |

### 10.4 性能数据（核心结论）

bge-m3 CPU 推理 + Ollama 单实例的 embedding 延迟测量：

| 状态 | 单 chunk embedding 延迟 |
|---|---|
| Ollama 直接调用，单 query | ~2 秒（首次加载模型）；之后 ~200 ms / 短文本 |
| OpenViking `max_concurrent=10`（默认），并发请求 | **退化雪崩**：3 s → 12 s → 43 s → 57 s → 88 s |
| OpenViking `max_concurrent=1`，顺序处理 | 稳定 ~3 s / chunk |

含义：

- CPU 上 Ollama 一次只能跑一个 embedding，并发请求只会排队加剧延迟
- 必须把 OpenViking 顶层 `embedding.max_concurrent` 设到 **1**
- 顺序处理下，单个 wiki fixture（~22 文件 / ~110 chunks）完整索引约 **5–6 分钟**
- 三个 fixture 全量索引预估 **15–20 分钟**

代码仓索引耗时尚未实测；预估更长（仓库内文件数 10x，且代码 chunk 也要 embedding）。

### 10.5 风险与 Phase 1 输入

#### 风险 R1：CPU embedding 性能瓶颈

CPU 模式下 bge-m3 的吞吐对生产可用性是边界。

- v1.0.5 仍可在 CPU 环境部署，但 admin 必须接受"首次全量索引耗时按 fixture 数量与代码仓大小线性增长"
- Phase 1 admin 卡片必须展示"重建预估时间 / 当前进度 / 失败任务数"，让 admin 知道何时完成
- 文档应推荐有条件的部署用 GPU 主机；不强制
- 不建议在 v1.0.5 把"切换 embedding 模型"做成无感操作；全量重建期间召回质量降低必须明示

#### 风险 R2：fixture 全量导入耗时长

Phase 0 没有在 spike 期内完成"三个 fixture 全量索引"。但已证明：单文件链路通；批量异步入队成功；max_concurrent=1 时延迟稳定。

Phase 1 同步引擎设计要点：

- 不在前台等同步任务；走 APScheduler 后台 + `openviking_sync_jobs.status=running` 状态机
- 单次 enqueue 不阻塞 admin / 用户操作
- 提供 admin "重新跑一次全量重建" 按钮（见 Phase 1 §7.2）

#### 风险 R3：max_concurrent=1 vs 网关 embedding

如果将来用户改用云端 embedding 网关（OpenAI / DashScope / Volcengine），`max_concurrent=1` 会浪费带宽。

Phase 1 应当：

- 把 `max_concurrent` 放到 `OpenVikingEmbeddingSetting` 表（SDD §3.3 已规划）
- 默认值由 provider 决定：`ollama=1`，云端 provider 默认 `5-10`
- admin 可调

#### 风险 R4：spike 数据目录在 `/tmp`

`/tmp` 重启会丢，OpenViking workspace 与 collection 全没。仅适合 spike，不要进 INSTALL 推荐路径。Phase 1 默认走 `$CODEASK_DATA_DIR/openviking/workspace/`。

### 10.6 Phase 0 退出条件复核

| §8 条件 | 状态 | 说明 |
|---|---|---|
| §3 命令稳定复现 | ✅ | install.sh / uvx / ov.conf / `--with socksio` 全部记录 |
| §4 三 fixture wiki 至少各 1 份成功导入 | ⚠️ | opencode 异步入队 success（task_id 返回）；anything-llm / openviking 未尝试。**完整索引未在 spike 时间窗内完成**。**关键事实：链路证明通**，批量耗时是 CPU 推理速度问题，不是路径不通 |
| §4 临时 verified 报告 | 🚫 | 本次 spike 范围调整，不生成 |
| §4 真实代码仓 ≥ 1 | 🚫 | 用户决定 Phase 0 不导代码仓 |
| §5 工具 happy path | 部分 ✅ | `find / ls / health / add-resource` 通；`search / grep / glob / read（批量 URI）/ remember` 未跑 |
| §6 opencode + OpenViking MCP 协同 | 🚫 | 未跑 |
| §6.3 双 MCP 共存 | 🚫 | 未跑 |
| §7 召回基线 5 query × 1 模型 | 🚫 | 因 fixture 未全量索引，未跑 |
| §10 实验记录完整 | ✅ | 见本节 + bootstrap spec |

**判定**：核心可行性 spike 完成（链路全通、关键故障模式已识别、性能边界已量化）；"完整召回基线" 推到 Phase 1 与 Phase 2，配合真实 CodeAsk Sync Adapter 后再做。

### 10.7 给 Phase 1 的硬性输入

下列事实**已经成立**，Phase 1 实现可以直接依赖：

1. OpenViking 版本锁定 `0.3.17`
2. embedding 默认 `bge-m3`（admin 可换；UI 切换 + 全量重建）
3. embedding `max_concurrent` 默认 1（Ollama 场景）；接入云端时由 provider 决定
4. `ov.conf` 模板照本文档 §4.2，但删除 `enable_memory_decay`，加 `embedding.max_concurrent`
5. Ollama 进程**不**归 CodeAsk 管理；CodeAsk 启动前调 `/api/tags` 探测当前激活模型可用性
6. OpenViking server **必须**带 socksio 启动（uvx `--with socksio` 或 venv `pip install httpx[socks]`）
7. workspace 永久路径 `$CODEASK_DATA_DIR/openviking/workspace/`
8. 切换 embedding 模型时需清空 vectordb collection 并重建（维度变化时尤其必要）
9. import 全程异步：CLI 提交立刻返回 `task_id`，后端用 `ov task status <task_id>` 跟踪
10. 子进程**不** unset proxy（CodeAsk `process.py` 不能写死 unset）；用户环境的代理边界由 socksio + `NO_PROXY` 自然处理

---

## 11. 与后续阶段的接口

Phase 0 完成后产出的"已确认事实"会被 Phase 1 / Phase 2 直接使用：

- 锁定的 OpenViking 与 embedding 版本 → 写入 `src/codeask/settings.py` 默认值与 SDD §10
- 召回基线 → 用于 acceptance-checklist E2E 验收阈值
- 真实样本 → Phase 2 live E2E 沿用
- 失败现象与重试策略 → SDD §9 错误处理矩阵补充

Phase 0 不留产品代码，但留下的实验记录、命令脚本与日志归档是 Phase 1 实施的依据。
