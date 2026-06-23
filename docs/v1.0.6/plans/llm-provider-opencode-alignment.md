# LLM 配置对齐 opencode provider 目录

> 状态：已规划，待实施（计划经用户批准，2026-06-23）
> 版本归属：**v1.0.6**
> 主题：把 LLM 配置从 CodeAsk 自维护的窄抽象（`protocol` + 7 个手维护 opencode `profile`）改成**结构化 provider 目录**——存 `provider_id`（models.dev id）+ `model_id` + `api_key` + 可选 `base_url`/`npm`，直接复用 opencode 通过 models.dev 适配的约 144 个 provider。
> 关联：`src/codeask/llm/`、`src/codeask/agent/opencode_compat/`、`src/codeask/api/llm_configs.py`、`src/codeask/db/models/llm.py`、`frontend/src/components/settings/llm/`、`CLAUDE.md`

## 1. 背景与触发

CodeAsk 现在用一层自维护窄抽象描述 LLM 配置：`protocol ∈ {openai, anthropic, openai_compatible}` + 7 个手维护的 opencode `profile`（npm 包 + baseURL 模式 + auth 模式）。展开读源码后确认的关键事实：

- opencode（已装 1.14.48）自己通过 **models.dev 目录**原生适配约 **144 个 provider**，运行时自解析 npm/baseURL。CodeAsk 这层抽象把它废掉了，只能用那 7 个 profile，**永远落后、还限制可用 provider**。
- 同一份 `LLMConfig` 被两个运行时消费：
  - **opencode（主对话）**——线上唯一 Agent 后端（`settings.agent_backend: Literal["opencode"]`）。
  - **native LiteLLM 网关**——仅 3 个轻量用途：会话标题生成（`sessions/title_generation.py`）、报告草稿（`sessions/report_generation.py`）、连通测试。
- 一整套 `native_backend`（orchestrator + scope_detection / sufficiency_judgement / code_investigation / answer_finalization 四个 stage）是 **死代码**：被 `Literal["opencode"]` 锁死，未被 api/app/sessions 任何 import，orchestrator 从不实例化。
- 死字段：`max_tokens` / `temperature` / `rpm_limit` / `quota_remaining` 全仓库**无运行时读取点**（标题/报告用硬编码值；主对话由 opencode 自管）。前端表单也未暴露。
- `name` 唯一约束是**全局唯一**（跨 scope/owner），多用户个人配置会误撞 409。

结论：**砍掉中间窄抽象、改用 provider 目录 id 直通**。手维护的东西从"7 个 profile（还限制 provider）"缩成"十来条纯改名映射（不限制 provider）"。

## 2. 已定决策（用户确认）

1. **结构化 provider 目录**（非粘原始 JSON、非扩 profile 表）。
2. **保留 LiteLLM** 作为标题/报告 + 连通测试的轻量工具；不再当平行 Agent 后端。
3. **删除 `native_backend` 整套死代码**。
4. **不迁移旧数据，要求重配**。
5. **连通测试保留**（现有 `opencode_compat.test_llm_config` 已实发探针请求验证主路径）。

### 顺带捆绑的修正

- 删 4 个死字段 `max_tokens`/`temperature`/`rpm_limit`/`quota_remaining`。
- `name` 唯一约束改为 `(scope, owner_subject_id, name)`。
- 迁移里清空 `llm_configs`/`llm_runtime_adapters` 现有行（配合"要求重配"，避免半残配置残留）。

## 3. 对齐策略（核心，回答"两边 provider 能不能确定对齐"）

实测：models.dev 144 个 vs `litellm.provider_list` 133 个，**纯同名交集仅 29 个**——静态层面**不能保证全对齐**。但两条链路对"对齐"的需求不同：

- **opencode 主链路：零映射**。写裸 `provider_id`（models.dev 全量原生支持），opencode 自解析 npm/baseURL。仅当用户配自定义 provider（带 `provider_npm`/`base_url`）才显式写 npm+baseURL。
- **LiteLLM 辅助链路**：新增 `provider_catalog`，把 `provider_id` 映射成 litellm provider 前缀：
  1. **同名直通**（对照 `litellm.provider_list`，运行时取，不手维护）；
  2. **小 override 表**（手维护约 10–15 条改名项：`google→gemini`、`amazon-bedrock→bedrock`、`moonshotai→moonshot`、`zai/zhipuai→…` 等）；
  3. **兜底 `openai`**（OpenAI 兼容端点）+ `base_url`，覆盖那 100+ 聚合器/网关。
- **运行时自证**：连通测试实发请求；映射错只会让 title/report 降级，主对话由 opencode 独立保证 → 影响面被隔离。

## 4. 实施阶段

### Phase 1 — provider 目录基础设施（后端，纯新增）
- 新建 `src/codeask/llm/provider_catalog.py`：
  - `litellm_provider_for(provider_id) -> str`：同名（查 `litellm.provider_list`）→ override 表 → `"openai"` 兜底。
  - `OVERRIDE: dict[str,str]`（models.dev → litellm 改名项，约十余条）。
  - UI provider 列表源：**committed models.dev 快照** `src/codeask/llm/data/models_dev_providers.json`（仅 `id`+`name`，小体积；刷新机制留后续），附加 `custom` 入口（npm+baseURL）。
- 单测：override/同名/兜底分支；快照可加载。

