# CodeAsk v1.0 实施路线图

> 本文件是 7 份子计划的**编排与验收文档**。具体每个任务的代码 / 测试 / 提交节奏在各 plan 文件里；本文回答三件事：先做什么、哪个阶段测什么、最后怎么算"做完了"。
>
> 当本文与具体 plan 冲突时，以具体 plan 为准。当具体 plan 与 SDD 冲突时，以 SDD 为准。当 SDD 与 PRD 冲突时，以 PRD 为准。

## 1. 顶层视图

```text
                     foundation
                          │
            ┌─────────────┴─────────────┐
            ▼                           ▼
     wiki-knowledge                code-index
            │                           │
            └─────────────┬─────────────┘
                          ▼
                    agent-runtime
                          │
            ┌─────────────┴─────────────┐
            ▼                           ▼
       metrics-eval              frontend-workbench
            │                           │
            └─────────────┬─────────────┘
                          ▼
                      deployment
```

7 份 plan。Foundation 是地基；其余 6 份按 DAG 依次落地，每份产出"可跑、可测、可演示"的中间产物。2026-05-02 起，v1.0 deployment 明确收缩为本地单进程部署；Docker / compose / 镜像发布后置到独立计划。

**当前实现状态（2026-05-02）：**

| Plan | 状态 | 当前结论 |
|---|---|---|
| foundation | 已完成 | 已合入 `main`，本地 tag：`foundation-v0.1.0` |
| wiki-knowledge | 已完成 | 已合入 `main`，本地 tag：`wiki-knowledge-v0.1.0`，Alembic head 到 `0005` |
| code-index | 已完成 | 已合入 `main`，本地 tag：`code-index-v0.1.0`，Alembic head 到 `0006` |
| agent-runtime | 已完成 | 已合入 `main`，tag：`agent-runtime-v0.1.0`，Alembic head 到 `0012`，REST + SSE API 已暴露 |
| frontend-workbench | 已完成 | React workbench 已落地；当前边界见 `../specs/frontend-workbench-handoff.md` |
| metrics-eval | 已完成 | feedback / frontend_events / audit_log、会话反馈接入、eval harness 与 CI workflow 已落地；Alembic head 到 `0016` |
| deployment | 未开始 | 本地单进程部署、前端静态挂载、CI、安全审计；Docker packaging 后置 |

**二期规划锚点（不属于 v1.0 必交付）：**

v1.0 出货后可单独规划 `tool-intelligence` / `code-context-optimization` 阶段，用于优化 Agent 使用代码工具的智能程度。该阶段规划前必须回看：

- `../design/code-index.md` §7.1 / §7.2：一期 Demo 边界与二期优化参考原则。
- `../design/tools.md` §8：工具系统一期 / 二期边界。
- `../design/agent-runtime.md`：Agent 状态机、工具调用轨迹和上下文预算的落点。

二期优化只能在不改变底层工具安全边界、不引入重型外部服务、不破坏单进程低部署门槛的前提下吸收开源实现经验。

## 2. 执行顺序与阶段产出

