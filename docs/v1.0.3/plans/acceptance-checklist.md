# v1.0.3 鉴权与访问控制验收清单

> 状态：自动化与真实数据验收已完成，等待人工复核
> 版本：v1.0.3
> 范围：登录、自动注册、匿名会话、特性管理员、Wiki/特性/全局配置权限、附件上传开关、审计、升级兼容、真实数据验收
> 项目级验收规则：见 `../../DEVELOPMENT_ACCEPTANCE.md`

## 0. 验收原则

本清单是 v1.0.3 的收口门禁，不允许只凭临时库、mock 数据或局部接口验证就声明版本完成。

状态标记：

- `[x]` 已实现并拿到测试或真实验收证据。
- `[ ]` 未完成、未验收或已发现问题。
- `[~]` 已部分覆盖，但还缺真实数据或人工浏览器收口。

v1.0.3 收口前必须同时满足：

- 自动化测试覆盖匿名、普通用户、admin、特性管理员和未授权写接口。
- 至少一次对真实数据目录或完整旧版本备份执行升级验收。
- 至少一次真实浏览器 E2E 直接连到真实后端，不经过临时空库。
- 输出可供用户逐项点击的人工验收列表，并记录剩余风险。

## 1. 身份与登录

- [x] 未登录访客可以直接进入会话页、发起会话、查看特性页、查看 Wiki 页。
- [x] 登录页复用注册：用户名不存在时自动注册并登录，存在时校验密码。
- [x] 用户名、密码都大小写敏感。
- [x] 非 admin 用户密码至少 6 位。
- [x] 登录成功后返回登录前页面，而不是固定跳转。
- [x] admin 登录不迁移匿名会话。
- [x] 普通用户登录会迁移当前浏览器匿名会话。
- [x] 修改密码后不应强制退出当前登录态。
- [x] 退出登录后，页面身份、会话列表和缓存应立即刷新到匿名状态。
- [x] 登录页会缓存上一次成功登录的用户名。
- [x] 普通用户设置页中，用户名输入框被退格清空后，不应自动回填当前用户名；已有前端隔离测试覆盖，并在 2026-05-11 重新执行。

## 2. 权限模型

- [x] 只有 admin 可以创建特性。
- [x] 非 admin 点击“添加特性”会得到明确提示，不会静默失败。
- [x] 只有 admin 可以添加或删除特性管理员。
- [x] 特性管理员可以管理自己特性的配置、Wiki、报告、仓库和 Skill。
- [x] 特性管理员不能管理其它特性，也不能管理管理员列表。
- [x] 普通用户和匿名用户可查看特性页、Wiki 页，但无写入口或写接口权限。
- [x] 全局设置、全局仓库、全局 LLM、用户管理只允许 admin。
- [x] 会话附件上传受全局开关控制；关闭后前端保留入口，但点击会提示不可用。
- [x] 非特性管理员生成的报告，仍可保存到特性问题草稿中。

## 3. 数据迁移与升级兼容

- [x] 升级前对真实数据目录完成备份。
- [x] 升级前记录数据库 revision。
- [x] 升级后 revision 从 `0024` 变为 `0025`。
- [x] 升级迁移只新增 `users`、`auth_sessions`、`feature_admins` 相关结构，没有清理业务数据。
- [x] 升级后原有 `features`、`llm_configs`、`repos` 计数保持不变。
- [x] 升级后能看到原有真实特性数据，如 `AnythingLLM Reference`、`小米`。
- [x] 升级后能看到原有真实 LLM 配置和仓库配置。
- [x] 后端当前实际连接的数据目录已明确记录，避免浏览器误连临时库。

## 4. 自动化测试门禁

- [x] 后端定向鉴权测试通过。
- [x] 后端 unit + integration 全量回归通过。
- [x] 前端 Vitest 全量通过。
- [x] 前端 TypeScript 类型检查通过。
- [x] 临时库 Playwright 鉴权 E2E 通过。
- [x] 新增真实数据专用 Playwright 配置，默认不自启临时库。
- [x] 真实数据 Playwright 验收只做只读或可审计检查，不批量改写业务数据。

## 5. 真实数据浏览器 E2E

