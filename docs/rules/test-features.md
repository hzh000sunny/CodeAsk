# 测试特性 Fixture 规则

> 范围：跨版本规则
> 状态：Active
> 起始：2026-05-20

本文定义 CodeAsk 中"测试特性 Fixture"的稳定产品规则。

本规则同时约束：

- spike 阶段的真实 Wiki / 报告 / 代码仓导入
- 版本级 E2E 与连续会话回归
- RAG 召回与质量基线
- 长上下文、特性源码调查、行动轨迹的真实数据回放

当版本级 PRD、SDD 或实现计划需要使用真实"测试特性"时，应引用本文与 `tests/fixtures/features/` 实际数据，而不是临时挑选数据集。

---

## 1. 设定目标

CodeAsk 的验收必须覆盖真实用户路径，不允许全部用合成样本。但每次版本验收都临时挑特性会导致：

- 不同版本结果不可对比（样本不一致）
- 同一特性在 spike 与 E2E 中行为漂移
- 真实数据敏感性导致没法在公开仓库里持续回归
- 用户首次复现验收时缺少明确样本指引

因此约定一组**长期固定、可公开提交、跨版本通用**的测试特性 fixture。

---

## 2. 固定测试特性集

| Slug | 显示名 | 上游 | Wiki 位置 | Git URL |
|---|---|---|---|---|
| `opencode` | OpenCode | `https://github.com/anomalyco/opencode` | `tests/fixtures/features/opencode/wiki/` | `git@github.com:anomalyco/opencode.git` |
| `anything-llm` | AnythingLLM | `https://github.com/Mintplex-Labs/anything-llm` | `tests/fixtures/features/anything-llm/wiki/` | `git@github.com:Mintplex-Labs/anything-llm.git` |
| `openviking` | OpenViking | `https://github.com/volcengine/OpenViking` | `tests/fixtures/features/openviking/wiki/` | `git@github.com:volcengine/OpenViking.git` |

每个特性目录下还有 `README.md`，记录该特性的上游主语言、抓取日期、锁定版本和典型 query。

### 2.1 为什么是这三个

- **opencode**：v1.0.4 CodeAsk 主链路已经深度集成的外部 Agent 引擎；既是 CodeAsk 自己依赖的对象，又是研发实际会问的真实问题来源。
- **anything-llm**：v1.0.5 RAG 设计的处理管线参考；wiki 内容覆盖文档管理、TextSplitter、embedding、vector DB、agent，对召回质量是一份天然的多模块挑战样本。
- **openviking**：v1.0.5 自身的 RAG 后端；wiki 覆盖 20 个模块，可作为 CodeAsk 集成 OpenViking 时"自查文档"的反查样本。

三者都是公开开源项目，许可证允许引用与 wiki 文档复制；wiki dump 体积合计约 1.3 MB，适合长期跟随仓库。

### 2.2 不在这里的内容

- 公司内部真实业务特性、Wiki、报告、代码仓不进本目录
- 个人测试用的临时特性不进本目录
- 公开但非长期回归依赖的项目不进本目录（避免目录膨胀）

---

## 3. 使用规则

### 3.1 何时使用

下列场景**必须**优先使用本 fixture，不允许另起一套：

- v1.0.5 及之后版本的 Phase 0 spike 中"真实样本"环节
- 任何版本的 RAG 召回质量基线测试
- 任何版本的连续会话回归（多轮追问 / 刷新继续追问 / 工具行动摘要）
- 特性范围代码调查 live E2E（`prepare_worktree` + 真实源码读取）
- 长上下文 live E2E

下列场景**可以选择性**使用本 fixture：

- admin / 权限 / 数据隔离回归（特性结构本身不是这类场景的核心，但有 fixture 总比合成数据干净）
- Wiki 编辑 / 报告生成验收（可以用更小样本，但 fixture 也可）

下列场景**不**使用本 fixture：

- 单元测试（应该用 mock，不依赖真实特性）
- 升级路径回归（应该用真实生产数据备份，不是 fixture）
- 性能压测（合成大数据集更合理）

### 3.2 如何注册

需要回归时，按下列顺序：

1. 准备临时 CodeAsk 数据目录（不污染 `/home/hzh/.codeask` 真实数据）
2. 启动 CodeAsk，作为 admin 登录
3. 注册三个特性，slug 严格按本规则 §2 表格
4. 通过 CodeAsk Wiki 导入接口把 `tests/fixtures/features/<slug>/wiki/` 完整导入到对应特性
5.（按场景需要）注册三个代码仓，URL 指向上游 git URL；若本机已 clone 到 `references/<slug>/`，也可用 `local_dir` 模式
6. 跑回归脚本 / live E2E / spike 流程

具体脚本和命令由各版本计划记录；本文只规定 fixture 内容与注册一致性。

### 3.3 何时刷新 wiki dump

- 上游项目重大版本变更（例如 anything-llm 主版本跳跃）后可刷新
- 刷新时必须更新对应 `tests/fixtures/features/<slug>/README.md` 中的"wiki 抓取日期"和"上游主语言 / 锁定版本"
- 旧版本回归遇到 wiki 内容差异时，可以临时 checkout 到刷新前的 commit 跑回归；不允许同时维护多份 dump

### 3.4 不允许的行为

- 不允许在 fixture 目录里放任何敏感内容（密钥、内部数据、客户信息）
- 不允许把测试运行产生的临时数据（导入失败的临时文件、向量缓存、worktree）写回 fixture 目录
- 不允许通过本目录提交对 CodeAsk 主产品代码 / 数据库 schema 的变更
- 不允许在不更新本规则的情况下增删测试特性

---

## 4. 与代码仓的边界

`tests/fixtures/features/<slug>/wiki/` 只承载 wiki dump，**不**承载源码 clone。

代码仓 clone 由开发者按需放到 `references/<slug>/`（已在 `.gitignore`）。每个特性 README 里都给出 `git clone` 命令。

| 内容 | 位置 | 是否提交到 git |
|---|---|---|
| Wiki Markdown dump | `tests/fixtures/features/<slug>/wiki/` | 是 |
| 特性 README（slug / git url / 元信息） | `tests/fixtures/features/<slug>/README.md` | 是 |
| 源码 clone | `references/<slug>/` | 否 |
| 运行时数据（导入后的 CodeAsk DB / 索引 / worktree） | `$CODEASK_DATA_DIR` 或临时目录 | 否 |

---

## 5. 与其它规则的关系

- `docs/rules/problem-report.md`：测试中生成的报告标题仍必须遵守 `YYYY-MM-DD <描述>` 格式
- `docs/rules/ui-feedback.md`：使用 fixture 跑 UI 回归时仍按全局反馈规则验收
- `docs/rules/upgrade-compatibility.md`：升级路径回归不使用本 fixture（用真实数据备份）
- `docs/DEVELOPMENT_ACCEPTANCE.md`：本规则补充其"真实数据 / 真实链路"的可重复 fixture 基线
- `docs/STRUCTURE.md`：本文件遵守 rules/ 目录约定，跨版本生效

---

## 6. 变更管理

修改本规则需要：

1. 同步更新 `tests/fixtures/features/` 实际目录内容
2. 在当前正在交付的版本 `plans/acceptance-checklist.md` 中检查影响范围
3. 在 commit message 中说明本规则与 fixture 的同步关系

回滚一次 fixture 内容变更时，必须明确写明回滚到哪个 commit 与原因。
