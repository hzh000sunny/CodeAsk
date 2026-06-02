# M13 OpenViking 模型配置实施计划

> **给 agentic worker：** 实施本计划时必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`，按任务逐项执行。所有步骤使用 checkbox（`- [ ]`）追踪。

**目标：** 让 OpenViking 的 embedding 模型和 VLM 模型都能在管理员 UI 中配置；默认环境不要求用户预装 Ollama 或提前拉好模型，也能使用 OpenViking 本地 embedding 默认能力启动。

**架构：** CodeAsk 不再把 Ollama `bge-m3` 写死为唯一运行形态。`ov.conf` 改由数据库中的管理员配置生成：embedding 默认使用 OpenViking 0.3.22 的本地 GGUF provider；管理员可以在 UI 中切到 Ollama 或第三方 provider；VLM 默认关闭，但可以在 UI 中开启和配置。Embedding 切换仍然是破坏性操作，会重启 OpenViking、清理向量根目录并触发索引重建；VLM 配置变更只重启 OpenViking，不清索引、不重排同步任务。

**技术栈：** Python 3.11、FastAPI、SQLAlchemy、Alembic、OpenViking `>=0.3.22,<0.4`、Pydantic 配置生成、React/TypeScript 管理后台、Playwright E2E。

---

## 0. 现状与决策

当前行为对新用户环境不友好：

- `pyproject.toml` 只依赖 `openviking>=0.3.22,<0.4`，没有安装 `local-embed` extra。
- [config.py](/home/hzh/workspace/CodeAsk/src/codeask/rag/openviking/config.py) 固定写入：
  - `embedding.dense.provider="ollama"`
  - `embedding.dense.model="bge-m3"`
  - `embedding.dense.api_base="http://127.0.0.1:11434/v1"`
  - `embedding.dense.dimension=1024`
- [openviking_admin.py](/home/hzh/workspace/CodeAsk/src/codeask/api/openviking_admin.py) 的 `_validate_embedding_candidate()` 只接受 `provider="ollama"`。
- 管理员 UI 只展示 Ollama `/api/tags` 候选和历史模型，没有第三方 provider 表单，也没有 VLM 配置入口。
- [app.py](/home/hzh/workspace/CodeAsk/src/codeask/app.py) 的周期 Ollama 健康检查默认假设当前 embedding provider 是 Ollama；如果改成本地或云端 provider，仍会错误提示 Ollama 缺失。

已核实的 OpenViking 0.3.22 事实：

- 如果不配置 embedding，`EmbeddingConfig.apply_default_local_dense()` 会注入：
  - `provider="local"`
  - `model="bge-small-zh-v1.5-f16"`
  - `dimension=512`
- 默认本地模型文件名是 `bge-small-zh-v1.5-f16.gguf`，默认缓存路径是 `~/.cache/openviking/models/bge-small-zh-v1.5-f16.gguf`。
- `openviking[local-embed]` 只安装 `llama-cpp-python>=0.3.0`，不会在 `uv sync` 或 pip 安装时预下载 GGUF。OpenViking 会在 local embedder 初始化时，如果缓存文件不存在，再懒下载模型。
- Embedding provider 是 OpenViking 0.3.22 源码中写死的白名单，来源是 `EmbeddingModelConfig.validate_config()`。
- VLM provider 不按 embedding 那套白名单校验。OpenViking 的 VLM registry 有一组常见 provider，但 `VLMBase.from_config()` 对未显式识别的 provider 会 fallback 到 `LiteLLMVLMProvider`。因此 VLM UI 不应做硬白名单下拉，而应做可输入的 provider 组合框，内置常见建议项。
- VLM 配置可以缺省。OpenViking 可以无 VLM 启动；无 VLM 时，依赖 VLM 的语义摘要、规划或多模态能力不可用或降级，具体表现由 OpenViking 上游实现决定。

M13 决策：

- CodeAsk 管理的 OpenViking 默认 embedding provider 改为 `local`，模型为 `bge-small-zh-v1.5-f16`。
- 依赖改为 `openviking[local-embed]>=0.3.22,<0.4`，保证默认 local provider 有 `llama-cpp-python`。
- 不承诺安装期下载模型。管理员 UI 必须展示本地模型缓存状态，例如 `model_cached` 和 `will_download_on_start`。
- Embedding provider 做成下拉列表，列表严格来自 OpenViking 0.3.22 的白名单：
  - `local`
  - `ollama`
  - `openai`
  - `azure`
  - `volcengine`
  - `vikingdb`
  - `jina`
  - `gemini`
  - `voyage`
  - `dashscope`
  - `minimax`
  - `cohere`
  - `litellm`
- VLM provider 做成可输入组合框，不做硬白名单限制。建议项来自 OpenViking 0.3.22 VLM registry 和常见 LiteLLM 使用方式：
  - `volcengine`
  - `openai`
  - `azure`
  - `kimi`
  - `glm`
  - `litellm`
  - `openai-codex`
  - 允许管理员输入其他 provider 名称，最终交给 OpenViking / LiteLLM 处理。
- API key、AK/SK 等敏感字段不回显，存储时复用现有 `codeask.crypto.Crypto` Fernet 加密模式，参考 `LLMConfig.api_key_encrypted`。
- Embedding 配置变化是破坏性操作：清理 `viking://resources/codeask`、重排 sync jobs、重启 OpenViking、触发索引重建。
- VLM 配置变化不是索引破坏性操作：只重写 `ov.conf` 并重启 OpenViking，不清向量根目录、不重排 sync jobs。

