# 常见问题排查

> 范围：本地安装、启动、前端联调和常见运行问题。
> 状态：Active

## 工具链

### `uv: command not found`

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv --version
```

### `corepack: command not found`

确认 Node.js 版本：

```bash
node --version
```

项目要求 Node.js 22+。版本正确但没有 Corepack 时：

```bash
npm install -g corepack
corepack enable
```

### 前端依赖安装失败

```bash
node --version
pnpm --version || corepack pnpm --version
corepack enable
```

## 数据密钥

### `CODEASK_DATA_KEY is not set`

首次启动前生成并导出：

```bash
export CODEASK_DATA_KEY="$(uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
```

首次启动成功后，CodeAsk 会把 key 缓存在 `<CODEASK_DATA_DIR>/secrets/data.key`。

### `CODEASK_DATA_KEY conflicts with cached data key`

通常原因：

- 用户对已有数据目录重新生成了 key。
- `CODEASK_DATA_DIR` 指向了另一个环境的数据目录。
- 部署系统 secret 配错。

处理方式：

1. 停止服务。
2. 确认当前 `CODEASK_DATA_DIR` 是否正确。
3. 如果继续使用该数据目录，应使用 `<CODEASK_DATA_DIR>/secrets/data.key` 对应的 key。
4. 如果要恢复旧环境，应恢复升级前备份的整个数据目录。

不要直接覆盖 `secrets/data.key`。

## 服务访问

### 前端 dev server 访问不到 API

确认后端运行在 `:8000`，并用仓库代理配置启动 Vite：

```bash
CODEASK_HOST=0.0.0.0 CODEASK_PORT=8000 uv run codeask
corepack pnpm --dir frontend dev --host 0.0.0.0 --port 5173
```

### 浏览器从远程机器访问不到服务

确认服务监听在 `0.0.0.0`，并检查防火墙或安全组：

```bash
CODEASK_HOST=0.0.0.0 CODEASK_PORT=8000 ./start.sh
```

开发联调时 Vite 也要监听 `0.0.0.0`：

```bash
corepack pnpm --dir frontend dev --host 0.0.0.0 --port 5173
```

### 端口被占用

```bash
CODEASK_PORT=8010 ./start.sh
```

开发联调时：

```bash
CODEASK_HOST=0.0.0.0 CODEASK_PORT=8010 uv run codeask
CODEASK_API_PROXY_TARGET=http://127.0.0.1:8010 corepack pnpm --dir frontend dev --host 0.0.0.0 --port 5173
```

## opencode 与代码检索

### 后台看不到 opencode 进程

先查询健康检查：

```bash
curl -fsS http://127.0.0.1:8000/api/healthz | python3 -m json.tool
```

重点查看：

- `agent_backend`：应为 `opencode`。
- `opencode.running`：`true` 表示后端认为 shared server 正在运行。
- `opencode.resolved_bin`：`null` 表示启动进程 PATH 找不到 `opencode`。
- `opencode.last_error`：最近一次启动失败原因。

如果 `resolved_bin` 是 `null`：

```bash
command -v opencode
opencode --version
```

必要时显式配置：

```bash
export CODEASK_OPENCODE_BIN="/absolute/path/to/opencode"
./start.sh
```

### 代码检索能力不完整

确认系统安装了 `ripgrep` 和 `universal-ctags`：

```bash
rg --version
ctags --version
```
