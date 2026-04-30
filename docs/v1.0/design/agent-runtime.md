# Agent 运行时设计

> 本文档属于 v1.0 SDD，描述 Agent 运行时的实现方式。
>
> 产品契约见同版本 `prd/codeask.md`。当 SDD 与 PRD 冲突时，以 PRD 为准。

## 1. 目标

Agent 运行时负责把一次用户请求组织成可审计的调查过程。它不是简单地把上下文拼给模型，而是通过状态机约束模型先查什么、后查什么、什么时候问用户、什么时候结束。

核心目标：

- 保证检索优先级：知识库（含已验证报告高优先级）→ 代码。
- 保证工具访问都经过统一边界。
- 保证答案带证据和不确定点；不确定时坦白。
- 保证调查过程可以通过事件和轨迹日志回放。

PRD 中两个致命假设直接落在本运行时：

- **A2 自动定界要够准**（`prd/codeask.md` §7.1.A2）：失败时通过 `ask_user` 回退或全局检索降级。
- **A3 "知识库够不够" 的自动判断要够准**（`prd/codeask.md` §7.1.A3）：判断必须在 UI 透明，并提供"再深查一下"按钮兜底。

## 2. 状态机

一期 Agent 状态机（与 PRD §3 主链路对齐：知识库 → 代码 两层）：

```text
InputAnalysis
→ ScopeDetection
→ KnowledgeRetrieval        // 统一检索知识库（报告 + 文档）
→ SufficiencyJudgement      // Agent 判断知识库是否足以回答
   ├─ 足够 → EvidenceSynthesis
   └─ 不足 → CodeInvestigation
→ VersionConfirmation       // 仅当代码调查需要绑定具体 commit
→ EvidenceSynthesis
→ AnswerFinalization
→（可选）ReportDrafting
```

阶段可以提前结束。例如知识库直接命中且 SufficiencyJudgement 判定足够时，跳过代码调查直接进入合成。

**与旧版的差异**：旧版 ReportRetrieval / ReportJudgement / WikiRetrieval / WikiJudgement 四阶段，合并为 KnowledgeRetrieval + SufficiencyJudgement 两阶段。报告作为知识库内的高优先级文档，不再单独走一层。

## 3. 阶段职责

| 阶段 | 职责 | 允许工具 |
|---|---|---|
| `InputAnalysis` | 分析用户问题、日志、附件、上下文字段 | `read_log` |
| `ScopeDetection` | 自动选择相关特性；失败时回退 `ask_user` 或全局检索 | `select_feature`, `ask_user` |
| `KnowledgeRetrieval` | 检索知识库（报告 + 文档），合并排序 | `search_wiki`, `search_reports`, `read_wiki_doc`, `read_report` |
| `SufficiencyJudgement` | 判断知识库证据是否足以回答 | 无外部工具（基于已收集证据推理） |
| `CodeInvestigation` | 检索代码、读取文件、定位符号 | `grep_code`, `read_file`, `list_symbols` |
| `VersionConfirmation` | 确认代码版本（branch / tag / commit） | `ask_user` |
| `EvidenceSynthesis` | 归并证据，形成候选结论 | 无外部工具 |
| `AnswerFinalization` | 输出最终回答（结论 + 证据折叠 + 不确定点） | 无外部工具 |
| `ReportDrafting` | 生成报告草稿（可选） | 可读已收集证据 |

## 4. 自动定界（A2 落地）

如果用户没有手动指定 `feature_ids`，Agent 必须先调用一次 `select_feature`。

输入给模型的定界上下文包括：

- 用户问题。
- 日志分析摘要。
- 所有特性的名称和简介。
- 每个特性的关键错误码、服务名、模块名摘要。

输出：

```json
{
  "feature_ids": ["feature_order"],
  "confidence": "high",
  "reason": "日志中出现 order submit 相关路径和 OrderService 符号"
}
```

允许选 0 个、1 个或多个特性。

**回退路径**（PRD §3 "定界失败" + §7.1.A2 缓解措施）：

- `confidence` 为 low 或多个特性概率接近 → 触发 `ask_user`，让用户从候选列表选
- 选 0 个特性 → 全局知识库检索降级（不限定特性）
- UI 必须醒目展示 Agent 选了哪个特性，提问者可一键改
- 定界结果与用户反馈纳入 eval 集（A2 假设的验证数据来源，详见 `testing-eval.md`）

## 5. 预检索

为了不让模型自由跳过知识库证据，API 网关在进入主循环前执行一次同步预检索：

```text
build_query(user_input, log_analysis)
→ search_wiki + search_reports（合并、报告高优先级）
→ 注入 Agent 初始上下文（L4）
```

Agent 仍可以在后续用更精炼的查询词再次调用工具。预检索结果以"知识库命中"统一表达，不再分"报告命中 vs 文档命中"两段——报告作为高优先级文档与文档同列展示，但排名靠前。

## 6. 充分性判断（A3 落地）

`SufficiencyJudgement` 是 PRD A3 致命假设的实现入口。判断错误的代价：

- 判过早（"够"实际不够）→ 代码层未启动 → 用残缺答案误导
- 判过晚（"不够"实际够了）→ 多调一次代码层 → 慢、贵

实现要求：

