# Wiki Tree Ordering Design

## Goal

为独立 Wiki 工作台补齐可维护的目录树排序能力，支持：

- 同级节点上下拖移排序
- 文档或普通目录拖拽进入目录
- 三点菜单中的 `上移` / `下移`
- 移动后自动刷新路径、索引和预览状态

本次只覆盖当前已存在的 native wiki tree，不改变报告生命周期、不引入跨特性拖拽。

## Current context

- 后端 `wiki_nodes` 已有 `sort_order` 字段。
- `PUT /api/wiki/nodes/{node_id}` 已支持基础 `parent_id` 和 `sort_order` 更新。
- 前端目录树当前只支持展开/收起、选择、三点菜单，不支持重排。
- 报告分组 `草稿 / 已验证 / 未通过` 是前端虚拟节点，不应被拖拽。

## Scope

本次实现包含：

1. 同父级节点排序
2. 文档/目录移动到另一个目录
3. 树节点菜单中的上移/下移
4. 拖拽中的高亮、放置校验和失败提示
5. 前后端模块拆分，避免继续把逻辑堆在 `WikiWorkbench` / `WikiTreeNode` 中
6. 文档和测试同步更新

本次不包含：

- 跨特性空间拖拽
- 报告投影节点移动
- 资源节点手动拖拽
- 多节点批量拖拽
- 自定义任意插入位置指示线

## Product rules

### Allowed node types

- `folder`: 可同级排序，可拖入普通目录
- `document`: 可同级排序，可拖入普通目录
- `asset`: 本次不开放树内手动拖拽
- `report_ref`: 不允许拖拽，不允许通过移动改变报告状态

### Restricted nodes

以下节点不允许被拖拽移动：

- `knowledge_base`
- `reports_root`
- `report_group`
- `feature_group_current`
- `feature_group_history`
- `feature_space_current`
- `feature_space_history`

### Valid drop rules

- 允许拖到同级节点的前后，用于重排
- 允许拖到普通目录节点本体，用于成为其子节点
- 不允许拖到自己
- 不允许拖到自己的后代目录
- 不允许拖到虚拟节点或系统保护节点
- 不允许跨 `space_id` 移动

## Interaction design

### Drag and drop

- 仅在 Wiki 树阅读态生效，搜索结果视图不支持拖拽。
- 节点 hover 时显示细微拖拽 affordance，不增加额外大图标，保持当前密度。
- 鼠标按下行主体开始拖拽。
- 目标行为分两种：
  - 行上半区 / 下半区：解释为同级前插 / 后插
  - 行中央目录区域：解释为放入该目录
- 非法目标显示禁用态，不提交请求。

### Menu actions

三点菜单补充：

- `上移`
- `下移`

规则：

- 只有普通目录/文档显示
- 位于同级第一项时隐藏 `上移`
- 位于同级最后一项时隐藏 `下移`
- 受系统目录和虚拟节点限制

### Result behavior

- 成功后保持当前展开态
- 成功后如果当前选中文档被移动，预览继续留在该文档
- 成功后刷新树和当前文档详情
- 失败时在工作台顶部显示消息，不静默失败

## Backend design

### Service split

将树写操作从 `WikiTreeService` 中拆出更明确的排序/移动边界：

- `tree/service.py`
  - 保留树读取、节点详情、创建、删除、恢复等主流程
- `tree/ordering.py`
  - 负责 sibling 重排、目标位置计算、批量重写 `sort_order`

### API shape

保留现有 `PUT /api/wiki/nodes/{node_id}` 兼容重命名。

新增：

- `POST /api/wiki/nodes/{node_id}/move`

请求体：

- `target_parent_id: int | null`
- `target_index: int`

语义：

- `target_parent_id` 为目标父目录
- `target_index` 为移动后在目标父目录下的最终顺序

这样前端不需要自己维护复杂的 `sort_order` 空洞值，也避免直接暴露“你自己猜一个排序整数”。

### Ordering rules

- 目标父级的所有可排序兄弟节点按当前 `sort_order, name, id` 形成基线顺序
- 先移除当前节点，再按 `target_index` 插入
- 最终从 `0...n-1` 重新写回同级 `sort_order`
- 若父级发生变化，继续走路径重算和子树路径刷新

## Frontend design

### Component split

当前树交互继续拆分：

- `components/wiki/tree/`
  - `WikiTreePane.tsx`
  - `WikiTreeNode.tsx`
  - `WikiNodeMenu.tsx`
  - `WikiTreeDropIndicator.tsx`
- `components/wiki/hooks/`
  - `useWikiNodeOrdering.ts`
  - `useWikiTreeDrag.ts`
- `lib/wiki/tree-ordering.ts`
  - 纯函数：可否移动、目标位置解析、兄弟索引计算

### State ownership

- `WikiWorkbench` 只持有 mutation 和 banner 回调
- 拖拽 hover / active / drop 目标等短生命周期状态下沉到 `useWikiTreeDrag`
- 菜单上下移通过 `useWikiNodeOrdering` 统一调用后端 `move` API

## Testing

后端：

- `tests/integration/test_wiki_nodes_api.py`
  - 同级重排
  - 移动到目录
  - 禁止移动到后代
  - 禁止移动系统节点

前端：

- `frontend/tests/wiki/tree-node-menu.test.tsx`
  - 菜单显示上移/下移
- `frontend/tests/wiki-node-workflow.test.tsx`
  - 点击上移/下移触发正确 mutation
- `frontend/tests/wiki-drag-workflow.test.tsx`
  - 文档拖入目录
  - 非法目标不提交

## Risks

- 当前树同时包含真实节点和虚拟节点，拖拽命中计算容易误把虚拟节点当合法目标
- 若继续直接复用 `updateWikiNode(sort_order)`，前端会承担过多排序细节，长期不可维护
- 大树拖拽若状态散落在单组件里，后续会继续失控，因此本次必须顺手拆模块

## Recommendation

采用“专用 move API + 前端轻量拖拽状态 + 同级重写 sort_order”的方案。

原因：

- 后端掌握最终顺序，避免前端猜测
- 能兼容三点菜单和拖拽两种入口
- 对现有路径重算逻辑复用最多
- 对其它页面影响最小
