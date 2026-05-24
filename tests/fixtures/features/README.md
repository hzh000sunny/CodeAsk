# Test Features Fixture

跨版本稳定的"测试特性"集合。三份特性同时承担：

- Phase 0 / Phase 1 / Phase 2 spike 与 E2E 的真实 Wiki 数据源
- 真实代码仓检索 / `prepare_worktree` / 源码读取链路的目标仓库
- RAG 召回基线、长上下文回归、连续会话回归的固定 query 来源

约定与使用规则见 [`../../../docs/rules/test-features.md`](../../../docs/rules/test-features.md)。本目录只承载数据；约定改动以约定文档为准。

## 目录布局

```text
tests/fixtures/features/
├── README.md                       ← 本文件
├── opencode/
│   ├── README.md                   ← 特性元信息
│   └── wiki/                       ← 上游 wiki dump（可作为 CodeAsk Wiki 文档导入）
├── anything-llm/
│   ├── README.md
│   └── wiki/
└── openviking/
    ├── README.md
    └── wiki/
```

## 不在此目录的内容

- 源码 clone：不进 git。开发者按需 `git clone` 到 `references/<slug>/`（已 ignore）。git URL 见各特性 README。
- 测试运行产物：不写入本目录。所有运行态数据写入 `CODEASK_DATA_DIR` 或临时目录。
- 评测结果：写入 `evals/` 目录，不污染 fixture。

## 修改规则

- 增删一个测试特性需要同时更新 `docs/rules/test-features.md` 和本目录
- 更新某个特性的 wiki dump 时，应明确记录上游 commit / 抓取日期（写到该特性的 README）
- 不在本目录里跑业务代码 / 临时调试脚本
