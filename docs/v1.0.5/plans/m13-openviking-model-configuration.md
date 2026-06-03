# M13 OpenViking 模型配置实施计划

> 版本：v1.0.5
> 状态：Completed（2026-06-03 release 复核：后端 + 前端 + E2E 已完成）

> **给 agentic worker：** 实施本计划时必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`，按任务逐项执行。所有步骤使用 checkbox 追踪；2026-06-03 release 复核时已按落地状态勾选。

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

> 2026-06-03 复核：上述“当前行为”已被本里程碑修复。依赖已经是 `openviking[local-embed]>=0.3.22,<0.4`；默认 provider 已为 local；周期 Ollama 健康检查只在 active provider 需要 Ollama 时执行。

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
- 本里程碑仍处在版本开发阶段，没有需要兼容的存量生产安装。默认 embedding 从 Ollama `bge-m3` / 1024 维切到 local / 512 维后，测试环境数据直接清理并重建索引；不增加“保留旧默认配置”的 migration 复杂度。

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
- `src/codeask/rag/openviking/health.py`：新增 OpenViking doctor 结果封装；不自研 embedding / VLM provider 连通性逻辑。
- `src/codeask/app.py`：Ollama 周期健康检查只在 active provider 是 `ollama` 时执行。
- `src/codeask/api/openviking_status.py`：status payload 增加 active embedding / VLM 配置摘要和 doctor 诊断结果。

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

- [x] 将依赖改为：

```toml
"openviking[local-embed]>=0.3.22,<0.4",
```

- [x] 刷新依赖：

```bash
uv lock
uv sync
```

- [x] 验证 `llama-cpp-python` 可导入：

```bash
uv run python - <<'PY'
import importlib.util
print(importlib.util.find_spec("llama_cpp") is not None)
PY
```

期望：输出 `True`。

- [x] 验证 OpenViking 版本仍在支持范围内：

```bash
uv pip show openviking
```

期望：`Version: 0.3.22` 或更新的 `0.3.x`。

### Task 2：重构 OpenViking runtime config 生成

**文件：**

- 修改：`src/codeask/rag/openviking/config.py`
- 测试：`tests/unit/test_openviking_config_uri.py`

- [x] 新增 provider-aware 配置 dataclass：

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
class OpenVikingEmbeddingRuntimeSettings:
    text_source: str = "content"
    max_input_tokens: int = 8192
    max_concurrent: int = 1
    max_retries: int = 3
    circuit_breaker: dict[str, Any] | None = None


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

- [x] 修改 `OpenVikingRuntimeConfig`，让它持有：

```python
embedding: OpenVikingEmbeddingRuntimeConfig = field(
    default_factory=OpenVikingEmbeddingRuntimeConfig
)
embedding_settings: OpenVikingEmbeddingRuntimeSettings = field(
    default_factory=OpenVikingEmbeddingRuntimeSettings
)
vlm: OpenVikingVLMRuntimeConfig = field(default_factory=OpenVikingVLMRuntimeConfig)
```

- [x] 重构 `build_ov_conf()` 时必须保留现有 embedding 同级配置和顶层开关，不能只生成 `embedding.dense`：
  - `embedding.text_source`
  - `embedding.max_input_tokens`
  - `embedding.max_concurrent`
  - `embedding.max_retries`
  - `embedding.circuit_breaker`
  - 顶层 `auto_generate_l0`
  - 顶层 `auto_generate_l1`

- [x] `EmbeddingApplyRequest.max_concurrent` 必须写入 `embedding.max_concurrent`，不要误写到 `embedding.dense`，也不要在 dataclass 重构中丢失。

- [x] 生成 `embedding.dense` 时省略空值：

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

- [x] 保留 Ollama `/v1` 规则：

```python
def _embedding_api_base(embedding: OpenVikingEmbeddingRuntimeConfig) -> str:
    if embedding.provider == "ollama" and embedding.base_url:
        return f"{embedding.base_url.rstrip('/')}/v1"
    return embedding.base_url or ""
