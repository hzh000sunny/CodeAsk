# 证据链与报告闭环设计

> 本文档属于 v1.0 SDD，描述证据链与报告飞轮的实现方式。
>
> 产品契约见同版本 `prd/codeask.md`。当 SDD 与 PRD 冲突时，以 PRD 为准。

## 1. 目标

CodeAsk 的可信度来自证据链，而不是模型语气。每个关键结论都必须能追溯到日志、代码、文档或已验证报告（PRD §4.2 "回答必须带证据" 承诺）。

证据与报告系统负责：

- 把 Agent 调查过程中的线索结构化。
- 让最终回答区分结论、证据、推理和不确定点。
- 生成可人工验证的定位报告。
- 只有验证后的报告才能进入高优先级检索。
- 防止错误经验污染未来回答。

报告飞轮是 PRD §2.3 的核心：Maintainer 沉淀 → Asker 命中 → 飞轮转。任何环节摩擦过大 → 飞轮停。

## 2. 证据类型

| 类型 | 来源 | 必要字段 |
|---|---|---|
| `log` | 用户粘贴日志或附件 | attachment_id、line_range、摘要、原始片段 hash |
| `code` | 代码仓库 | repo_id、commit_sha、path、line_range、摘要 |
| `wiki_doc` | 知识库文档 | document_id、path、heading、摘要 |
| `report` | 已验证历史报告 | report_id、标题、适用条件、摘要 |
| `user_answer` | `ask_user` 回复 | question、answer、created_at |
| `system` | 系统配置或运行状态 | key、value、摘要 |

代码证据必须绑定 commit。来自默认分支预查但尚未确认版本的代码片段只能作为 `provisional_code`，不能进入最终已验证报告。

## 3. 证据模型

```json
{
  "id": "ev_001",
  "type": "code",
  "source": {
    "repo_id": "repo_order",
    "commit_sha": "abc123",
    "path": "src/order/service.py",
    "line_start": 88,
    "line_end": 104
  },
  "summary": "submit_order 在 user 为空时仍直接读取 user.id",
  "relevance": "supports",
  "confidence": "high",
  "captured_at": "2026-04-28T10:00:00Z"
}
```

`relevance` 取值：

- `supports`：支持结论。
- `contradicts`：与结论冲突。
- `context`：提供背景。
- `uncertain`：相关但无法直接判断。

## 4. 结论模型

Agent 在合成答案前应形成一个或多个候选结论：

```json
{
  "claim": "订单提交偶发失败可能由用户上下文为空导致",
  "confidence": "medium",
  "evidence_ids": ["ev_log_1", "ev_code_2"],
  "counter_evidence_ids": [],
  "missing_information": [
    "故障版本尚未确认"
  ],
  "recommended_checks": [
    "确认故障日志对应的镜像 tag 或 commit",
    "检查灰度入口是否可能绕过用户上下文初始化"
  ]
}
```

置信度不是模型自信程度，而是证据充分程度：

| 置信度 | 标准 |
|---|---|
| high | 有明确日志证据、代码证据和版本绑定，且无明显冲突 |
| medium | 有强相关证据，但缺少版本确认、运行时条件或复现验证 |
| low | 只有弱线索，仍存在多个候选根因 |

## 5. 回答结构

默认回答结构（与 `debugging-workflow.md` §8 输出要求一致）：

```text
结论（醒目展示）
建议操作
置信度
不确定点
证据（默认折叠）
```

如果当前回答基于默认分支预查，必须加提示：

```text
代码证据来自仓库默认分支，尚未确认与故障发生版本一致，因此当前结论是初步判断。
```

## 6. 报告结构

定位报告建议为 Markdown + 结构化 metadata。

Markdown 主体：

```text
# 故障定位报告

## 摘要

## 影响范围

## 现象与日志

## 根因判断

## 证据

## 修复建议

## 验证方式

## 适用条件

## 未确认事项
```

metadata：

```json
{
  "feature_ids": [],
  "repo_commits": [
    {
      "repo_id": "repo_order",
      "commit_sha": "abc123"
    }
  ],
  "error_signatures": [],
  "trace_signals": [],
  "verified": false,
  "verified_by": null,
  "verified_at": null,
  "status": "draft"
}
```

### 6.1 报告草稿的预填

为降低 Maintainer 的录入摩擦（PRD §7.1.A1 致命假设），报告草稿应由 Agent 自动预填：

