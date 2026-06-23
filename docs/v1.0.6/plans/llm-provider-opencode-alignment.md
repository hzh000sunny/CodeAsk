# LLM 配置对齐 opencode provider 目录

> 状态：已规划，待实施（计划经用户批准，2026-06-23；2026-06-23 二次讨论后改为「1:1 照搬 opencode 配置能力」）
> 版本归属：**v1.0.6**
> 主题：把 LLM 配置从 CodeAsk 自维护的窄抽象（`protocol` + 7 个手维护 opencode `profile`）改成**完全对齐 opencode 的 provider 配置能力**——两种模式：①目录 provider（models.dev 已知 provider，只给 key）②自定义 provider（自建网关 / 三方中转站，恒为 `@ai-sdk/openai-compatible`，给 baseURL + key + models[] + headers[]）。不发明任何 opencode 没有的抽象。
> 关联：`src/codeask/llm/`、`src/codeask/agent/opencode_compat/`、`src/codeask/api/llm_configs.py`、`src/codeask/db/models/llm.py`、`frontend/src/components/settings/llm/`、`CLAUDE.md`
> opencode 配置格式真值源（已 checkout）：`/home/hzh/wiki/opencode/packages/app/src/components/dialog-custom-provider-form.ts`、`dialog-connect-provider.tsx`、`dialog-custom-provider.tsx`、`dialog-select-provider.tsx`。

## 1. 背景与触发

CodeAsk 现在用一层自维护窄抽象描述 LLM 配置：`protocol ∈ {openai, anthropic, openai_compatible}` + 7 个手维护的 opencode `profile`（npm 包 + baseURL 模式 + auth 模式）。展开读源码后确认的关键事实：

- opencode（已装 1.14.48）自己通过 **models.dev 目录**原生适配约 **144 个 provider**，运行时自解析 npm/baseURL。CodeAsk 这层抽象把它废掉了，只能用那 7 个 profile，**永远落后、还限制可用 provider**。
- 同一份 `LLMConfig` 被两个运行时消费：
  - **opencode（主对话）**——线上唯一 Agent 后端（`settings.agent_backend: Literal["opencode"]`）。
  - **native LiteLLM 网关**——仅 3 个轻量用途：会话标题生成（`sessions/title_generation.py`）、报告草稿（`sessions/report_generation.py`）、连通测试。
- 一整套 `native_backend`（orchestrator + scope_detection / sufficiency_judgement / code_investigation / answer_finalization 四个 stage）是 **死代码**：被 `Literal["opencode"]` 锁死，未被 api/app/sessions 任何 import，orchestrator 从不实例化。
- 死字段：`max_tokens` / `temperature` / `rpm_limit` / `quota_remaining` 全仓库**无运行时读取点**（标题/报告用硬编码值；主对话由 opencode 自管）。前端表单也未暴露。
- `name` 唯一约束是**全局唯一**（跨 scope/owner），多用户个人配置会误撞 409。

结论：**砍掉中间窄抽象、改用 provider 目录 id 直通，并 1:1 镜像 opencode 自身的可视化配置能力。**

## 2. opencode 的配置真相（决策依据）

读 opencode 源码确认它把 provider 配置切成**两条完全独立的流程**，二者不可混：

### ① 目录连接（`dialog-connect-provider.tsx`）
从 models.dev 列表选一个**已知 provider**。opencode 调 `provider.auth()` 拿该 provider 支持的鉴权方式（OAuth / API key…）。**无 npm / baseURL 输入框**——目录里已有。非 OpenAI 协议（Anthropic / Google / Bedrock / OpenRouter…）**只能从这条路进**。

### ② 自定义（`dialog-custom-provider-form.ts`）
自建网关 / 三方中转站走这里。`FormState` 字段（全部照搬）：

