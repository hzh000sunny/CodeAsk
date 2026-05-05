import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { WikiTreePane } from "../../src/components/wiki/WikiTreePane";
import type { WikiTreeNodeRecord } from "../../src/lib/wiki/tree";
import type { WikiSearchHitRead } from "../../src/types/wiki";

function createNode(
  overrides: Partial<WikiTreeNodeRecord> &
    Pick<WikiTreeNodeRecord, "id" | "name" | "path">,
): WikiTreeNodeRecord {
  return {
    id: overrides.id,
    space_id: overrides.space_id ?? 1,
    feature_id: overrides.feature_id ?? 7,
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

describe("WikiTreePane usability", () => {
  it("keeps the tree toolbar focused on search only", () => {
    render(
      <WikiTreePane
        canManageFeature
        collapsed={false}
        expandedIds={new Set()}
        onCreateDocument={() => undefined}
        onCreateFolder={() => undefined}
        onDeleteNode={() => undefined}
        onImport={() => undefined}
        onImportNode={() => undefined}
        onRenameNode={() => undefined}
        onResizeFromCollapseButton={() => undefined}
        onSelectSearchHit={() => undefined}
        onSelectNode={() => undefined}
        onToggleCollapsed={() => undefined}
        onToggleNode={() => undefined}
        roots={[
          createNode({
            id: 1,
            name: "知识库",
            path: "知识库",
            system_role: "knowledge_base",
          }),
        ]}
        search=""
        searchGroups={[]}
        searchLoading={false}
        selectedNodeId={null}
        setSearch={() => undefined}
      />,
    );

    expect(screen.getByPlaceholderText("搜索")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "导入 Wiki" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "新建 Wiki" })).not.toBeInTheDocument();
  });

  it("exposes the full node name for long labels", () => {
    render(
      <WikiTreePane
        canManageFeature
        collapsed={false}
        expandedIds={new Set([1])}
        onCreateDocument={() => undefined}
        onCreateFolder={() => undefined}
        onDeleteNode={() => undefined}
        onImport={() => undefined}
        onImportNode={() => undefined}
        onRenameNode={() => undefined}
        onResizeFromCollapseButton={() => undefined}
        onSelectSearchHit={() => undefined}
        onSelectNode={() => undefined}
        onToggleCollapsed={() => undefined}
        onToggleNode={() => undefined}
        roots={[
          createNode({
            id: 1,
            name: "这是一个非常长的 Wiki 节点名称用于验证完整标题是否仍然可访问",
            path: "知识库/长名称",
            children: [
              createNode({
                id: 2,
                parent_id: 1,
                type: "document",
                name: "子文档",
                path: "知识库/长名称/子文档",
              }),
            ],
          }),
        ]}
        search=""
        searchGroups={[]}
        searchLoading={false}
        selectedNodeId={null}
        setSearch={() => undefined}
      />,
    );

    expect(
      screen.getByRole("button", {
        name: "这是一个非常长的 Wiki 节点名称用于验证完整标题是否仍然可访问",
      }),
    ).toHaveAttribute(
      "title",
      "这是一个非常长的 Wiki 节点名称用于验证完整标题是否仍然可访问",
    );
  });

  it("shows matched heading paths in search results and forwards the hit on click", () => {
    const onSelectSearchHit = vi.fn();
    const hit: WikiSearchHitRead = {
      kind: "document",
      node_id: 8,
      title: "回调 Runbook",
      path: "知识库/回调 Runbook",
      heading_path: "回调 Runbook > 排查步骤",
      feature_id: 7,
      group_key: "current_feature",
      group_label: "当前特性",
      snippet: "先检查 webhook 回调是否超时。",
      score: 4,
      document_id: 15,
      report_id: null,
    };

    render(
      <WikiTreePane
        canManageFeature
        collapsed={false}
        expandedIds={new Set()}
        onCreateDocument={() => undefined}
        onCreateFolder={() => undefined}
        onDeleteNode={() => undefined}
        onImport={() => undefined}
        onImportNode={() => undefined}
        onRenameNode={() => undefined}
        onResizeFromCollapseButton={() => undefined}
        onSelectSearchHit={onSelectSearchHit}
        onSelectNode={() => undefined}
        onToggleCollapsed={() => undefined}
        onToggleNode={() => undefined}
        roots={[]}
        search="回调"
        searchGroups={[{ key: "current_feature", label: "当前特性", items: [hit] }]}
        searchLoading={false}
        selectedNodeId={null}
        setSearch={() => undefined}
      />,
    );

    expect(screen.getByText("回调 Runbook > 排查步骤")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /回调 Runbook/ }));
    expect(onSelectSearchHit).toHaveBeenCalledWith(hit);
  });
});
