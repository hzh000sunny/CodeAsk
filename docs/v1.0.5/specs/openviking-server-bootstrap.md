# OpenViking Server 首次启动实测记录

> 版本归属：v1.0.5
> 状态：Recorded（2026-05-21 Phase 0 spike 完成）
> 性质：Phase 0 spike 在本机首次启动 OpenViking server 的命令、配置漂移、故障模式和修复路径
> 关联：[`../plans/phase-0-spike.md`](../plans/phase-0-spike.md) §3.3-§5 · [`./ollama-installation.md`](./ollama-installation.md)

---

## 1. 文档定位

记录 v1.0.5 Phase 0 spike 阶段在本机首次启动 OpenViking 0.3.17 server 的真实过程。**不是**上游官方安装指南，**不是**正式 INSTALL 文档。

目的：

- 给 Phase 1 实现 `src/codeask/rag/openviking/{config,process,client}.py` 提供已验证的命令、ov.conf 字段、错误模式与修复方向
- 让其它环境复现 spike 时少踩相同的坑
- 沉淀上游 example 文件与 0.3.17 schema 之间的真实差异

不进 `INSTALL.md` 的内容也留在这里，便于后续 v1.0.5 收口时再决定要不要迁移片段。

---

## 2. 环境前置

| 项 | 值 |
|---|---|
| OS | Ubuntu 24.04 |
| Python | 3.12.3（uvx 内部用 3.11.15） |
| uv | 0.11.8 |
| zstd | v1.5.5 |
| 磁盘起点 | 5.7 GB（Ollama 装完后） |
| Ollama | 0.24.0 active@127.0.0.1:11434（无模型） |
| 网络环境 | 本机 7890 端口同时支持 HTTP 与 SOCKS5 代理；`NO_PROXY=localhost,127.0.0.1,::1` |

---

## 3. uvx 拉取 OpenViking 0.3.17

```bash
uvx --from openviking==0.3.17 openviking-server --version
# Installed 133 packages in 421ms
# openviking-server 0.3.17
```

- 133 个依赖，因 uv cache 命中实际只新增 ~200 MB（磁盘 5.7 → 5.6 GB）
- uv cache 在 `~/.cache/uv`，spike 期间总占 2.3 GB
- 不污染 CodeAsk 项目自己的 venv

---

## 4. ov.conf 与上游 example 的差异

上游 `examples/ov.conf.example` 包含较多字段，但 0.3.17 server 实际启动时 **schema strict**。本次实测在 example 基础上**最小化**生成可工作 ov.conf，并发现以下漂移：

### 4.1 字段漂移

| example 字段 | 0.3.17 实际 | 处理 |
|---|---|---|
| `embedder.*` （CodeAsk 之前误写） | 顶层 key 实际是 `embedding` | 改用 `embedding` |
| `embedding.dense.api_base` | 必须包含 `/v1` OpenAI 兼容路径，不是裸 base URL | 写 `http://127.0.0.1:11434/v1` |
| `enable_memory_decay` | **0.3.17 拒绝**：`Unknown config field 'enable_memory_decay' in OpenVikingConfig` 并立即退出 | 删除该字段 |
| `auto_generate_l0` / `auto_generate_l1` | 0.3.17 接受；但仅影响后续资源，不阻止 init 阶段对 preset 目录调用 embedder | 设 false，但准备好 ollama 模型 |
| `vlm.enabled` | **0.3.17 拒绝**：`Unknown config field 'vlm.enabled'` 并立即退出 | 不生成 `vlm` 字段；v1.0.5 M1 只处理文本 RAG |
| `vlm` 段未配 | doctor 报 FAIL，但 server 启动 OK | spike 不配 VLM |
| HTTP 响应 envelope | 0.3.17 的 `temp_upload` / `resources` 返回 `{status, result}`，不是裸 payload | CodeAsk client 必须先解 `result`，再读 `temp_file_id` / `task_id` |

### 4.2 最小可工作 ov.conf（本次 spike 使用）

```json
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
```

### 4.3 doctor 输出参考

