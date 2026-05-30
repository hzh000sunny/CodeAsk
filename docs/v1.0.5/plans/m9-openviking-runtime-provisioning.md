# M9 — OpenViking 改为声明依赖 + 像 opencode 一样直接拉起

> 版本：v1.0.5
> 状态：Completed
> 关联：[acceptance §1/§3.1](./acceptance-checklist.md) · [openviking-agpl-review](../specs/openviking-agpl-review.md) · [openviking-integration 设计](../design/openviking-integration.md) · [m8](./m8-dashboard-ux.md)
> 来源：2026-05-29 OpenViking "拉不起来" 事故定位 + 负责人定调。

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

## 7. 完成记录（2026-05-29）

- `pyproject.toml` 已声明 `openviking==0.3.17`、`socksio>=1.0.0`，并将 `litellm` 钉到 `1.83.14`；`uv lock` / `uv sync` 已重新生成并安装依赖。
- `OpenVikingProcessManager` 已改为 `openviking_bin` 直接拉起 `[openviking-server, --config, ov.conf]`，`describe()` 返回 `configured_bin` / `resolved_bin`，缺失二进制时返回 `openviking_bin_not_found` 并提示先 `uv sync`。
- `Settings` 新增 `openviking_bin`，默认 `openviking-server`；`app.py` 注入该配置。
- 已验证 `uv run openviking-server --help` 能正常输出帮助信息，运行期不再需要 `uvx --from ...` 在线解析依赖。
- 文档已同步：`openviking-agpl-review.md`、README、INSTALL、acceptance checklist 均改为"声明依赖 + 独立子进程"，保留"不修改源码、不在业务代码 import openviking"边界。
