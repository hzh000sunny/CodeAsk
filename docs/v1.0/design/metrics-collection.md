# 指标采集设计（alpha 用户跟踪表骨架）

> 本文档属于 v1.0 SDD，描述 PRD §5 成功指标 + §7.1 致命假设的**线上**数据采集机制。
>
> 与 `testing-eval.md` 的关系：本文是**线上、真实、慢**的指标系统（看真实使用发生了什么）；`testing-eval.md` §4 是**线下、标注、快**的 Agent 评测（验证模型行为是否回归）。两者互补——eval 是改 prompt 的反馈环，指标是产品决策的反馈环。
>
> 当 SDD 与 PRD 冲突时，以 PRD 为准。

## 1. 目标

PRD §10 第 2 步要求"建立 alpha 用户跟踪表"。本文落地这件事：

- 把 PRD §5（成功指标）+ §7.1（致命假设 A1 / A2 / A3）每个指标写清楚——**定义 / 数据来源 / 公式 / 阈值方向 / 当前状态**
- 锁定数据采集口径（可 vs 不可、采什么字段、写哪张表），避免 alpha 阶段临时改 schema
- **不锁阈值具体数值**——PRD §5 明确"MVP 阶段拍数字没有意义，等真实部署校准"

## 2. 指标全景

```text
PRD §5 + §7.1 涉及的指标
├── 致命假设验证（§3）
│   ├── A1 Maintainer 录入摩擦（PRD §7.1.A1）
│   ├── A2 自动定界准确率（PRD §7.1.A2）
│   └── A3 充分性判断准确率（PRD §7.1.A3）
├── 主指标（§4）
│   └── deflection rate（PRD §5.1，双轨测量）
├── 质量护栏（§5）
│   ├── 错误反馈率（PRD §5.2）
│   ├── 回流率（PRD §5.2）
│   └── 报告拒绝率（PRD §5.2）
├── 飞轮健康（§6，次级）
│   ├── Maintainer 月均验证报告数
│   ├── 已验证报告被命中次数
│   └── 知识库文档新增 / 更新频率
└── 反向指标（§7，明确不采）
```

每条指标统一字段：

| 字段 | 含义 |
|---|---|
| **定义** | 一句话语义 |
| **数据来源** | 哪张表 / 哪个事件 / 哪个轨迹日志 |
| **公式** | 如何计算 |
| **阈值方向** | 健康方向（"持续上升 = 警报" / "为 0 = 飞轮没启动" 等） |
| **采集状态** | `ready` / `partial` / `TODO` |

`TODO` 项是 alpha 之前必须补完的事；`partial` 项是已经在写但需要 review。

## 3. 致命假设验证指标（PRD §7.1）

致命假设错了 = 产品死。这一组指标是**最早需要看见的数据**，alpha 阶段 Day 1 必须能看到。

### 3.1 A1 — Maintainer 维护知识库的意愿

PRD §7.1.A1：Maintainer 觉得"维护时间 > 省下的被打扰时间" → 飞轮死。

| 指标 | 定义 | 数据来源 | 公式 | 阈值方向 | 状态 |
|---|---|---|---|---|---|
| 录入耗时 | Maintainer 每次新增 / 编辑文档 / 创建报告草稿 / 验证报告 的实际时长 | 前端事件：`doc_edit_session_started` / `doc_edit_session_completed`；前端打点 | `Σ(completed_at - started_at) per maintainer per month` | 不锁绝对值；趋势：随飞轮转起来应稳定或下降 | TODO |
| 被打扰减少 | 自报：Maintainer 每周自评"本周被同事直接来问的次数" | 周一推送的简易表单（前端弹窗，可跳过） | `count per maintainer per week` | 持续下降 = A1 成立 | TODO |
| 一键沉淀使用率 | "从会话生成报告草稿"按钮被点击数 / "部分解决" 会话数 | 前端事件 + DB | `clicks / partial_sessions` | 持续上升 = 录入摩擦低 | TODO |

**采集要点**：

- 录入耗时**只统计 Maintainer 角色**（一期通过自报身份 + UI 行为推断："新建特性 / 上传文档 / 验证报告"任意一项 ≥ 1 次的 `subject_id`）
- "被打扰减少" 是**自报数据**——alpha 必备但不进 dashboard 当 KPI（避免数据被人为优化）
- 三个数据需要每月组合成一份"维护成本 vs 价值"对比表给团队看

### 3.2 A2 — 自动定界准确率

PRD §7.1.A2：定界错 → 后续所有检索范围错 → 所有答案错。

