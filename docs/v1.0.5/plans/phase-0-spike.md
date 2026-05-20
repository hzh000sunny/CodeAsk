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
- 召回质量在锁定 embedding 模型后达到记录基线（不要求最优，但要可重复）

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
# 安装
curl -fsSL https://ollama.com/install.sh | sh

# 启动（保留前台 / 或 systemctl --user enable --now ollama 根据环境）
ollama serve > $DATA/ollama.log 2>&1 &
OLLAMA_PID=$!

# 健康
curl -sf http://127.0.0.1:11434/api/tags | head -c 200

# 三个候选模型；每个模型实测后选最终一个
ollama pull bge-m3
ollama pull nomic-embed-text
ollama pull mxbai-embed-large

# 列模型确认
curl -sf http://127.0.0.1:11434/api/tags
```

记录每个模型的 size、dim、pull 耗时。

### 3.3 OpenViking server 启动（不污染 CodeAsk venv）

```bash
# 临时方式：uvx 拉 PyPI 包
uvx --from openviking==0.3.17 openviking-server --version
uvx --from openviking==0.3.17 openviking --help | head -40

# 生成基础配置（手写或 doctor 引导）
cat > $OPENVIKING_CONFIG_FILE <<'EOF'
{
  "storage": {
    "workspace": "/tmp/codeask-v105-spike/openviking/workspace",
    "vectordb": {"name": "context", "backend": "local"},
    "agfs": {"backend": "local"}
  },
  "server": {
    "host": "127.0.0.1",
    "port": 1933,
    "auth_mode": "trusted",
    "cors_origins": ["http://127.0.0.1:5173"],
    "temp_upload": {"default_mode": "local"}
  },
  "embedder": {
    "provider": "ollama",
    "base_url": "http://127.0.0.1:11434",
    "model": "bge-m3"
  },
  "vlm": {"enabled": false}
}
EOF

# 启动
uvx --from openviking==0.3.17 openviking-server \
  --config $OPENVIKING_CONFIG_FILE \
  --host 127.0.0.1 --port 1933 \
  > $DATA/openviking/server.log 2>&1 &
OV_PID=$!

# 健康
curl -sf http://127.0.0.1:1933/health
uvx --from openviking==0.3.17 openviking health
uvx --from openviking==0.3.17 openviking status | head -40
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

```bash
# 1. 准备 spike 工作目录中的样本根
mkdir -p $DATA/openviking/_samples

# 2. 链接（或拷贝）仓库内的 fixture wiki 到 spike 临时区
ln -sfn $(pwd)/tests/fixtures/features/opencode/wiki         $DATA/openviking/_samples/opencode-wiki
ln -sfn $(pwd)/tests/fixtures/features/anything-llm/wiki     $DATA/openviking/_samples/anything-llm-wiki
ln -sfn $(pwd)/tests/fixtures/features/openviking/wiki       $DATA/openviking/_samples/openviking-wiki

# 3. 临时 verified 报告（仅 spike 用，不回写 fixture）
mkdir -p $DATA/openviking/_samples/opencode-reports/verified
cat > $DATA/openviking/_samples/opencode-reports/verified/2026-05-20-opencode-mcp-handshake-empty.md <<'EOF'
# 2026-05-20 opencode 启动后 MCP tools/list 返回空数组

## 问题背景
... (spike 临时编造一份小型 verified 报告用于召回质量验证) ...

## 定位过程
...
EOF

# 4. 导入三个 Wiki
for slug in opencode anything-llm openviking; do
  uvx --from openviking==0.3.17 openviking add-resource \
    $DATA/openviking/_samples/$slug-wiki \
    --to viking://resources/codeask/features/$slug/knowledge-base/ \
    --parent-auto-create \
    --reason "v105-spike-feature-wiki:$slug" \
    --wait --timeout 600
done

# 5. 导入临时 verified 报告（绑定到 opencode 特性）
uvx --from openviking==0.3.17 openviking add-resource \
  $DATA/openviking/_samples/opencode-reports/verified \
  --to viking://resources/codeask/features/opencode/problem-reports/verified/ \
  --parent-auto-create \
  --reason "v105-spike-verified-report:opencode" \
  --wait --timeout 300

# 6. 导入代码仓（先确保本地已 clone 到 references/）
test -d references/opencode || \
  git clone git@github.com:anomalyco/opencode.git references/opencode
uvx --from openviking==0.3.17 openviking add-resource \
  references/opencode \
  --to viking://resources/codeask/repos/opencode/ \
  --parent-auto-create \
  --reason "v105-spike-code-repo:opencode" \
  --ignore-dirs "node_modules,dist,build,.venv,.git,target" \
  --wait --timeout 1800
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

锁定 embedding 模型前，依次跑 `bge-m3` / `nomic-embed-text` / `mxbai-embed-large`：

1. 同一组 5 个真实业务问题（写到 §10 实验记录）
2. 同一组样本（同一 Feature Wiki + 一个 verified 报告）
3. 每个模型重新 `add-resource`（先 `forget` 清空再导）
4. 跑 `find / search`，记录 top-5 URI 与 score
5. 主观判断 relevance@5（人工标 0/1）

最终选定模型写入 PRD §7 与 SDD §5.4。基线包含：

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
6. §7 至少完成 1 个 embedding 模型的基线；relevance@5 ≥ 3/5
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

## 10. 实验记录（执行时填）

| 字段 | 值 |
|---|---|
| 实验启动日期 | — |
| 实验结束日期 | — |
| 执行人 | — |
| OpenViking 版本 | — |
| Ollama 版本 | — |
| 最终 embedding 模型 | — |
| 三个 fixture 导入结果（opencode / anything-llm / openviking 的 viking:// URI 与耗时） | — |
| 临时 verified 报告路径 | `$DATA/openviking/_samples/opencode-reports/verified/2026-05-20-...` |
| 关键命令日志归档路径 | `$DATA/evidence/` |
| 召回基线 | 见 §7 表 |
| 失败现象与修复 | — |
| 通过 §8 退出条件 | Yes / No |
| 是否进入 Phase 1 | — |

完整命令输出与日志保留在 `$DATA/evidence/` 下。spike 结束后选取关键截屏 / 文本片段附在本节末尾。

---

## 11. 与后续阶段的接口

Phase 0 完成后产出的"已确认事实"会被 Phase 1 / Phase 2 直接使用：

- 锁定的 OpenViking 与 embedding 版本 → 写入 `src/codeask/settings.py` 默认值与 SDD §10
- 召回基线 → 用于 acceptance-checklist E2E 验收阈值
- 真实样本 → Phase 2 live E2E 沿用
- 失败现象与重试策略 → SDD §9 错误处理矩阵补充

Phase 0 不留产品代码，但留下的实验记录、命令脚本与日志归档是 Phase 1 实施的依据。
