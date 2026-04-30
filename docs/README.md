# CodeAsk 文档

## 当前版本

[**v1.0**](./v1.0/) — MVP 初始版本（Active，2026-04-29 起）

进入版本目录后请先读该目录下的 `README.md`。

## 历史版本

（暂无）

## 文档约定

文档目录结构、版本命名、bump 规则、引用路径等约定见 **[STRUCTURE.md](./STRUCTURE.md)**。

### 速查

```text
docs/
├── README.md          ← 本文件（顶层版本索引）
├── STRUCTURE.md       ← 文档约定的权威来源
├── v1.0/              ← 当前版本
│   ├── README.md      ← 该版本元信息
│   ├── prd/           ← PRD
│   ├── design/        ← SDD
│   ├── plans/         ← 实现计划（拆 SDD → 可执行 task）
│   └── specs/         ← 早期草稿 / 过程性产物
├── v1.1/              ← 未来 minor 演进
└── v2.0/              ← 未来 major 演进
```

### 关键原则（详见 STRUCTURE.md）

- **旧版本目录一律不就地覆盖**——保留为历史
- **同版本内引用**用相对路径（如 `design/overview.md`）
- **跨版本引用**用 `../vN.M/...`
- **PRD vs SDD 冲突**永远以 PRD 为准