| 字段 | 约束 | 说明 |
|---|---|---|
| `providerID` | 正则 `^[a-z0-9][a-z0-9-_]*$`、唯一 | 自定义 slug |
| `name` | 必填 | 显示名 |
| `baseURL` | 必填、必须 `^https?://` | 网关入口（含不含 `/v1` 用户自负） |
| `apiKey` | —— | 密钥 |
| `models[]` | id+name 行列表，可增删，id 去重 | 该 provider 透传的模型 |
| `headers[]` | key+value 行列表，可增删，key 去重 | 额外请求头 |

**关键：`npm` 写死 `@ai-sdk/openai-compatible`（常量，第 2 行 + 输出第 140 行），自定义 provider 永远是 OpenAI 兼容，没有协议/adapter 选择。** 鉴权怪癖（`Authorization: Bearer` / `x-api-key` 等）靠 `headers[]` 解决，不靠切 adapter。输出形状：

```json
{ "<slug>": { "npm": "@ai-sdk/openai-compatible", "name": "...",
              "options": { "baseURL": "...", "headers": {...}? },
              "models": { "<id>": { "name": "..." } } } }
```

> opencode 还支持 `apiKey` 的 `{env:VAR}` 语法（引用环境变量、走它自己的 keychain）。CodeAsk 是托管多用户应用、Fernet 加密落盘，**不采纳 `{env:}`**，直接存密文。

## 3. 已定决策（用户确认）

1. **完全对齐 opencode 的配置能力**，两模式（目录 / 自定义），不发明 opencode 没有的抽象。
2. **自定义 provider 恒为 `@ai-sdk/openai-compatible`**——砍掉 adapter 下拉、砍掉 7 个 profile。协议多样性全部走目录路径。
3. **照搬 opencode 自定义表单的 `headers[]`**（opencode 的原生字段，非我们另加的逃生口）；`models[]` 因 CodeAsk 维持「一配置一模型」(见 §3 已定取舍)固定为单元素，不暴露多模型增删行。
4. **保留 LiteLLM** 作为标题/报告 + 连通测试的轻量工具；不再当平行 Agent 后端。
5. **删除 `native_backend` 整套死代码**。
6. **不迁移旧数据，要求重配**。
7. **连通测试保留**（现有 `opencode_compat.test_llm_config` 已实发探针请求验证主路径）。

### 顺带捆绑的修正
- 删 4 个死字段 `max_tokens`/`temperature`/`rpm_limit`/`quota_remaining`。
- `name` 唯一约束改为 `(scope, owner_subject_id, name)`。
- 迁移里清空 `llm_configs`/`llm_runtime_adapters` 现有行（配合"要求重配"，避免半残配置残留）。

### 已定取舍（用户 2026-06-23 确认）
- **保留「一配置一模型」（方案 A）**：一条 `LLMConfig` 仍 = 一个 provider + 一个 `model_name` + 一个 key，与现状设置界面一致，**不**引入 `models_json`/`default_model`，选择语义不变。opencode 那边生成时把它当「单模型 provider 块」写。自定义模式仍照搬 slug/baseURL/`headers[]`，仅 `models` 固定为单元素（即 `model_name`），不暴露多模型增删行。
- **reasoning 维持 config 级**（作用于该 config 的唯一模型），不做 per-model reasoning。

## 4. 双运行时对齐策略

实测：models.dev 144 个 vs `litellm.provider_list` 133 个，纯同名交集仅 29 个——但两条链路对"对齐"的需求不同：

- **opencode 主链路：零映射**。目录模式写裸 `provider_id`（opencode 自解析）；自定义模式写 `@ai-sdk/openai-compatible` + baseURL + headers。
- **LiteLLM 辅助链路**（用 config 的 `model_name`）：
  - **目录模式**：`provider_catalog.litellm_provider_for(provider_id)`——同名直通（查 `litellm.provider_list`，运行时取）→ 小 override 表（`google→gemini`、`amazon-bedrock→bedrock`、`moonshotai→moonshot`、`zai/zhipuai→…`，约十余条）→ 兜底 `openai`。
  - **自定义模式**：**恒 `openai/<model_name>` + `api_base=baseURL`（+ extra_headers）**，连映射都不需要，天然对齐。
