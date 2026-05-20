# v1.0.5 收口验收清单

> 版本：v1.0.5
> 状态：Draft
> 关联：[PRD](../prd/rag-knowledge.md) · [设计](../design/openviking-integration.md) · [Phase 0](./phase-0-spike.md) · [Phase 1](./phase-1-sync-adapter.md) · [Phase 2](./phase-2-opencode-integration.md) · [DEVELOPMENT_ACCEPTANCE](../../DEVELOPMENT_ACCEPTANCE.md)

---

## 0. 验收原则（重申）

- 不能只看后端单测通过，也不能只看前端能渲染；必须覆盖模型实际看到的上下文、工具调用、证据回填、降级语义和真实用户路径
- 涉及 LLM / Agent / RAG / 工具调用必须有 live E2E 通道（默认跳过，显式环境变量开启）
- 升级路径必须在真实数据备份上跑过一次
- OpenViking 与 Ollama 的依赖关系必须有明确失败语义，不允许"前端看上去能用，但后端实际不可用"

---

## 1. OpenViking 集成边界

- [ ] `specs/openviking-agpl-review.md` 状态 = Recorded（已完成）
- [ ] CodeAsk README / INSTALL 包含 OpenViking 引用与许可证披露
- [ ] CodeAsk 仓库未拷贝 OpenViking 源码（grep 验证）
- [ ] `pyproject.toml` 把 OpenViking 放在 optional-dependencies
- [ ] 没有任何文件 `import openviking` 作为业务代码（grep 验证）

---

## 2. Phase 0 spike

- [ ] `phase-0-spike.md` §10 实验记录已填
- [ ] OpenViking 版本与 embedding 模型已锁定并写入 PRD / SDD
- [ ] 召回基线满足 §7 阈值（relevance@5 ≥ 3/5）
- [ ] §8 退出条件全部满足

---

## 3. Phase 1 同步适配器

- [ ] `src/codeask/rag/openviking/` 模块全部就位
- [ ] alembic head 包含 `openviking_sync_jobs`
- [ ] OpenViking server startup / keepalive / shutdown 行为符合 SDD §5
- [ ] Wiki / 报告 / 仓库变更 hook 全部接入；启动 sweep 行为正确
- [ ] 失败重试与 cancelled 转换符合 SDD §9
- [ ] admin 诊断接口与卡片可读
- [ ] 后端 pytest 全量通过；不引入 ruff / pyright 新红
- [ ] 真实数据备份升级回归通过

---

## 4. Phase 2 opencode 接入

- [ ] `opencode.json` 中加入 OpenViking remote MCP，工具白名单按 PRD §6.2 限定
- [ ] 动态上下文与 `AGENTS.md` 包含 RAG 使用原则
- [ ] 前端 action-trace 展示 OpenViking 工具事件，路径脱敏正常
- [ ] OpenViking 失败语义按 SDD §9 落地；前端居中弹窗
- [ ] 不静默回退 v1.0.4 file-grep 主链路

---

## 5. 多环境 E2E 矩阵

| 环境 | 命令 / 范围 | 结论 |
|---|---|---|
| 临时空库 `start.sh` | 空数据目录 → OpenViking server 拉起、首次同步、admin 卡片可见 | TBD |
| 真实数据只读 | 连接真实数据备份 → admin 看到全量同步状态；不写 Wiki / 仓库 | TBD |
| 真实数据可写沙箱 | 在沙箱中触发 Wiki / 报告 / 仓库变更，验证增量同步 | TBD |
| 真实 LLM / opencode / OpenViking / Ollama live | `CODEASK_RUN_LIVE_OPENVIKING_E2E=1` 跑 Phase 2 §5 全部用例 | TBD |
| OpenViking 不可用降级 | 关停 OpenViking → 新会话立即弹错；恢复后会话可继续 | TBD |
| Ollama 不可用降级 | 关停 Ollama → 同步任务 failed；admin 卡片提示 embedding 不可用 | TBD |
| 升级部署 | `start.sh` 升级 v1.0.4 → v1.0.5；首次 sweep 自动补齐 | TBD |
| 长对话 | 真实 LLM 多轮、跨会话切换、刷新继续追问 | TBD |
| 特性源码调查 | OpenViking 召回代码候选 → `codeask_prepare_worktree` → opencode 读取真实文件 | TBD |

---

## 6. 连续会话验收

- [ ] 同一会话第二轮追问能看到 OpenViking 召回历史摘要
- [ ] 刷新后追问保持上一轮工具行动摘要
- [ ] 上一轮 OpenViking 工具结果摘要进入模型上下文（不是只显示在行动轨迹）
- [ ] 历史 turns 与 traces 都保存且按权限可读

---

## 7. 权限与隔离

- [ ] OpenViking MCP token 按会话校验；跨会话 token 拒绝
- [ ] OpenViking 工具事件返回前端前完成路径脱敏（沿用 v1.0.4 出口规则）
- [ ] OpenViking server 进程崩溃不影响 CodeAsk 主进程
- [ ] 未授权用户不能触发 admin OpenViking 操作

---

## 8. 文档收口

- [ ] PRD / SDD / Phase 0/1/2 / Acceptance / 集成边界声明 全部 status = Completed 或 Recorded
- [ ] `docs/README.md` 顶层指针更新为 v1.0.5
- [ ] v1.0.4 README 末尾追加"由 v1.0.5 接续"指引
- [ ] `future/rag-knowledge-pipeline.md` 加 superseded 提示，指向 v1.0.5
- [ ] `future/openviking-rag-research-2026-05-20.md` 加 superseded 提示，指向 v1.0.5 spike 结果

---

## 9. 风险声明（收口前确认）

- [ ] OpenViking 版本未来变更的升级路径有方案（升级后能重建索引）
- [ ] Ollama 模型变更不影响已有索引（或有重建脚本）
- [ ] 大代码仓导入失败有 admin 重试与诊断
- [ ] CodeAsk 主进程不再依赖任何 v1.0.5 spike 阶段的临时配置（`/tmp/codeask-v105-spike/...`）
- [ ] OpenViking 集成边界（不修改源码、不内嵌源码）与 docker 镜像策略已对外文档化
