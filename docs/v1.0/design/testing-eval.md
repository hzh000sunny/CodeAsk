# 测试与 Eval 设计

> 本文档属于 v1.0 SDD，描述测试金字塔与 Agent eval 基线。
>
> 与 `metrics-collection.md` 的关系：本文是**线下、标注、快**的评测系统（改一行 prompt 知道是好是坏）；`metrics-collection.md` 是**线上、真实、慢**的指标系统（看真实使用发生了什么）。
>
> 当 SDD 与 PRD 冲突时，以 PRD 为准。

## 1. 目标

研发级问答系统必须可回归验证。测试不只覆盖 API，还要覆盖 Agent 是否遵守调查流程和证据规则。

PRD §10 第 3 步要求"建立 Agent eval 基线"——本文 §4 承担这一目标，为 PRD §7.1 的 A2 / A3 致命假设提供线下验证手段。

## 2. 单元测试

覆盖：

- 工具参数校验
- 路径安全
- 日志分析器
- Prompt 组装
- Markdown 引用解析
- FTS5 切词、n-gram 兜底和排序融合
- 证据模型校验

## 3. 集成测试

使用临时 `~/.codeask/`：

- SQLite + FTS5
- 小型测试仓库
- 真 `git`、`rg`、`ctags`
- `MockLLMClient` 回放工具调用

端到端路径：

```text
创建特性
→ 注册仓库
→ 上传文档
→ 创建会话
→ 上传日志
→ 自动定界
→ 知识库检索 + 充分性判断
→ 代码深入分析（如需）
→ 输出答案
→ 生成报告
→ 验证报告
→ 再次命中报告
```

## 4. Agent Eval

Agent eval 是一组**线下、人工标注、快速**的评测集，用于：

- 验证 PRD §7.1 致命假设 A2 / A3 在 prompt / 模型 / 检索权重变化下是否退化
- 改 prompt 时立刻知道"好是坏"——不必等线上数据
- 与 `metrics-collection.md` §3.2 / §3.3 的线上指标互相校准

### 4.1 Eval 集结构

所有 eval 集统一目录布局：

```text
evals/
├── scope_detection/        ← A2 自动定界（§4.2）
│   ├── cases/              ← JSONL，每行一个 case
│   ├── fixtures/           ← 共享的特性元信息快照
│   └── score.py            ← 评分脚本
├── sufficiency/            ← A3 充分性判断（§4.3）
│   ├── cases/
│   ├── fixtures/           ← 知识库快照（脱敏）
│   └── score.py
└── answer_quality/         ← 通用回答质量（§4.4）
    ├── cases/
    ├── fixtures/
    └── score.py
```

每个 eval 集统一 case schema：

```json
{
  "id": "scope_001",
  "input": { "...": "测试输入（问题 / 附件 / 上下文快照）" },
  "expected": { "...": "标注的期望（正确特性 / 期望决策 / 期望证据类型）" },
  "annotator": "alice@2026-04-30",
  "tags": ["domain:order", "complexity:high"],
  "notes": "标注理由"
}
```

打分脚本统一接口：

```python
def score(case: Case, agent_output: AgentOutput) -> Score:
    """返回 0-1 分数 + 详细维度分解（用于失败 case 复盘）"""
```

### 4.2 A2 — Scope Detection Eval

**目标**：验证 Agent 在"问题 → 正确特性"上的命中率。

**Case schema**：

```json
{
  "id": "scope_001",
  "input": {
    "question": "订单提交失败后多久退款？",
    "attachments": [],
    "feature_summaries": [/* 当时的特性元信息快照 */]
  },
  "expected": {
    "correct_feature_id": "feat_order",
    "acceptable_feature_ids": ["feat_order"],
    "should_trigger_ask_user": false
  }
}
```

`acceptable_feature_ids` 是为多解情况留的——比如某问题确实跨"订单 / 结算"两个特性，命中任一都算正确。

**评分公式**：

| 指标 | 公式 | 目标 |
|---|---|---|
| top-1 准确率 | `Agent 选的特性 ∈ acceptable / 总数` | alpha 起始 ≥ 70%，3 月内 ≥ 85% |
| top-3 准确率 | `Agent 候选 top 3 中至少一个 ∈ acceptable` | ≥ 95% |
| confidence 标定 | high 桶正确率 ≥ medium 桶 ≥ low 桶 | 单调即可 |
| ask_user 触发准确性 | `should_trigger_ask_user` 与实际触发一致的比例 | ≥ 80% |

**种子 case 方向**（前 30 条目标，按比例分布）：

| 类别 | 数量 | 用途 |
|---|---|---|
| 单特性明确命中 | 10 | baseline，confirm 模型不会乱选 |
| 跨特性合理 | 5 | 验证 `acceptable_feature_ids` 多选场景 |
| 模糊问题（应 ask_user） | 5 | 验证 confidence 低时主动追问 |
| 关键词陷阱（含特性名但实际无关） | 3 | 抗干扰 |
| 日志附件主导（错误签名匹配特性） | 4 | 验证日志信号利用 |
| 全局问题（无明确特性） | 3 | 验证降级到全局检索 |

数量目标：**30 条种子 → alpha 第 1 月扩到 100 条 → 长期 200+**。

### 4.3 A3 — Sufficiency Judgement Eval

**目标**：验证 Agent 判断"知识库够不够"的准确性。

**Case schema**：

