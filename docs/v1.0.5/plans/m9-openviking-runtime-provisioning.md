# M9 — OpenViking 改为声明依赖 + 像 opencode 一样直接拉起

> 版本：v1.0.5
> 状态：Completed（uvx→venv 根因，§0-§7）；**§8 进程生命周期加固 = 待修复**（2026-05-31 复盘新发现，未实现前不闭环）
> 关联：[acceptance §1/§3.1](./acceptance-checklist.md) · [openviking-agpl-review](../specs/openviking-agpl-review.md) · [openviking-integration 设计](../design/openviking-integration.md) · [m8](./m8-dashboard-ux.md)
> 来源：2026-05-29 OpenViking "拉不起来" 事故定位 + 负责人定调；2026-05-31 复盘发现第二类 respawn 死循环（§8）。

---

## 0. 事故与根因

OpenViking 服务长时间无法监听 1933。根因：

- 启动命令是运行时 `uvx --from openviking==0.3.17 --with socksio openviking-server`（`process.py:ensure_server` 100-109），**每次启动都在线解析依赖**。
- 传递依赖**未锁定**，漂移到新发布的 `volcengine-python-sdk==5.0.31`（wheel 35.1 MiB）。新版本不在 uv 缓存里 → 要下。
- 实测吞吐：直连 ~20 KB/s（35 MiB 约 30 分钟），超过 `process.py:53` 的 `startup_grace_seconds=30`；keepalive 把"还在下依赖"的进程当崩溃 kill 重启 → 下载没下完不进缓存 → 死循环（日志 Downloading×29 / Downloaded×2）。
- 那串 `ERROR…SystemExit:0…CancelledError` 是 SIGTERM 优雅退出的重启噪声，不是崩溃。

**根因一句话**：把 `uvx` 当长期服务的直接启动命令——运行时在线解析未锁定依赖，在当前网络下下载超时被反复杀掉。**不是 OpenViking 或 M8 代码问题**。

## 1. 决策（2026-05-29 负责人拍板）

> 原话：litellm 暂时钉死当前版本，不做额外声明；后续 OpenViking 更新自然兼容更高版本，到时同步升级。不再额外维护环境——只希望部署时 `uv sync` 拿到所有环境，OpenViking 的拉起就和 opencode 一样，运行时不用再管环境。**环境依赖管理不是 CodeAsk 服务运行时该考虑的事。**

落地为：

1. **OpenViking 进 CodeAsk 的依赖声明**，`uv sync` 时一并装进 CodeAsk venv（含 `openviking-server` 控制台脚本到 `.venv/bin/`）。
2. **运行期不再用 `uvx`**：`process.py` 改为像 `OpenCodeProcessManager` 一样，用配置的 `openviking_bin`（默认 `openviking-server`）经 `shutil.which` 解析后**直接拉起固定二进制**，无在线解析、无下载。
3. **不引入** 独立 venv / `ensure_runtime` / constraints 文件 / 准备态 / keepalive bootstrap 门控——这些随本决策全部作废。锁版本交给 CodeAsk 的 `uv.lock`。
4. **litellm 暂钉**：接受 OpenViking 的 `litellm<1.84.1` 约束，把 litellm 钉在兼容版本（当前 1.83.14 即在窗口内）。OpenViking 放宽后再同步升。

### 已知并接受的权衡（负责人已确认）
- CodeAsk 的 litellm 被 OpenViking 封顶在 `<1.84.1`，在 OpenViking 放宽前不能独立升 litellm。
- CodeAsk 的 `uv.lock` 会纳入 OpenViking 整棵依赖树（volcengine / grpcio / protobuf6 / tree-sitter×11 / 文档解析库等），供应链面扩大。

## 2. 许可证边界更新（必须同步改 `openviking-agpl-review.md`）

`agpl-review` 是"边界承诺记录、非合规审查"，且已记录负责人判断"不修改 + 不做 SaaS → AGPL 不构成风险"。本决策改变其中两处措辞，**需要有意识更新，不能让文档与实现矛盾**：

- §2 "不内嵌"那条的落地证据从"通过 uvx 拉起、不作为 Python 业务依赖导入"改为：**作为声明依赖随 `uv sync` 安装进 CodeAsk venv，以独立 `openviking-server` 子进程运行，适配层只走 HTTP / MCP，业务代码不 `import openviking`**。
- §3 披露项"不随主包默认安装"改为"随 `uv sync` 安装；仍不重新分发 OpenViking 二进制、不在业务代码 import"。
- **保持不变的硬承诺**：不修改源码；不重新分发（不打包进 docker / 安装件直接分发——`agpl-review §4` 的回访触发器仍有效，若未来要发布捆绑安装件需回访）。
- 仍然成立的亮线：**没有任何文件 `import openviking` 作为业务代码**（只拉起 `openviking-server` 控制台脚本，不导入 python 模块）。