| # | Plan | 文件 | 任务 / 步骤 | 主产出 | 阶段交付状态 |
|---|---|---|---|---|---|
| 1 | foundation | `foundation.md` | 14 / 86 | FastAPI app + SQLAlchemy 2.0 async + Alembic + Fernet 加密 + subject_id 中间件 + structlog + `/api/healthz` + 23 单元/集成测试 | `curl /api/healthz` 返回 `status:ok` |
| 2 | wiki-knowledge | `wiki-knowledge.md` | 14 / 88 | features / documents / document_chunks / document_references / reports 表 + FTS5 三虚拟表 + n-gram 分词 + DocumentChunker + WikiSearchService 多路召回 + reports verify/unverify | 上传 .md → 搜索命中 → 报告草稿 → verified → 报告检索命中 |
| 3 | code-index | `code-index.md` | 12 / 80 | repos / feature_repos 表 + 异步 clone + worktree manager + ripgrep / ctags / file_reader + `/api/code/*` 工具 endpoints + 24h 闲置清理 | 注册仓库 → cloning → ready；grep / read / symbols 工具走通 |
| 4 | agent-runtime | `agent-runtime.md` | 19 / 96 | llm_configs（加密） + sessions 4 张关联表 + agent_traces + skills + LLM Gateway（LiteLLM 三协议） + 9 阶段状态机 + ToolRegistry + SSEMultiplexer + ScopeDetection / SufficiencyJudgement | 命令行端到端走通一次完整问答（MockLLM） |
| 5 | frontend-workbench | `frontend-workbench.md` + `../specs/frontend-workbench-handoff.md` | 19 / 158 + Phase B corrections | frontend/ 项目骨架（Vite + React + TanStack Query）+ SSE 客户端 + 会话/特性/设置三入口 + 会话附件 + 报告生成入口 + 管理员全局配置 + Playwright e2e smoke | 浏览器跑通当前 workbench happy path；完整 LLM Wiki 后置 |
| 6 | metrics-eval | `metrics-eval.md` | 13 / 80 | feedback / frontend_events / audit_log 表 + audit_log writer 替换 02/04 的 stub + `evals/` harness（scope_detection / sufficiency / answer_quality）+ exemplar cases + GH Actions eval workflow + 会话反馈持久化接入 | CI 跑 scope_detection + sufficiency 红线生效 |
| 7 | deployment | `deployment.md` | 7 / 34 | StaticFiles 挂载 frontend/dist + start.sh 本地启动增强 + pre-commit + backend/frontend GH workflows + 安全审计 checklist | `./start.sh` → healthz + SPA smoke 通过 |

## 3. 各阶段依赖

| Plan | 硬依赖（必须先完成） | 软依赖（接口契约对齐） |
|---|---|---|
| foundation | — | — |
| wiki-knowledge | foundation | — |
| code-index | foundation, wiki-knowledge（feature_repos 引用 features 表） | — |
| agent-runtime | foundation, wiki-knowledge, code-index | LLM 网关接口 (`llm-gateway.md`)、Tool 协议 (`tools.md`) |
| frontend-workbench | foundation（subject_id 契约） | wiki-knowledge / code-index / agent-runtime 暴露的 REST + SSE |
| metrics-eval | foundation, wiki-knowledge, agent-runtime（消费 agent_traces） | 02 / 04 plan 留下的 audit_log stub 调用点 |
| deployment | 全部前置 plan | — |

**Migration 链路**（连续无 gap，写到 alembic 后不可改）：

```text
foundation        : 0001
wiki-knowledge    : 0002 → 0003 → 0004 → 0005
code-index        : 0006
agent-runtime     : 0007 → 0008 → 0009 → 0010 → 0011 → 0012
frontend-workbench: 0013 → 0014 → 0015
metrics-eval      : 0016
deployment        : —（不动 schema）
```

## 4. 测试策略——按金字塔分层

### 4.1 总体分布（plan 完成后预期）

| 层级 | 工具 | 数量级（粗估） | 何时跑 |
|---|---|---|---|
| **单元测试** | pytest + pytest-asyncio | ~150-200 | 每个 task 必跑；CI PR 必跑 |
| **集成测试**（DB + API） | pytest + httpx ASGITransport + 临时 SQLite | ~80-100 | 每个 task 必跑；CI PR 必跑 |
| **前端组件测试** | Vitest + Testing Library | ~30-50 | 每个组件 task 必跑；CI PR 必跑 |
| **端到端测试**（浏览器） | Playwright | ~3-5（smoke 级） | 每个 plan 收尾跑；CI PR 跑 |
| **Agent eval**（线下回归） | 自家 runner + MockLLM | 30 + 30 + 1-2 exemplar | CI PR 跑（cheap model）；发布前手动跑全集（real model） |
| **安全审计**（自动） | pytest（路径遍历 / shell 注入 / MIME） | ~6 | CI PR 必跑 |
| **本地部署 smoke** | shell + uv/start.sh | 1 | 07 deployment 完成后 + 每次发布前 |