- [x] 匿名访问特性页时，能看到真实特性列表。
- [x] 匿名访问 Wiki 页时，能打开真实特性下的 Wiki 文档。
- [x] 匿名访问 Wiki 预览时，相对资源图片可以渲染。
- [x] 匿名访问设置页时，显示“未登录访客”。
- [x] admin 登录后，能看到真实全局 LLM 列表。
- [x] admin 登录后，能看到真实仓库列表。
- [x] admin 退出后，界面身份立即回到未登录状态。
- [x] 退出后重新打开登录页，会预填上一次成功登录用户名。
- [x] Wiki、设置等页面刷新后，仍停留在当前路由。

## 6. 真实数据验收记录（2026-05-11）

### 6.1 数据与迁移

- [x] 真实数据目录：`/home/hzh/.codeask`
- [x] 升级前备份：`/home/hzh/backups/codeask-v103-preupgrade-20260511-093324.tar.gz`
- [x] 升级前 revision：`0024`
- [x] 升级后 revision：`0025`
- [x] 升级前后计数一致：
  - `features = 8`
  - `llm_configs = 7`
  - `repos = 5`
  - `system_settings = 0`
- [x] 升级后新增：
  - `users = 1`
  - `feature_admins = 0`

### 6.2 自动化命令结果

- [x] `uv run pytest tests/unit/test_auth_passwords.py tests/unit/test_auth_sessions.py tests/unit/test_feature_permissions.py tests/integration/test_auth_users_api.py tests/integration/test_feature_admins_api.py tests/integration/test_authz_features_api.py tests/integration/test_authz_wiki_api.py tests/integration/test_attachment_upload_gate.py tests/integration/test_audit_authz_api.py -v`
- [x] `uv run pytest tests/unit tests/integration -q`
- [x] `corepack pnpm --dir frontend test:run`，2026-05-11 后续复跑结果：`40 个测试文件 / 201 个用例通过`
- [x] `corepack pnpm --dir frontend typecheck`
- [x] `corepack pnpm --dir frontend test:e2e -- auth-access-control.spec.ts route-refresh.spec.ts wiki-tail.spec.ts auth-session-switch.spec.ts --project=chromium`
- [x] `corepack pnpm --dir frontend exec playwright test -c playwright.realdata.config.ts e2e/realdata-auth-readonly.spec.ts --project=chromium`，2026-05-11 结果：`2 passed`
- [x] `corepack pnpm --dir frontend test:run -- settings-page.test.tsx -t "allows clearing the username draft without restoring the current username"`，2026-05-11 结果：通过（命令实际复跑了整套前端测试）

### 6.3 真实数据样本

- [x] 真实特性样本：`AnythingLLM Reference`、`Browser Smoke`、`小米`
- [x] 真实 LLM 样本：`火山-Anthropic-glm-5.1`、`DeepSeek-OpenAI`
- [x] 真实仓库样本：`E2E claude-code 1778123017269`
- [x] 真实 Wiki 文档样本：`小米 / 小米病历`

## 7. 人工验证范围

- [ ] 普通用户登录后修改用户名、修改密码、退出后重新登录的完整链路。
- [ ] 特性管理员实际被授权后，对指定特性有写权限、对未授权特性无写权限。
- [ ] 附件上传全局开关在真实浏览器中的 UI 提示文案和阻断表现。

## 8. 输出要求

最终人工验收列表必须包含：

- 备份路径；
- 实际数据目录；
- revision 变化；
- 自动化命令和结果；
- 用户需要逐项点击的页面与预期；
- 未覆盖边界和剩余风险。

## 9. 本版本追加收口项

这项是 2026-05-11 新增的版本内修复要求，不能再误挂到 v1.0.2。

