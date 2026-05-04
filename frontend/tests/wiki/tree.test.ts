import {
  buildWikiTree,
  filterWikiTreeByQuery,
  type WikiTreeNodeRecord,
} from "../../src/lib/wiki/tree";
import type { WikiNodeRead } from "../../src/types/wiki";

function node(overrides: Partial<WikiNodeRead> & Pick<WikiNodeRead, "id" | "name" | "path">): WikiNodeRead {
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
  };
}

describe("filterWikiTreeByQuery", () => {
  function buildSampleTree(): WikiTreeNodeRecord[] {
    return buildWikiTree([
      node({
        id: 10,
        name: "知识库",
        path: "知识库",
        system_role: "knowledge_base",
      }),
      node({
        id: 11,
        name: "架构设计",
        path: "知识库/架构设计",
        parent_id: 10,
      }),
      node({
        id: 12,
        name: "导入流程",
        path: "知识库/架构设计/导入流程",
        parent_id: 11,
        type: "document",
      }),
      node({
        id: 20,
        name: "问题定位报告",
        path: "问题定位报告",
        system_role: "reports",
      }),
      node({
        id: 21,
        name: "首轮报告",
        path: "问题定位报告/首轮报告",
        parent_id: 20,
        type: "document",
      }),
    ]);
  }

  it("returns the full tree when query is empty", () => {
    const tree = buildSampleTree();

    expect(filterWikiTreeByQuery(tree, "")).toEqual(tree);
  });

  it("keeps the ancestor chain when a descendant matches the query", () => {
    const tree = buildSampleTree();

    const filtered = filterWikiTreeByQuery(tree, "导入");

    expect(filtered).toHaveLength(1);
    expect(filtered[0].name).toBe("知识库");
    expect(filtered[0].children).toHaveLength(1);
    expect(filtered[0].children[0].name).toBe("架构设计");
    expect(filtered[0].children[0].children).toHaveLength(1);
    expect(filtered[0].children[0].children[0].name).toBe("导入流程");
  });

  it("keeps a whole subtree when the parent itself matches the query", () => {
    const tree = buildSampleTree();

    const filtered = filterWikiTreeByQuery(tree, "问题定位");

    expect(filtered).toHaveLength(1);
    expect(filtered[0].name).toBe("问题定位报告");
    expect(filtered[0].children).toHaveLength(1);
    expect(filtered[0].children[0].name).toBe("首轮报告");
  });
});