### 4.2 各 plan 内的测试节奏

每个 task 严格 TDD 五步：

1. **写失败测试**：先写期望行为
2. **跑测试确认 fail**：确认测试在没有实现的情况下确实红
3. **写最小实现**：让测试转绿
4. **跑测试确认 pass**：确认绿
5. **commit**：每个 task 一次

每个 plan 的**最后一个 task** 是回归 + lint + type check：

- `uv run pytest` 全量绿
- `uv run ruff check src tests`、`uv run ruff format --check`
- `uv run pyright src/codeask`
- 前端 plan 额外：`pnpm tsc --noEmit`、`pnpm test`、`pnpm e2e`

### 4.3 阶段间集成 smoke

每完成一个 plan，跑一次跨 plan 集成 smoke（目的是在两个 plan 衔接处发现集成问题）：

| 完成的 plan | 跨 plan smoke |
|---|---|
| foundation | `./start.sh` 起服务 → `curl /api/healthz` 通 |
| wiki-knowledge | curl 上传 / 搜索 / 创建报告 / 验证全链路 |
| code-index | curl 注册本机 git 仓 → 等 `ready` → grep 命中已知字符串 |
| agent-runtime | 跑 `tests/integration/test_orchestrator_sufficient.py` / `test_orchestrator_insufficient.py` / `test_orchestrator_ask_user.py`：MockLLM 回放三条运行时路径 |
| frontend-workbench | `pnpm dev` + 后端跑着 → 浏览器手动走 happy path（自动 Playwright 已覆盖核心） |
| metrics-eval | `uv run python -m evals.run --suite scope_detection` 拿到 score |
| deployment | `./start.sh` → curl healthz + `/` 静态页面 smoke → 停服务 |

### 4.4 线下 eval vs 线上指标

两套独立反馈环（详见 `../design/testing-eval.md` §1 + `../design/metrics-collection.md` §1）：

| 维度 | 线下 eval | 线上指标 |
|---|---|---|
| 何时收集 | CI 阶段（PR 必跑） + 发布前手动 | 用户真实使用时持续 |
| 来源 | `evals/` 目录的标注 case JSONL | `feedback` / `frontend_events` / `audit_log` / `agent_traces` 四张表 |
| 速度 | 秒级（MockLLM）/ 分钟级（cheap model） | 周 / 月级（要等真实数据沉淀） |
| 用途 | 改 prompt / 模型 / 检索时立刻知道好坏 | 看真实使用退化 / 飞轮是否启动 |
| 红线 | A2 top-1 准确率不退化 > 5pp / A3 漏判率不上升 | deflection rate 长期上升、错误反馈率不持续上升 |

## 5. 各 plan 的验收标志

每份 plan 在文件末尾有**自家"验收标志"清单**。本文只列**最关键的 1-3 条**作快速核对：

### 5.1 foundation 验收
- [x] `./start.sh` 在 30 秒内（首次 `uv sync` 之后）跑起服务
- [x] `curl /api/healthz` 返回 `{"status":"ok","db":"ok","version":"0.1.0","subject_id":...}`
- [x] 缺失 `CODEASK_DATA_KEY` 时 `start.sh` 给清晰错误，**不**启动到一半
- [x] 23 测试 PASS / ruff + pyright 零错

### 5.2 wiki-knowledge 验收
- [x] 上传 markdown → `document_chunks` 表落地 → `docs_fts` / `docs_ngram_fts` 同步索引
- [x] `GET /api/documents/search?q=订单` 同时命中 BM25 通道和 n-gram 通道
- [x] 报告 verify → `reports_fts` 命中；unverify → `reports_fts` 不命中
- [x] alembic head = `0005`

