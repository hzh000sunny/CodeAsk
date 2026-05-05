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
    expect(screen.queryByRole("menuitem", { name: "重命名" })).not.toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "删除" })).toBeInTheDocument();
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
});
