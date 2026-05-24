# Ollama 安装实测记录

> 版本归属：v1.0.5
> 状态：Recorded（2026-05-20 本机首次安装实测完成）
> 性质：Phase 0 spike 真实安装过程的命令与输出归档
> 关联：[`../plans/phase-0-spike.md`](../plans/phase-0-spike.md) §3.2

---

## 1. 文档定位

记录 v1.0.5 Phase 0 spike 阶段在本机首次安装 Ollama 的命令、参数选择、磁盘占用、systemd 行为与遇到的具体问题。

本文档不是 Ollama 通用安装教程，也不替代上游官方文档；目的是：

- 为后续把 Ollama 的安装指引写入 `INSTALL.md`（如果 v1.0.5 正式接入并对外发布）提供实测依据
- 让其它环境复现 spike 时有可执行清单
- 沉淀本次安装中验证过的、与 CodeAsk / OpenViking 相关的边界（embedding 模型选择、不要拉大模型、systemd 服务行为、API 端口）

---

## 2. 安装前置事实（本机实测）

| 项 | 实测值 |
|---|---|
| OS | Ubuntu 24.04 (glibc 2.39-0ubuntu8.7) |
| 内核 | Linux 6.8.0-55-generic |
| 架构 | amd64 |
| 当前用户 | `hzh`（非 root） |
| passwordless sudo | 可用 |
| GPU | 无（仅 Cirrus Logic GD 5446 虚拟 VGA；无 NVIDIA / AMD） |
| CUDA / ROCm | 未安装 |
| zstd | `/usr/bin/zstd`（install.sh 解压 .tar.zst 要用） |
| 当前 `/` 剩余 | 9.2 GB / 40 GB（76% 使用） |
| Python | 3.12.3 |
| uv | 0.11.8 |

`install.sh` 的 Linux 路径会：

- 装到 `/usr/local/bin/ollama` 与 `/usr/local/lib/ollama/`
- 创建 `ollama` 系统用户，`-d /usr/share/ollama -s /bin/false`
- 把当前用户加到 `ollama` group
- 写 `/etc/systemd/system/ollama.service`，`User=ollama Group=ollama Restart=always`
- 启动 service，API 监听 `127.0.0.1:11434`

> 实测纠正：**无 GPU 主机仍会拉 CUDA / Vulkan 运行时**。Ollama 0.24.0 默认把全平台运行时打包到 `tar.zst`，启动时按硬件选择加载哪一份。本次安装实际占用 ~3.5 GB（详见 §5）。文档前期"无 GPU 主机预估 < 500 MB"的判断是错的，已修订。

---

## 3. 安装命令

### 3.1 一行式（推荐）

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

此命令会：

1. 下载 `ollama-linux-amd64.tar.zst`
2. 解压到 `/usr/local/lib/ollama/`
3. 把 `ollama` 二进制软链到 `/usr/local/bin/ollama`
4. 创建系统用户和 systemd 服务并启动

实际执行需要 sudo 提权（脚本内部用 `$SUDO` 包裹关键操作）。

### 3.2 实测输出（2026-05-20）

```text
>>> Installing ollama to /usr/local
>>> Downloading ollama-linux-amd64.tar.zst
>>> Creating ollama user...
>>> Adding ollama user to render group...
>>> Adding ollama user to video group...
>>> Adding current user to ollama group...
>>> Creating ollama systemd service...
>>> Enabling and starting ollama service...
Created symlink /etc/systemd/system/default.target.wants/ollama.service → /etc/systemd/system/ollama.service.
>>> The Ollama API is now available at 127.0.0.1:11434.
>>> Install complete. Run "ollama" from the command line.
WARNING: No NVIDIA/AMD GPU detected. Ollama will run in CPU-only mode.
```

附带噪声（可忽略）：

```text
cannot connect to /var/run/nscd/socket
```

`nscd` 是 GNU Name Service Cache Daemon。Ubuntu 24.04 默认不启用，install.sh 调用 `useradd`/`usermod` 时会尝试通信，连不上不影响实际行为。

### 3.3 关键文件落点