## 1. 范围

本轮范围：

- 依赖增加 `openviking[local-embed]`。
- embedding 配置从 Ollama-only 扩展为 OpenViking 白名单 provider。
- 新增 VLM 配置持久化、API 和 UI。
- `ov.conf` 由持久化的 embedding / VLM 配置生成。
- 管理员 UI 提供：
  - 当前 embedding 配置展示
  - embedding provider 下拉
  - provider 对应字段表单
  - 本地模型缓存状态
  - VLM 启用/禁用和配置表单
- 健康检查和状态接口 provider-aware，不再在非 Ollama provider 下误报 Ollama 缺失。
- 为 local 默认、Ollama 切换、自定义 provider、VLM 开关、重启/重建行为补单元、集成和 E2E 验证。

不在本轮范围：

- 自动安装 Ollama。
- 自动执行 `ollama pull`。
- 自动开通第三方账号或验证第三方余额。
- 每个 feature 使用不同 embedding provider。
- 同时运行多套 embedding 模型或做 A/B 流量。
- 依赖安装阶段预下载 GGUF。

## 2. 文件边界

后端：

- `pyproject.toml` / `uv.lock`：依赖改成 `openviking[local-embed]>=0.3.22,<0.4`。
- `src/codeask/settings.py`：默认 embedding 改成本地 provider；VLM 默认 disabled。
- `src/codeask/rag/openviking/config.py`：`OpenVikingRuntimeConfig` 支持 provider-specific embedding 和 optional VLM；生成 `ov.conf` 时不再写死 Ollama。
- `src/codeask/rag/openviking/models.py`：扩展 embedding 设置表字段；新增 VLM 设置表。
- `src/codeask/db/models/__init__.py`：导出新增模型。
- `alembic/versions/20260602_0033_openviking_model_configuration.py`：新增 provider 字段和 VLM 表的 migration。
- `src/codeask/api/openviking_admin.py`：扩展 embedding 配置 API；新增 VLM 配置 API。
- `src/codeask/rag/openviking/health.py`：新增 provider-aware readiness。
- `src/codeask/app.py`：Ollama 周期健康检查只在 active provider 是 `ollama` 时执行。
- `src/codeask/api/openviking_status.py`：status payload 增加 active embedding / VLM readiness。

前端：

