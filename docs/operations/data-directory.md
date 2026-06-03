# 数据目录与密钥

> 范围：`CODEASK_DATA_DIR`、敏感字段密钥和备份约定。
> 状态：Active

默认数据根目录是：

```text
~/.codeask
```

典型结构：

```text
~/.codeask/
├── data.db
├── secrets/
│   └── data.key
├── wiki/
├── skills/
├── sessions/
├── repos/
├── index/
└── logs/
```

## 关键规则

- `data.db` 是主数据库。
- `secrets/data.key` 是敏感字段加密主密钥缓存，权限应为 `0600`。
- 会话附件、Wiki 资源、仓库缓存和数据库记录之间存在引用关系。
- 备份和迁移必须备份整个 `CODEASK_DATA_DIR`，不要只备份 `data.db`。
- 同一个数据目录必须使用同一个 `CODEASK_DATA_KEY`。
- 不要覆盖已有 `secrets/data.key`；这不是 key rotation。

## 常用子目录

| 路径 | 用途 |
|---|---|
| `data.db` | SQLite 数据库 |
| `secrets/data.key` | 本地敏感字段加密 key |
| `wiki/` | Wiki 相关持久化资源 |
| `sessions/` | 会话附件、会话工作区相关文件 |
| `repos/` | bare repo 和 worktree 缓存 |
| `index/` | 可重建的索引缓存 |
| `logs/` | 本地运行日志 |

更完整的跨版本规则见 [upgrade-compatibility.md](../rules/upgrade-compatibility.md)。