| 路径 | 用途 |
|---|---|
| `/usr/local/bin/ollama` | CLI 二进制（实际为软链） |
| `/usr/local/lib/ollama/` | 本体与依赖库 |
| `/etc/systemd/system/ollama.service` | systemd 单元文件 |
| `/usr/share/ollama/` | `ollama` 用户 home，模型默认存放点 `/usr/share/ollama/.ollama/models` |
| `/var/log/syslog`（或 `journalctl -u ollama`） | 运行日志 |

---

## 4. 安装后验证

```bash
# 二进制
which ollama
ollama --version

# 服务
sudo systemctl status ollama --no-pager
ss -tlnp 2>/dev/null | grep 11434 || true

# HTTP API
curl -sf http://127.0.0.1:11434/api/tags
curl -sf http://127.0.0.1:11434/api/version 2>/dev/null
```

预期：

- `ollama --version` 输出版本号
- `systemctl status` 显示 `active (running)`
- `/api/tags` 返回 `{"models":[]}`（未拉模型时为空数组）

### 4.1 本次实测输出（2026-05-20）

```text
$ which ollama
/usr/local/bin/ollama

$ ollama --version
ollama version is 0.24.0

$ systemctl is-active ollama
active

$ systemctl is-enabled ollama
enabled

$ curl -sf http://127.0.0.1:11434/api/version
{"version":"0.24.0"}

$ curl -sf http://127.0.0.1:11434/api/tags
{"models":[]}
```

---

## 5. 磁盘占用

| 阶段 | `/` 剩余 | 增量 |
|---|---|---|
| 安装前 | 9.2 GB | — |
| 安装后（无模型） | 5.7 GB | **-3.5 GB** |
| 拉 nomic-embed-text（参考，未拉） | 预估 | -270 MB |
| 拉 mxbai-embed-large（参考，未拉） | 预估 | -670 MB |
| 拉 bge-m3（参考，未拉） | 预估 | -1.2 GB |

### 5.1 安装大头实测分解

```text
/usr/local/bin/ollama          43 MB    # 二进制本体
/usr/local/lib/ollama/         3.5 GB
├── cuda_v12                   2.5 GB
├── cuda_v13                   953 MB
├── vulkan                      55 MB
└── ggml-cpu-*.so 系列            ~7 MB（多个 CPU 微架构变体）
```

### 5.2 关于 CUDA / Vulkan 库

Ollama 0.24.0 默认把全平台 runtime 打入 install 包。无 GPU 主机不会 *使用* 这些库（启动时只 load `libggml-cpu-*.so` 对应的 CPU 变体），但 *占用磁盘*。

如果磁盘紧张，可以在 ollama 服务运行正常后**安全删除**未使用的 GPU 后端：

```bash
sudo systemctl stop ollama
sudo rm -rf /usr/local/lib/ollama/cuda_v12 \
            /usr/local/lib/ollama/cuda_v13 \
            /usr/local/lib/ollama/vulkan
sudo systemctl start ollama
# 验证
curl -sf http://127.0.0.1:11434/api/version
```

删除前提：

- 主机确认无 NVIDIA / AMD GPU（`lspci | grep -iE 'vga|3d|nvidia|amd'` 只有虚拟 VGA）
- install.sh 启动信息已经出现 `No NVIDIA/AMD GPU detected. Ollama will run in CPU-only mode.`
- 不计划将来给主机加 GPU；如果加 GPU 需要重跑 install.sh 恢复

风险：

- 下次 `install.sh` 升级会重新解压完整包，CUDA 文件回来；想保持精简需要重复清理或写脚本
- 极少数主板可能误报 GPU；如果删除后 `ollama serve` 启动失败，回滚就是重跑 install.sh

> 本机 spike 是否执行该清理：见 §10 决策记录。

---

## 6. 与 CodeAsk / OpenViking 的衔接

Ollama 装好后，OpenViking `ov.conf` 中 `embedding` 段配置（顶层 key 是 `embedding`，dense 子段；详见 `./openviking-server-bootstrap.md` §4）：

```json
{
  "embedding": {
    "dense": {
      "provider": "ollama",
      "api_base": "http://127.0.0.1:11434/v1",
      "model": "bge-m3",
      "dimension": 1024,
      "input": "text"
    },
    "max_concurrent": 1
  }
}
```

CodeAsk 后端在 v1.0.5 实现阶段会通过 settings 暴露：

