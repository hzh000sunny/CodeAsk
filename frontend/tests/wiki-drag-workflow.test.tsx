import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { WikiTreePane } from "../src/components/wiki/WikiTreePane";
import type { WikiMoveNodePayload, WikiSearchHitRead } from "../src/types/wiki";
import type { WikiTreeNodeRecord } from "../src/lib/wiki/tree";

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

describe("Wiki drag workflow", () => {
  it("moves a document into a folder from the tree drop zone", () => {
    const onMoveNodeRequest = vi.fn();
    const roots = [
      createNode({
        id: 1,
        name: "知识库",
        path: "knowledge-base",
        system_role: "knowledge_base",
        children: [
          createNode({
            id: 11,
            parent_id: 1,
            type: "folder",
            name: "Runbooks",
            path: "knowledge-base/runbooks",
            sort_order: 0,
            children: [],
          }),
          createNode({
            id: 12,
            parent_id: 1,
            type: "document",
            name: "Callback",
            path: "knowledge-base/callback",
            sort_order: 1,
          }),
        ],
      }),
    ];

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
        onMoveDownNode={() => undefined}
        onMoveNodeRequest={onMoveNodeRequest}
        onMoveUpNode={() => undefined}
        onRenameNode={() => undefined}
        onResizeFromCollapseButton={() => undefined}
        onSelectNode={() => undefined}
        onSelectSearchHit={(_hit: WikiSearchHitRead) => undefined}
        onToggleCollapsed={() => undefined}
        onToggleNode={() => undefined}
        roots={roots}
        search=""
        searchGroups={[]}
        searchLoading={false}
        selectedNodeId={null}
        setSearch={() => undefined}
      />,
    );

    fireEvent.dragStart(screen.getByRole("button", { name: "Callback" }));
    const insideDropZone = document.querySelector(
      '[data-drop-zone="inside"][data-node-id="11"]',
    ) as HTMLElement | null;
    expect(insideDropZone).not.toBeNull();
    fireEvent.dragOver(insideDropZone as HTMLElement);
    fireEvent.drop(insideDropZone as HTMLElement);

    expect(onMoveNodeRequest).toHaveBeenCalledWith(
      expect.objectContaining({ id: 12, name: "Callback" }),
      {
        target_parent_id: 11,
        target_index: 0,
      } satisfies WikiMoveNodePayload,
    );
  });
});
