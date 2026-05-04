import { buildWikiTree } from "../../src/lib/wiki/tree";
import {
  groupWikiSearchHits,
  injectWikiReportProjections,
} from "../../src/lib/wiki/presentation";
import type { WikiNodeRead, WikiReportProjectionRead, WikiSearchHitRead } from "../../src/types/wiki";

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

describe("injectWikiReportProjections", () => {
  it("injects draft, verified, and rejected report groups under the report root", () => {
    const tree = buildWikiTree([
      node({
        id: 1,
        name: "知识库",
        path: "知识库",
        system_role: "knowledge_base",
      }),
      node({
        id: 2,
        name: "问题定位报告",
        path: "问题定位报告",
        system_role: "reports",
      }),
      node({
        id: 3,
        name: "草稿报告",
        path: "问题定位报告/草稿报告",
        parent_id: 2,
        type: "report_ref",
      }),
    ]);

    const projections: WikiReportProjectionRead[] = [
      {
        node_id: 3,
        report_id: 10,
        feature_id: 1,
        title: "草稿报告",
        status: "draft",
        status_group: "draft",
        verified: false,
        verified_by: null,
        verified_at: null,
        updated_at: "2026-05-04T00:00:00Z",
      },
      {
        node_id: 4,
        report_id: 11,
        feature_id: 1,
        title: "已验证报告",
        status: "verified",
        status_group: "verified",
        verified: true,
        verified_by: "owner@test",
        verified_at: "2026-05-04T00:00:00Z",
        updated_at: "2026-05-04T00:00:00Z",
      },
    ];

    const injected = injectWikiReportProjections(tree, projections);
    const reportsRoot = injected.find((node) => node.system_role === "reports");
    expect(reportsRoot?.children.map((child) => child.name)).toEqual([
      "草稿",
      "已验证",
      "未通过",
    ]);
    expect(reportsRoot?.children[0].children[0].name).toBe("草稿报告");
    expect(reportsRoot?.children[0].children[0].type).toBe("report_ref");
  });
});

describe("groupWikiSearchHits", () => {
  it("groups hits by current feature documents and report refs", () => {
    const hits: WikiSearchHitRead[] = [
      {
        kind: "document",
        node_id: 11,
        title: "Doc hit",
        path: "知识库/Doc hit",
        feature_id: 1,
        group_key: "current_feature",
        group_label: "当前特性",
        snippet: "doc",
        score: 4,
      },
      {
        kind: "report_ref",
        node_id: 12,
        title: "Report hit",
        path: "问题定位报告/Report hit",
        feature_id: 1,
        group_key: "current_feature_reports",
        group_label: "问题定位报告",
        snippet: "report",
        score: 3,
        report_id: 99,
      },
    ];

    const grouped = groupWikiSearchHits(hits);
    expect(grouped.map((group) => group.label)).toEqual(["当前特性", "问题定位报告"]);
    expect(grouped[0].items[0].title).toBe("Doc hit");
    expect(grouped[1].items[0].report_id).toBe(99);
  });
});