- 用户问题
- Agent 的回答（结论 / 建议操作 / 置信度 / 不确定点 / 证据）
- 用户反馈备注（"已解决 / 部分解决"时附的文字）

Maintainer 只需要补充实际根因 / 长期方案等"机器答不出但人脑里有"的部分。对应 PRD §8.4 旅程 4"Alice 抽 5-10 分钟就能完成"和 §8.3 旅程 3"一键沉淀"。

## 7. 验证闸门

### 7.1 报告生命周期

```text
draft → verified → archived
```

一期不引入 `submitted_for_review` 状态——这与 PRD §6.2 MVP Anti-Goal "不做权限 / 审核工作流"一致。任何人可以直接把 `draft` 改为 `verified`，不走提交-审核两步。

### 7.2 验证动作

**谁能验证**：一期任意人都能验证（PRD §4.4.1 "无身份模型"）。"特性 owner" 是命名上的角色，不是系统强制；验证由团队**社会契约**约束。

**验证前系统检查**：

- 报告至少包含一个日志证据或代码证据。代码调查类报告允许没有日志，但不能没有可追溯证据。
- 如果报告引用代码，所有代码证据都绑定明确 commit（不允许 `provisional_code` 进入 verified）。
- 报告有适用条件。
- 报告有修复建议或验证方式。

**验证后只有 `verified=true` 的报告**才进入索引参与高优先级检索（详见 `wiki-search.md` §11，报告通过 query-driven 命中进入回答；不进入基础上下文 digest）。

### 7.3 verified_by 字段

记录验证动作的来源，用于事后追溯和"一键回退"：

| 阶段 | `verified_by` 取值 |
|---|---|
| 一期（普通用户无登录 + 自报身份） | `subject_id = nickname@client_id`（无昵称时 `device@client_id`，详见 `deployment-security.md` §3）；管理员功能由内置 admin cookie 保护 |
| 未来（接入 AuthProvider） | `subject_id` 来自 `Identity`（详见 `deployment-security.md` §4） |

UI 展示时同时显示 `subject_id` 和"自报"标识，提示团队成员这是软识别非鉴权（PRD §4.4.1 风险缓解）。

`verified_at` 一期就开始记录，便于未来识别"哪些 verified 报告是自报身份阶段产生的、需要回顾"。

### 7.4 一键回退到 draft

PRD §4.4.1 风险缓解措施：

> 报告被错误验证后污染检索 → 缓解：UI 展示报告时显示"由谁验证、何时验证"，可以一键回退到 draft

实现要求：

- 报告详情页显著展示 `verified_by` 和 `verified_at`
- 提供"撤销验证"按钮，把 `verified` 改回 `draft`，从索引中下架
- 撤销动作本身写入审计日志（操作时间 + 来源），便于事后排查

## 8. 报告过期与冲突

报告可能随代码演进失效。报告应支持以下状态：

| 状态 | 含义 |
|---|---|
| `verified` | 当前有效，可高优先级检索 |
| `stale` | 可能过期，仍可展示但降低优先级 |
| `superseded` | 被新报告替代 |
| `rejected` | 人工确认错误，不参与检索 |

触发过期提示的情况：

- 报告绑定 commit 与当前默认分支差异较大。
- 相关文件在报告后被大量修改。
- 用户标记报告不适用。
- 新报告声明替代旧报告。

## 9. 检索使用规则

报告命中后，Agent 必须判断适用条件：

- feature 是否匹配。
- 错误签名是否匹配。
- 版本范围是否冲突。
- 日志关键符号是否一致。

报告不能被盲目复述。如果当前日志或代码证据与报告冲突，Agent 必须明确指出冲突。

## 10. 与 PRD 的对齐

本文已按 `prd/codeask.md` §9 对齐表更新，主要变化：

- §7.1 报告生命周期从 4 阶段简化为 3 阶段（删除 `submitted_for_review`），与 PRD §6.2 "不做审核工作流"一致
- §7.2 明确"任意人可验证"——"特性 owner" 是命名上的角色而非系统强制（PRD §4.4.1）
- §7.3 新增 `verified_by` / `verified_at` 字段设计，一期记 `anonymous@session_id` 或 timestamp，未来可填 `subject_id`
- §7.4 新增"一键回退到 draft"机制，落地 PRD §4.4.1 的污染缓解措施
- §6.1 新增"报告草稿预填"小节，落地 PRD A1 致命假设的录入摩擦缓解
- §1 / §7.2 明确报告作为知识库高优先级条目（与 `wiki-search.md` §11 对齐）