### 5.3 code-index 验收
- [x] `POST /api/repos`（local_dir 来源）→ 后台 cloning → `status=ready`，bare git 数据落 `~/.codeask/repos/<repo_id>/bare/`
- [x] `POST /api/code/grep` 找到已知字符串、行号匹配
- [x] 模拟 25h 后 cleanup job 移除 worktree、保留 DB 中的 binding 记录但 path 置 null
- [x] alembic head = `0006`

### 5.4 agent-runtime 验收
- [x] `tests/integration/test_orchestrator_sufficient.py` / `test_orchestrator_insufficient.py` / `test_orchestrator_ask_user.py` 跑通三条路径：sufficient（不进代码层）/ insufficient（进代码层）/ ask_user
- [x] `agent_traces` 表每个阶段有一行；含 ScopeDetection 输入/输出 + SufficiencyJudgement 输入/输出（A2 / A3 eval 数据来源）
- [x] LLM API key 落库为加密；`GET /api/llm-configs` 返回 mask 后的 key
- [x] alembic head = `0012`

### 5.5 frontend-workbench 验收
- [ ] 会话 / 特性 / 设置三入口可用，一级与二级侧边栏均可收起展开
- [ ] 普通用户匿名可用，管理员登录后只能看到全局配置；普通用户不能读取全局 LLM 配置
- [ ] 会话支持搜索、新建、三点菜单、删除确认、批量删除、默认会话发送、会话附件上传 / 重命名 / 说明 / 删除和报告生成入口
- [ ] 特性支持搜索、新建、删除确认、知识库上传入口、报告列表、仓库 checkbox 关联和特性 Skill 管理
- [ ] LLM 配置支持 OpenAI / Anthropic 协议选择、添加、编辑、switch 启停、删除；不展示 Max Tokens / Temperature / RPM / 剩余额度 / 默认配置切换
- [ ] Playwright happy-path e2e 通过
- [ ] `corepack pnpm --dir frontend build` 零错误

Dashboard、feedback 持久化和完整 LLM Wiki 管理不作为 frontend-workbench 当前验收阻塞项；见 `../specs/frontend-workbench-handoff.md` §9。

### 5.6 metrics-eval 验收
- [x] `uv run python -m evals.run --suite scope_detection` 拿到 score；JSON 报告落盘
- [x] CI workflow 在 PR 阶段触发 scope_detection + sufficiency；红线（top-1 退化 > 5pp）能阻断
- [x] 反向指标审计单测：grep `tools_called_count` 等不在任何 dashboard API 输出
- [x] alembic head = `0016`

### 5.7 deployment 验收
- [ ] 后端在 `frontend/dist/index.html` 存在时通过 `/` 直接服务 SPA，且 `/api/*` 不被静态路由吞掉
- [ ] `./start.sh` 缺少 `CODEASK_DATA_KEY` 时清晰失败；dist 缺失时自动构建或清晰警告；backend 仍可启动
- [ ] 安全 checklist 中 AUTO 项有对应 pytest 单测全绿；MANUAL 项不包含 Docker / compose / 镜像发布
- [ ] tag `deployment-v0.1.0` 已打

## 6. v1.0 整体出货验收（MVP）

7 份 plan 全部完成后，跑下面这份"v1.0 验收 checklist"。**任意一条不过 = 不出货**：

### 6.1 自动化（CI 必跑）

- [ ] `uv run pytest` 全量 PASS（预计 250-350 测试，含 backend 单元/集成/security）
- [ ] `uv run ruff check src tests evals` 零错误
- [ ] `uv run pyright src/codeask` 零错误
- [ ] `cd frontend && pnpm tsc --noEmit` 零错误
- [ ] `cd frontend && pnpm test` 全量 PASS
- [ ] `cd frontend && pnpm e2e` Playwright happy-path PASS
- [ ] `uv run python -m evals.run --suite scope_detection --mock` PASS（A2 top-1 ≥ baseline）
- [ ] `uv run python -m evals.run --suite sufficiency --mock` PASS（A3 漏判率 ≤ baseline）
- [ ] `./start.sh` 本地启动 smoke 通过，`/api/healthz` 和 `/` 同时可达