- `frontend/src/types/api.ts`：扩展 embedding request/response；新增 VLM 类型。
- `frontend/src/lib/api-openviking.ts`：新增 VLM API 调用；扩展 embedding apply 调用。
- `frontend/src/components/settings/OpenVikingDashboard.tsx`：改造 embedding 卡片；新增 VLM 配置区。
- `frontend/src/styles/globals.css`：补 provider 表单样式，保持当前 OpenViking dashboard 的紧凑工作台风格。

测试：

- `tests/unit/test_openviking_config_uri.py`：覆盖 local、Ollama、OpenAI-compatible、VLM enabled 的 `ov.conf` 生成。
- `tests/unit/test_openviking_process_health.py`：默认配置和 status 元数据回归。
- `tests/unit/test_openviking_app_tasks.py`：provider-aware 周期健康检查。
- `tests/integration/test_openviking_admin_api.py`：embedding apply、VLM apply/disable、secret redaction、重启/重建行为。
- `frontend/e2e/openviking-dashboard-model-config-live.spec.ts`：隔离数据目录下的 live E2E。

## 3. 实施清单

### Task 1：依赖接入 OpenViking local embedding

**文件：**

- 修改：`pyproject.toml`
- 修改：`uv.lock`

- [ ] 将依赖改为：

```toml
"openviking[local-embed]>=0.3.22,<0.4",
```

- [ ] 刷新依赖：

```bash
uv lock
uv sync
```

- [ ] 验证 `llama-cpp-python` 可导入：

```bash
uv run python - <<'PY'
import importlib.util
print(importlib.util.find_spec("llama_cpp") is not None)
PY
```

期望：输出 `True`。

- [ ] 验证 OpenViking 版本仍在支持范围内：

```bash
uv pip show openviking
```

期望：`Version: 0.3.22` 或更新的 `0.3.x`。

### Task 2：重构 OpenViking runtime config 生成

**文件：**

- 修改：`src/codeask/rag/openviking/config.py`
- 测试：`tests/unit/test_openviking_config_uri.py`

- [ ] 新增 provider-aware 配置 dataclass：

```python
@dataclass(frozen=True)
class OpenVikingEmbeddingRuntimeConfig:
    provider: str = "local"
    model: str = "bge-small-zh-v1.5-f16"
    base_url: str | None = None
    api_key: str | None = None
    dimension: int | None = 512
    input: str = "text"
    extra: dict[str, Any] | None = None


@dataclass(frozen=True)
class OpenVikingVLMRuntimeConfig:
    enabled: bool = False
    provider: str | None = None
    model: str | None = None
    api_key: str | None = None
    api_base: str | None = None
    temperature: float = 0.0
    max_retries: int = 3
    timeout: float = 60.0
    extra: dict[str, Any] | None = None
```

- [ ] 修改 `OpenVikingRuntimeConfig`，让它持有：

```python
embedding: OpenVikingEmbeddingRuntimeConfig = field(
    default_factory=OpenVikingEmbeddingRuntimeConfig
)
vlm: OpenVikingVLMRuntimeConfig = field(default_factory=OpenVikingVLMRuntimeConfig)
```

- [ ] 生成 `embedding.dense` 时省略空值：

```python
dense: dict[str, Any] = {
    "provider": config.embedding.provider,
    "model": config.embedding.model,
}
if config.embedding.base_url:
    dense["api_base"] = _embedding_api_base(config.embedding)
if config.embedding.api_key:
    dense["api_key"] = config.embedding.api_key
if config.embedding.dimension is not None:
    dense["dimension"] = config.embedding.dimension
if config.embedding.input:
    dense["input"] = config.embedding.input
if config.embedding.extra:
    dense.update(config.embedding.extra)
```

- [ ] 保留 Ollama `/v1` 规则：

```python
def _embedding_api_base(embedding: OpenVikingEmbeddingRuntimeConfig) -> str:
    if embedding.provider == "ollama" and embedding.base_url:
        return f"{embedding.base_url.rstrip('/')}/v1"
    return embedding.base_url or ""
```

