import { fireEvent, render, screen } from "@testing-library/react";

import { WikiTreeNode } from "../../src/components/wiki/WikiTreeNode";
import type { WikiTreeNodeRecord } from "../../src/lib/wiki/tree";

function createNode(
  overrides: Partial<WikiTreeNodeRecord> &
    Pick<WikiTreeNodeRecord, "id" | "name" | "path">,
): WikiTreeNodeRecord {
  return {
    id: overrides.id,
    space_id: overrides.space_id ?? 1,
    parent_id: overrides.parent_id ?? null,
    type: overrides.type ?? "folder",
    name: overrides.name,
    path: overrides.path,
    system_role: overrides.system_role ?? null,
    sort_order: overrides.sort_order ?? 0,
    created_at: overrides.created_at ?? "2026-05-04T00:00:00Z",
    updated_at: overrides.updated_at ?? "2026-05-04T00:00:00Z",
    children: overrides.children ?? [],
  };
}

describe("WikiTreeNode menu", () => {
  it("uses folder icons instead of disclosure chevrons for folders", () => {
    const { container, rerender } = render(
      <ul>
        <WikiTreeNode
          canManage
          depth={0}
          expandedIds={new Set()}
          node={createNode({
            id: 10,
            name: "运行手册",
            path: "知识库/运行手册",
            parent_id: 1,
            children: [
              createNode({
                id: 11,
                parent_id: 10,
                type: "document",
                name: "子文档",
                path: "知识库/运行手册/子文档",
              }),
            ],
          })}
          onCreateDocument={() => undefined}
          onCreateFolder={() => undefined}
          onDelete={() => undefined}
          onImport={() => undefined}
          onReindex={() => undefined}
          onRename={() => undefined}
          onSelect={() => undefined}
          onToggle={() => undefined}
          selectedNodeId={null}
        />
      </ul>,
    );

    expect(container.querySelector(".lucide-folder-open")).toBeInTheDocument();
    expect(container.querySelector(".lucide-chevron-right")).not.toBeInTheDocument();
    expect(container.querySelector(".lucide-chevron-down")).not.toBeInTheDocument();

    rerender(
      <ul>
        <WikiTreeNode
          canManage
          depth={0}
          expandedIds={new Set([10])}
          node={createNode({
            id: 10,
            name: "运行手册",
            path: "知识库/运行手册",
            parent_id: 1,
            children: [
              createNode({
                id: 11,
                parent_id: 10,
                type: "document",
                name: "子文档",
                path: "知识库/运行手册/子文档",
              }),
            ],
          })}
          onCreateDocument={() => undefined}
          onCreateFolder={() => undefined}
          onDelete={() => undefined}
          onImport={() => undefined}
          onReindex={() => undefined}
          onRename={() => undefined}
          onSelect={() => undefined}
          onToggle={() => undefined}
          selectedNodeId={null}
        />
      </ul>,
    );

    expect(container.querySelector(".lucide-folder-open")).toBeInTheDocument();
    expect(container.querySelector(".lucide-chevron-right")).not.toBeInTheDocument();
    expect(container.querySelector(".lucide-chevron-down")).not.toBeInTheDocument();
  });

  it("uses a component icon for feature root nodes", () => {
    const { container } = render(
      <ul>
        <WikiTreeNode
          canManage
          depth={0}
          expandedIds={new Set()}
          node={createNode({
            id: -100007,
            name: "小米",
            path: "当前特性/xiaomi",
            system_role: "feature_space_current",
            children: [
              createNode({
                id: 1,
                parent_id: -100007,
                name: "知识库",
                path: "knowledge-base",
                system_role: "knowledge_base",
              }),
            ],
          })}
          onCreateDocument={() => undefined}
          onCreateFolder={() => undefined}
          onDelete={() => undefined}
          onImport={() => undefined}
          onReindex={() => undefined}
          onRename={() => undefined}
          onSelect={() => undefined}
          onToggle={() => undefined}
          selectedNodeId={null}
        />
      </ul>,
    );

    expect(container.querySelector(".lucide-component")).toBeInTheDocument();
    expect(container.querySelector(".lucide-folder-open")).not.toBeInTheDocument();
  });

  it("shows create and mutate actions for regular folders", () => {
    render(
      <ul>
        <WikiTreeNode
          canManage
          depth={0}
          expandedIds={new Set()}
          node={createNode({
            id: 10,
            name: "运行手册",
            path: "知识库/运行手册",
            parent_id: 1,
          })}
          onCreateDocument={() => undefined}
          onCreateFolder={() => undefined}
          onDelete={() => undefined}
          onImport={() => undefined}
          onReindex={() => undefined}
          onRename={() => undefined}
          onSelect={() => undefined}
          onToggle={() => undefined}
          selectedNodeId={null}
        />
      </ul>,
    );

    fireEvent.click(screen.getByRole("button", { name: /打开节点 运行手册 的更多操作/ }));

    expect(screen.getByRole("menuitem", { name: "新建目录" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "新建 Wiki" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "导入 Wiki" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "重新索引" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "重命名" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "删除" })).toBeInTheDocument();
  });

  it("keeps system knowledge root non-renamable but clearable", () => {
    render(
      <ul>
        <WikiTreeNode
          canManage
          depth={0}
          expandedIds={new Set()}
          node={createNode({
            id: 1,
            name: "知识库",
            path: "知识库",
            system_role: "knowledge_base",
          })}
          onCreateDocument={() => undefined}
          onCreateFolder={() => undefined}
          onDelete={() => undefined}
          onImport={() => undefined}
          onReindex={() => undefined}
          onRename={() => undefined}
          onSelect={() => undefined}
          onToggle={() => undefined}
          selectedNodeId={null}
        />
      </ul>,
    );

    fireEvent.click(screen.getByRole("button", { name: /打开节点 知识库 的更多操作/ }));

    expect(screen.getByRole("menuitem", { name: "新建目录" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "新建 Wiki" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "导入 Wiki" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "重新索引" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "重命名" })).not.toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "删除" })).toBeInTheDocument();
  });

  it("shows restore action for archived feature roots", () => {
    render(
      <ul>
        <WikiTreeNode
          canManage
          canRestoreArchivedSpace
          depth={0}
          expandedIds={new Set()}
          node={createNode({
            id: -100008,
            feature_id: 8,
            name: "历史特性",
            path: "历史特性/history-feature",
            system_role: "feature_space_history",
            children: [],
          })}
          onCreateDocument={() => undefined}
          onCreateFolder={() => undefined}
          onDelete={() => undefined}
          onImport={() => undefined}
          onReindex={() => undefined}
          onRename={() => undefined}
          onRestoreArchivedSpace={() => undefined}
          onSelect={() => undefined}
          onToggle={() => undefined}
          selectedNodeId={null}
        />
      </ul>,
    );

    fireEvent.click(screen.getByRole("button", { name: /打开节点 历史特性 的更多操作/ }));

    expect(screen.getByRole("menuitem", { name: "恢复特性" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "重新索引" })).not.toBeInTheDocument();
  });

  it("does not show reindex for current feature roots", () => {
    render(
      <ul>
        <WikiTreeNode
          canManage
          depth={0}
          expandedIds={new Set()}
          node={createNode({
            id: -100007,
            feature_id: 7,
            name: "支付结算",
            path: "当前特性/payment-settlement",
            system_role: "feature_space_current",
            children: [],
          })}
          onCreateDocument={() => undefined}
          onCreateFolder={() => undefined}
          onDelete={() => undefined}
          onImport={() => undefined}
          onReindex={() => undefined}
          onRename={() => undefined}
          onSelect={() => undefined}
          onToggle={() => undefined}
          selectedNodeId={null}
        />
      </ul>,
    );

    fireEvent.click(screen.getByRole("button", { name: /打开节点 支付结算 的更多操作/ }));

    expect(screen.queryByRole("menuitem", { name: "重新索引" })).not.toBeInTheDocument();
  });

  it("shows clear actions for report lifecycle groups", () => {
    render(
      <ul>
        <WikiTreeNode
          canManage
          depth={0}
          expandedIds={new Set()}
          node={createNode({
            id: -1001,
            name: "已验证",
            path: "问题定位报告/已验证",
            system_role: "report_group",
          })}
          onCreateDocument={() => undefined}
          onCreateFolder={() => undefined}
          onDelete={() => undefined}
          onImport={() => undefined}
          onRename={() => undefined}
          onSelect={() => undefined}
          onToggle={() => undefined}
          selectedNodeId={null}
        />
      </ul>,
    );

    fireEvent.click(screen.getByRole("button", { name: /打开节点 已验证 的更多操作/ }));

    expect(screen.queryByRole("menuitem", { name: "新建目录" })).not.toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "重命名" })).not.toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "删除" })).toBeInTheDocument();
  });

  it("does not show a manage menu for report projections", () => {
    render(
      <ul>
        <WikiTreeNode
          canManage
          depth={0}
          expandedIds={new Set()}
          node={createNode({
            id: 22,
            name: "支付失败复盘",
            path: "问题定位报告/草稿/支付失败复盘",
            type: "report_ref",
            parent_id: 9,
          })}
          onCreateDocument={() => undefined}
          onCreateFolder={() => undefined}
          onDelete={() => undefined}
          onImport={() => undefined}
          onRename={() => undefined}
          onSelect={() => undefined}
          onToggle={() => undefined}
          selectedNodeId={null}
        />
      </ul>,
    );

    expect(
      screen.queryByRole("button", { name: /打开节点 支付失败复盘 的更多操作/ }),
    ).not.toBeInTheDocument();
  });

  it("shows move-up for later movable siblings and hides move-down at the end", () => {
    render(
      <ul>
        <WikiTreeNode
          canManage
          depth={0}
          expandedIds={new Set([1])}
          node={createNode({
            id: 1,
            name: "知识库",
            path: "knowledge-base",
            system_role: "knowledge_base",
            children: [
              createNode({
                id: 11,
                parent_id: 1,
                type: "document",
                name: "Alpha",
                path: "knowledge-base/alpha",
                sort_order: 0,
              }),
              createNode({
                id: 12,
                parent_id: 1,
                type: "document",
                name: "Beta",
                path: "knowledge-base/beta",
                sort_order: 1,
              }),
            ],
          })}
          onCreateDocument={() => undefined}
          onCreateFolder={() => undefined}
          onDelete={() => undefined}
          onImport={() => undefined}
          onMoveDown={() => undefined}
          onMoveUp={() => undefined}
          onRename={() => undefined}
          onSelect={() => undefined}
          onToggle={() => undefined}
          selectedNodeId={null}
        />
      </ul>,
    );

    fireEvent.click(screen.getByRole("button", { name: /打开节点 Beta 的更多操作/ }));

    expect(screen.getByRole("menuitem", { name: "上移" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "下移" })).not.toBeInTheDocument();
  });
});