```

- [x] 只在 VLM enabled 且 provider/model 存在时写 `vlm` 段。不要写 `{"enabled": false}`，因为历史 0.3.17 拒绝过 `vlm.enabled`，0.3.22 的 `VLMConfig` 也不需要这个字段。

- [x] 增加 config 单测：

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

    assert ov_conf["embedding"]["text_source"] == "content"
    assert ov_conf["embedding"]["max_concurrent"] == 1
    assert "auto_generate_l0" in ov_conf
    assert "auto_generate_l1" in ov_conf


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

- [x] 扩展 `OpenVikingEmbeddingSetting`：

```python
api_key_encrypted: Mapped[str | None] = mapped_column(String(2048), nullable=True)
input: Mapped[str] = mapped_column(String(32), nullable=False, default="text")
extra: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
```

- [x] 对 embedding API key 使用：

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

- [x] 新增 `OpenVikingVLMSetting`：

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

- [x] migration 必须是 additive，不能破坏已有 `openviking_embedding_settings` 行。

- [x] 导出 `OpenVikingVLMSetting`。

- [x] 增加集成断言：保存 embedding 或 VLM API key 后，SQLite 文件中不能出现原始密钥文本。

### Task 4：扩展后端 Admin API

**文件：**

- 修改：`src/codeask/api/openviking_admin.py`
- 测试：`tests/integration/test_openviking_admin_api.py`

- [x] 用 provider-aware request 替换现有 `EmbeddingSwitchRequest`：

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

- [x] embedding provider 下拉列表使用 UI 候选常量；这个常量只用于 response / 前端展示，不作为后端最终校验的单一真相源：

```python
EMBEDDING_PROVIDER_OPTIONS = {
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

- [x] embedding 后端校验必须跟随 OpenViking，不复制 `EmbeddingModelConfig.validate_config()` 里的 provider-specific `if/elif`。做法：
  - 从 request 组装候选 `dense` dict。
  - 构造 OpenViking `EmbeddingModelConfig` 并调用其校验。
  - 捕获 `ValueError` / `pydantic.ValidationError`，转换为 HTTP 400。
  - CodeAsk 只保留必要的 UI 体验检查和敏感字段加密，不额外发明 provider 业务规则。

```python
from pydantic import ValidationError
from openviking_cli.utils.config.embedding_config import EmbeddingModelConfig

try:
    EmbeddingModelConfig.model_validate(candidate_dense)
except (ValueError, ValidationError) as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc
```

- [x] 为 UI 候选列表补回归测试：如果 OpenViking 0.3.x 的 embedding provider 白名单变化，测试要提示同步前端下拉候选；但运行时最终校验仍以 OpenViking 为准。

- [x] `local` 状态检查：
  - 默认 model 为 `bge-small-zh-v1.5-f16`，默认 dimension 为 `512`。
  - 如果设置了 `model_path`，检查该路径是否存在。
  - 否则使用 `cache_dir` override；没有 override 时使用 OpenViking `DEFAULT_LOCAL_MODEL_CACHE_DIR`。
  - 通过 `get_local_model_spec(model).filename` 拼出缓存文件路径；如果当前 OpenViking 版本提供 `get_local_model_cache_path(model, cache_dir)`，也可以调用它，但不能忽略 `model_path` / `cache_dir` override。
  - `model_cached` / `will_download_on_start` 是状态展示，不作为 local provider 的阻断性校验。

- [x] `ollama` 校验：
  - 保留 `/api/tags` 探测。
  - 模型不存在时报 400。

- [x] 云端 provider 的必填字段和 dimension 规则交给 OpenViking 校验。`vikingdb` 的 `ak` / `sk` 等敏感字段仍由 CodeAsk 加密存储，但是否必填不在 CodeAsk 里平行维护。

- [x] 写入新 embedding setting 后，沿用当前切换流程：
  - 重写 `ov.conf`
  - 重启 OpenViking
  - clear `viking://resources/codeask`
  - 非 running sync jobs 置 pending
  - 写 `embedding_model_switched`
  - 写 audit log

- [x] 新增 VLM request：

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

- [x] 新增 VLM 端点：

```text
GET  /api/admin/openviking/vlm
POST /api/admin/openviking/vlm
POST /api/admin/openviking/vlm/disable
GET  /api/admin/openviking/vlm/history
```

- [x] 新增候选配置测试端点：

```text
POST /api/admin/openviking/embedding/test
POST /api/admin/openviking/vlm/test
```

- [x] 点击“测试”只测试当前表单里的候选配置，不能保存项目配置：
  - 不写入 `openviking_embedding_settings` / `openviking_vlm_settings`
  - 不覆盖 CodeAsk-managed 正式 `ov.conf`
  - 不重启 OpenViking
  - 不清理 `viking://resources/codeask`
  - 不重排 sync jobs
  - 不写 `embedding_model_switched` / `vlm_config_changed`

- [x] 测试端点必须按候选配置生成临时 `ov.conf`，再通过 OpenViking doctor 诊断。临时文件目录必须遵守 [临时目录规则](/home/hzh/workspace/CodeAsk/docs/rules/temp-directory.md)：放在当前用户可写目录下，例如 `settings.data_dir / "tmp" / "openviking-doctor" / <run_id>/`，不要使用 `/tmp`。

- [x] 测试完成后清理该 run 的临时目录。清理失败只记录日志，不影响测试结果返回，也不能污染正式配置。

- [x] VLM provider 不做 embedding 那种硬白名单。后端只做基础字符串校验和最小形态校验：
  - provider 非空
  - model 非空
  - `api_key` 可选；如果管理员依赖环境变量、Codex OAuth 或 LiteLLM 自身认证，CodeAsk 不应误拒
  - 其他未知 provider 不拒绝，作为 LiteLLM-compatible provider 传给 OpenViking

- [x] VLM apply 行为：
  - 写新 VLM setting
  - 重写 `ov.conf`
  - 重启 OpenViking
  - 写 `vlm_config_changed`
  - 写 audit log
  - 不清 `viking://resources/codeask`
  - 不重排 sync jobs

- [x] 所有 response 不回显原始密钥。

### Task 5：OpenViking doctor 诊断和启动状态

**文件：**

- 修改：`src/codeask/app.py`
- 修改：`src/codeask/rag/openviking/health.py`
- 修改：`src/codeask/api/openviking_status.py`
- 测试：`tests/unit/test_openviking_app_tasks.py`、`tests/integration/test_openviking_admin_api.py`

- [x] CodeAsk 不封装自己的 embedding / VLM provider 连通性测试。active 配置诊断统一使用 OpenViking 0.3.22 自带 doctor 逻辑：
  - `openviking_cli.doctor.check_embedding()`
  - `openviking_cli.doctor.check_vlm()`
  - `openviking_cli.doctor.check_ollama()`
  - 或等价的 `openviking-server doctor` 执行结果

- [x] 调用 CLI doctor 时必须显式绑定当前 CodeAsk-managed `ov.conf`。推荐环境变量方式：

```bash
OPENVIKING_CONFIG_FILE=/path/to/user-owned/ov.conf openviking-server doctor
```

也可以使用 CLI 参数，但子命令必须放在第一位：

```bash
openviking-server doctor --config /path/to/user-owned/ov.conf
```

不要写成 `openviking-server --config /path/to/user-owned/ov.conf doctor`；0.3.22 会把 `doctor` 当成未知参数。

- [x] active 状态页的 doctor 用于“已保存并已写入正式 `ov.conf` 的 active 配置”。候选配置测试必须写用户目录下的临时 `ov.conf` 并绑定 `OPENVIKING_CONFIG_FILE`，不能为了测试候选配置改写全局或项目正式 `ov.conf`。

- [x] 在 `health.py` 增加封装，返回结构化 doctor 结果，保留 OpenViking 给出的 detail / fix，不改写 provider-specific 语义：

```json
{
  "embedding": {
    "ok": true,
    "detail": "local/bge-small-zh-v1.5-f16 (will auto-download during startup initialization)",
    "fix": null
  },
  "vlm": {
    "ok": false,
    "detail": "No VLM provider configured",
    "fix": "Add vlm section to ov.conf"
  },
  "ollama": {
    "ok": true,
    "detail": "not configured",
    "fix": null
  }
}
```

- [x] VLM 默认关闭时，doctor 的 `No VLM provider configured` 不应让 CodeAsk 整体状态 degraded。UI 可以展示为“未配置”，但不算故障。

- [x] status payload 增加：

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
  },
  "doctor": {
    "embedding": {
      "ok": true,
      "detail": "local/bge-small-zh-v1.5-f16 (will auto-download during startup initialization)"
    },
    "vlm": {
      "ok": false,
      "detail": "No VLM provider configured"
    }
  }
}
```

- [x] `ollama` 字段只在 active provider 为 `ollama`，或 VLM 使用 `litellm` + `ollama/...` 时作为真实健康状态展示；非 Ollama provider 下不要把 Ollama missing 算作 degraded。

- [x] 周期 Ollama 健康检查增加短路：

```python
if active_provider != "ollama":
    return