- [ ] 只在 VLM enabled 且 provider/model 存在时写 `vlm` 段。不要写 `{"enabled": false}`，因为历史 0.3.17 拒绝过 `vlm.enabled`，0.3.22 的 `VLMConfig` 也不需要这个字段。

- [ ] 增加 config 单测：

```python
def test_build_ov_conf_defaults_to_local_embedding(tmp_path: Path) -> None:
    config = OpenVikingRuntimeConfig(data_dir=tmp_path)
    ov_conf = build_ov_conf(config)

    dense = ov_conf["embedding"]["dense"]
    assert dense == {
        "provider": "local",
        "model": "bge-small-zh-v1.5-f16",
        "dimension": 512,
        "input": "text",
    }
    assert "vlm" not in ov_conf


def test_build_ov_conf_supports_ollama_embedding(tmp_path: Path) -> None:
    config = OpenVikingRuntimeConfig(
        data_dir=tmp_path,
        embedding=OpenVikingEmbeddingRuntimeConfig(
            provider="ollama",
            model="bge-m3",
            base_url="http://127.0.0.1:11434",
            dimension=1024,
        ),
    )

    dense = build_ov_conf(config)["embedding"]["dense"]
    assert dense["api_base"] == "http://127.0.0.1:11434/v1"
    assert dense["model"] == "bge-m3"


def test_build_ov_conf_writes_vlm_when_enabled(tmp_path: Path) -> None:
    config = OpenVikingRuntimeConfig(
        data_dir=tmp_path,
        vlm=OpenVikingVLMRuntimeConfig(
            enabled=True,
            provider="litellm",
            model="ollama/qwen3.5:2b",
            api_key="no-key",
            api_base="http://127.0.0.1:11434",
        ),
    )

    vlm = build_ov_conf(config)["vlm"]
    assert vlm["provider"] == "litellm"
    assert vlm["model"] == "ollama/qwen3.5:2b"
```

### Task 3：持久化 generalized embedding 和 VLM 配置

**文件：**

- 修改：`src/codeask/rag/openviking/models.py`
- 修改：`src/codeask/db/models/__init__.py`
- 新增：`alembic/versions/20260602_0033_openviking_model_configuration.py`
- 测试：`tests/integration/test_openviking_admin_api.py`

- [ ] 扩展 `OpenVikingEmbeddingSetting`：

```python
api_key_encrypted: Mapped[str | None] = mapped_column(String(2048), nullable=True)
input: Mapped[str] = mapped_column(String(32), nullable=False, default="text")
extra: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
```

- [ ] 对 embedding API key 使用：

```python
Crypto(request.app.state.settings.data_key).encrypt(api_key)
```

返回时只提供：

```json
{
  "api_key_configured": true,
  "api_key_masked": "sk-***xyz"
}
```

- [ ] 新增 `OpenVikingVLMSetting`：

```python
class OpenVikingVLMSetting(Base, TimestampMixin):
    __tablename__ = "openviking_vlm_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    base_url: Mapped[str | None] = mapped_column(String(256), nullable=True)
    api_key_encrypted: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    temperature: Mapped[str] = mapped_column(String(32), nullable=False, default="0.0")
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    timeout: Mapped[str] = mapped_column(String(32), nullable=False, default="60.0")
    extra: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    activated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    previous_setting_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
```

- [ ] migration 必须是 additive，不能破坏已有 `openviking_embedding_settings` 行。

- [ ] 导出 `OpenVikingVLMSetting`。

- [ ] 增加集成断言：保存 embedding 或 VLM API key 后，SQLite 文件中不能出现原始密钥文本。

### Task 4：扩展后端 Admin API

**文件：**

- 修改：`src/codeask/api/openviking_admin.py`
- 测试：`tests/integration/test_openviking_admin_api.py`

- [ ] 用 provider-aware request 替换现有 `EmbeddingSwitchRequest`：

