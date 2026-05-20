# Sync / Event Sourcing 系统文档

## 目录

1. [什么是 Event Sourcing](#1-什么是-event-sourcing)
2. [核心概念与设计目标](#2-核心概念与设计目标)
3. [架构概览](#3-架构概览)
4. [SyncEvent 定义 API](#4-syncevent-定义-api)
5. [SyncEvent 与 BusEvent 对比](#5-syncevent-与-busevent-对比)
6. [事件流程详解](#6-事件流程详解)
7. [聚合（Aggregate）与序列号](#7-聚合aggregate与序列号)
8. [事件版本化](#8-事件版本化)
9. [Projector 系统](#9-projector-系统)
10. [向后兼容性策略](#10-向后兼容性策略)
11. [多设备同步架构](#11-多设备同步架构)
12. [数据库结构](#12-数据库结构)
13. [API 使用指南](#13-api-使用指南)
14. [关键源文件索引](#14-关键源文件索引)

---

## 1. 什么是 Event Sourcing

Event Sourcing（事件溯源）是一种软件架构模式，将应用程序状态的每一次变更都表示为一个不可变的事件（Event），并按发生顺序存储在事件日志中。当前状态不是直接存储在数据库中，而是通过重放（Replay）所有历史事件来重建。

### 在 OpenCode 中的应用场景

OpenCode 的 Session（会话）系统需要进行以下操作：

- **创建、更新、删除会话**：修改 Session 的标题、权限、归档状态等
- **消息管理**：添加、更新、删除消息和消息片段
- **跨设备同步**：允许一个设备写入，其他设备通过重放事件日志实时同步

传统的直接数据库写操作无法支持"重放"能力。Event Sourcing 通过引入事件日志，使得每个 Session 的完整生命周期都记录在事件中，任何设备都可以通过重放事件来重建相同的状态。

### 核心收益

| 收益 | 说明 |
|------|------|
| **完全重放性** | Session 的所有变更记录为事件序列，可以完整重放 |
| **审计追踪** | 每个变更都有时间戳和顺序，可追溯 |
| **多设备同步** | 设备通过同步事件日志来保持状态一致 |
| **时间旅行** | 可以回溯到 Session 在任意事件点上的状态 |
| **向后兼容** | 与现有 Bus 系统无缝集成，不破坏已有 API |

---

## 2. 核心概念与设计目标

### 2.1 单一写入者（Single Writer）

系统设计的基础假设：**同一时刻只有一个设备对某个 Session（Aggregate）拥有写入权**。

这意味着：

- **不需要分布式时钟**：不需要 Vector Clock、CRDT 等复杂机制
- **不需要因果序（Causal Ordering）**：并发写入冲突不存在
- **全序仅靠序列号**：使用简单的单调递增序列号（Sequence Number）即可保证全序

### 2.2 Bus 集成与向后兼容

现有系统中已经存在 `Bus` 抽象，用于发布/订阅事件（如 `session.created`、`session.updated`）。同步系统不能破坏这个已有抽象。

设计目标：

1. 引入新的 `SyncEvent` 抽象来处理事件溯源和 Projector
2. 将这些新事件无缝集成到现有的 `Bus` 系统中
3. 保持完全的向后兼容性，对用户不可见

**关键设计决策**：Sync 事件执行后会自动**重新发布**（re-publish）为 Bus 事件。`Bus` 仍然是系统中监听单个事件的首要方式。

### 2.3 事件在变更之前发生

传统的 Bus 事件是在数据库变更**之后**发出的：

```
修改 DB → Bus.publish(event)
```

Event Sourcing 要求事件在变更**之前**发出：

```
SyncEvent.run(event, data) → Projector 执行变更 → Bus 重新发布
```

这个顺序变化虽然微小，但对于同步机制的正确性至关重要。

---

## 3. 架构概览

```
                        ┌─────────────────────────┐
                        │    SyncEvent.run()       │
                        │    SyncEvent.replay()    │
                        │    SyncEvent.replayAll() │
                        └───────────┬─────────────┘
                                    │
                                    ▼
                        ┌─────────────────────────┐
                        │   Event Registry         │
                        │   (type → Definition)    │
                        └───────────┬─────────────┘
                                    │
                                    ▼
                        ┌─────────────────────────┐
                        │   process()              │
                        │   ┌───────────────────┐  │
                        │   │ 1. 分配 ID 和 Seq  │  │
                        │   │ 2. 执行 Projector  │  │
                        │   └───────────────────┘  │
                        └───────────┬─────────────┘
                                    │
                  ┌─────────────────┼─────────────────┐
                  ▼                 ▼                   ▼
        ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐
        │  SQLite DB   │  │  ProjectBus  │  │  GlobalBus       │
        │  event_table │  │  (实例级)     │  │  (全局级)         │
        │ event_seq    │  │              │  │                  │
        └──────────────┘  └──────────────┘  └──────────────────┘
```

### 核心组件

| 组件 | 职责 |
|------|------|
| `SyncEvent` | 事件溯源系统的入口，提供 `run`、`replay`、`replayAll`、`remove`、`claim` API |
| `Definition` | 事件定义，包含 type、version、aggregate、schema、busSchema |
| `Event` | 运行时事件实例，包含 id、seq、aggregateID、data |
| `Projector` | 事件处理器，接收事件并执行数据库变更 |
| `registry` | 全局事件注册表（Map），按 type.version 存储事件定义 |
| `versions` | 全局版本跟踪表（Map），记录每种事件类型的最新版本号 |

---

## 4. SyncEvent 定义 API

### 4.1 基本定义

```typescript
const Created = SyncEvent.define({
  type: "session.created",   // 事件类型标识符
  version: 1,                 // 事件版本号
  aggregate: "sessionID",     // 聚合根 ID 字段名
  schema: z.object({          // 事件数据 Schema
    sessionID: SessionID.zod,
    info: Info,
  }),
})
```

### 4.2 带 Bus Schema 的定义（用于向后兼容）

当 Sync 事件的 data 形状与旧版 Bus 事件的 properties 形状不同时，使用 `busSchema`：

```typescript
const Updated = SyncEvent.define({
  type: "session.updated",
  version: 1,
  aggregate: "sessionID",
  schema: z.object({          // Sync 事件的实际数据
    sessionID: SessionID.zod,
    info: partialSchema(Info), // 仅包含变更的字段
  }),
  busSchema: z.object({       // Bus 事件的数据（向后兼容）
    sessionID: SessionID.zod,
    info: Info,               // 完整的 Session 对象
  }),
})
```

### 4.3 序列化事件（SerializedEvent）

```typescript
type SerializedEvent = {
  id: string          // 事件唯一 ID（如 "evt_abc123"）
  type: string        // 带版本号的事件类型（如 "session.created.1"）
  seq: number         // 单调递增序列号
  aggregateID: string // 聚合根 ID（如 sessionID）
  data: unknown       // 事件数据
}
```

### 4.4 事件 ID

事件 ID 使用 `EventID` 类型，基于 `Identifier.ascending("event", ...)` 生成，保证以下特性：

- 全局唯一性
- 按时间排序（ascending 模式）

```typescript
const id = EventID.ascending()  // 生成类似 "evt_..." 的 ID
```

### 4.5 冻结机制

`SyncEvent.define()` 只能在系统初始化（`SyncEvent.init()`）之前调用。`init()` 执行后系统会**冻结**（frozen = true），此后任何新的 `define()` 调用都会抛出错误。

这是为了确保所有事件定义在系统启动时完成注册，避免动态注册导致的类型不一致和运行时错误。

---

## 5. SyncEvent 与 BusEvent 对比

### 5.1 定义方式对比

**BusEvent 定义（旧）：**

```typescript
const Diff = BusEvent.define(
  "session.diff",
  z.object({
    sessionID: SessionID.zod,
    diff: Snapshot.FileDiff.array(),
  }),
)

// 用法
Bus.publish(Diff, { sessionID, diff })
Bus.subscribe(Diff, (event) => { /* event.properties */ })
```

**SyncEvent 定义（新）：**

```typescript
const Created = SyncEvent.define({
  type: "session.created",
  version: 1,
  aggregate: "sessionID",
  schema: z.object({
    sessionID: SessionID.zod,
    info: Info,
  }),
})

// 用法
SyncEvent.run(Created, { sessionID, info })
Bus.subscribe(Created, (event) => { /* event.properties */ }) // 兼容！
```

### 5.2 事件形状（Shape）对比

| 字段 | SyncEvent | BusEvent |
|------|-----------|----------|
| 类型标识 | `type` | `type` |
| 事件数据 | `data` | `properties` |
| 序列号 | `seq` | 无 |
| 聚合 ID | `aggregateID` | 无 |
| 事件 ID | `id` | `id` |
| 事件版本 | 通过 type 字段包含（如 `session.created.1`） | 无 |

**SyncEvent 多出的元数据字段**（`seq`、`aggregateID`）用于支持事件溯源和按聚合重放。

设计选择：`data` 和 `properties` 使用不同的命名，以在代码中**清晰地消歧义**两种事件类型。

### 5.3 功能差异

| 能力 | SyncEvent | BusEvent |
|------|-----------|----------|
| 写入数据库 | 通过 Projector | 无（只通知） |
| 事件持久化 | 是（存入 event 表） | 否 |
| 事件重放 | 支持 `replay()` | 不支持 |
| 序列号跟踪 | 是 | 否 |
| 聚合过滤 | 支持（按 aggregateID） | 不支持 |
| 按类型订阅 | 不支持（只能 `subscribeAll`） | 支持 `subscribe(type)` |
| 自动转为 Bus 事件 | 是 | N/A |

### 5.4 互操作性

SyncEvent 定义可以传递给 Bus API：

```typescript
// ✅ 正确：使用 Bus.subscribe 监听 Sync 事件
Bus.subscribe(Created, (event) => {
  event.properties.info.title  // 类型安全
})

// ✅ 正确：通过 Client 订阅
client.subscribe("session.updated", (evt) => {
  evt.properties.info.title    // 类型安全
})

// ❌ 错误：不要用 Bus.publish 发布 Sync 事件
// Bus.publish(Updated, { ... })  // 应当使用 SyncEvent.run
```

---

## 6. 事件流程详解

### 6.1 时序图

```
调用者                  SyncEvent.run()         SQLite DB            Projector          Bus System
  │                          │                      │                    │                  │
  │  run(Created, data)      │                      │                    │                  │
  │─────────────────────────►│                      │                    │                  │
  │                          │                      │                    │                  │
  │                          │ 1. 验证 version      │                    │                  │
  │                          │    ──────────────    │                    │                  │
  │                          │    if (def.version   │                    │                  │
  │                          │     !== latest)      │                    │                  │
  │                          │       throw Error    │                    │                  │
  │                          │                      │                    │                  │
  │                          │ 2. 开始事务           │                    │                  │
  │                          │    (immediate)       │                    │                  │
  │                          │─────────────────────►│                    │                  │
  │                          │                      │                    │                  │
  │                          │ 3. 生成 EventID     │                    │                  │
  │                          │    (ascending)       │                    │                  │
  │                          │                      │                    │                  │
  │                          │ 4. 查询当前 seq      │                    │                  │
  │                          │─────────────────────►│                    │                  │
  │                          │◄─────────────────────│                    │                  │
  │                          │    row?.seq ?? -1    │                    │                  │
  │                          │                      │                    │                  │
  │                          │ 5. 递增 seq          │                    │                  │
  │                          │    seq = last + 1    │                    │                  │
  │                          │                      │                    │                  │
  │                          │ 6. process(def,evt)  │                    │                  │
  │                          │──────────────────────────────────────────►│                  │
  │                          │                      │                    │                  │
  │                          │                      │ 7. Projector 执行   │                  │
  │                          │                      │◄───────────────────│                  │
  │                          │                      │ INSERT/UPDATE/DEL   │                  │
  │                          │                      │───────────────────►│                  │
  │                          │                      │                    │                  │
  │                          │             8. 持久化 event + seq          │                  │
  │                          │                      │◄───────────────────│                  │
  │                          │                      │───────────────────►│                  │
  │                          │                      │                    │                  │
  │                          │                      │ 9. convertEvent()  │                  │
  │                          │                      │◄───────────────────│                  │
  │                          │                      │ 重塑事件数据         │                  │
  │                          │                      │───────────────────►│                  │
  │                          │                      │                    │                  │
  │                          │                      │ 10. Bus.publish()   │                  │
  │                          │                      │──────────────────────────────────────►│
  │                          │                      │                    │                  │
  │                          │                      │ 11. GlobalBus.emit │                  │
  │                          │                      │──────────────────────────────────────►│
  │                          │                      │                    │                  │
  │  return void             │                      │                    │                  │
  │◄─────────────────────────│                      │                    │                  │
  │                          │                      │                    │                  │
```

### 6.2 步骤详解

| 步骤 | 说明 |
|------|------|
| **1. 版本验证** | 检查事件定义的版本号是否是最新版本，不允许运行旧版本事件 |
| **2. 开始事务** | 使用 `immediate` 模式开始事务，确保在事务期间没有其他写入者修改数据 |
| **3. 生成 EventID** | 使用 ascending 标识符生成全局唯一的、按时间排序的事件 ID |
| **4. 查询当前 seq** | 从 `event_sequence` 表查询该 aggregate 当前的序列号 |
| **5. 递增 seq** | seq = lastSeq + 1（首次事件 seq = 0） |
| **6. 调用 process()** | 内部事务处理函数 |
| **7. Projector 执行** | 调用注册的 Projector 函数，执行数据库变更（INSERT/UPDATE/DELETE） |
| **8. 持久化** | 将事件写入 `event` 表，更新 `event_sequence` 表 |
| **9. 事件重塑** | 执行 `convertEvent` 钩子，将 Sync 事件数据转换为 Bus 兼容格式 |
| **10. Bus 发布** | 通过 `ProjectBus.publish()` 发布到实例级 Bus |
| **11. GlobalBus 发布** | 通过 `GlobalBus.emit()` 发布到全局 Bus（用于跨实例通信和 IDE 集成） |

### 6.3 Replay 流程

Replay（重放）用于从已有事件日志重建状态：

```typescript
SyncEvent.replay(serializedEvent, {
  publish: true,
  ownerID: "device-123",
})
```

Replay 流程的特殊之处：

1. **序列号检查**：检查事件的 seq 是否大于当前记录的 seq（跳过已应用的事件）
2. **拥有者检查**：如果 aggregate 已被其他设备声明（claim），则跳过
3. **顺序检查**：验证事件的 seq 是否等于 `latest + 1`（不允许跳号）
4. **批量重放**：`replayAll()` 会验证所有事件属于同一 aggregate 且序号连续

---

## 7. 聚合（Aggregate）与序列号

### 7.1 什么是 Aggregate

Aggregate（聚合根）是 Domain-Driven Design 中的概念。在 OpenCode 中，`aggregate` 字段指定事件数据中哪个字段充当聚合根 ID：

```typescript
const Created = SyncEvent.define({
  aggregate: "sessionID",  // 表示 event.data.sessionID 是聚合根 ID
  // ...
})
```

当运行事件时，系统自动从 data 中提取聚合 ID：

```typescript
const agg = data[def.aggregate]  // data["sessionID"]
```

如果聚合 ID 为 null 或未定义，系统会抛出错误。TypeScript 类型系统在编译期保证了这一点。

### 7.2 序列号（Sequence Number）

序列号是每个 Aggregate 独立的**单调递增整数**：

- 每个 Aggregate 的序列号独立计数，从 0 开始
- 每次运行事件时，序列号递增 1
- 序列号存储在 `event_sequence` 表中

```sql
-- event_sequence 表结构
CREATE TABLE event_sequence (
  aggregate_id TEXT PRIMARY KEY,  -- 聚合根 ID
  seq INTEGER NOT NULL,           -- 当前序列号
  owner_id TEXT                   -- 当前拥有者（多设备同步用）
);
```

### 7.3 序列号的用途

1. **全序保证**：确保同一 Aggregate 的事件严格按顺序排列
2. **去重**：Replay 时跳过已处理的序列号
3. **顺序验证**：Replay 时验证事件的 seq 是否为 `latest + 1`
4. **事件分页**：按 seq 范围查询事件用于增量同步

---

## 8. 事件版本化

### 8.1 版本号的设计

每个事件定义携带一个 `version` 字段：

```typescript
const Created = SyncEvent.define({
  type: "session.created",
  version: 1,  // 当前版本
  // ...
})
```

### 8.2 带版本号的类型标识符

内部存储使用 `versionedType` 函数，生成格式为 `{type}.{version}` 的标识符：

```typescript
versionedType("session.created", 1)  // → "session.created.1"
```

这个带版本号的标识符是 registry 中的 key。

### 8.3 版本演进策略

```
版本规则：
─────────────────────────────────────────────────────────────
• 代码中只运行最新版本的事件（def.version 必须等于 versions 表中记录的最新版本）
• 旧版本的事件保留在 registry 中，用于 Replay 历史事件
• Replay 不经过 Bus，简化了 Bus 系统的设计
• Bus 上只发布不携带版本号的最新事件类型
```

在 `init()` 过程中，系统使用最新的类型（不含版本号）注册到 Bus：

```typescript
for (let [type, version] of versions.entries()) {
  let def = registry.get(versionedType(type, version))!
  BusEvent.define(def.type, def.properties)  // 不带版本号
}
```

### 8.4 Schema 演进示例

当事件 Schema 需要变更时，典型的演进方式：

1. 定义新版本的事件（version: 2）
2. 在 Projector 中处理新旧版本的兼容逻辑
3. `convertEvent` 钩子可以将不同版本的 data 转换为统一的 Bus 输出格式

---

## 9. Projector 系统

### 9.1 什么是 Projector

Projector 是响应事件并执行副作用（主要是数据库变更）的函数。它是 Event Sourcing 模式中的"投射"（Projection）概念。

在 OpenCode 中，Projector 是**同步执行**的：它直接在事件发布的事务中修改数据库，确保事件和状态的一致性。

### 9.2 Projector 定义

使用 `SyncEvent.project()` 定义 Projector：

```typescript
export default [
  SyncEvent.project(Session.Event.Created, (db, data) => {
    db.insert(SessionTable)
      .values(Session.toRow(data.info))
      .run()
    
    if (data.info.workspaceID) {
      db.update(WorkspaceTable)
        .set({ time_used: Date.now() })
        .where(eq(WorkspaceTable.id, data.info.workspaceID))
        .run()
    }
  }),

  SyncEvent.project(Session.Event.Updated, (db, data) => {
    const info = data.info
    const row = db
      .update(SessionTable)
      .set(toPartialRow(info))
      .where(eq(SessionTable.id, data.sessionID))
      .returning()
      .get()
    if (!row) throw new NotFoundError({
      message: `Session not found: ${data.sessionID}`
    })
  }),

  SyncEvent.project(Session.Event.Deleted, (db, data) => {
    db.delete(SessionTable)
      .where(eq(SessionTable.id, data.sessionID))
      .run()
  }),
]
```

### 9.3 Projector 签名

```typescript
type ProjectorFunc = (
  db: Database.TxOrDb,      // 数据库事务对象
  data: unknown,            // 事件数据（类型由 Definition 的 schema 推断）
  event: Event              // 完整的事件对象（含 id、seq、aggregateID）
) => void
```

### 9.4 Projector 安装

在 `server/projectors.ts` 中通过 `initProjectors()` 安装：

```typescript
export function initProjectors() {
  SyncEvent.init({
    projectors: sessionProjectors,      // Projector 列表
    convertEvent: (type, data) => {     // 事件转换钩子
      if (type === "session.updated") {
        const id = data.sessionID
        const row = Database.use((db) =>
          db.select().from(SessionTable)
            .where(eq(SessionTable.id, id)).get()
        )
        if (!row) return data
        return {
          sessionID: id,
          info: Session.fromRow(row),   // 从 DB 读取完整对象
        }
      }
      return data
    },
  })
}

initProjectors()  // 在模块加载时执行
```

### 9.5 关键约束

| 约束 | 说明 |
|------|------|
| **每个事件必须有 Projector** | 运行未注册 Projector 的事件会抛出错误 |
| **Projector 在事务中执行** | 确保事件写入和数据变更的原子性 |
| **转换后发布** | Projector 执行完并持久化后，才通过 Bus 发布 |
| **不可重复注册** | 系统冻结后不允许定义新事件或注册新 Projector |

---

## 10. 向后兼容性策略

### 10.1 三层兼容性保障

```
Level 1: Schema 兼容
   ↓     busSchema 定义独立的 Bus 事件形状
Level 2: 运行时转换
   ↓     convertEvent 钩子动态重塑事件数据
Level 3: 类型安全
   ↓     TypeScript + Zod Schema 确保类型正确性
```

### 10.2 busSchema：声明式兼容

当 Sync 事件的 data 形状与 Bus 事件的 properties 形状不同时，使用 `busSchema` 声明兼容形状：

```typescript
const Updated = SyncEvent.define({
  type: "session.updated",
  version: 1,
  aggregate: "sessionID",
  schema: z.object({          // Sync 事件形状（仅变更字段）
    sessionID: SessionID.zod,
    info: partialSchema(Info),
  }),
  busSchema: z.object({       // Bus 事件形状（完整对象）
    sessionID: SessionID.zod,
    info: Info,
  }),
})
```

`busSchema` 内部存储在 `Definition.properties` 字段上，这就是为什么 Sync 事件定义可以传递给 `Bus.subscribe()` 并自动获得正确的类型推断。

### 10.3 convertEvent：运行时转换

`convertEvent` 钩子在运行时将 Sync 事件数据转换为 Bus 兼容格式：

```typescript
convertEvent: (type, data) => {
  if (type === "session.updated") {
    // 从数据库读取完整对象来补充 Bus 事件所需的所有字段
    const id = data.sessionID
    const row = Database.use((db) =>
      db.select().from(SessionTable)
        .where(eq(SessionTable.id, id)).get()
    )
    if (!row) return data
    return {
      sessionID: id,
      info: Session.fromRow(row), // 重建完整 Info
    }
  }
  return data  // 其他事件直接透传
},
```

**重要提醒**：`convertEvent` 的运行时行为与 `busSchema` 的类型声明是**独立验证的**。两者必须保持一致，但目前没有自动的编译期检查。这是设计权衡：转换逻辑的灵活性 vs. 类型安全的保障。

### 10.4 为什么不用 convertSchema

系统设计者曾探索过用 `convertSchema` 在运行时转换 Schema 的方案，但发现了一个致命缺陷：

> **需要类型检查早于运行时完成**。对 SDK 消费者的类型生成（通过 Zod → TypeScript 转换）可以工作，但对内部代码中的 `Bus.subscribe` 调用无法正确推断类型。

### 10.5 为何不直接提供 Sync 事件独立订阅

另一个被探索的方案是为 SyncEvent 提供类似 Bus 的按类型订阅 API，但面临两个问题：

1. **实例作用域**：Bus 是实例级（instance-scoped）的，Sync 事件也需要实例级隔离。这将增加显著的实现复杂度。
2. **SDK 消费者**：无法改变外部 SDK 消费者的代码，他们仍然使用旧的 Bus 事件。为了一致性，不如统一使用 Bus。

### 10.6 当前策略总结

```
               SyncEvent.run()
                    │
                    ▼
              [Projector 执行]
                    │
                    ▼
           convertEvent() 重塑
                    │
                    ▼
         Bus.publish(def, data)
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
   Bus.subscribe()        Client.subscribe()
   (内部 TypeScript)       (SDK 消费者)
```

---

## 11. 多设备同步架构

### 11.1 架构设计

```
设备 A (写入者)               设备 B (同步者)
─────────────                ────────────────
                             
 SyncEvent.run()             (等待新事件)
      │                           
      ▼                           
 [Event Table] ──poll──►  [发现新 seq]
      │                           
      ▼                           
 [Projector 执行]               
      │                           
      ▼                           
 [Bus 发布] ──listen──►  [客户端收到事件]
                              │
                              ▼
                        [更新本地 UI]
```

### 11.2 核心 API

#### SyncEvent.claim() - 声明写入权

```typescript
SyncEvent.claim(aggregateID: string, ownerID: string)
```

在 `event_sequence` 表中设置该 Aggregate 的 `owner_id`，标记当前设备为该 Session 的写入者。

#### SyncEvent.replay() - 重放单个事件

```typescript
SyncEvent.replay(event: SerializedEvent, options?: {
  publish: boolean      // 是否重新发布到 Bus
  ownerID?: string      // 当前设备的 ownerID
})
```

内部流程：
1. 检查该 Aggregate 的当前 seq
2. 如果 event.seq <= latest，跳过（已处理）
3. 如果 ownerID 不匹配，跳过（不是写入者的事件）
4. 验证 seq === expected（latest + 1）
5. 执行 Projector

#### SyncEvent.replayAll() - 批量重放

```typescript
SyncEvent.replayAll(events: SerializedEvent[], options?: {
  publish: boolean
  ownerID?: string
})
```

额外验证：
- 所有事件必须属于同一个 Aggregate
- 事件序列号必须连续

### 11.3 单写入者保证

系统通过 `event_sequence` 表中的 `owner_id` 字段实现单写入者：

```
事件重放检查逻辑：
─────────────────────────────────────────────
1. 检查 aggregate 的 owner_id
2. 如果 owner_id 存在且不等于 replay 请求的 ownerID
   → 跳过该事件（不属于当前设备的写入者）
3. 如果 owner_id 为空或匹配
   → 执行 Projector 并更新 seq
```

### 11.4 同步场景

| 场景 | 流程 |
|------|------|
| **新设备加入** | 获取该 Aggregate 的完整事件日志 → `replayAll()` 重放到最新状态 |
| **增量同步** | 获取 seq 大于本地的增量事件 → `replay()` 逐个重放 |
| **设备切换写入权** | 新设备调用 `claim()` → 旧设备的事件不再被 replay |
| **离线写入** | 本地记录事件 → 重连后推送到服务器 → 其他设备 replay |

---

## 12. 数据库结构

### 12.1 表结构

```sql
-- 事件序列表（每个 Aggregate 一行）
CREATE TABLE event_sequence (
  aggregate_id TEXT PRIMARY KEY NOT NULL,  -- 聚合根 ID（如 sessionID）
  seq INTEGER NOT NULL,                     -- 当前序列号
  owner_id TEXT                             -- 写入者设备 ID
);

-- 事件表
CREATE TABLE event (
  id TEXT PRIMARY KEY,                      -- 事件唯一 ID（evt_... 格式）
  aggregate_id TEXT NOT NULL                -- 聚合根 ID
    REFERENCES event_sequence(aggregate_id)
    ON DELETE CASCADE,
  seq INTEGER NOT NULL,                     -- 序列号
  type TEXT NOT NULL,                       -- 类型+版本（如 "session.created.1"）
  data TEXT NOT NULL                        -- JSON 格式的事件数据
);
```

### 12.2 数据流

```
event_sequence                   event
┌────────────────────────┐      ┌────────────────────────────────┐
│ aggregate_id │ seq │ owner│     │ id │ aggregate_id │ seq │ type   │ data │
│──────────────│─────│──────│     │────│──────────────│─────│────────│──────│
│ sess_abc123  │  0  │ null │     │evt1│ sess_abc123  │  0  │s.crd.1 │ {...}│
│ sess_abc123  │  1  │ d-1  │     │evt2│ sess_abc123  │  1  │s.upd.1 │ {...}│
│ sess_def456  │  0  │ d-2  │     │evt3│ sess_def456  │  0  │s.crd.1 │ {...}│
└────────────────────────┘      └────────────────────────────────┘
```

---

## 13. API 使用指南

### 13.1 定义事件

```typescript
import { SyncEvent } from "@/sync"

// 基本事件定义
const MyEvent = SyncEvent.define({
  type: "my-feature.action",
  version: 1,
  aggregate: "entityID",
  schema: Schema.Struct({
    entityID: Schema.String,
    payload: Schema.String,
  }),
})

// 带向后兼容的 Bus Schema
const MyUpdated = SyncEvent.define({
  type: "my-feature.updated",
  version: 1,
  aggregate: "entityID",
  schema: Schema.Struct({
    entityID: Schema.String,
    changes: Schema.Record(Schema.String, Schema.Unknown),
  }),
  busSchema: Schema.Struct({
    entityID: Schema.String,
    fullData: Schema.Record(Schema.String, Schema.Unknown),
  }),
})
```

### 13.2 定义 Projector

```typescript
import { SyncEvent } from "@/sync"
import { eq } from "drizzle-orm"

const myProjectors = [
  SyncEvent.project(MyEvent, (db, data) => {
    db.insert(myTable)
      .values({
        id: data.entityID,
        payload: data.payload,
      })
      .run()
  }),

  SyncEvent.project(MyUpdated, (db, data) => {
    db.update(myTable)
      .set(data.changes)
      .where(eq(myTable.id, data.entityID))
      .run()
  }),
]
```

### 13.3 初始化系统

```typescript
import { SyncEvent } from "@/sync"

SyncEvent.init({
  projectors: myProjectors,
  convertEvent: (type, data) => {
    // 可选的运行时事件转换
    return data
  },
})
```

### 13.4 运行事件

```typescript
import { SyncEvent } from "@/sync"

// 标准运行（自动发布到 Bus）
SyncEvent.run(MyEvent, { entityID: "123", payload: "hello" })

// 静默运行（不发布到 Bus，适用于清理等不需要通知的场景）
SyncEvent.run(MyEvent, { entityID: "123", payload: "hello" }, {
  publish: false,
})
```

### 13.5 订阅事件

```typescript
import { Bus } from "@/bus"

// 订阅特定类型的事件（通过 Bus 系统）
Bus.subscribe(MyEvent, (event) => {
  console.log(event.properties.payload) // 类型安全
})

// 订阅所有 Sync 事件（用于记录/转发）
SyncEvent.subscribeAll((event) => {
  console.log(event.type, event.seq, event.aggregateID)
  // event.data 是 unknown 类型，因为监听所有事件
})
```

### 13.6 Replay 事件

```typescript
import { SyncEvent } from "@/sync"

// 重放单个事件
SyncEvent.replay(serializedEvent, {
  publish: true,
  ownerID: "device-456",
})

// 批量重放
const sourceID = SyncEvent.replayAll(eventLog, {
  publish: false,  // 批量同步时不重复发布
  ownerID: "device-456",
})
```

### 13.7 管理写入权

```typescript
import { SyncEvent } from "@/sync"

// 声明写入权
SyncEvent.claim("session_abc123", "device-789")

// 移除 Aggregate 及其所有事件
SyncEvent.remove("session_abc123")
```

---

## 14. 关键源文件索引

| 文件 | 说明 |
|------|------|
| `packages/opencode/src/sync/index.ts` | SyncEvent 核心实现：定义、运行、重放、移除、声明 API |
| `packages/opencode/src/sync/schema.ts` | EventID 类型定义（ascending 标识符生成） |
| `packages/opencode/src/sync/event.sql.ts` | 数据库表定义（event、event_sequence） |
| `packages/opencode/src/sync/README.md` | 英文原始设计文档 |
| `packages/opencode/src/session/session.ts` | Session 事件定义（Created/Updated/Deleted）和业务逻辑 |
| `packages/opencode/src/session/message-v2.ts` | MessageV2 事件定义（Updated/Removed/PartUpdated/PartRemoved） |
| `packages/opencode/src/session/projectors.ts` | Session 和 Message 的 Projector 实现 |
| `packages/opencode/src/server/projectors.ts` | Projector 安装入口和 convertEvent 钩子 |
| `packages/opencode/src/bus/index.ts` | Bus 系统实现（发布/订阅） |
| `packages/opencode/src/bus/bus-event.ts` | BusEvent 定义 API |
| `packages/opencode/src/v2/event.ts` | EventV2 定义封装（统一的 Sync 事件定义方式） |

---

## 附录：事件类型清单

### 当前已注册的 Sync 事件

| 事件类型 | 版本 | Aggregate | 用途 |
|----------|------|-----------|------|
| `session.created` | 1 | sessionID | 创建新 Session |
| `session.updated` | 1 | sessionID | 更新 Session 属性（标题、权限等） |
| `session.deleted` | 1 | sessionID | 删除 Session |
| `message.updated` | 1 | sessionID | 创建或更新消息 |
| `message.removed` | 1 | sessionID | 删除消息 |
| `part.updated` | 1 | sessionID | 创建或更新消息片段 |
| `part.removed` | 1 | sessionID | 删除消息片段 |

### 非 Sync 事件（仍使用 BusEvent）

| 事件类型 | 用途 |
|----------|------|
| `session.diff` | 文件差异通知 |
| `session.error` | 错误通知 |
| `part.delta` | 消息流式增量更新 |
| `instance.disposed` | 实例销毁通知 |
