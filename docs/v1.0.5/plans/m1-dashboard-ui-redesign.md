# M1 看板 UI / UX 重做 — OpenViking Admin Dashboard

> 版本：v1.0.5
> 状态：Completed。第一轮重做、第二轮对齐/去重、第三轮标题区压缩已实现；2026-05-28 M8 进一步完成真实数据可读性、完整分页事件流、指标采集和调优折叠配置面板收敛。
> 关联：[功能补齐 m1-dashboard-management](./m1-dashboard-management.md) · [设计 SDD §13.4](../design/openviking-integration.md) · 截图证据 `/home/hzh/img/1.png`、`/home/hzh/img/2.png`、`/home/hzh/img/3.png`、`/home/hzh/img/4.png`、`/home/hzh/img/6.png`、`/home/hzh/img/7.png`
> 现状文件：`frontend/src/components/settings/OpenVikingDashboard.tsx` · `frontend/src/styles/globals.css`（`.settings-openviking-*` / `.settings-diagnostic-*`）

## 0. 背景与边界

管理层功能（切模型 / 调参 / 重试 / 事件过滤等）已补齐并能调用，但**真实渲染效果不可用**：组件不对齐、信息挤在一起、什么都长一样分不清、事件一面墙没时间没详情、同步任务无限平铺无分页、进度/推荐值/指标是空占位。本文是**纯 UI/UX 重做规格**，逐卡给"现状问题 → 目标 + 根因"。

- 不重复 [m1-dashboard-management](./m1-dashboard-management.md) 的功能/端点/e2e 行为项；本文只管"长什么样、好不好用"。
- 部分"丑"来自**缺数据**（旧版 `进度 ?`、`推荐值 -`、Breaker/Latency 占位、事件无 payload）。本轮已修正：推荐值/API 事件 payload 已接入；普通单资源同步任务无增量进度时不再显示进度条；Metrics 已接 5 分钟真实采集，冷启动无样本时才显示"warming up / 未采集"。
- 验收方式：**对着截图/真实页面看**，不是"控件存在即通过"。

## 1. 总体问题与根因（基于截图 + 代码）

| 现象（截图） | 根因（代码/CSS） |
|---|---|
| 健康卡 6 个指标框挤一行、最右 Embedding 框溢出被切（图1） | `.settings-diagnostic-grid` = `auto-fit, minmax(150px,1fr)`，宽卡里项数多就挤/溢；卡 `overflow:hidden` 直接裁切 |
| 健康指标和 Embedding 配置长得一模一样、分不清（图1） | 两处都用 `.settings-diagnostic-grid`，无分区标题、无视觉区隔 |
| 路径（配置/工作目录/日志）像可编辑输入框（图1） | `PathBlock` 用 `<code>` 但样式接近输入框，缺只读视觉语义 |
| 调参输入框宽到离谱、值"1"占 60% 宽（图5） | 旧版 `.settings-openviking-tuning-row` 第一列 `minmax(220px,1fr)`，input 填满该列；M8 后改为 scope 折叠面板内的统一四列配置表 |
| 按钮文字是整串 key `应用 openviking.embedding.max_concurrent`（图5） | 旧版 `OpenVikingTuningCard` 按钮文案 = `应用 ${key}`；M8 后视觉文案收敛为短按钮"应用"，aria-label 保留 key 便于无障碍与测试定位 |
| 推荐值全是 `-`（图5） | 后端 GET tuning 未返回 `recommended`（功能文档 A2 项，未完成） |
| 同步任务每条 `进度 ?` / `ETA ?`、空进度条（图2-4） | `progressForStatus` 占位 + `progress`/ETA 未接真实 `job.progress`（功能文档 F-FE 项） |
| 同步任务几十条全量平铺、滚不到底、无分页（图2-4） | `OpenVikingSyncJobsCard` 直接 `jobs.map` 全量渲染，无分页/折叠/分组 |
| 测试垃圾 job（`e2e_unknown` / `mgmt-retry-*`）混在真实任务里（图2） | 真实库被测试数据污染（见 §8 数据卫生） |
| 事件流一面墙 `tuning_change/system/success`、无时间、无详情（图2-3） | `EventItem` 只渲染 `event_type + source_type + outcome`，无 `created_at` / `payload` 摘要 |
| Metrics 卡半幅孤悬、Breaker=0 / Latency `-` 占位（图6） | 2 列网格 + 写死占位（功能文档 Metrics 后置项） |
| 整体无层次、不知每个功能干嘛 | 全靠 `.settings-diagnostic-grid` 堆框，无卡内分区/说明/帮助文案 |

