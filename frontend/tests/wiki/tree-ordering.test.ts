import {
  buildDropMovePayload,
  buildMoveDownPayload,
  buildMoveUpPayload,
  getNodeMoveFlags,
} from "../../src/lib/wiki/tree-ordering";
import type { WikiTreeNodeRecord } from "../../src/lib/wiki/tree";

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

describe("wiki tree ordering helpers", () => {
  it("computes move-up and move-down payloads from the sibling order", () => {
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
      }),
    ];

    expect(getNodeMoveFlags(roots, 11)).toEqual({ canMoveUp: false, canMoveDown: true });
    expect(getNodeMoveFlags(roots, 12)).toEqual({ canMoveUp: true, canMoveDown: false });
    expect(buildMoveUpPayload(roots, 12)).toEqual({
      target_parent_id: 1,
      target_index: 0,
    });
    expect(buildMoveDownPayload(roots, 11)).toEqual({
      target_parent_id: 1,
      target_index: 1,
    });
  });

  it("builds a drop payload that moves a document into a folder", () => {
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

    expect(
      buildDropMovePayload(roots, {
        draggedNodeId: 12,
        targetNodeId: 11,
        position: "inside",
      }),
    ).toEqual({
      target_parent_id: 11,
      target_index: 0,
    });
  });

  it("rejects dropping a folder into its own descendant", () => {
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
            name: "Parent",
            path: "knowledge-base/parent",
            sort_order: 0,
            children: [
              createNode({
                id: 12,
                parent_id: 11,
                type: "folder",
                name: "Child",
                path: "knowledge-base/parent/child",
                sort_order: 0,
                children: [],
              }),
            ],
          }),
        ],
      }),
    ];

    expect(
      buildDropMovePayload(roots, {
        draggedNodeId: 11,
        targetNodeId: 12,
        position: "inside",
      }),
    ).toBeNull();
  });
});