- [x] 完成 `references/opencode` 的多模型 provider / protocol / reasoning / compaction 源码学习，并形成版本内学习记录：`../specs/opencode-provider-protocol-lessons.md`。
- [x] reasoning 请求参数构造不得继续以厂商命名 profile 作为长期主接口。已新增 `codeask.llm.request_options`，旧 `volcengine_thinking` / `vllm_enable_thinking` / `custom_json` 只作为兼容 alias 归一化到 provider-neutral request patch。
- [x] 后端不得根据模型名、厂商名或 `base_url` 域名去猜 reasoning 参数格式。当前新增路径只读取显式 profile / patch / metadata，不根据模型名或 URL 推断。
- [x] OpenAI-compatible / Anthropic 的 reasoning 请求差异必须收敛到协议 serializer，而不是散落在业务层条件分支中。第一版已把请求构造收敛到 `request_options`，后续完整 protocol serializer 拆分仍需继续。
- [x] 未知模型默认保守：未显式声明能力描述或 request patch 时，不自动启用 reasoning 请求参数。
- [x] 对私有网关仍需保留通用 request patch 扩展口，但 patch 必须是通用 JSON/path 机制，不能再次新增 vendor-style profile 名称。当前以 `request_patch` / legacy `custom_json` 表达。
- [x] `request_patch`、`reasoning_effort`、`thinking` 等请求侧细节不得暴露在普通用户或管理员的 LLM 配置表单中；用户配置应保持接近 opencode 体验，只填写配置名称、接口协议、Base URL、API Key、模型名称和启用状态。接口协议只保留 `OpenAI` / `Anthropic` 两个用户可见选项，其中 `OpenAI` 表示 OpenAI Chat Completions / OpenAI-compatible 消息格式，不限定 OpenAI 官方服务。
- [x] 协议选择不得通过 URL 域名、URL 路径、模型名或厂商名自动推断；用户选择 `OpenAI` 就按 OpenAI 消息格式请求，用户选择 `Anthropic` 就按 Anthropic Messages 请求。历史 `openai_compatible` 配置仅作为内部兼容值保留，前端展示和编辑时归一为 `OpenAI`。
- [x] 内部消息结构需要能表达结构化 reasoning part 或等价 metadata，以支持按协议要求回放 `reasoning_content` / `reasoning_details` / signature，而不是把 reasoning 混入普通 answer text。已新增 `ReasoningBlock`。
- [x] OpenAI-compatible reasoning history policy 必须由配置明确声明；未声明时不根据模型名自动回放。已支持 `metadata.reasoning_history.mode = openai_interleaved` 且 `field = reasoning_content | reasoning_details` 时才回放。
- [x] Agent 行动轨迹可展示 reasoning 观察摘要，例如字段名、chunk 数、长度、redacted 标记，但不能展示 raw reasoning 原文。既有 `reasoning_observed` 测试继续覆盖。
- [x] 报告生成、标题生成、普通上下文压缩默认不读取 raw reasoning。当前新增 `ReasoningBlock` 默认不会序列化进 visible content；报告/标题仍基于可见文本。
- [x] 补齐第一版自动化测试：
  - 协议族 serializer 的默认输出；
  - 能力描述到最终请求 payload 的映射；
  - 未知模型/未知网关不猜参数；
  - 显式 request patch 的透传；
  - 历史 vendor profile 到新配置形态的兼容迁移或失败提示。
  - `reasoning_content` / `reasoning_details` 历史回放策略。
  - raw reasoning 不进入报告和标题生成。
- [x] 补齐真实前后端 E2E 和真实 LLM 配置验证，覆盖 OpenAI 消息格式、Anthropic 消息格式、全局配置和用户配置。
- [x] 前端设置页已补充反向验收：创建/编辑 LLM 配置时不展示 `Reasoning 请求方式`、`Reasoning 请求 JSON`，编辑已有配置时不提交隐藏 reasoning 字段，避免误覆盖内部适配配置。
- [x] 前端设置页补充协议选项验收：创建/编辑 LLM 配置时不展示 `OpenAI Compatible`，只展示 `OpenAI` 和 `Anthropic`；历史 `openai_compatible` 在列表中显示为 `OpenAI`，避免把兼容实现细节暴露给用户。

### 9.1 本轮后端切片验证记录