## 3. 改动面

### 3-1 依赖声明（pyproject + lock）
- `pyproject.toml` 增加运行依赖：`openviking==0.3.17`、`socksio`（保留原 `--with socksio` 的 SOCKS 能力）。按负责人意见**作为普通依赖**加入（不做 optional-extra）。
- 显式钉 `litellm`（兼容 OpenViking 的 `<1.84.1`，当前 1.83.14）。
- `uv lock` 重生成锁；**验证能解析**（重点盯 litellm / fastapi / urllib3 等共享包）；`uv sync` 后确认 `.venv/bin/openviking-server` 存在且 `--help` 可跑。

### 3-2 `process.py` 改为直接拉起（对齐 opencode）
- 新增 `openviking_bin: str = "openviking-server"` 注入参数（仿 `OpenCodeProcessManager._opencode_bin`）。
- `ensure_server()` 的 `cmd`（`process.py:100-109`）从 `["uvx","--from",self._package,"--with","socksio","openviking-server","--config",...]` 改为 `[self._openviking_bin, "--config", str(config_path)]`。
- 删除 `_package`(uvx 包名) 相关、`--from`/`--with socksio`/`uvx` 机制。
- 启动失败分类参考 opencode：`shutil.which(self._openviking_bin)` 解析不到时给明确 code（如 `openviking_bin_not_found`）+ 可操作提示（"未找到 openviking-server，请先 `uv sync`"）。
- `describe()`（162-180）增加 `resolved_bin`（`shutil.which` 结果），便于诊断。
- `startup_grace_seconds=30`（:53）**保持不变**——不再触发下载，秒级启动。

### 3-3 settings
- 新增 `openviking_bin`（默认 `openviking-server`，仿 `opencode_bin`），允许覆盖。
- 删除/弃用任何 uvx 包版本相关 setting（如有）。

### 3-4 文档
- `README.md` / `INSTALL`：OpenViking 改为"随 CodeAsk `uv sync` 安装的依赖、以子进程拉起"，不再写"运行时 uvx 拉起"。
- 同步 §2 的 `agpl-review` 更新。

## 4. 测试

- 单测：
  - `ensure_server` 的 `cmd[0]` 指向 `openviking_bin` 解析出的固定二进制，**不含** `uvx`/`--from`。
  - `openviking_bin` 解析不到 → 抛出且 `last_error_code == "openviking_bin_not_found"`、`describe().resolved_bin is None`。
  - 已有的健康/重启/续传单测随 cmd 改动同步更新（popen_factory mock 断言新 cmd）。
- 集成/部署：
  - 干净环境 `uv sync` 后 `.venv/bin/openviking-server --help` 可跑；CodeAsk 启动后 OpenViking 在 30s 内监听 1933。
  - `uv.lock` 解析无冲突；litellm 落在 OpenViking 窗口内。
- 回归：`grep -rn "import openviking" src/codeask` 仍为空（亮线未破）。

## 5. 验收清单增量（写入 acceptance §1 / §3.1，并修订旧措辞）

- [x] OpenViking 改为 CodeAsk 声明依赖，`uv sync` 安装；运行期不再 `uvx` 在线解析依赖
- [x] `process.py` 像 opencode 一样用 `openviking_bin`（`shutil.which`）直接拉起固定二进制；`startup_grace_seconds=30` 不变
- [x] `openviking-server` 缺失时给 `openviking_bin_not_found` + "请先 uv sync" 提示，不进 kill 重启循环
- [x] `uv.lock` 纳入 OpenViking 依赖树且解析无冲突；litellm 钉在 `<1.84.1` 兼容版本
- [x] 业务代码仍无 `import openviking`（grep）；未拷贝 OpenViking 源码（grep）
- [x] `openviking-agpl-review.md` §2/§3 措辞已同步为"声明依赖 + 子进程拉起"，硬承诺（不修改/不重分发）保留；README/INSTALL 同步
- [x] 旧的 acceptance §1 "通过 uvx 拉起 / 不作为业务依赖内嵌" 行已修订

