# v1.0.3 真实数据升级与浏览器验收记录

> 状态：自动化、真实数据验收和人工复核已完成
> 版本：v1.0.3
> 范围：真实数据目录升级、只读浏览器验收、人工验收输出基线

## 1. 验收目标

v1.0.3 不能只在空数据目录上通过自动化测试。必须证明：

1. 真实用户数据在 `0024 -> 0025` 迁移后仍完整可见。
2. 浏览器当前连到的就是目标真实数据目录，而不是临时测试目录。
3. 匿名访客和 admin 的关键读路径在真实数据上可正常访问。
4. 文档中已经沉淀可重复的真实数据 E2E 通道和人工验收清单。

## 2. 本次验收环境

- 仓库：`/home/hzh/workspace/CodeAsk`
- 真实数据目录：`/home/hzh/.codeask`
- 升级前备份：`/home/hzh/backups/codeask-v103-preupgrade-20260511-093324.tar.gz`
- 后端端口：`8000`
- 前端端口：`5173`
- 前端真实数据 Playwright 配置：`frontend/playwright.realdata.config.ts`
- 真实数据只读 E2E：`frontend/e2e/realdata-auth-readonly.spec.ts`

## 3. 升级前后证据

### 3.1 升级前

- Alembic revision：`0024`
- `features = 8`
- `llm_configs = 7`
- `repos = 5`
- `system_settings = 0`

### 3.2 升级后

- Alembic revision：`0025`
- `features = 8`
- `llm_configs = 7`
- `repos = 5`
- `system_settings = 0`
- `users = 1`
- `feature_admins = 0`

### 3.3 迁移审计结论

本次 migration 只新增鉴权相关表和索引：

- `users`
- `auth_sessions`
- `feature_admins`

未发现删除 `features`、`llm_configs`、`repos`、Wiki、会话或报告数据的迁移语句。

## 4. 真实数据浏览器验收基线

### 4.1 只读检查

- 匿名访客读取特性页、Wiki 页、设置页。
- admin 登录后读取全局 LLM、仓库和设置页。
- Wiki 使用真实文档 `小米 / 小米病历`，验证 Markdown 正文和相对图片资源。
- 登录退出后验证身份缓存和登录页用户名缓存。
- Wiki / 设置路由刷新后保持当前路由。

### 4.2 禁止项

- 不在真实数据目录上运行会创建、删除、批量重排业务数据的自动化脚本。
- 不向真实业务特性写入调试节点。
- 不批量修改真实 LLM、仓库、Wiki 或报告数据。

## 5. 真实数据 E2E 命令

```bash
CODEASK_RUN_REAL_DATA_E2E=1 \
CODEASK_REALDATA_BASE_URL=http://127.0.0.1:5173 \
CODEASK_REALDATA_EXPECT_FEATURES='AnythingLLM Reference,小米' \
CODEASK_REALDATA_EXPECT_REPOS='E2E claude-code 1778123017269' \
CODEASK_REALDATA_EXPECT_LLM_CONFIGS='火山-Anthropic-glm-5.1,DeepSeek-OpenAI' \
corepack pnpm --dir frontend exec playwright test \
  -c playwright.realdata.config.ts \
  e2e/realdata-auth-readonly.spec.ts \
  --project=chromium
```

执行结果（2026-05-11）：

- `2 passed (7.7s)`
- 匿名访客读路径通过：特性页、`小米 / 小米病历` Wiki 预览、设置页。
- admin 读路径通过：全局 LLM、仓库、退出后登录页用户名缓存。

## 6. 人工复核结论

- 2026-05-12，用户已在真实浏览器中确认普通用户链路、特性管理员授权链路和附件上传全局开关 UX。
- 自动化 E2E 仍以只读或可清理的隔离数据为主，避免在真实业务数据目录中批量创建、删除或重排数据。
- v1.0.3 真实数据升级和浏览器验收已闭环。
