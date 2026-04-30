# Foundation Hand-off — 给后续 6 份子计划

本文档记录 foundation 计划留下的“接口契约”。02 / 03 / 04 / 05 / 06 / 07 在添加自家功能时遵循以下约定。

## 1. 添加新表

每份后续计划添加自家表的标准流程：

1. 在 `src/codeask/db/models/` 下新建模块（按业务域命名，如 `wiki.py` / `code_repo.py` / `session.py` / `agent_trace.py`）
2. 在 `src/codeask/db/models/__init__.py` 把新模型 re-export
3. 在 `alembic/versions/` 加一份新 migration，`down_revision` 指向上一个 revision
4. 用 `op.create_table(...)` 显式建表（不用 autogenerate，避免漂移）
5. 跑 `uv run pytest` 必须仍全绿（已有测试不能破）

**禁止**：直接在 `0001_initial.py` 中加表。`0001` 已发布，会 break 所有部署。

## 2. 添加新 API

1. 在 `src/codeask/api/` 下新建 router 模块
2. 在 `src/codeask/app.py` 的 `create_app()` 中 `app.include_router(..., prefix="/api")`
3. 路由处理函数通过 `request.app.state.session_factory` 拿 session，通过 `request.state.subject_id` 拿身份
4. 集成测试用 `tests/conftest.py` 提供的 `client` fixture

## 3. 加密敏感字段

任何 DB 字段存 LLM API key、用户 token 等敏感数据时：

- 字段命名后缀 `_encrypted`
- 写入前用 `Crypto(settings.data_key).encrypt(plaintext)`
- 读出后用 `Crypto(settings.data_key).decrypt(ciphertext)`

不要绕过这层。原始密钥落库就是事故。

## 4. 新增配置

新计划如果需要新环境变量：

- 加到 `Settings` 类，字段名小写、加 `description`
- 改 README 的配置项表格
- 如果是必填，用 `Field(...)` 强制，缺失时 fail-fast，不要默默 fallback

## 5. 不在本地基范围

- LLM 网关：04 agent-runtime 计划负责（含 `CODEASK_DATA_KEY` vs `llm-gateway.md` 旧文档 `CODEASK_MASTER_KEY` 的统一）
- 仓库 / worktree：03 code-index 计划负责
- 文档 / 报告 / FTS5：02 wiki-knowledge 计划负责
- `agent_traces` / `feedback` / `frontend_events` / `audit_log`：04 / 06 各自负责
- 前端编译产物挂载：05 frontend-workbench 计划负责
- Docker / 多阶段镜像：07 deployment 计划负责

## 6. SDD 文档同步

凡是改动了某个 SDD 文档对应的实现，要同步更新该文档的“与 PRD 的对齐”小节。本计划没有改动任何 SDD，因为它就是 SDD 的第一次实现。