```text
OpenViking Doctor

  Config:        PASS  /tmp/codeask-v105-spike/openviking/ov.conf
  Python:        PASS  3.11.15 (>= 3.10 required)
  Native Engine: PASS  variant=x86_avx512
  AGFS:          PASS  AGFS SDK 0.1.7
  Embedding:     PASS  ollama/bge-m3
  VLM:           FAIL  No VLM provider configured
                 Fix: Add vlm section to ov.conf
  Ollama:        PASS  running at 127.0.0.1:11434
  Disk:          PASS  5.6 GB free in /tmp/codeask-v105-spike/openviking/workspace

  1 check(s) failed. See above for fix suggestions.
```

VLM FAIL 不阻塞启动；spike 不需要 VLM。

---

## 5. 启动命令（spike 调试用）

```bash
nohup uvx --from openviking==0.3.17 --with socksio openviking-server \
  --config /tmp/codeask-v105-spike/openviking/ov.conf \
  > /tmp/codeask-v105-spike/openviking/logs/server.log 2>&1 &
```

启动后日志显示 Uvicorn 监听 `http://127.0.0.1:1933`，QueueManager / LockManager / WatchScheduler / OpenVikingService 全部就位。

### 5.1 验证

```bash
$ curl -sf --noproxy '*' http://127.0.0.1:1933/health
{"status":"ok","healthy":true,"version":"0.3.17","auth_mode":"dev"}
```

`auth_mode=dev` 是因为 `ov.conf.server.root_api_key=null`，spike 阶段足够；生产环境由 CodeAsk 后端按需注入 token。

---

## 6. 故障模式与修复

### 6.1 SOCKS proxy + 缺 socksio

第一次启动失败：

```text
ImportError: Using SOCKS proxy, but the 'socksio' package is not installed.
Make sure to install httpx using `pip install httpx[socks]`.
```

原因：本机环境 `ALL_PROXY=socks5://127.0.0.1:7890`；OpenViking 通过 `openai` SDK 创建 client 时 httpx 在 `__init__` 直接校验 proxy URL 协议，缺 socksio 即 raise。即使 `NO_PROXY=127.0.0.1` 也不影响这一阶段——校验发生在 client 实例化时，请求路由还没开始。

修复方向（按推荐顺序）：

1. **推荐**：装 socksio 进 OpenViking 运行环境
   ```bash
   uvx --from openviking==0.3.17 --with socksio openviking-server ...
   # 或在生产环境：
   uv pip install 'httpx[socks]'
   ```
2. 把 `ALL_PROXY` 改成 HTTP 协议（如果代理同时支持）
3. 子进程 `env -u ALL_PROXY -u all_proxy ...` 临时剥离 proxy（**本机调试可用**，**不进文档 / 不进代码**）

**生产指引**（写进 CodeAsk INSTALL 时）：

- 不修改用户的 proxy 环境
- 不在 `process.py` 启动 OpenViking 子进程时 unset proxy
- 在 INSTALL 文档"已知问题"段记录 SOCKS proxy ImportError，给出推荐修复（装 socksio）

### 6.2 `enable_memory_decay` Unknown field

见 §4.1。修复：移除字段。

### 6.3 CPU embedding 并发雪崩（重要）

bge-m3 在 Ollama CPU 模式下**只能一次跑一个**。OpenViking 默认 `embedding.max_concurrent=10` → 多个并发请求堆队列 → 单 chunk 延迟从 3 s 雪崩到 88 s（spike 实测）。

```text
2026-05-21 00:52:41 - openviking - WARNING - embedding slow call duration_ms=3169.85
...
2026-05-21 00:54:39 - openviking - WARNING - embedding slow call duration_ms=88267.22
```

修复：

```json
{
    "embedding": {
        ...
        "max_concurrent": 1
    }
}
```

字段位置：**顶层 `embedding`**，不是 `embedding.dense`（验证自源码 `embedding_config.py:373`）。

设为 1 后单 chunk 稳定 ~3 s；22 文件 fixture 估约 5-6 分钟完成索引。

Phase 1 的处理：

- `OpenVikingEmbeddingSetting` 表存储 `max_concurrent`
- 默认值由 provider 决定：`ollama → 1`，云端 provider（OpenAI / DashScope / Volcengine） → `5-10`
- admin UI 可调，但不在第一版暴露给普通用户