- **输入**：用户问题 + 已检索到的知识库证据片段 + 证据相关性分数
- **输出**：`enough | partial | insufficient` + 缺什么的简短说明
- **UI 透明**：通过 `sufficiency_judgement` SSE 事件把判断结论和理由暴露给前端（"已查 4 篇文档，但均未涉及字段变更影响"）
- **兜底**：UI 提供"再深查一下"按钮，强制进入 `CodeInvestigation`
- **eval 闭环**：判断结论与最终用户反馈（"已解决 / 部分解决 / 答错"）的关联，作为 A3 假设的验证信号，详见 `testing-eval.md`

## 7. 代码调查

代码调查只在 `SufficiencyJudgement` 判定知识库不足时启动。Agent 不直接读文件系统，必须通过代码工具。

默认策略：

1. 优先用日志中提取的符号、文件路径、错误码做精确检索。
2. 如果符号明确，先 `list_symbols` 再 `read_file`。
3. 如果符号不明确，先 `grep_code`。
4. 对大型 monorepo，优先指定 `path_glob` 或从特性绑定仓库缩小范围。
5. 工具结果不足时，Agent 可以重写查询词，但单轮工具调用总数受限。

## 8. 版本确认

当代码调查需要读取仓库时，运行时需要准备 `repo_id + ref/commit`。

策略：

- 如果用户已指定 commit，直接使用。
- 如果用户提供 branch/tag，解析到 commit 后使用。
- 如果日志里有版本候选，前端或 Agent 可请求用户确认。
- 如果没有版本信息，可以用默认分支做探索性预查。
- 生成正式报告前必须有明确 commit。

触发 `ask_user` 的情况：

- 默认分支预查无法收敛。
- 默认分支代码与日志线索冲突。
- 多个候选根因依赖不同代码版本。
- 用户请求生成正式报告但当前代码证据未绑定 commit。

## 9. Prompt 分层

Prompt 从稳定到易变分层：

```text
L0 全局规则：研发问答 Agent 角色、输出格式、工具协议
L1 调查状态：当前阶段、允许工具、退出条件
L2 特性基础上下文：选中特性 summary_text、navigation_index、feature skill
   ※ digest 仅含文档摘要，不含报告（避免案例污染常青背景，详见 wiki-search.md §11）
L3 仓库上下文：repo、ref、commit、语言统计、路径提示
L4 预检索结果：知识库命中（含报告高优先级合并 —— 报告通过 query 匹配在此层进入）
L5 会话历史：用户消息、工具调用、模型回答
L6 当前输入：问题、日志摘要、附件摘要、上下文字段
```

这样便于未来接 prompt cache，也能避免每轮重复拼接无关内容。

## 10. 工具循环

Agent 主循环：

```text
组装 messages + tools
→ 调 LLM
→ 流式输出 token
→ 捕获 tool_call
→ 校验工具名、参数和阶段权限
→ 调用工具
→ 工具结果截断和结构化
→ 回填 tool_result
→ 继续下一轮
```

硬上限：

- 单轮最多 20 次工具调用，默认可配置。
- `ask_user` 单轮最多 3 次。
- 单条工具结果默认不超过 4KB。

软上限：

- 上下文接近模型窗口 80% 时，截断早期工具结果，并保留结构化摘要。

## 11. SSE 事件

前端通过 SSE 展示调查过程：

```text
event: stage
event: token
event: tool_call
event: tool_result
event: evidence
event: ask_user
event: sufficiency_judgement   // A3 判断在 UI 透明的载体
event: done
event: error
```

`stage` 示例：

```json
{
  "name": "code_investigation",
  "status": "running",
  "message": "知识库不足，正在使用默认分支进行探索性代码调查"
}
```

`sufficiency_judgement` 示例：

```json
{
  "verdict": "insufficient",
  "reason": "已查 4 篇文档，但均未涉及字段变更影响清单",
  "next": "code_investigation"
}
```

## 12. 错误回收

工具失败不直接中断会话。工具异常作为结构化 `tool_result` 回填给模型：

```json
{
  "ok": false,
  "error_code": "REPO_NOT_READY",
  "message": "仓库仍在预取，当前不可读取代码"
}
```

LLM 调用失败由 LLM 网关重试。重试耗尽后，API 输出 SSE `error`，本轮会话停在可恢复状态。

## 13. 轨迹记录

每轮 Agent 运行写轨迹日志：

- 当前阶段。
- 系统提示摘要或完整提示。
- LLM 原始事件。
- 工具调用参数。
- 工具结果。
- 证据项。
- `ScopeDetection` 输入 / 输出 / 用户是否改特性（A2 假设的 eval 数据来源）。
- `SufficiencyJudgement` 输入证据 / 输出结论 / 用户是否点"再深查一下"（A3 假设的 eval 数据来源）。
- 最终回答。
- 用户反馈（已解决 / 部分解决 / 答错）—— A2/A3 闭环验证信号。

轨迹日志用于调试、审计和 eval 复盘。

## 14. 与 PRD 的对齐

本文已按 `prd/codeask.md` §9 对齐表更新，主要变化：

- 状态机从 11 阶段简化为 9 阶段：报告 / 知识库的两阶段四步骤（Retrieval + Judgement × 2）合并为 KnowledgeRetrieval + SufficiencyJudgement
- 显式落地 A2（定界回退）和 A3（充分性判断透明 + 兜底）两个致命假设
- 新增 `sufficiency_judgement` SSE 事件让 A3 判断在 UI 透明
- 轨迹记录新增 ScopeDetection / SufficiencyJudgement 的 eval 数据点
- §9 Prompt L2 显式说明"基础上下文 digest 仅含文档摘要、不含报告"——报告只通过 L4 query-driven 命中进入（与 `wiki-search.md` §11 对齐）
