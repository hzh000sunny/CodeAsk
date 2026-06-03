# 升级已有部署

> 范围：从一个已有 CodeAsk 部署升级到新代码或新 release。
> 状态：Active

升级原则：源码可以更新，依赖可以重装，前端可以重新构建，但用户数据目录不能被破坏。

## 标准流程

```bash
# 1. 停止当前 CodeAsk 服务

# 2. 确认数据目录，默认是 ~/.codeask
export CODEASK_DATA_DIR="${CODEASK_DATA_DIR:-$HOME/.codeask}"

# 3. 备份整个数据目录。不要只备份 data.db。
tar -czf "$HOME/codeask-backup-$(date +%Y%m%d-%H%M%S).tar.gz" \
  -C "$(dirname "$CODEASK_DATA_DIR")" \
  "$(basename "$CODEASK_DATA_DIR")"

# 4. 拉取新代码。也可以切换到明确的 release branch / tag。
git pull --ff-only

# 5. 更新依赖并重新构建前端。
uv sync
corepack pnpm --dir frontend install --frozen-lockfile
corepack pnpm --dir frontend build

# 6. 使用原数据目录启动。已有 secrets/data.key 时，可以不再导出 CODEASK_DATA_KEY。
./start.sh
```

如果离线环境只安装了系统 pnpm，可以把前端命令替换为：

```bash
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend build
```

## 升级后检查

```bash
curl -s http://127.0.0.1:8000/api/healthz -H 'X-Subject-Id: alice@dev-1' | python3 -m json.tool
```

浏览器确认：

- 会话列表可以加载。
- Wiki 页面可以打开并预览文档。
- 设置页可以打开。
- 管理员账号可以登录。
- 已有 LLM 配置仍能正常使用。

## 回滚规则

- 如果新版本还没有启动，数据库 migration 没有执行，可以直接切回旧代码。
- 如果新版本已经启动并执行 migration，不要只回滚代码。
- migration 已执行后的回滚应恢复升级前备份的整个数据目录。
- 不承诺任意 Alembic downgrade 都能安全恢复业务数据。

更完整规则见 [upgrade-compatibility.md](../rules/upgrade-compatibility.md)。