| 指标 | 定义 | 数据来源 | 公式 | 阈值方向 | 状态 |
|---|---|---|---|---|---|
| 定界一次命中率 | Agent 选的特性与用户最终接受的特性一致的比例 | `轨迹日志.scope_detection` + 用户在 UI 上是否点击"切到候选" | `1 - (用户切换次数 / 总会话数)` | 上升趋势；具体阈值见 eval | partial |
| 定界 confidence 标定 | Agent 自评 confidence 与实际正确率的对齐度 | `轨迹日志.scope_detection.confidence` + 上一项是否正确 | 按 `high/medium/low` 分桶看正确率 | high 桶正确率应 ≥ medium 桶 ≥ low 桶 | TODO |
| ask_user 触发率 | confidence 低或多候选时主动追问的比例 | `轨迹日志.ask_user` 事件 + scope_detection | `ask_user触发数 / 总会话数` | 不锁阈值；过高 = 模型不自信，过低 = 不该自信时也不问 | partial |

**采集要点**：

- `轨迹日志.scope_detection` 必须记录：候选特性列表、各 confidence、最终选择、是否触发 ask_user（详见 `agent-runtime.md` §13）
- "用户切换"事件由前端 §4.2 定界透明区"一键改正"按钮触发
- 这一组数据同时喂给**线下 eval**（`testing-eval.md` §4.2 scope_detection eval）做对比

### 3.3 A3 — 充分性判断准确率

PRD §7.1.A3：判断过早进代码 = 慢、贵；过晚 = 用残缺答案误导。

| 指标 | 定义 | 数据来源 | 公式 | 阈值方向 | 状态 |
|---|---|---|---|---|---|
| 用户兜底使用率 | 用户在 Agent 判定"够"后仍点"再深查一下" | 前端事件：`force_deeper_investigation` | `clicks / sufficient_judgements` | 持续偏高 = Agent 判太松 | TODO |
| 答得过浅率 | 用户反馈"部分解决"且备注暗示"想要更深"的比例 | 反馈表 `feedback = partial` + 备注关键词 / 人工标注 | 估算 — alpha 阶段先人工每周抽样 | 上升 = A3 失效 | TODO |
| 进代码层比例 | 进入 CodeInvestigation 阶段的会话比例 | `轨迹日志.stage_transitions` | `code_investigated_sessions / total_sessions` | 不锁；alpha 期人工观察是否合理（不该 100%，也不该 0%） | partial |

**采集要点**：

- "再深查一下" 按钮（`frontend-workbench.md` §4.3）的点击事件必须携带：会话 ID、当前 sufficiency 判断结果、判断理由
- 答得过浅率一期**人工抽样**——线上信号弱，规则化太早会引入噪声

## 4. 主指标 — Deflection Rate（PRD §5.1）

> 提问者通过 CodeAsk 拿到答案、不需要再去找真人的比例。

**双轨测量**：

| 指标 | 定义 | 数据来源 | 公式 | 阈值方向 | 状态 |
|---|---|---|---|---|---|
| 显式 deflection（金标准） | 用户主动点 `solved` 的会话占比 | `feedback` 表，`feedback ∈ {solved, partial, wrong}` | `count(solved) / count(any feedback)` | 上升趋势；长期 > 50%（PRD §5.1） | partial |
| 隐式 deflection | 回答后 N 分钟内未提新问题且未点"找人帮忙"的会话占比 | 会话事件流 + 计时 | `自然结束会话 / 总会话` | 与显式互相校准 | TODO |
| 校准差 | 显式 vs 隐式的差距 | 派生 | `\|显式 - 隐式\|` | 差距 > 一定值时 = 一种轨在偏 | TODO |

**采集要点**：

- N 分钟阈值一期取 **30 分钟**（拍脑袋；alpha 第一周校准后改）
- "找人帮忙" 按钮一期**不内置**（PRD §8.4 末段）——隐式信号在一期靠"未自然结束"间接捕捉
- 显式反馈必须包含 `wrong` 选项（不只 solved/partial），用于护栏指标 §5
- 同一会话多次问答时，**按最后一轮问答**算 deflection（避免双计）

## 5. 质量护栏（PRD §5.2）

> 防止"高 deflection 但答错"——最坏情况是 Maintainer 比之前更累（替系统纠错）。

| 指标 | 定义 | 数据来源 | 公式 | 阈值方向 | 状态 |
|---|---|---|---|---|---|
| 错误反馈率 | 用户主动 flag "回答错误"的占比 | `feedback = wrong` | `count(wrong) / count(any feedback)` | 持续上升 = 警报 | partial |
| 回流率 | N 天内同一 `subject_id` 重复问"相似问题"的比例 | 问题相似度（FTS 召回 + 阈值） | TBD — alpha 前选一种相似度算法 | 高回流 = 实际没解决 | TODO |
| 报告拒绝率 | 报告草稿被人工撤销验证 / 标 stale 的比例 | `reports.status` 转换日志 | `count(verified→draft) / count(verified)` | 高 = Agent 推理质量差 | TODO |