**一句话根因**：当前是"把每个字段塞进统一方框网格"的数据堆砌，没有做信息设计。修这个不是调几个 margin，是**重排信息层次 + 收敛控件 + 补空/缺态**。

## 2. 设计原则

- **层次**：每卡 = 标题 + 一句话用途 + 1~2 个分区；同卡内不同语义的数据要有视觉区隔（分区标题/分隔线/不同密度），不能全是等价方框。
- **控件尺寸合理**：数值输入框按内容宽（数字类 80–120px），不要 1fr 撑满；按钮视觉文案短（"应用"），key 放在行标签处，无障碍 label 可包含 key。
- **可解释**：每个会改状态/破坏性的操作旁边有一句说明或 tooltip（这个按钮干嘛、有什么后果）。
- **空/加载/错误三态统一**：缺数据显示 `—` 或"暂无/未采集"，不要显示 `?`；加载用骨架/占位；失败有内联错误。
- **长列表要可控**：同步任务分页/分组/折叠 + 默认收起 indexed；事件流使用完整分页栏，默认 5 条/页，提供总页数、每页条数和页码跳转，每页展示独立事件行，不用无限加载或跨页聚合。
- **一致性**：复用现有 design token / 间距；只读路径用只读视觉（非输入框样式）。
- **响应式**：窄屏单列、宽屏合理分栏，卡片不溢出裁切。

## 3. 全局布局重排

- [x] 去掉顶部独立状态条，避免与 Health / Embedding / SyncJobs 重复；运行、健康、模型和队列信息分别归入对应卡片。
- [x] 卡片网格逻辑配对，避免 Metrics 半幅孤悬：
  - 行1：Health（状态+诊断）｜ Embedding（独立卡，从 Health 拆出）
  - 行2：SyncJobs（宽）
  - 行3：EventStream ｜ Metrics
  - 行4：Tuning（宽）
- [x] 窄屏统一单列；卡片去掉会裁切内容的 `overflow:hidden`（改为内部各自处理溢出）。

## 4. 逐卡重做

### 4.1 HealthCard（图1）
- [x] 诊断指标改为**固定列**（如 3 列）整齐网格，不用 `auto-fit` 导致溢出；卡不再整体裁切
- [x] 路径（配置/工作目录/日志）用**只读样式**（带复制按钮的 code 行），不要长得像输入框
- [x] 从本卡**拆出 Embedding 为独立卡**（见 4.2）

### 4.2 EmbeddingCard（新独立卡，图1 下半）
- [x] 当前配置（provider/base_url/model/dimension/max_concurrent/rebuild_status）独立成卡，标题"Embedding 模型"
- [x] 候选下拉 + "切换模型" + "重建向量索引" 一组操作区，旁边一句说明"切换会清空索引并全量重建（约数分钟）"
- [x] 重建中显示 `rebuild_status` + 真实 `rebuild_progress`（无进度数据时不显示假进度条）

### 4.3 SyncJobsCard（图2-4）
- [x] **分页或分组 + 默认收起 indexed**：默认只展示进行中/失败 + 计数摘要（"已索引 N 条，展开查看"），不要几十条平铺
- [x] 进度列接**真实 `job.progress`**（百分比 + `eta_seconds`）；无真实增量进度的单资源任务只显示状态，**禁止 `进度 ?` / `ETA ?`**
- [x] 失败行错误文案截断 + hover 全文，不溢出
- [x] 卡级操作（重试失败/重新同步/重排同步队列）保留；重排同步队列有二次确认并说明不会切换 Embedding 模型