### 6.2 端到端 happy path（手动）

模拟真实用户旅程：

1. 干净环境 → `export CODEASK_DATA_KEY=$(...)` → `./start.sh`
2. 浏览器打开 frontend dev server → 自动进入会话页，未登录用户可直接使用
3. 创建特性 "订单" → 上传一份 markdown 文档（基础 Wiki 上传入口）
4. 管理员登录 → 设置 → 注册一个本机 git 仓（local_dir 来源） → 等 `ready`
5. 普通特性详情 → 勾选关联仓库 "order-service"
6. 新建会话 → 提问 "订单超时是怎么处理的？" → 看到 SSE 阶段切换（ScopeDetection → KnowledgeRetrieval → SufficiencyJudgement → AnswerSynthesis） → 拿到回答
7. 上传日志 → 在会话数据区看到该会话自己的附件 → 重命名 / 编辑用途说明 / 删除
8. 点"生成报告" → 绑定特性 → 生成成功后跳转到特性的问题报告 tab
9. 管理员设置 → 创建 / 编辑 / 启停 / 删除全局 LLM 配置
10. 运行 `corepack pnpm --dir frontend test:e2e`

### 6.3 安全审计（手动）

`docs/v1.0/plans/deployment-security-checklist.md` 中 MANUAL 项确认：

- [ ] 默认监听 `127.0.0.1`（grep 业务代码 `0.0.0.0` 应零命中）
- [ ] `./start.sh` 缺少 `CODEASK_DATA_KEY` 时退出并打印明确错误
- [ ] `frontend/dist/index.html` 存在时，`/` 直接返回 SPA；不存在时 `/api/*` 仍可用
- [ ] 加密字段验证：`sqlite3 ~/.codeask/data.db "select api_key_encrypted from llm_configs"` 看不到明文
- [ ] 路径遍历手测：尝试 `POST /api/code/read` 路径含 `../etc/passwd`，应返 `INVALID_PATH`
- [ ] 上传 .exe 改名 .pdf 应被 MIME 检查拒绝
- [ ] 依赖扫描：`pnpm audit` + `uv pip list --outdated` 无高危
- [ ] 关闭服务 → `~/.codeask/data.db` 不可写损坏（WAL checkpoint）
- [ ] LLM API key 在所有 GET 类 API 响应中都是 mask 状态

### 6.4 SDD 与 PRD 对齐

- [ ] `prd/codeask.md` §9 对齐表中所有"按对齐表更新"项 SDD 已落地
- [ ] PRD §5 主指标 / 致命假设 / 飞轮指标在 metrics-collection.md 状态全部 `ready`（alpha 第 1 周校准前可保留少量 `partial`）
- [ ] `design/testing-eval.md` §4 三组 eval 集骨架就绪 + 至少 1 exemplar case

### 6.5 文档对齐

- [ ] `README.md`（仓库根）含完整本地部署演示 + 配置表
- [ ] `docs/STRUCTURE.md` / `docs/v1.0/README.md` / `docs/v1.0/design/overview.md` 描述与代码现状一致
- [ ] 各 plan 的"验收标志"小节全部勾选

### 6.6 飞轮 sanity（不阻塞 MVP，但出货时记录）

`metrics-collection.md` §3 / §4 / §5 / §6 状态字段当前快照：

- 致命假设三组指标的 `TODO` 全部 ≥ `partial`
- deflection rate 双轨测量数据流通（即使数字还小）
- 错误反馈率有写入路径（即使没人触发过 `wrong`）
- 月均验证报告数有写入路径