**采集要点**：

- 回流率算法 alpha 阶段先用 **n-gram 相似度 + 简单阈值**（避免引入向量库依赖；与 `wiki-search.md` 检索栈一致）
- N 天 = 7 天（拍）
- 撤销验证事件必须写入审计日志（`evidence-report.md` §7.4）

## 6. 飞轮健康（PRD §5.3，次级）

| 指标 | 定义 | 数据来源 | 公式 | 阈值方向 | 状态 |
|---|---|---|---|---|---|
| 月均验证报告数 | 全团队当月新增 `verified` 报告 | `reports` 表 + 状态转换日志 | `count where status changed to verified in month` | 为 0 = 飞轮没启动 | partial |
| 已验证报告被命中数 | 检索召回 + 实际进入 prompt 的报告引用次数 | `轨迹日志.tool_calls.search_wiki` 命中报告的事件 | `count of report citations in answers` | 持续为 0 = 报告库没价值或检索不命中 | partial |
| 知识库文档新增 / 更新频率 | 月维度文档变更次数 | `documents` 表变更日志 | `count(create + update) per month` | 持平 / 上升 = 仍在被维护 | partial |

**采集要点**：这三条 alpha 阶段月度看一次即可，不进 Maintainer Dashboard 主视图（避免和 §3 / §4 / §5 抢注意力）。

## 7. 反向指标（明确不采，PRD §5.4）

写进文档作为防御——避免后续被误导加进 dashboard：

- ❌ 提问数量
- ❌ Token 消耗
- ❌ Agent 调用工具次数
- ❌ 回答字数

**仅在排查问题时**临时拉一次，不作为 KPI 展示。

## 8. 数据源汇总

| 数据源 | 写入位置 | 用于 |
|---|---|---|
| 反馈表 | `feedback` 表（每个回答一行） | §4 deflection / §5 质量护栏 |
| 轨迹日志 | `agent_traces` 表（按事件流） | §3 致命假设 / 飞轮健康部分 |
| 前端事件 | 前端打点上报到后端，写入 `frontend_events` 表 | §3.1 录入耗时 / §3.3 兜底使用率 / §4 隐式 deflection |
| DB 表变更日志 | `audit_log` 表（含 `from_status` / `to_status` / `subject_id` / `at`） | §5 报告拒绝率 / §6 飞轮健康 |

详细 schema 见 `api-data-model.md`（如需新增字段，alpha 启动前补齐）。

`metrics-eval` 阶段已落地 raw data 写入：

- `POST /api/feedback` 写 `feedback` 表，verdict 固定为 `solved / partial / wrong`。
- `POST /api/events` 写 `frontend_events` 表，事件类型白名单为：`doc_edit_session_started`、`doc_edit_session_completed`、`force_deeper_investigation`、`feature_switch`、`report_unverify_clicked`、`feedback_submitted`、`session_naturally_ended`、`ask_for_human_clicked`。
- `GET /api/audit-log` 按实体只读查询 `audit_log`。
- 会话界面当前已接入 `feedback_submitted` 与 `force_deeper_investigation` 两类前端事件；文档编辑耗时、自然结束和找人按钮事件仍等待对应 UI/流程落地。

## 9. 阶段计划

PRD §5.1 阶段方向：

| 时间点 | 目标 |
|---|---|
| MVP 上线第 1 个月 | §3 / §4 数据全部 `ready`；建立 baseline |
| 第 3 个月 | deflection rate 出现稳定上升趋势；§5 / §6 全部 `ready` |
| 长期 | deflection rate > 50%（具体阈值随团队规模和知识库密度调整） |

## 10. 与 PRD 的对齐

本文落地 PRD §10 第 2 步"建立 alpha 用户跟踪表"，主要承诺：

- §3 致命假设验证 — A1 / A2 / A3 三组各自带"数据来源 / 公式 / 阈值方向 / 状态"四列骨架
- §4 deflection rate 双轨测量与 PRD §5.1 一致
- §5 质量护栏与 PRD §5.2 完全对齐
- §6 飞轮健康与 PRD §5.3 一致
- §7 反向指标与 PRD §5.4 一致
- §2 / §8 明确"骨架不锁数值，锁口径"——避免 alpha 前临时改 schema

后续 patch 节奏：alpha 启动前每个 `TODO` 项落到 `partial` 或 `ready`；alpha 第一周回填阈值校准结果。