### 4.4 EventStream（图2-3）
- [x] 每条事件补 **`created_at` 时间** + **一行摘要**（从 `payload` 提炼，如 tuning_change 显示 `key: before→after`），不能只有 `event_type/system/success`
- [x] outcome 着色（现有 `data-outcome` 可用）做成明显的状态标签
- [x] 改为完整分页；默认 5 条/页，显示总条数 / 当前页 / 总页数，支持每页条数选择和页码跳转；按 outcome / event_type 过滤
- [x] 每页直接展示事件行，不再把连续同类型事件折叠成 `×N`，避免"加载更多后数字膨胀但看不到新事件"

### 4.5 TuningCard（图5）
- [x] 按 scope（openviking / codeask / ollama_recommend）**分组小节**，每组默认折叠；summary 显式显示"展开参数 / 收起参数"、参数数量和 chevron，hover / focus / open 状态有反馈，让首次进入页面也能判断可展开
- [x] 展开后使用统一四列：`参数 | 自定义值 | 推荐值 | 操作`；表头与行列宽一致，所有操作列靠右对齐
- [x] 每行：`key 标签` + 参数描述 / 影响说明 + **窄输入框**（数值类 ~100px，不撑满）+ 推荐值 + "应用"；不再展示"对齐推荐"或"回滚"
- [x] 推荐值接后端 `recommended`；推荐值只作为参考，不再驱动偏离高亮或自动展开
- [x] 修改值后点击"应用"必须先弹页面内居中确认框；取消不发请求，确认后提交；值未变化时只提示无需应用
- [x] systemd snippet 区：code 块完整可见/可滚 + 复制按钮，标题说明用途

### 4.6 MetricsCard（图6）
- [x] 接 status API `metrics_5min` 契约；当前未采集时明确显示"未采集"，不要 `0` / `-` 假占位冒充
- [x] 与 EventStream 同行排布，不再半幅孤悬

## 5. 文案与可用性

- [x] 每卡标题下一句"这是什么/给谁看"；每个破坏性按钮保留二次确认，破坏性后果在卡内文案说明
- [x] 统一术语（中文 + 必要英文 key）；徽章/状态色保持一致语义
- [x] 所有"缺值"统一 `—` / "未采集"，杜绝 `?` / 空白 / 假 `0`

## 6. 空 / 加载 / 错误态

- [x] 加载：使用"正在读取…"稳定占位
- [x] 空：每个列表/卡有友好空态（"暂无同步任务"等）
- [x] 错误：读取失败内联提示；写操作失败可见反馈（与功能文档 onError 项对齐）

## 7. 数据/后端依赖（交叉项，归 [m1-dashboard-management](./m1-dashboard-management.md)）

UI 重做依赖这些数据真实化，否则再美也是空壳：
- [x] GET tuning 返回 `recommended`（→ 4.5 推荐值）
- [x] sync job 真实 `progress` / `eta_seconds` 只在任务有增量进度时展示；普通 `add_text_resource` 单任务不显示假进度条（→ 4.3 进度）
- [x] 事件 `created_at` + `payload` 摘要可取（→ 4.4）
- [x] Metrics API 返回真实 `metrics_5min`：throughput 由 5 分钟内 `last_indexed_at` 聚合，breaker trips 由 dashboard events 聚合，latency p95 / samples 由 OpenViking client 请求耗时 recorder 采集；冷启动无样本时显示明确的 warming up / 未采集态

## 8. 数据卫生

- [x] 清理真实库里的测试污染 job：`e2e_unknown` / `mgmt-retry-*` / `m1_smoke_*` 等（图2 可见）不应出现在生产看板；本轮 live E2E 后已将 `openviking_sync_jobs` / `openviking_dashboard_events` 中对应测试数据清理为 0。后续仍应使用隔离数据目录跑破坏性 E2E。

## 9. 验收（对着截图/真实页面）