### Phase 2 — 数据模型 + 迁移
- `src/codeask/db/models/llm.py`：删 `protocol`/`opencode_provider_profile`/`max_tokens`/`temperature`/`rpm_limit`/`quota_remaining`；加 `provider_id`（非空）、`provider_npm`（可空）。保留 `model_name`/`base_url`/`api_key_encrypted`/`name`/`scope`/`owner_subject_id`/`is_default`/`enabled`/`reasoning_profile*`/provider 测试状态列 + `runtime_adapters`。改 `name` 唯一约束为 `(scope, owner_subject_id, name)`。
- 新增 alembic 修订（仿 `alembic/versions/20260602_0033_*.py` 命名）：drop/add 列 + 改约束 + 清空 `llm_configs`/`llm_runtime_adapters`。

### Phase 3 — opencode 配置生成（去 profile）
- `src/codeask/agent/opencode_compat/profiles.py`：删 7 个 `OpenCodeProviderProfile` + `select_provider_profile` + `provider_profile_options/by_id`，精简为 provider key 用 `provider_id`、自定义时给 npm。
- `config.py` `build_opencode_provider_entry`：产出 `{ "options": {"apiKey", 可选 "baseURL"}, "models": {model: {"tool_call"}} }`，**仅当 `provider_npm` 存在时**才加 `"npm"`；provider 块 key = `provider_id`（自定义则清洗 id）。
- `backend.py`：`_write_provider_test_config`/`_config_input`/`_with_profile` 去 profile 参数链；连通测试改裸 provider 写法（保持探针逻辑 `_wait_for_probe_result` 不变）。

### Phase 4 — native 网关消费 provider_id
- `src/codeask/llm/gateway.py` `ClientFactory`：不再按 `protocol` 三分支；按 `provider_catalog.litellm_provider_for(provider_id)` 构建 litellm 模型串。`_runtime_config_from_metadata`（访客配置）用 `provider_id` 替 `protocol`。
- `src/codeask/llm/client.py`：collapse `OpenAIClient/OpenAICompatibleClient/AnthropicClient` 为按 litellm provider 前缀路由的统一客户端（保留 reasoning kwargs；anthropic `/v1/messages` 归一化按映射后 provider 判定）。
- `src/codeask/llm/repo.py`：`LLMConfigInput/Public/WithSecret`、`_to_secret`、`list` 字段同步。

### Phase 5 — API schema / service / routes
- `src/codeask/api/schemas/llm_config.py`：Create/Update/Response 用 `provider_id`（+ 可选 `provider_npm`）替 `protocol`；删 4 个死字段。
- `src/codeask/llm/api_service.py` + `src/codeask/api/llm_configs.py`：CRUD 字段同步；`_draft_config_from_*`/`update_scoped_config` 合并逻辑改 `provider_id`（**保留"留空 api_key 复用旧值"**）；`runtime_fields_changed` 触发条件改看 `provider_id`/`model_name`/`base_url`/`api_key`。
- `/llm-runtime-profiles` 替换为 **`/llm-providers`**（返回 models.dev 快照 provider 列表 + custom），供前端下拉。

### Phase 6 — 前端
- `settings-types.ts`：删 `LlmProtocol`/profile 类型；payload 加 `provider_id`/`provider_npm`。
- `LlmConfigForm.tsx` / `LlmConfigEditForm.tsx`：把"协议"+"Agent 适配方式"两个 select 换成 **provider 下拉**（拉 `/llm-providers`）+ model 输入 + key + 可选 base_url（custom 时显示 npm 输入）。保留测试按钮。
- `LlmConfigManager.tsx`：`runtimeProfiles` 查询换成 `providers` 查询。
- `LlmConfigList.tsx`：展示 `provider_id` 取代 protocol/profile。
- `frontend/src/types/api.ts` + `lib/api.ts`：类型与接口路径同步。

### Phase 7 — 删死代码
- 删 `src/codeask/agent/native_backend/` 整个目录及其专属测试。
- ⚠️ 区分：**保留** `src/codeask/agent/chat_runtime/`（共享，`messages.py`/`sessions.py` 用 `chat_runtime.events.ChatRuntimeEvent`）；只删 `native_backend.chat_runtime`。
- grep 确认无残留 import。

## 5. 关键复用点（已存在，勿重造）
- `litellm.provider_list`（133 项，运行时取）——provider 目录真值源之一。
- `opencode_compat.test_llm_config` + `_wait_for_probe_result`——连通测试已实发请求，保留。
- repo "留空 api_key 复用旧值"（`update_scoped_config` 的 `fields` 合并）——保留。
- `is_default` 的 partial unique index、Fernet 加密落盘——保留。

## 6. 验证
- 静态：`corepack pnpm exec tsc --noEmit` + `eslint`（frontend/）；`ruff check`（repo 根，去代理）。
- 单测：`provider_catalog`（映射分支）、opencode 配置生成（裸 provider id / 自定义 npm）、gateway client 构建、API CRUD（provider_id）、连通测试；删 `native_backend` 测试后整体 `pytest` 绿。
- 端到端（去代理重启后端 `env -u *proxy* uv run codeask`）：
  1. LLM 设置页新建：provider 下拉选 `deepseek` + model + key → 测试连通（opencode 实发探针）通过。
  2. 发起对话，确认主对话用该配置正常出字。
  3. 触发标题生成（litellm 路径，deepseek 同名直通）确认能生成。
  4. 配 override 项（如 `google`），确认 litellm 走 `gemini` 不报 unknown provider。
  5. 配兜底项（某聚合器）+ base_url，确认 openai-compatible 兜底可用。