## 6. Ops
- 迁移完成后，运行时不再依赖 `~/.cache/uv` 的临时解压；`.tmp*` 残留可随时 `uv cache prune` 清理（不再有"清了又重下"的时序顾虑——依赖已被 CodeAsk venv 硬引用）。
- 临时止血（未实现 §8 前）：发现 dashboard 出现连续 `openviking_restart_detected` 时，`pkill -f "openviking-server"` 把**所有** OV 进程（含孤儿）清掉，再让 keepalive 重新拉起单一实例。

## 7. 完成记录（2026-05-29）

- `pyproject.toml` 已声明 `openviking==0.3.17`、`socksio>=1.0.0`，并将 `litellm` 钉到 `1.83.14`；`uv lock` / `uv sync` 已重新生成并安装依赖。
- `OpenVikingProcessManager` 已改为 `openviking_bin` 直接拉起 `[openviking-server, --config, ov.conf]`，`describe()` 返回 `configured_bin` / `resolved_bin`，缺失二进制时返回 `openviking_bin_not_found` 并提示先 `uv sync`。
- `Settings` 新增 `openviking_bin`，默认 `openviking-server`；`app.py` 注入该配置。
- 已验证 `uv run openviking-server --help` 能正常输出帮助信息，运行期不再需要 `uvx --from ...` 在线解析依赖。
- 文档已同步：`openviking-agpl-review.md`、README、INSTALL、acceptance checklist 均改为"声明依赖 + 独立子进程"，保留"不修改源码、不在业务代码 import openviking"边界。

---

## 8. 进程生命周期加固（2026-05-31 复盘新发现 · 待修复）

> §0-§7 解决的是"用 uvx 在线解析依赖导致拉不起来"。本节是 m9 完成后、2026-05-31 在真实实例上暴露的**第二类 respawn 死循环**——与依赖无关，根因在**进程生命周期管理**。负责人 2026-05-31 提出两条硬约束，本节据此定方向，待开发实现、架构验收。

### 8.0 事故事实（已核对事件库 + 进程 + OV 日志）

- 事件库 `openviking_restart_detected` 在 2026-05-31 21:39→22:21（本地 UTC+8，UTC 13:39→14:21）**每 30s 一条、共约 84 次**，payload 全是 `old_pid → new_pid` 在递增变化。
- 重启前系统内并存两个 `openviking-server`：`268276`（**ppid=1 孤儿**，实际占着 `:1933`）+ 后端子进程（其 pid 正出现在 churn 的 `new_pid` 序列里）。
- OV 历史日志可见 `[Errno 98] error while attempting to bind on address ('127.0.0.1', 1933): address already in use`（5/25、5/27 同病复发）。
- 手动 `pkill -f "openviking-server"`（清掉含孤儿的全部 OV）后重启 → 单实例 `pid 278968` 稳定，restart 事件归零。

### 8.1 根因（三连）

1. **manager 只认自己 `Popen` 出的句柄，从不探端口**：`process.py:ensure_server`（:86-95）复用判据是 `self._process is not None and poll() is None`；后端重启后 `self._process is None` → **无条件 spawn 新进程**，从不 probe `:1933/health` 看是否已有可复用实例。
2. **回收依赖优雅退出**：仅 `shutdown()`/atexit 杀子 OV；后端被 `SIGKILL`/OOM/断电带走时该路径不执行 → 子 OV 被 init 收养成孤儿、继续占端口。
3. **端口写死 1933**：撞 `EADDRINUSE` 后 keepalive 不分支、不退避，盲目 kill-respawn → 30s 一轮死循环；若端口被占即"永远拉不起来"。

### 8.2 负责人约束（2026-05-31）

- **C1**：不能只靠"后端停止时 kill OV"——后端可能异常被杀，优雅收尾不可依赖。
- **C2**：不能写死 1933——端口被占就永远起不来；且"端口被占"多半意味着 OV 已在跑，应优先复用而非对抗。

### 8.3 设计（分层，互为兜底）

**A. 治本防孤儿 —— 内核级父死子亡（满足 C1）**
- spawn OV 时 `preexec_fn` 设 `prctl(PR_SET_PDEATHSIG, SIGTERM)`：**无论后端怎么死（含 SIGKILL）**，内核给 OV 发信号，孤儿不再产生。
- 局限：Linux-only、对 spawning 线程死亡敏感 → 作为第一道防线，不作唯一防线。

