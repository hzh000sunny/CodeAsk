# 部署验收清单

> 范围：人工或自动化部署后的最小验收。
> 状态：Active

## 基础工具链

- [ ] Python 3.11+ 可用。
- [ ] `uv --version` 可用。
- [ ] Node.js 22+ 可用。
- [ ] `corepack pnpm --version` 或 `pnpm --version` 可用。
- [ ] `git`、`rg`、`ctags` 可用。

## 依赖与启动

- [ ] `uv sync` 成功完成。
- [ ] `corepack pnpm --dir frontend install --frozen-lockfile` 成功完成。
- [ ] `CODEASK_DATA_KEY` 已生成并导出；正式环境已持久保存。
- [ ] 首次启动后，`<CODEASK_DATA_DIR>/secrets/data.key` 已生成。
- [ ] 后续无 env 启动可读取缓存 key。
- [ ] `./start.sh` 能启动服务，日志显示监听地址和数据目录。
- [ ] `curl /api/healthz` 返回正常 JSON。

## 浏览器检查

- [ ] 单进程部署可打开 `http://127.0.0.1:8000`。
- [ ] 开发联调可打开 `http://127.0.0.1:5173`。
- [ ] 管理员账号能登录。
- [ ] 正式环境已修改默认管理员密码。
- [ ] 会话、Wiki、设置页可打开。

## 可选能力

- [ ] 如果需要远程访问，`CODEASK_HOST=0.0.0.0`、防火墙和安全组已配置。
- [ ] 如果需要代码检索，`rg` 和 `ctags` 已安装。
- [ ] 如果使用 Ollama provider，Ollama 服务和目标模型已由 operator 准备好。

## 开发验收

- [ ] 后端测试通过：`uv run pytest`。
- [ ] 后端静态检查通过：`uv run ruff check src tests`。
- [ ] 后端类型检查通过：`uv run pyright src/codeask`。
- [ ] 前端测试通过：`corepack pnpm --dir frontend test:run`。
- [ ] 前端构建通过：`corepack pnpm --dir frontend build`。
- [ ] 端到端测试通过：`corepack pnpm --dir frontend test:e2e --project=chromium`。