- [x] **逐项对照本文截图问题**复核：6 指标不溢出、Embedding 独立成卡、路径只读样式、调参输入窄+按钮短+分组+说明、推荐值/进度/指标无 `?`/假占位、事件有时间+摘要、同步任务不再无限平铺
- [x] 真实浏览器在 1280/1440/窄屏三档宽度下不溢出、不错位；窄屏设置二级导航已改为横向紧凑 tabs，避免占用半屏空白
- [x] 视觉/交互 e2e：在 [m1-dashboard-management §4](./m1-dashboard-management.md) 的 E1（五卡布局/对齐）基础上，已覆盖"事件含时间列""事件流总页数 / 每页条数 / 页码跳转""调参输入非全宽""同步任务分页/折叠/真实进度"等结构特征
- [x] 前端 tsc + vitest + eslint 绿；改动不破坏其它 settings 页

## 10. 排序建议

1. §3 全局布局 + §4.1/4.2 Health/Embedding 拆分（最显眼的溢出/雷同）
2. §4.5 Tuning（输入宽度/按钮/分组/说明——"难用"重灾区）
3. §4.3 SyncJobs 分页/折叠 + 真实进度（依赖 §7 数据）
4. §4.4 EventStream 时间+摘要（依赖 §7 数据）
5. §4.6 Metrics 真实化、§8 数据卫生、§5/§6 文案与三态收尾

---

## 11. 第二轮打磨清单（2026-05-27 截图复核发现）

> 第一轮把骨架（布局/分组/分页/真实数据）做对了，但**结构对齐、信息冗余、语义重复、细节留白**仍未干净。以下逐条 现象 → 改动（真实文件锚点）→ 验收。
> 优先级：🔴 阻塞 · 🟡 应做 · ⚪ 暂缓。

### 11.A 结构与对齐

- [x] 🔴 **整列卡片左边距右移 22px，与 header 不齐**。根因：`.settings-stack` 已有 `padding:22px`（`globals.css:3451`），`.openviking-dashboard` 又重复 `padding:22px`（`:3503`）。改：`.openviking-dashboard` 删横向/顶部 padding，只留 `display:grid; gap:14px;`（底部留白如需单独 `padding-bottom`）。验收：header 卡左边与下方所有卡左边对齐。
- [x] 🔴 **删 header 下那排横向状态条** `.openviking-status-strip`（`OpenVikingDashboard.tsx` 渲染处 + `globals.css:3507`）。运行/health/ollama/模型/计数信息健康卡已有。验收：页面无该 6-pill 行，信息不丢。

### 11.B 删冗余/重复

- [x] 🔴 **运行指标去掉重复队列计数**：Metrics 卡的等待/运行/已索引/失败（`OpenVikingDashboard.tsx:851-854`）与"同步任务"卡 pending/running/failed/indexed pill 同一组数；删 Metrics 这 4 项，只留真实指标（吞吐/Latency/Breaker，未采集显"未采集"）。
- [x] 🟡 **健康卡内信息收敛**：`Required model` 与 Embedding 卡"当前模型"重复，二选一（建议模型只归 Embedding 卡）。

### 11.C 语义清晰

- [x] 🔴 **admin 路径改绝对**：`api/openviking_status.py` 的 `config_file/workspace_path/log_file` 以及 `last_error`、health / Ollama / sync job / rebuild 清理错误均返回**绝对路径**。**理由（经负责人 2026-05-27 澄清）**：脱敏红线只约束**会话事件流（全体用户可见，`sessions/trace_redaction.py`）**；admin 诊断页是 `require_admin` 专属，配置须完整，管理员要据此去环境查文件。会话侧脱敏**不动**。
- [x] 🟡 **两个"重建"按钮区分**：Embedding 卡"重建向量索引" vs 同步任务"重排同步队列"改名 + 各加一句说明。
- [x] 🟡 **调参分组标签二选一**：每组左有中文"OpenViking 服务"、右有淡色原始 scope key（`openviking`）；保留中文标题，去右侧裸 key。
- [x] 🟡 **取消偏离推荐高亮**：M8 复核后取消"偏离推荐 / 已对齐"分流展示；推荐值只作为参考信息，避免把推荐值变成唯一明显路径。