```json
{
  "id": "suf_001",
  "input": {
    "question": "如果在 order 表里把 payment_method 字段改成枚举，下游会有哪些代码受影响？",
    "feature_id": "feat_order",
    "kb_snapshot": [
      { "doc_id": "...", "summary": "...", "matched_chunks": [/* FTS 召回的前 K 段 */] }
    ]
  },
  "expected": {
    "decision": "insufficient",
    "rationale_keywords": ["字段变更", "影响清单", "下游"],
    "should_recommend_code_investigation": true
  }
}
```

`rationale_keywords` 用于校验 Agent 给出的理由覆盖核心要点（关键词级模糊匹配，避免完全 string match 的脆弱性）。

**评分公式**：

| 指标 | 公式 | 目标 |
|---|---|---|
| 决策准确率 | `Agent 判断 ∈ {sufficient, insufficient} 与 expected 一致` | ≥ 80% |
| 漏判率（应进代码而判够） | `false_sufficient / total_insufficient_cases` | ≤ 10%（致命方向） |
| 误判率（不该进代码而判不够） | `false_insufficient / total_sufficient_cases` | ≤ 20%（成本方向，可容忍） |
| 理由覆盖率 | `命中 rationale_keywords 数 / total_keywords` | ≥ 60% |

**种子 case 方向**（前 30 条）：

| 类别 | 数量 | 用途 |
|---|---|---|
| 知识库直接命中 → sufficient | 8 | baseline，confirm 不过度进代码 |
| 知识库无相关文档 → insufficient | 8 | baseline，confirm 该进代码就进 |
| 知识库部分相关但缺关键信息 → insufficient | 6 | 难判，A3 真正考验点 |
| 知识库有报告但报告与问题版本不符 → insufficient | 4 | 验证版本意识 |
| 用户明确说"快速回答即可"→ sufficient（即使知识库弱） | 2 | 验证用户意图优先 |
| 边界 case：知识库刚刚够 | 2 | 标注为 sufficient 但应附"不确定点" |

数量目标：**30 条种子 → alpha 第 1 月扩到 80 条 → 长期 150+**。

**注意**：A3 比 A2 更难标注——多个标注员可能对同一 case 给出不同决策。alpha 阶段每个 case **由 2 人独立标注**，不一致的进入"难 case 池"专门讨论。

### 4.4 通用回答质量 Eval

PRD §4.2 / §6.1 / §8.4 涉及的多条产品承诺需要回归测试。

**Case schema**：

```json
{
  "id": "qa_001",
  "input": { /* 完整会话上下文 */ },
  "expected": {
    "must_cite_evidence": true,
    "must_disclose_uncertainty": ["故障版本未确认"],
    "must_not_phrase_as_decision": true,
    "must_bind_commit_for_code_evidence": true
  }
}
```

**Case 类型**：

- 报告命中型（验证报告通过 query 召回，不在 base context）
- 文档命中型
- 代码定位型（验证 commit 绑定）
- 信息不足型（验证"不假装自信"）
- 冲突型（日志 vs 文档冲突时的处理）
- 多特性型
- 默认分支预查型（验证"未确认故障版本"标识）

**指标**：

- 是否引用证据
- 是否绑定 commit（代码证据必须）
- 是否承认不确定性
- 是否避免"决策语气"（PRD §6.1）
- 工具调用次数是否合理（用作护栏，不作为优化目标）
- 最终结论是否正确（人工评分）

数量目标：**alpha 起始 20 条**（每类 ~3 条），覆盖关键产品承诺即可——这一类 eval 数量不追求多。

### 4.5 运行方式

```text
开发阶段：本地跑 evals/scope_detection/ + evals/sufficiency/
         （快速反馈，单次 < 1 分钟，靠 MockLLM 或廉价模型）

PR 阶段：CI 跑 scope_detection + sufficiency 全集（廉价模型）
        （阈值红线：A2 top-1 不退化 > 5pp / A3 漏判率不上升）

发布前：手动跑 answer_quality 全集（真模型）
        （人工抽样复核，不阻塞发布但记录基线）

每月：扩 case，回顾不一致标注
```

**eval 与线上指标的闭环**：

- 线上指标（`metrics-collection.md` §3.2 / §3.3）若发现退化 → 回到对应 eval 集 → 找出失败 case → 修 prompt / 检索 → eval 通过 → 上线
- 线上发现的"难 case" → 脱敏后入 eval 集（标注为新增 case），让下次回归覆盖

## 5. CI

一期最小 CI：

- lint
- 单元测试
- 集成测试
- Agent eval（scope_detection + sufficiency 廉价模型版）

真模型 eval 不在默认 CI 中运行，作为手动评估任务。

`metrics-eval` 阶段已实现项目根级 `evals/` harness：

- `uv run python -m evals.run --suite scope_detection`
- `uv run python -m evals.run --suite sufficiency`
- `uv run python -m evals.run --suite answer_quality`

三套 suite 当前使用 stub agent 回放 expected labels，目标是先固定 case schema、score 结构、红线比较与 CI 入口。`tests/mocks/mock_llm.py` 已补 `ScriptedMockLLMClient`，后续接真 Agent replay 时替换 runner 的 stub 调用，不改变 case 文件和 score 接口。

## 6. 与 PRD 的对齐

本文已按 `prd/codeask.md` §10 第 3 步更新，主要变化：

- §4 Agent Eval 章节从粗描述扩为完整的"集结构 / case schema / 评分 / 种子方向 / 数量目标"骨架
- §4.2 / §4.3 落地 PRD §7.1 致命假设 A2 / A3 的线下验证手段
- §4.5 运行方式与 `metrics-collection.md` 形成线下 / 线上闭环
- §5 CI 把 scope_detection + sufficiency 加入默认 CI（廉价模型版），avoid 退化