```python
class EmbeddingApplyRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=32)
    base_url: str | None = Field(default=None, max_length=256)
    model: str = Field(min_length=1, max_length=128)
    dimension: int | None = Field(default=None, ge=1, le=16384)
    max_concurrent: int = Field(default=1, ge=1, le=128)
    input: str = Field(default="text", max_length=32)
    api_key: str | None = Field(default=None, max_length=4096)
    extra: dict[str, Any] | None = None
```

- [ ] embedding provider 白名单使用常量：

```python
SUPPORTED_EMBEDDING_PROVIDERS = {
    "local",
    "ollama",
    "openai",
    "azure",
    "volcengine",
    "vikingdb",
    "jina",
    "gemini",
    "voyage",
    "dashscope",
    "minimax",
    "cohere",
    "litellm",
}
```

- [ ] `local` 校验：
  - 只允许 `bge-small-zh-v1.5-f16`，除非 OpenViking 后续公开更多 local model。
  - 默认 dimension 为 `512`。
  - 通过 `get_local_model_cache_path()` 计算 `model_cached`。

- [ ] `ollama` 校验：
  - 保留 `/api/tags` 探测。
  - 模型不存在时报 400。

- [ ] 云端 provider 校验：
  - `openai` 有 `api_key` 或 `api_base` 即可。
  - `azure` 必须有 `api_key` 和 `api_base`。
  - `volcengine`、`jina`、`gemini`、`voyage`、`dashscope`、`minimax`、`cohere` 必须有 `api_key`。
  - `litellm` 必须显式提供 `dimension`。
  - `vikingdb` 必须有 `ak`、`sk`、`region`；`ak` / `sk` 必须加密存储。

- [ ] 写入新 embedding setting 后，沿用当前切换流程：
  - 重写 `ov.conf`
  - 重启 OpenViking
  - clear `viking://resources/codeask`
  - 非 running sync jobs 置 pending
  - 写 `embedding_model_switched`
  - 写 audit log

- [ ] 新增 VLM request：

```python
class VLMApplyRequest(BaseModel):
    enabled: bool = True
    provider: str = Field(min_length=1, max_length=64)
    base_url: str | None = Field(default=None, max_length=256)
    model: str = Field(min_length=1, max_length=128)
    api_key: str | None = Field(default=None, max_length=4096)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    timeout: float = Field(default=60.0, gt=0.0, le=600.0)
    max_retries: int = Field(default=3, ge=0, le=10)
    extra: dict[str, Any] | None = None
```

- [ ] 新增 VLM 端点：

```text
GET  /api/admin/openviking/vlm
POST /api/admin/openviking/vlm
POST /api/admin/openviking/vlm/disable
GET  /api/admin/openviking/vlm/history
```

- [ ] VLM provider 不做 embedding 那种硬白名单。后端只做基础字符串校验和必填项校验：
  - provider 非空
  - model 非空
  - 如果 provider 不是 `litellm` 且不是 `openai-codex`，首次启用时要求 `api_key`
  - `openai-codex` 可允许无 api_key，但要把配置交给 OpenViking，由 OpenViking 检查 Codex OAuth
  - 其他未知 provider 不拒绝，作为 LiteLLM-compatible provider 传给 OpenViking

- [ ] VLM apply 行为：
  - 写新 VLM setting
  - 重写 `ov.conf`
  - 重启 OpenViking
  - 写 `vlm_config_changed`
  - 写 audit log
  - 不清 `viking://resources/codeask`
  - 不重排 sync jobs

- [ ] 所有 response 不回显原始密钥。

### Task 5：Provider-aware 健康检查和启动状态

**文件：**

- 修改：`src/codeask/app.py`
- 修改：`src/codeask/rag/openviking/health.py`
- 修改：`src/codeask/api/openviking_status.py`
- 测试：`tests/unit/test_openviking_app_tasks.py`、`tests/integration/test_openviking_admin_api.py`

- [ ] 新增 active embedding readiness helper：