### 11.D 布局打磨

- [x] 🟡 **事件流大片空白**：取消跨事件聚合后，每页直接展示事件行；卡片高度随当前页内容自适应，不再因单个 `×N` 聚合组显得空。
- [x] 🟡 **运行指标网格不齐**：删重复计数后重排为整齐网格（不要"Breaker trips"单独吊行）。
- [x] 🟡 **Health 与 Embedding 卡不等高**：右列底部留空；等高或重排。
- [x] 🟡 **调参行收敛**：调优参数默认折叠；展开后 `参数 | 自定义值 | 推荐值 | 操作` 四列对齐；数值输入 ~100px；操作列只保留短按钮"应用"。
- [x] 🟡 **`?` → `—`**：同步任务无真实进度时显示 `—`，不显示 `进度 ? / ETA ?`；同步更新 e2e 中 `进度 ?` 断言。

### 11.E 文档 / 测试纠偏（随 11.C 路径项）

- [x] 🔴 **acceptance §3.2.2 / §3.5 纠正**：删除/改写"admin 卡片不显示宿主机绝对路径"——脱敏只约束会话事件流；注明经负责人澄清。
- [x] 🔴 **e2e 纠偏**：`openviking-dashboard-live.spec.ts` 中针对 **admin 看板**的"无 `/home//tmp/`"断言删除；该脱敏断言只挂会话 trace。

### 11.F 遗留功能项（暂缓，非阻塞）

- [ ] ⚪ 破坏性 live e2e（E2 切模型 / E4 rebuild / E7 openviking 调参重启）隔离数据目录补全
- [x] ⚪ Ollama 轻量实测探测 `verify_ollama_recommend` + `ollama_settings_verified` 事件已接入；真实高压并发压测仍不在本轮范围
- [ ] ⚪ APScheduler interval 重排（codeask scope `progress_sweep_interval`/`scheduled_refresh_hours`）
- [x] ⚪ scheduled_refresh / 24h sweep 已接入 startup backfill 与 APScheduler 周期任务，完成后发送 `scheduled_refresh_summary`

### 11.G 验收（含真实页面，我来做）

- [x] 🔴 新截图三档（1440/1280/390）逐项对照：左边距与 header 对齐、无状态条、无重复计数、admin 路径为绝对、两个重建可区分、调参高亮/收敛、无 `?`、各卡无大片空白/不等高
- [x] 🔴 390 窄屏不溢出、二级导航不占半屏
- [x] 🟡 pyright 0 / pytest / ruff / tsc / vitest / eslint 全绿；管理 e2e（去 admin 脱敏断言后）仍绿

> 建议顺序：11.A（对齐+删条）→ 11.C 路径 + 11.E 文档纠偏 → 11.B 去重 → 11.D 打磨 → 11.F 暂缓。

---

## 12. 第三轮标题区压缩（2026-05-27 图 6 / 图 7 对比）

> 图 6 的 OpenViking 看板卡片标题区仍然过重：大标题 + 大段说明 + 孤立图标形成空标题区，内容被下推；图 7 的运行状态页更接近目标：图标和标题同行，说明降级，内容快速出现。

- [x] 抽出 OpenViking 专用 `OpenVikingCardHeader`，统一 Health / Embedding / SyncJobs / EventStream / Metrics / Tuning 六张卡的标题结构。
- [x] 图标与标题绑定到同一行，去掉孤立落在说明下方的图标。
- [x] 描述文案降级为小号 muted 文本，减少标题区高度。
- [x] SyncJobs 的主要操作（重试失败、重新同步、重排同步队列、显示 indexed）放入标题行右侧，减少全宽卡片左侧标题小块 + 右侧大空白的问题。
- [x] Tuning 的"套用预设"放入标题行右侧，减少单独操作行。
- [x] e2e / 单测覆盖：OpenViking 看板内存在 6 个 `.settings-openviking-card-header`，不存在旧 `.section-title-row`。
- [x] 真实浏览器截图复核：2048 / 1280 / 390 三档均无标题区大块空白；窄屏标题和操作自然折行。
