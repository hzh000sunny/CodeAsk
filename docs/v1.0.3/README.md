# CodeAsk v1.0.3

v1.0.3 聚焦登录、用户、特性管理员和权限控制。目标是在保留“未登录也能直接发起会话”的低门槛体验前提下，把特性配置、Wiki 管理、全局配置、用户管理等写操作收敛到明确的权限模型中。

## 文档索引

- [鉴权与访问控制设计草案](./specs/auth-access-control.md)
- [鉴权与访问控制实现计划](./plans/auth-access-control.md)
- [鉴权与访问控制验收清单](./plans/acceptance-checklist.md)
- [真实数据升级与浏览器验收记录](./specs/real-data-acceptance.md)
- [opencode 多模型协议与 Reasoning 处理学习记录](./specs/opencode-provider-protocol-lessons.md)

## 当前状态

- 阶段：鉴权、用户体系、特性管理员、资源权限、审计日志、前端权限 UI、临时库回归、真实数据升级验收、真实浏览器 E2E、LLM 协议选择收口和真实 LLM 配置验证已完成；等待人工验收。
- 已提交阶段：
  - `bcb1670 fix(auth): renew sessions by remaining lifetime`
  - `61307fb feat(auth): add unified login and user APIs`
  - `e5d6abe feat(authz): add feature administrator permissions`
  - `002d56b feat(authz): enforce resource permissions`
  - `4a89462 feat(audit): record auth and authorization events`
  - `09ba8ee feat(ui): add unified auth and guest llm settings`
  - `35aff25 feat(ui): add feature admin and user management controls`
  - `0051275 test(e2e): cover auth access control`

## 已实现能力

- 未登录访客仍可直接创建和使用自己的会话，也可以查看特性页面和 Wiki 页面。
- 普通用户通过统一登录页自动注册或登录，用户名和密码大小写敏感。
- 普通用户登录后会迁移当前浏览器匿名会话；admin 登录不会迁移匿名会话。
- `admin` 用户固定存在，默认密码为 `admin`，正式部署必须修改。
- 只有 admin 可以创建、归档特性、管理全局配置、管理全局仓库、管理全局 LLM 和添加/删除特性管理员。
- 特性管理员可以管理被授权特性的配置、仓库关联、分析策略、Wiki 和问题报告。
- 未授权用户可以查看特性和 Wiki，但不能执行写操作。
- 访客 LLM 配置只保存在浏览器本地；登录用户使用自己的用户级 LLM；admin 维护全局 LLM。
- 会话附件上传受 admin 全局开关控制；关闭后所有用户的新上传都会被拒绝。
- 登录、自动注册、权限拒绝、特性变更、管理员变更、报告保存、附件拒绝等关键动作写入审计日志。

## 最新验证记录

- 后端定向鉴权测试：`uv run pytest tests/unit/test_auth_passwords.py tests/unit/test_auth_sessions.py tests/unit/test_feature_permissions.py tests/integration/test_auth_users_api.py tests/integration/test_feature_admins_api.py tests/integration/test_authz_features_api.py tests/integration/test_authz_wiki_api.py tests/integration/test_attachment_upload_gate.py tests/integration/test_audit_authz_api.py -v`，39 passed。
- 后端全量回归：`uv run pytest tests/unit tests/integration -q`，通过。
- 前端全量测试：`corepack pnpm --dir frontend test:run -- settings-page.test.tsx`，命令实际复跑前端全量 Vitest，2026-05-11 结果为 40 个测试文件、201 个用例通过。
- 前端类型检查：`corepack pnpm --dir frontend typecheck`，通过。
- 真实浏览器组合 E2E：`corepack pnpm --dir frontend test:e2e -- auth-access-control.spec.ts route-refresh.spec.ts wiki-tail.spec.ts auth-session-switch.spec.ts --project=chromium`，8 passed。
- 真实数据只读 E2E：`corepack pnpm --dir frontend exec playwright test -c playwright.realdata.config.ts e2e/realdata-auth-readonly.spec.ts --project=chromium`，2026-05-11 结果为 2 passed。
- 真实 LLM 配置逐个验证：使用真实数据目录 `/home/hzh/.codeask` 的 7 个启用配置真实请求，覆盖 OpenAI 消息格式、Anthropic 消息格式、全局配置和用户配置，结果 `passed=7 failed=0 marker_leaks=0 empty_answers=0`。
- `git diff --check`：通过。

## 真实数据升级验收要求

v1.0.3 不能只在临时空数据目录验收。收口前必须补齐以下证据：

- 明确当前浏览器和后端连接的 `CODEASK_DATA_DIR`。
- 对真实用户数据目录或其完整备份先做备份，再执行升级。
- 记录升级前数据库 revision 和升级后 revision。
- 验证原有 `features`、`llm_configs`、`repos`、`system_settings`、Wiki、会话和报告数据仍然可见。
- 验证 admin、普通用户、匿名访客的登录与权限行为不会覆盖原有业务数据。
- 浏览器 E2E 如连接真实数据目录，只能执行只读检查或已验证可清理的临时写操作。

## 人工验收输出要求

最终给用户的人工验收列表必须至少包含：

- 升级前备份路径。
- 实际使用的数据目录。
- 数据库 revision 变化。
- 自动化测试命令与结果。
- 需要用户手动点击验证的页面、账号、预期结果。
- 剩余风险和未覆盖边界。

## 剩余人工验收

- reasoning 请求侧已完成第一版收口：`request_options` 成为 provider-neutral 请求选项入口，旧 vendor-style profile 只作为兼容 alias 保留，不再作为新能力扩张方式。
- 已完成 `references/opencode` 源码学习和版本内落地记录，当前实现遵循“用户选择 OpenAI / Anthropic 消息格式，后端不按 URL 或模型名自动推断协议”的边界。
- 仍需用户在真实浏览器中完成人工验收，并确认 v1.0.3 可以结束。
- 人工验收通过后提交并推送 v1.0.3 收尾改动。