```python
async def active_embedding_readiness(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    ollama_transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    setting = await read_latest_embedding_setting(session_factory, settings)
    if setting.provider == "local":
        return local_embedding_readiness(setting)
    if setting.provider == "ollama":
        return await ollama_embedding_readiness(setting, transport=ollama_transport)
    return remote_embedding_readiness(setting)
```

- [ ] local readiness 返回：

```json
{
  "provider": "local",
  "model": "bge-small-zh-v1.5-f16",
  "healthy": true,
  "model_available": true,
  "model_cached": false,
  "will_download_on_start": true,
  "error": null
}
```

- [ ] status payload 增加：

```json
{
  "embedding": {
    "provider": "local",
    "model": "bge-small-zh-v1.5-f16",
    "healthy": true
  },
  "vlm": {
    "enabled": false,
    "provider": null,
    "model": null
  }
}
```

- [ ] `ollama` 字段只在 active provider 为 `ollama` 时作为真实健康状态展示；非 Ollama provider 下不要把 Ollama missing 算作 degraded。

- [ ] 周期 Ollama 健康检查增加短路：

```python
if active_provider != "ollama":
    return
```

- [ ] 只有当能可靠检测到本地模型缓存缺失时，才发 `local_embedding_model_download` 或展示 `will_download_on_start`。不要编造下载进度。

### Task 6：前端模型配置 UI

**文件：**

- 修改：`frontend/src/types/api.ts`
- 修改：`frontend/src/lib/api-openviking.ts`
- 修改：`frontend/src/components/settings/OpenVikingDashboard.tsx`
- 修改：`frontend/src/styles/globals.css`

- [ ] Embedding provider 使用下拉列表，选项固定为：

```text
Local
Ollama
OpenAI
Azure
VolcEngine
VikingDB
Jina
Gemini
Voyage
DashScope
MiniMax
Cohere
LiteLLM
```

- [ ] Local provider 字段：

```text
Model: bge-small-zh-v1.5-f16
Dimension: 512
Cache status: cached / first startup will download
```

- [ ] Ollama provider 字段：

```text
Base URL
Model select from /api/tags
Dimension
Max concurrent
```

- [ ] OpenAI-compatible / 云端 provider 字段：

```text
API base
Model
Dimension
API key
Max concurrent
```

- [ ] VikingDB provider 字段：

```text
AK
SK
Region
Host
Model
Dimension
```

- [ ] VLM provider 使用可输入组合框，不做硬下拉。建议项：

```text
volcengine
openai
azure
kimi
glm
litellm
openai-codex
```

- [ ] VLM 字段：

```text
Enabled toggle
Provider combobox
Base URL
Model
API key
Temperature
Timeout
Max retries
Disable button
```

- [ ] Embedding apply 使用破坏性确认：

```text
确认切换 Embedding 配置？这会清理 OpenViking 索引并重新排队同步任务。
```

- [ ] VLM apply 使用非破坏性确认：

```text
确认更新 VLM 配置？这会重启 OpenViking，但不会清理向量索引。
```

- [ ] 不使用大段功能说明文字。错误、状态和字段标签要简洁，符合现有 OpenViking dashboard 工作台风格。

### Task 7：E2E 和真实运行验证

**文件：**

- 新增：`frontend/e2e/openviking-dashboard-model-config-live.spec.ts`

- [ ] 使用隔离 `CODEASK_DATA_DIR`，不要在共享开发数据目录上跑破坏性 model switch E2E。

- [ ] E1：fresh local default。

期望：

```text
管理员 OpenViking 页面显示 provider local、model bge-small-zh-v1.5-f16、dimension 512。
非 Ollama provider 下不显示 Ollama missing。
OpenViking 可启动；如果本地 GGUF 未缓存，UI 显示首次启动会下载。
```

- [ ] E2：切换到 Ollama。

期望：

```text
选择 provider ollama 后，模型来自 /api/tags。
保存后重启 OpenViking、清理索引、重排 sync jobs。
```

- [ ] E3：切换到 OpenAI-compatible / LiteLLM embedding。