### 6.4 模型未拉取 → Circuit Breaker 跳闸

server 启动成功，但日志反复出现：

```text
Failed to generate embedding: OpenAI API error: Error code: 404 -
  {'error': {'message': 'model "bge-m3" not found, try pulling it first'}}
Circuit breaker tripped after 9 consecutive failures
```

原因：OpenViking init 时给 preset 目录（约 9 个）生成 L0 embedding，调 Ollama → 404。9 次失败后 circuit breaker 跳闸。

修复：

- **执行 `ollama pull <model>`**
- circuit breaker 会按 `embedding.circuit_breaker.reset_timeout`（默认 60s）自动半开重试
- 模型拉到后下一轮重试成功，断路器关闭

CodeAsk 后端在 v1.0.5 实现中应该在 `process.py.ensure_server()` 之前先 `health.py.ollama_models_available()` 探测当前激活模型是否在 `/api/tags` 中。**不在**就把状态置为 `embedding_model_missing`，前端报错"OpenViking embedding 模型未就绪"，不让 server 继续跑空转。

### 6.5 LiteLLM SOCKS 缓存映射 fetch 警告

每次启动 / 每次 doctor 都会出：

```text
LiteLLM: Failed to fetch remote model cost map from
https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json:
Using SOCKS proxy, but the 'socksio' package is not installed.
Falling back to local backup.
```

- 装 socksio 后该报错也消失（因为 fetch 也走 SOCKS）
- 即使不装，也只是回退到本地映射，**不影响功能**
- 不需要单独处理

---

## 7. MCP 端点实测

OpenViking 0.3.17 通过 streamable-http MCP 暴露在 `POST /mcp`。

### 7.1 initialize

```bash
curl -sf --noproxy '*' -X POST http://127.0.0.1:1933/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"v105-spike","version":"0"}}}' \
  -i
```

返回：

```text
HTTP/1.1 200 OK
content-type: text/event-stream
mcp-session-id: 0de459d52dcb4c8e8e0f799716ebb4ba

event: message
data: {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05",
  "capabilities":{"experimental":{},"prompts":{"listChanged":false},
  "resources":{"subscribe":false,"listChanged":false},"tools":{"listChanged":false}},
  "serverInfo":{"name":"openviking","version":"1.27.1"}}}
```

注意：`serverInfo.version` 是 MCP 实现版本（1.27.1，来自上游 mcp SDK），不是 OpenViking 版本（0.3.17）。

### 7.2 tools/list

```bash
SID=0de459d52dcb4c8e8e0f799716ebb4ba

curl ... -d '{"jsonrpc":"2.0","id":2,"method":"notifications/initialized"}'
curl ... -d '{"jsonrpc":"2.0","id":3,"method":"tools/list"}'
```

返回 10 个工具，名称、签名与 `future/openviking-rag-research-2026-05-20.md` §4 调研一致：

| name | 类型 | 关键 input |
|---|---|---|
| `find` | 语义检索（全局） | `query`, `target_uri?`, `limit=10`, `min_score=0.35`, `level?` |
| `search` | 会话感知检索 | `query`, `target_uri?`, `session_id?`, `limit=10`, `min_score=0.35`, `level?` |
| `read` | 读取 URI | `uris: str \| list[str]` |
| `list` | 列目录 | `uri`, `recursive=false` |
| `remember` | 写入记忆 | `messages: list[{role, content}]` |
| `add_resource` | 远程导入 | `path: HTTP/HTTPS/Git URL`, `description?` |
| `grep` | 正则文本匹配 | `uri`, `pattern: str \| list[str]`, `case_insensitive=false`, `node_limit=10` |
| `glob` | 路径模式匹配 | `pattern`, `uri="viking://"`, `node_limit=100` |
| `forget` | 删除 URI（不可逆） | `uri`, `recursive=false` |
| `health` | 健康检查 | 无参 |

要点：

- `add_resource` 的 description 明确说**不接受本地路径**，只接受 HTTP/HTTPS/Git URL（spike 同步本地 fixture wiki 必须走 CLI / SDK，不能走 MCP）
- v1.0.5 PRD §6.2 已经规定 `add_resource / remember / forget` 不暴露给 opencode；MCP 直接挂上时需要在 opencode 工具白名单或 CodeAsk MCP proxy 层屏蔽这三个工具
- `search` 接受 `session_id` 是 OpenViking 自己的 session，不直接对应 CodeAsk session（映射策略由 Phase 2 决定）

