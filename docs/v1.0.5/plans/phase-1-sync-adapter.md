# Phase 1 — OpenViking Sync Adapter 实现

> 版本：v1.0.5
> 状态：Framework Draft（待 Phase 0 通过后细化）
> 关联：[PRD](../prd/rag-knowledge.md) · [设计](../design/openviking-integration.md) · [Phase 0](./phase-0-spike.md) · [Phase 2](./phase-2-opencode-integration.md)

---

## 0. 前置条件

进入 Phase 1 之前必须：

- Phase 0 实验记录通过退出条件（见 [`phase-0-spike.md`](./phase-0-spike.md) §8）
- 锁定 OpenViking 版本和 embedding 模型已写入 PRD / SDD
- OpenViking 集成边界声明已记录（不修改源码、不内嵌源码）

未达成上述条件不开 Phase 1 实现工单。

---

## 1. 范围

Phase 1 = 把 OpenViking 接入 CodeAsk 后端，但**不接入 opencode 主链路**。

包含：

- 新增 `src/codeask/rag/openviking/` 兼容模块（参考 SDD §1.1）
- 新增 `openviking_sync_jobs` 表 + alembic migration
- 启动 OpenViking server 进程管理 + keepalive
- Wiki / 报告 / 仓库变更 hook 写入同步队列
- 同步引擎执行 add-resource / 索引追踪 / 失败重试
- admin 诊断接口 `GET /api/admin/openviking/status`
- admin 设置页 OpenViking 状态卡片
- 后端单元 / 集成测试

不包含：

- 不在 opencode 会话注入 OpenViking 资源提示
- 不在 `opencode.json` 加 OpenViking MCP
- 不暴露 OpenViking 工具事件到前端行动轨迹
- 不删除 / 替换 v1.0.4 Wiki FTS5 / native_search 实现
- 不接入 Claude Code backend

Phase 1 完成后，OpenViking 在 CodeAsk 后端可用，但用户会话仍使用 v1.0.4 的 file-based grep + workspace/wiki 兜底。Phase 2 才把 OpenViking 接入 opencode。

---

## 2. 模块清单

按 SDD §1.1 实施：

```text
src/codeask/rag/openviking/
├── __init__.py
├── config.py
├── process.py
├── client.py
├── sync.py
├── uri.py
├── models.py
├── health.py
└── README.md
```

每个文件的职责、关键接口、最低测试见 SDD §1.5（待 Phase 0 后回填）。

---

## 3. 数据库

新增表 `openviking_sync_jobs`（schema 见 SDD §3.1）。

- 新建 alembic migration：`alembic/versions/XXXX_openviking_sync_jobs.py`
- 不修改任何现有表
- 升级路径在临时数据库与真实数据备份上各跑一次（写入 acceptance-checklist）

---

## 4. 启动与生命周期

`src/codeask/app.py` 生命周期内增加：

- `app.state.openviking_process` —— OpenViking server 管理
- APScheduler 任务：
  - `openviking_keepalive`：每 `openviking_keepalive_interval_seconds` 拉起
  - `openviking_sync`：每 `openviking_sync_interval_seconds` 取 pending job 执行
- 关停时优雅终止 OpenViking 进程

参考 v1.0.4 `_ensure_opencode_server`。Ollama 进程不归 CodeAsk 管。

---

## 5. 同步触发点（hook 清单）

| 事件 | hook 位置 | 写入 source_type |
|---|---|---|
| Wiki 节点保存（create / update / publish） | `src/codeask/wiki/...` 写操作 commit 后 | `wiki_doc` |
| Wiki 目录变化（move / rename / soft-delete） | 同上 | `wiki_dir` |
| Feature 创建 / 重命名 / 归档 | `src/codeask/api/features.py` | `feature_readme` + `global_index` |
| 报告 verify / unverify / delete | `src/codeask/wiki/reports.py` 或 `sessions/report_generation.py` 完成处 | `report` + `global_index` |
| 仓库 `ready` / 同步完成 / 删除 | `src/codeask/code_index/cloner.py` | `repo` + `global_index` |
| OpenViking 启动后首次 sweep | `app.py` startup | 扫描全量主数据，未在 jobs 中的写入 pending |

所有 hook 必须在 DB 事务 commit 后再 enqueue，避免脏写。

---

## 6. 错误处理

按 SDD §9 实现：

- failed → 指数退避：30s / 2m / 10m / 1h / 6h
- 超过 `openviking_sync_max_repeat_failures` 标 `cancelled`，写审计事件
- OpenViking server 健康检查失败时整体暂停同步，admin 面板可见

---

## 7. admin 诊断

新增 `src/codeask/api/openviking_status.py`：

```python
GET /api/admin/openviking/status
→ {
  "running": bool,
  "pid": int|null,
  "port": int|null,
  "version": str|null,
  "verified_version": str,
  "embedder": {"provider": str, "model": str, "ollama_healthy": bool},
  "queue": {"pending": int, "running": int, "failed": int, "cancelled": int},
  "last_health_at": str,
  "last_error": str|null,
  "log_file": str
}
```

前端在 `frontend/src/components/settings/...` 新增卡片，沿用 v1.0.4 opencode 状态卡片样式。

---

## 8. 测试矩阵

| 层次 | 用例 |
|---|---|
| 单元 | URI 映射往返；`ov.conf` 生成；同步状态机；指数退避 |
| 集成 | 真实 openviking-server（spike 锁定版本）；fake Ollama；端到端同步 1 个文档 + 1 个仓库 |
| 升级 | v1.0.4 数据库 → alembic head；首次 sweep 行为；OpenViking 工作区从空到非空 |
| 安全 | trusted-mode header 注入；MCP bearer token；路径遍历拒绝 |
| 性能 | spike 锁定模型下，Wiki 单文件同步耗时；100 个 wiki 节点同步总耗时 |
| 故障 | OpenViking 进程杀死 → keepalive 拉回；Ollama 关闭 → 队列正确退避 |

详细 case 写到 `acceptance-checklist.md`。

---

## 9. 实施顺序（建议工单切分）

1. settings + alembic migration + 空 module（编译通过）
2. process + health（启停 + 探测，纯单元）
3. client（HTTP + MCP 调用真实 server，集成）
4. uri + sync（无 hook 触发，手动 enqueue 跑一次）
5. hooks（接入 wiki / report / repo 变更点）
6. APScheduler 任务
7. admin status API + 前端卡片
8. 升级路径在真实数据备份上的回归
9. acceptance-checklist 内 Phase 1 子项打勾

---

## 10. 退出条件

- 临时空库 `start.sh` 跑通；OpenViking server 自动拉起，sync 队列从空开始
- 真实数据备份升级路径完成；老数据无回归
- 全量 sweep 后所有现存 Feature / Wiki / verified 报告 / ready 仓库都在 OpenViking 中可见
- admin 诊断接口与卡片可读 / 可看 / 不显示宿主机绝对路径
- 后端测试矩阵通过；CI 不引入新红
- 不依赖 opencode 会话即可独立验证（手动调 OpenViking MCP / CLI 看到资源）

下一步进入 Phase 2。