- **运行时自证**：连通测试实发请求；映射错只让 title/report 降级，主对话由 opencode 独立保证 → 影响面隔离。

## 5. 实施阶段

### Phase 1 — provider 目录基础设施（后端，纯新增）
- 新建 `src/codeask/llm/provider_catalog.py`：
  - `litellm_provider_for(provider_id) -> str`：同名（查 `litellm.provider_list`）→ override 表 → `"openai"` 兜底。
  - `OVERRIDE: dict[str,str]`（models.dev → litellm 改名项，约十余条）。
  - UI provider 列表源：**committed models.dev 快照** `src/codeask/llm/data/models_dev_providers.json`（仅 `id`+`name`，小体积；刷新机制留后续）。自定义模式不在此列表内、是独立入口。
- 单测：override/同名/兜底分支；快照可加载。

### Phase 2 — 数据模型 + 迁移（provider-centric）
- `src/codeask/db/models/llm.py` `LLMConfig`：
  - **删**：`protocol`、`opencode_provider_profile`、`max_tokens`、`temperature`、`rpm_limit`、`quota_remaining`。
  - **加**：`mode`（`catalog`|`custom`）、`provider_id`（目录=models.dev id；自定义=slug）、`headers_encrypted`（自定义 headers[]，含密则 Fernet 加密整块；可空）。
  - **保留**：`model_name`（仍一配置一模型）、`name`、`scope`、`owner_subject_id`、`base_url`（自定义必填、目录可选覆盖）、`api_key_encrypted`、`is_default`、`enabled`、`reasoning_profile*`、`opencode_provider_*` 测试状态列、`runtime_adapters`。
  - `npm` 不入库（自定义恒 `@ai-sdk/openai-compatible`，生成时常量）。
  - `name` 唯一约束 → `(scope, owner_subject_id, name)`。
- 新增 alembic 修订（仿 `alembic/versions/20260602_0033_*.py` 命名）：drop/add 列 + 改约束 + 清空 `llm_configs`/`llm_runtime_adapters`。

### Phase 3 — opencode 配置生成（去 profile）
- `src/codeask/agent/opencode_compat/profiles.py`：删 7 个 `OpenCodeProviderProfile` + `select_provider_profile` + `provider_profile_options/by_id`。`LLMConfigLike` 改用 `mode`/`provider_id`/`models`/`headers` 替 `protocol`/`opencode_provider_profile`。
- `config.py` `build_opencode_provider_entry`（`models` 块恒单元素 = 该 config 的 `model_name`）：
  - **目录**：`{ <provider_id>: { options:{apiKey, baseURL?}, models:{ <model_name>:{name,tool_call:true} } } }`。
  - **自定义**：`{ <slug>: { npm:"@ai-sdk/openai-compatible", name, options:{baseURL, apiKey, headers?}, models:{ <model_name>:{...} } } }`。
  - provider 块 key = `provider_id`（自定义即 slug，已正则校验）；每条 config 自成一个 provider 块。
- `backend.py`：`_write_provider_test_config`/`_config_input`/`_with_profile` 去 profile 参数链；连通测试用 `model_name` 探针，保持 `_wait_for_probe_result` 不变。

### Phase 4 — native 网关消费新字段
- `src/codeask/llm/gateway.py` `ClientFactory`：不再按 `protocol` 三分支；目录模式按 `provider_catalog.litellm_provider_for(provider_id)`、自定义模式恒 `openai/` + `api_base`，配 `model_name` 构 litellm 模型串。`_runtime_config_from_metadata`（访客配置）同步。
- `src/codeask/llm/client.py`：collapse `OpenAIClient/OpenAICompatibleClient/AnthropicClient` 为按 litellm provider 前缀路由的统一客户端（保留 reasoning kwargs；headers 透传 `extra_headers`）。
- `src/codeask/llm/repo.py`：`LLMConfigInput/Public/WithSecret`、`_to_secret`、`list` 字段同步。