具体阈值不锁——alpha 第 1 周回填校准。

## 7. 推荐执行节奏

### 7.1 单 plan 内

```text
开始 plan
  └─ Task 1：写测试 → fail → 实现 → pass → commit
  └─ Task 2：...
  ...
  └─ 最后一个 Task：lint + type check + 全量回归 + 打 git tag
```

每个 task 控制在 30 分钟内（可能比 2-5 分钟/步骤的累加略多，因为含 review）；超过就要怀疑是不是 task 拆得不够细，回头重新切分。

### 7.2 跨 plan

```text
foundation 完成 → tag foundation-v0.1.0 → 跑跨 plan smoke → 进入下一 plan
wiki-knowledge 完成 → tag wiki-knowledge-v0.1.0 → 跨 plan smoke → 下一 plan
...
全部完成 → 跑 §6 v1.0 整体验收 → tag v1.0.0 → 出货
```

### 7.3 执行模式选择（参考 writing-plans skill）

| 模式 | 适用 |
|---|---|
| Subagent-Driven | 每 task 派独立 subagent + 两阶段 review；适合不熟悉的 plan / 高风险 task |
| Inline | 当前会话顺序跑 + checkpoint 让用户审；适合熟悉的 plan / 节奏紧 |

## 8. 已知交付债 / 风险

| 项 | 计划处理 | 处理时机 |
|---|---|---|
| 02 / 04 plan 留 `audit_log_writer` stub | 06 metrics-eval plan 替换为真实实现 | 06 执行时 |
| LiteLLM 在某些私有模型场景失控（stream chunking 异常） | 切回直连 SDK | 真实使用观察后 |
| 前端 dev 模式需手动起 backend daemon | start.sh 增加 `--dev` 选项 | 07 deployment（可选） |
| Eval 种子 case 仅 1-2 exemplar | 30 / 30 / 20 条标注是内容工作 | alpha 第 1 个月扩 |
| 真模型 eval 不进 CI 默认 | 手动 `workflow_dispatch` 触发 | alpha 上线后 |
| metrics-collection.md 中 TODO 状态项 | alpha 第 1 周补 + 校准阈值 | alpha 第 1 周 |

## 9. v1.0 不在范围（明确不做）

引用 PRD §6.2 + `dependencies.md` §7 Anti-list：

- 向量数据库 / embedding 推理（FTS5 + n-gram + 精确信号召回够）
- Postgres 默认（SQLite WAL 单进程是底座）
- Redis / RabbitMQ / Kafka（APScheduler 单进程足够）
- Elasticsearch / Meilisearch
- K8s helm chart 默认部署
- Docker / compose / 镜像发布（后置独立 packaging 计划）
- Sourcegraph / AnythingLLM / Dify 作底座
- LangChain / LlamaIndex / Haystack
- Streamlit / Gradio
- 真鉴权（OIDC / LDAP / SSO）
- 监控 dashboard（线上指标进 metrics-collection.md，非 dashboard）
- 多租户 / 多组织
- 提交验证 / 审核工作流（draft → verified 一步）
- TipTap in-app 文档编辑

## 10. 后续操作建议

- 每完成一个 plan 在 git 打 tag：`foundation-v0.1.0` / `wiki-knowledge-v0.1.0` / ...
- 每个 plan 的子任务在 feature branch 跑、PR review、合入 main
- alpha 第 1 周：回填 `metrics-collection.md` TODO 项 + 第一次 deflection rate 阈值校准
- alpha 第 1 月：A2 / A3 eval 集种子从 30 扩到 100 / 80 条
- alpha 第 3 月：评估"是否触发 MVP+"（向量叠加 / LSP / 真鉴权三件中是否有线上数据要求）

## 11. 引用

- PRD：`../prd/codeask.md`
- SDD 总览：`../design/overview.md`
- 文档约定：`../../STRUCTURE.md`
- 各 plan：本目录其他 `.md` 文件