- [x] `uv run pytest tests/unit/test_agent_chat_runtime_reasoning.py tests/unit/test_llm_request_profiles.py tests/unit/test_llm_types.py tests/unit/test_llm_client_adapter.py tests/unit/test_llm_gateway.py -v`，51 passed。
- [x] `corepack pnpm --dir frontend test:run -- settings-page.test.tsx -t "creates a personal LLM config from user settings|edits, toggles, and deletes existing global LLM configs"`，命令实际复跑前端全量 Vitest；后续复跑结果见 9.2 / 9.3，已更新为 40 个测试文件 / 201 个用例通过。
- [x] 已使用真实数据目录 `/home/hzh/.codeask` 做真实 LLM 配置调用验证；后续复跑覆盖 7 个启用配置，OpenAI 消息格式 / Anthropic 消息格式均可连通，结构化 reasoning 已隔离，真实浏览器会话 E2E 已补齐。

### 9.2 真实测试记录（2026-05-11）

- [x] `uv run pytest tests/unit/test_session_report_generation.py tests/unit/test_agent_chat_runtime_reasoning.py tests/unit/test_llm_request_profiles.py tests/unit/test_llm_types.py tests/unit/test_llm_client_adapter.py tests/unit/test_llm_gateway.py -v`，57 passed。
- [x] `corepack pnpm --dir frontend test:run -- reasoning-leak-guard.test.ts settings-page.test.tsx`，命令实际复跑前端全量 Vitest：40 个测试文件 / 201 个用例通过。
- [x] `corepack pnpm --dir frontend typecheck`，TypeScript 检查通过。
- [x] `CODEASK_RUN_REAL_DATA_E2E=1 ... playwright.realdata.config.ts e2e/realdata-auth-readonly.spec.ts --project=chromium`，真实数据浏览器只读 E2E：2 passed。
- [x] 真实 LLM 配置调用验证：`/home/hzh/.codeask` 中 7 个启用配置全部可返回可见答案，覆盖全局配置和用户配置，`marker_leaks=0`，`empty_answers=0`。
- [x] 真实浏览器会话链路验证：Vite `5173` 连接后端 `8000`，新建会话并询问 `用一句话说明 Python list 和 tuple 的区别。`，页面出现答案关键词，Agent 行动轨迹可见，`<think>` / `</think>` / `<tool_call>` 标记未泄漏，浏览器 console error 为 0。
- [x] `git diff --check` 通过。

### 9.2.1 离线部署模型 `<think>` 泄漏修复记录（2026-05-11）

- [x] 根因：部分私有 OpenAI-compatible 模型服务把 raw thinking 混入 `delta.content`，而不是返回结构化 `reasoning_content`；旧实现只在前端直播流遮蔽，后端仍可能把原始 `<think>` 文本写入历史、报告上下文和后续会话上下文。
- [x] 后端补充极窄 Content Leak Guard：仅把 `content` 中的 `<think>...</think>` 正文泄漏转换成 `reasoning_delta(content_think_tag)`，不作为主协议解析方案，不扩展到任意私有标签。
- [x] 前端 Leak Guard 同一轮只追加一次 `reasoning_leak_detected` 诊断，避免长思考链刷出大量 Agent 事件。
- [x] `uv run pytest tests/unit/test_llm_client_adapter.py -q`，15 passed。
- [x] `corepack pnpm --dir frontend exec vitest run tests/reasoning-leak-guard.test.ts`，7 passed。

### 9.3 协议选择 UI 收口验证（2026-05-11）

- [x] `corepack pnpm --dir frontend test:run -- settings-page.test.tsx`，命令实际复跑前端全量 Vitest：40 个测试文件 / 201 个用例通过。
- [x] `corepack pnpm --dir frontend typecheck` 通过。
- [x] `git diff --check` 通过。
- [x] 设置页创建和编辑 LLM 配置只展示 `OpenAI` / `Anthropic`，不展示 `OpenAI Compatible`。
- [x] 历史 `openai_compatible` 配置在列表中显示为 `OpenAI`，编辑时协议选择归一为 `OpenAI`。
- [x] 使用真实数据目录 `/home/hzh/.codeask` 逐个验证全部启用 LLM 配置：7 个配置全部真实请求通过，覆盖 OpenAI 消息格式、Anthropic 消息格式、全局配置和用户配置；结果 `passed=7 failed=0 marker_leaks=0 empty_answers=0`。