### Phase 5 — API schema / service / routes
- `src/codeask/api/schemas/llm_config.py`：Create/Update/Response 用 `mode`/`provider_id`/`model_name`/`headers` 替 `protocol`；删 4 个死字段。slug 正则、baseURL `^https?://`、headers key 去重，在 schema 层校验（对齐 opencode `validateCustomProvider`）。
- `src/codeask/llm/api_service.py` + `src/codeask/api/llm_configs.py`：CRUD 字段同步；`_draft_config_from_*`/`update_scoped_config` 合并改新字段（**保留"留空 api_key 复用旧值"**，headers 同理留空复用）；`runtime_fields_changed` 触发条件改看 `provider_id`/`model_name`/`base_url`/`api_key`/`headers`。
- `/llm-runtime-profiles` 替换为 **`/llm-providers`**（返回 models.dev 快照 provider 列表，供目录模式下拉；自定义模式前端独立表单）。

### Phase 6 — 前端（镜像 opencode 两条流程）
- `settings-types.ts`：删 `LlmProtocol`/profile 类型；payload 加 `mode`/`provider_id`/`headers`（`model_name` 保留单值）。
- `LlmConfigForm.tsx` / `LlmConfigEditForm.tsx`：
  - 顶部「目录 / 自定义」模式切换。
  - **目录**：provider 下拉（拉 `/llm-providers`）+ 单 model 输入 + key + 可选 base_url 覆盖。
  - **自定义**：slug + 名称 + base_url + key + 单 model 输入 + headers 行列表（add/remove）。
  - 保留测试按钮（探该 config 的 `model_name`）。
- `LlmConfigManager.tsx`：`runtimeProfiles` 查询换成 `providers` 查询。
- `LlmConfigList.tsx`：展示 `provider_id`/`mode`/`model_name` 取代 protocol/profile。
- `frontend/src/types/api.ts` + `lib/api.ts`：类型与 `/llm-providers` 路径同步。

### Phase 7 — 删死代码
- 删 `src/codeask/agent/native_backend/` 整个目录及其专属测试。
- ⚠️ 区分：**保留** `src/codeask/agent/chat_runtime/`（共享，`messages.py`/`sessions.py` 用 `chat_runtime.events.ChatRuntimeEvent`）；只删 `native_backend.chat_runtime`。
- grep 确认无残留 import。

## 6. 关键复用点（已存在，勿重造）
- `litellm.provider_list`（133 项，运行时取）——目录模式映射真值源之一。
- `opencode_compat.test_llm_config` + `_wait_for_probe_result`——连通测试已实发请求，保留。
- repo "留空 api_key 复用旧值"（`update_scoped_config` 的 `fields` 合并）——保留，headers 同理。
- `is_default` 的 partial unique index、Fernet 加密落盘——保留。
- opencode `dialog-custom-provider-form.ts` 的 `validateCustomProvider`——校验规则直接对照搬到 schema 层。

## 7. 验证
- 静态：`corepack pnpm exec tsc --noEmit` + `eslint`（frontend/）；`ruff check`（repo 根，去代理）。
- 单测：`provider_catalog`（映射分支）、opencode 配置生成（目录裸 id / 自定义 openai-compatible + headers，均单模型块）、gateway client 构建、API CRUD（两模式 + 校验）、连通测试；删 `native_backend` 测试后整体 `pytest` 绿。
- 端到端（去代理重启后端 `env -u *proxy* uv run codeask`）：
  1. 目录模式新建：选 `deepseek` + model + key → 测试连通（opencode 实发探针）通过。
  2. 发起对话，确认主对话用该配置正常出字。
  3. 触发标题生成（litellm 路径，deepseek 同名直通）确认能生成。
  4. 目录模式配 override 项（如 `google`），确认 litellm 走 `gemini` 不报 unknown provider。
  5. 自定义模式配一个中转站 + baseURL + headers，确认 opencode（openai-compatible）与 litellm（`openai/` + api_base）都可用。