- `openviking_embed_base_url` 默认 `http://127.0.0.1:11434`
- `openviking_embed_model` 默认 `bge-m3`（Phase 0 锁定）
- `openviking_embed_dimension` 默认 `1024`（bge-m3 维度）

Ollama 进程**不**归 CodeAsk 管理；CodeAsk 只在健康检查时探测 `<base_url>/api/tags` 是否可达。

---

## 7. 卸载方式（备查）

```bash
sudo systemctl stop ollama
sudo systemctl disable ollama
sudo rm /etc/systemd/system/ollama.service
sudo rm /usr/local/bin/ollama
sudo rm -rf /usr/local/lib/ollama
sudo rm -rf /usr/share/ollama
sudo userdel ollama
sudo groupdel ollama 2>/dev/null || true
```

完整卸载后 `/api/tags` 不再响应。

---

## 8. 已知风险

- **磁盘**：本机仅 9.2 GB 余量。任何拉模型操作前必须先 `df -h /` 检查，且优先选最小模型（`nomic-embed-text` 270 MB）。
- **systemd 服务自动重启**：`Restart=always`。开发期反复改 ollama 行为时可临时 `systemctl stop ollama`，否则升级 / 故障注入测试会被 Restart 干扰。
- **API 默认绑定 127.0.0.1**：CodeAsk 私有部署同机访问 OK；如果跨容器或远程访问需要改 `Environment="OLLAMA_HOST=0.0.0.0:11434"`，但这会扩大暴露面，需要单独评估。
- **二进制升级**：再次跑 `install.sh` 会清理旧 `/usr/local/lib/ollama`。如果有已经拉的模型，它们存在 `/usr/share/ollama/.ollama/models` 不受影响。
- **GPU 推理**：本机无 GPU；推理走 CPU。embedding 速度受 CPU 影响，第一次跑召回基线时要记录耗时。
- **CPU 并发雪崩**：CPU 模式下 Ollama 一次只能跑一个 embedding；OpenViking 默认 `max_concurrent=10` 会让单 chunk 延迟从 3 s 雪崩到 88 s。生产部署必须显式把 `embedding.max_concurrent` 设到 1（Ollama 场景）。详见 [`./openviking-server-bootstrap.md`](./openviking-server-bootstrap.md) §6.3。

---

## 9. 与 INSTALL.md 的分工（已收口）

v1.0.5 已决定把 Ollama 作为 RAG embedding 的默认（且当前唯一）provider，operator 安装指引已落入根目录 [`../../../INSTALL.md`](../../../INSTALL.md) 的"Ollama 与 RAG embedding（v1.0.5）"段，对应的产品契约见 [`../prd/rag-knowledge.md`](../prd/rag-knowledge.md) §7.0。

分工：

| 内容 | 落点 |
|---|---|
| 一行式安装命令、`ollama pull bge-m3`、`/api/tags` 验证、CodeAsk 探测行为承诺 | INSTALL.md |
| Operator vs CodeAsk 生命周期边界、模型缺失时的 admin 仪表盘行为 | PRD §7.0 |
| 本机首次安装的命令输出、磁盘分解、CUDA / Vulkan 处置、systemd 行为、卸载方式 | 本文件（spike 证据） |
| OpenViking ov.conf 中 `embedding.dense` 与 `max_concurrent=1` 的配置细节 | [`./openviking-server-bootstrap.md`](./openviking-server-bootstrap.md) §4 / §6.3 |

本文件保留为 Phase 0 实测档案，**不**复制 INSTALL.md 的指引；如果未来 Ollama 升级、`install.sh` 行为变化、或新增 provider，先更新 INSTALL.md / PRD §7.0，再把"实测差异"补到本文件 §10 决策记录。

---

## 10. 决策记录

| 日期 | 决策 | 原因 |
|---|---|---|
| 2026-05-20 | 安装 Ollama 0.24.0 | Phase 0 spike 启动；OpenViking 需要 embedding provider |
| 2026-05-20 | 不拉模型 | 用户要求严格控制磁盘 |
| 2026-05-20 | CUDA / Vulkan 库 **不清理** | 保持原装状态，便于将来切换有 GPU 主机或重装时一致；当前 5.7 GB 余量在拉一个小 embedding 模型 + OpenViking 索引后仍 > 3 GB |