---

## 8. 资源占用

| 阶段 | 进程 | RSS | 备注 |
|---|---|---|---|
| `uvx --version` 一次性命令 | 短暂 | — | 421ms 装完 |
| 启动 server（无导入） | 1 | 140 MB | uvicorn 父进程 |
| `--with socksio` 启动 | 1 | 64 MB（仍在初始化） | socksio 不显著增加 |

磁盘：

| 阶段 | `/` 剩余 |
|---|---|
| Ollama 装完 | 5.7 GB |
| uvx 拉 OpenViking | 5.6 GB |
| `--with socksio` 二次拉 | 5.5 GB |
| 拉 bge-m3（进行中） | 预计 4.4 GB |

---

## 9. 与 Phase 1 实现的衔接

下列事项必须沉淀进 `src/codeask/rag/openviking/`：

| 来源 | 落点 |
|---|---|
| §4.1 字段漂移表 | `config.py` 生成 ov.conf 时显式只用 0.3.17 验证字段；写单元测试快照锁定 |
| §4.2 最小 ov.conf | `config.py.build_ov_conf()` 的基础模板 |
| §5 启动命令 | `process.py.ensure_server()`；**不**在子进程 unset proxy；如果发现 socksio 缺失，前端报错并提示安装 |
| §6.1 SOCKS 修复路径 | INSTALL.md "已知问题"段，给装 socksio 的命令 |
| §6.3 模型未拉 | `health.py.ollama_models_available()` 启动前探测；缺模型则状态 `embedding_model_missing`，admin 卡片可见 |
| §7 MCP 工具白名单 | `opencode_compat/config.py` 写 opencode.json 时只允许 7 个只读工具 |
| §7 `serverInfo.version` 是 mcp SDK 版本 | 健康检查中读 OpenViking 自己的 version 走 `GET /health`，不读 MCP serverInfo |

---

## 10. 已知待补

- VLM 段：spike 不配；Phase 1 决定要不要支持
- `auth_mode` 切换：spike 用 `dev`；生产可能用 `trusted` 或 `api_key`，需要在 SDD §5.4 补完
- workspace 持久化：spike 用 `/tmp/codeask-v105-spike/openviking/workspace`，重启会丢；生产用 `$CODEASK_DATA_DIR/openviking/workspace`
- Circuit breaker 配置：spike 默认 60s reset；Phase 1 可能要在 ov.conf 暴露调整入口
- MCP serverInfo.version 上报问题：与 OpenViking 自己的 0.3.17 不一致，文档要说明

---

## 11. 决策记录

| 日期 | 决策 | 原因 |
|---|---|---|
| 2026-05-20 | spike 用 `--with socksio` 启动 | 不修改用户 proxy 环境；治本不绕开 |
| 2026-05-20 | 删除 example 中的 `enable_memory_decay` | 0.3.17 拒绝该字段；example 滞后于实际 schema |
| 2026-05-20 | spike 阶段不配 VLM | 不影响 spike 核心目标；正式版再决定 |
| 2026-05-21 | embedding 模型选 bge-m3 | 中文 wiki 优先；用户决策 |
| 2026-05-21 | embedding 模型设计为 admin UI 可切换 | 用户决策；落到 v1.0.5 PRD §7.1 / SDD §3.3 |
| 2026-05-21 | `embedding.max_concurrent` 默认按 provider 决定（ollama=1，cloud=5–10），落 `OpenVikingEmbeddingSetting` 表 | CPU bge-m3 并发雪崩实测 |
| 2026-05-21 | spike 不全量索引 fixture；批量耗时是 CPU 性能问题，不阻塞 Phase 1 | 链路证明已通，Phase 1 后台异步同步引擎本来就该处理长耗时 |
| 2026-05-21 | Phase 0 收口；不进入完整召回基线（推到 Phase 2 live E2E） | 召回基线依赖完整 fixture 索引，CPU 时间约束下 spike 期内不现实 |