期望：

```text
API key 被接受但不回显。
status 返回 api_key_configured=true。
```

- [ ] E4：启用自定义 VLM provider。

期望：

```text
provider 可以输入建议项以外的值。
OpenViking 重启。
sync jobs 不重排。
向量根目录不删除。
事件流出现 vlm_config_changed。
```

- [ ] E5：禁用 VLM。

期望：

```text
ov.conf 不包含 vlm 段。
OpenViking 重启。
不触发索引重建。
```

## 4. 验收闸门

- [ ] 新安装环境不装 Ollama，也能用 local embedding dependency 启动 CodeAsk-managed OpenViking。
- [ ] active provider 非 Ollama 时，admin status 不把 Ollama 缺失算作 degraded。
- [ ] Embedding provider 在 UI 中是白名单下拉。
- [ ] VLM provider 在 UI 中是可输入组合框，支持建议项以外的值。
- [ ] 管理员可以通过 UI/API 切换 local、Ollama、至少一种 OpenAI-compatible embedding。
- [ ] Embedding 切换总是清向量根目录并重排 sync jobs。
- [ ] VLM apply/disable 只重启 OpenViking，不清向量根目录、不重排 sync jobs。
- [ ] API key、AK、SK 不在 API response、dashboard event、audit payload、SQLite 明文中出现。
- [ ] CodeAsk 生成的 `ov.conf` 在 OpenViking 0.3.22 下通过 local embedding、Ollama embedding、VLM enabled 三类配置验证。
- [ ] 单元测试、集成测试、ruff、pyright、frontend lint/build、Playwright E2E 通过。

## 5. 验证命令

实现后运行：

```bash
uv lock
uv sync
uv run python - <<'PY'
import importlib.util
print(importlib.util.find_spec("llama_cpp") is not None)
PY
uv run pytest tests/unit/test_openviking_config_uri.py tests/unit/test_openviking_process_health.py tests/unit/test_openviking_app_tasks.py tests/integration/test_openviking_admin_api.py -q
uv run ruff check pyproject.toml src/codeask/rag/openviking src/codeask/api/openviking_admin.py src/codeask/app.py tests/unit/test_openviking_config_uri.py tests/unit/test_openviking_app_tasks.py tests/integration/test_openviking_admin_api.py
uv run pyright src/codeask/rag/openviking src/codeask/api/openviking_admin.py src/codeask/app.py tests/unit/test_openviking_config_uri.py tests/unit/test_openviking_app_tasks.py tests/integration/test_openviking_admin_api.py
cd frontend
npm run lint
npm run build
CODEASK_RUN_LIVE_OPENVIKING_E2E=1 npx playwright test e2e/openviking-dashboard-model-config-live.spec.ts
cd ..
git diff --check
```

期望：

- `llama_cpp` 可导入，输出 `True`。
- pytest 通过。
- ruff 通过。
- pyright 报告 `0 errors`。
- frontend lint/build 通过。
- isolated data dir 下 live E2E 通过。
- `git diff --check` 无输出。

## 6. 风险和注意事项

- `openviking[local-embed]` 可能增加安装摩擦；某些平台上 `llama-cpp-python` 可能从源码编译。如果这在实际安装中频繁失败，后续应改成 `codeask[openviking-local]` 可选 extra，并在 UI 中显示安装缺失状态。
- 默认 GGUF 下载依赖 HuggingFace 可达。UI 只能在 `get_local_model_cache_path()` 存在时显示 cached；缓存不存在时显示“首次启动会下载”，不能显示“已安装”。
- 从现有 Ollama `bge-m3` 的 1024 维切到 local 512 维会导致向量维度变化，必须全量重建索引。
- VLM disabled 是合法状态。生成 `ov.conf` 时不要写 `vlm.enabled=false`。
- 历史 spike 文档记录的是 0.3.17 / Ollama 实验事实，不要回写修改；只更新面向未来的安装和管理员配置文档。