**B. 启动时对账 + adopt-or-spawn（满足 C2，兼治 §8.1-1）**
- 维护运行时状态文件 `$workspace/openviking-runtime.json`：`{pid, port, version, owner_token, started_at}`（owner_token 标识"这是 CodeAsk 起的 OV"）。
- `ensure_server` 在"自己的子进程不在"时，新增分支（替代当前无条件 spawn）：
  ```
  probe 首选端口/health：
   ├─ 健康 ∧ 版本匹配 ∧ 是我们的(对 owner_token/状态文件)  → adopt：记 pid，不新拉
   ├─ 端口空闲                                            → 在首选端口 spawn（+ pdeathsig）
   └─ 端口被“非我们的 / 不健康”进程占用：
        ├─ pidfile 证明是我们上次陈旧 OV → 按 pid kill 再 spawn
        └─ 否则 → 选空闲端口 spawn（bind(0) 取临时口或扫小范围）
  ```
- **adopt 工程可行性**：OV 日志按 `ov.conf` 写文件、不走子进程 stdout 管道，故无 `Popen` 句柄也不丢功能——监活改用 `os.kill(pid,0)` / `/proc/<pid>`，日志照常读文件。pdeathsig 没兜住的场景（非 Linux、re-parent 抢跑）由此条对账补上。

**C. 端口动态化（满足 C2）**
- 1933 降级为"首选值"而非硬约束；选定端口要**传播三处**：`write_ov_conf`、client `base_url`（已从 handle 派生，天然跟随）、opencode MCP endpoint（`agent/opencode_compat/config.py`）+ 状态文件。

**D. keepalive 不再紧打循环**
- spawn 撞 `EADDRINUSE` → 走 B 的分支（能 adopt 就 adopt，不能就换口/告警），**不再盲目重拉**。
- 加退避；最坏情况落 `degraded=true` + `last_error_code=openviking_port_unavailable` 在 dashboard 明确报出，而非 30s 一轮 respawn。

### 8.4 故障回放验证（设计自检）
- 新后端启动 → 读状态文件见 268276 在 1933 → probe 健康/0.3.17/是我们的 → **adopt**，零新拉、零 Errno 98、零 respawn。
- 268276 若是外部/坏进程 → 换口或明确报错，**不进死循环**。
- 加 pdeathsig → "后端被 kill 留孤儿"将来不再发生。

### 8.5 改动面
- `src/codeask/rag/openviking/process.py`：`ensure_server` 增 adopt-or-spawn 分支；`preexec_fn` 设 PDEATHSIG；非自管 pid 的监活（`os.kill(pid,0)`）；spawn 撞端口的分支 + 退避；写/读运行时状态文件。
- `src/codeask/settings.py`：`openviking_port` 由"固定"改为"首选 + 允许动态"；可加端口候选范围。
- `src/codeask/agent/opencode_compat/config.py`：MCP endpoint 用运行时实际端口，不写死。
- `app.py` / dashboard 状态：`last_error_code=openviking_port_unavailable`、adopt/换口在 `describe()` 与事件流可见。
- 文档：本节 + acceptance 增量。

### 8.6 测试要点
- 单测：端口已被"健康同版本 OV"占用 → `ensure_server` 走 adopt（不调 popen_factory）、`describe().pid` == 既有 pid。
- 单测：端口被"不健康/外部"进程占用 → 选新端口 spawn，新端口传播到 ov.conf / base_url / MCP 配置。
- 单测：spawn 设了 PDEATHSIG（断言 `preexec_fn` 注入）；撞 `EADDRINUSE` 走分支而非直接重拉，并退避。
- 集成：起一个孤儿 OV 占 1933 → 启动 CodeAsk → 不产生 restart 风暴（事件库无连续 `restart_detected`），最终单实例可用。
- 回归：后端 `SIGKILL` 后子 OV 在短时间内消失（PDEATHSIG 生效）。

### 8.7 验收清单增量（待实现）
- [ ] **C1**：后端被 `SIGKILL` 后子 OV 自动退出（PDEATHSIG），不留孤儿
- [ ] **B**：`ensure_server` 在端口已有健康同版本 OV 时 adopt 复用，不盲目新拉
- [ ] **C2**：首选端口被占且不可复用时换空闲端口，并把实际端口传播到 ov.conf / client base_url / opencode MCP 配置
- [ ] **D**：撞 `EADDRINUSE` 不再 30s 紧打循环；最坏落 `degraded + openviking_port_unavailable` 并在 dashboard 报出
- [ ] 集成：孤儿占端口场景不产生连续 `restart_detected`；事故可回放通过
- [ ] 后端 pytest / 前端 vitest / e2e 全绿，ruff / pyright / tsc / eslint clean