```

- [x] 本地模型缓存、`will auto-download`、Codex OAuth、Ollama 可达性等诊断文案以 OpenViking doctor 输出为准。CodeAsk 不编造下载进度，也不自己实现云端 provider 连通性 smoke test。

### Task 6：前端模型配置 UI

**文件：**

- 修改：`frontend/src/types/api.ts`
- 修改：`frontend/src/lib/api-openviking.ts`
- 修改：`frontend/src/components/settings/OpenVikingDashboard.tsx`
- 修改：`frontend/src/styles/globals.css`

- [x] Embedding provider 使用下拉列表，选项固定为：

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

- [x] Local provider 字段：

```text
Model: bge-small-zh-v1.5-f16
Dimension: 512
Cache status: cached / first startup will download
```

- [x] Ollama provider 字段：

```text
Base URL
Model select from /api/tags
Dimension
Max concurrent
```

- [x] OpenAI-compatible / 云端 provider 字段：

```text
API base
Model
Dimension
API key
Max concurrent
```

- [x] VikingDB provider 字段：

```text
AK
SK
Region
Host
Model
Dimension
```

- [x] VLM provider 使用可输入组合框，不做硬下拉。建议项：

```text
volcengine
openai
azure
kimi
glm
litellm
openai-codex
```

- [x] VLM 字段：

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

- [x] Embedding 配置区提供“测试”按钮和“保存”按钮，语义必须分开：
  - “测试”调用 `POST /api/admin/openviking/embedding/test`，只用临时 `ov.conf` 跑 OpenViking doctor，不保存 DB，不覆盖正式 `ov.conf`，不重启 OpenViking，不清索引，不重排 sync jobs。
  - “保存”才调用 embedding apply，触发破坏性确认和正式配置持久化。

- [x] VLM 配置区提供“测试”按钮和“保存”按钮，语义必须分开：
  - “测试”调用 `POST /api/admin/openviking/vlm/test`，只用临时 `ov.conf` 跑 OpenViking doctor，不保存 DB，不覆盖正式 `ov.conf`，不重启 OpenViking，不清索引，不重排 sync jobs。
  - “保存”才调用 VLM apply，触发非破坏性确认和正式配置持久化。

- [x] Embedding apply 使用破坏性确认：

```text
确认切换 Embedding 配置？这会清理 OpenViking 索引并重新排队同步任务。
```

- [x] VLM apply 使用非破坏性确认：

```text
确认更新 VLM 配置？这会重启 OpenViking，但不会清理向量索引。
```

- [x] 不使用大段功能说明文字。错误、状态和字段标签要简洁，符合现有 OpenViking dashboard 工作台风格。

### Task 7：E2E 和真实运行验证

**文件：**

- 新增：`frontend/e2e/openviking-dashboard-model-config-live.spec.ts`

- [x] 使用隔离 `CODEASK_DATA_DIR`，不要在共享开发数据目录上跑破坏性 model switch E2E。实际落地并入 `frontend/e2e/openviking-dashboard-management-live.spec.ts` 的 E2b，不另建单独 spec。

- [x] E1：fresh local default。

期望：

```text
管理员 OpenViking 页面显示 provider local、model bge-small-zh-v1.5-f16、dimension 512。
非 Ollama provider 下不显示 Ollama missing。
OpenViking 可启动；如果本地 GGUF 未缓存，UI 显示首次启动会下载。
```

- [x] E2：切换到 Ollama。

期望：

```text
选择 provider ollama 后，模型来自 /api/tags。
点击测试只返回 OpenViking doctor 诊断；正式 ov.conf、DB setting、OpenViking 进程、sync jobs 均不变化。
保存后重启 OpenViking、清理索引、重排 sync jobs。
```

- [x] E3：切换到 OpenAI-compatible / LiteLLM embedding。

期望：

```text
API key 被接受但不回显。
status 返回 api_key_configured=true。
点击测试只返回 OpenViking doctor 诊断；正式 ov.conf、DB setting、OpenViking 进程、sync jobs 均不变化。
保存并写入 ov.conf 后，UI 展示 OpenViking doctor 的 embedding 诊断结果。
不要求 CodeAsk 自己发 embedding smoke test；需要外部云端凭据的 live 场景 gate 跳过。
```

- [x] E4：启用自定义 VLM provider。

期望：

```text
provider 可以输入建议项以外的值。
点击测试只返回 OpenViking doctor 诊断；正式 ov.conf、DB setting、OpenViking 进程、sync jobs 均不变化。
OpenViking 重启。
sync jobs 不重排。
向量根目录不删除。
事件流出现 vlm_config_changed。
保存并写入 ov.conf 后，UI 展示 OpenViking doctor 的 VLM 诊断结果。
不要求 CodeAsk 自己发 VLM smoke test；需要外部云端凭据的 live 场景 gate 跳过。
```

- [x] E5：禁用 VLM。

期望：

```text
ov.conf 不包含 vlm 段。
OpenViking 重启。
不触发索引重建。
```

## 4. 验收闸门

- [x] 新安装环境不装 Ollama，也能用 local embedding dependency 启动 CodeAsk-managed OpenViking。
- [x] active provider 非 Ollama 时，admin status 不把 Ollama 缺失算作 degraded。
- [x] Embedding provider 在 UI 中是白名单下拉。
- [x] VLM provider 在 UI 中是可输入组合框，支持建议项以外的值。
- [x] 管理员可以通过 UI/API 切换 local、Ollama、至少一种 OpenAI-compatible embedding。
- [x] 后端 embedding 校验以 OpenViking `EmbeddingModelConfig` 为准；CodeAsk 不复制 provider-specific 必填规则。
- [x] Local embedding 缓存状态尊重 `model_path` 和 `cache_dir` override。
- [x] UI/API 的“测试”操作只写当前用户目录下的临时 `ov.conf` 并运行 OpenViking doctor；点击“测试”不能持久化配置、不能覆盖正式 `ov.conf`、不能重启 OpenViking、不能清索引、不能重排 sync jobs。
- [x] Embedding 切换总是清向量根目录并重排 sync jobs。
- [x] VLM apply/disable 只重启 OpenViking，不清向量根目录、不重排 sync jobs。
- [x] 管理员页面的 embedding / VLM 诊断来自 OpenViking doctor；CodeAsk 不自研 provider 连通性测试。
- [x] API key、AK、SK 不在 API response、dashboard event、audit payload、SQLite 明文中出现。
- [x] CodeAsk 生成的 `ov.conf` 在 OpenViking 0.3.22 下通过 local embedding、Ollama embedding、VLM enabled 三类配置验证。
- [x] 单元测试、集成测试、ruff、pyright、frontend lint/build、Playwright E2E 通过。

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
- 默认 GGUF 下载依赖 HuggingFace 可达。UI 只能在可靠判定缓存文件存在时显示 cached；缓存不存在时显示“首次启动会下载”，不能显示“已安装”。缓存路径判断必须尊重 OpenViking local embedding 的 `model_path` / `cache_dir` override。
- 从现有 Ollama `bge-m3` 的 1024 维切到 local 512 维会导致向量维度变化，必须全量重建索引。
- VLM disabled 是合法状态。生成 `ov.conf` 时不要写 `vlm.enabled=false`。
- VLM `api_key` 缺失不由 CodeAsk 自定义拦截；OpenViking / LiteLLM / 环境变量认证失败时再由上游错误暴露。
- 历史 spike 文档记录的是 0.3.17 / Ollama 实验事实，不要回写修改；只更新面向未来的安装和管理员配置文档。

## 7. 完成记录（2026-06-03）

- 关键提交：`e1c9cf4 Upgrade OpenViking dependency range`、`edc4678 Clarify OpenViking model config diagnostics`、`cdc0536 Add OpenViking model configuration admin`、`9862761 Fix OpenViking embedding switch rebuild`。
- 后端落地：`openviking[local-embed]>=0.3.22,<0.4`、provider-aware `ov.conf`、`OpenVikingVLMSetting`、embedding/VLM apply/test/history API、OpenViking doctor 诊断、非 Ollama provider 下跳过 Ollama degraded。
- 前端落地：OpenViking dashboard 的 Embedding / VLM 卡片、测试/保存分离、居中反馈弹框、provider-aware 健康状态、真实 PID 和运行版本展示。
- 验证覆盖：`tests/unit/test_openviking_config_uri.py`、`tests/unit/test_openviking_app_tasks.py`、`tests/integration/test_openviking_admin_api.py`、`frontend/tests/openviking-dashboard.test.tsx`、`frontend/e2e/openviking-dashboard-management-live.spec.ts`。
