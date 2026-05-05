import { buildWikiTree } from "../../src/lib/wiki/tree";
import {
  formatWikiSearchHitHeading,
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

  it("creates synthetic report nodes when projections arrive before tree report nodes", () => {
    const tree = buildWikiTree([
      node({
        id: 2,
        name: "问题定位报告",
        path: "问题定位报告",
        system_role: "reports",
      }),
    ]);

    const projections: WikiReportProjectionRead[] = [
      {
        node_id: 44,
        report_id: 77,
        feature_id: 7,
        title: "支付超时复盘",
        status: "verified",
        status_group: "verified",
        verified: true,
        verified_by: "owner@test",
        verified_at: "2026-05-04T00:00:00Z",
        updated_at: "2026-05-04T00:00:00Z",
      },
    ];

    const injected = injectWikiReportProjections(tree, projections);
    const reportsRoot = injected.find((item) => item.system_role === "reports");
    const verifiedGroup = reportsRoot?.children.find((item) => item.name === "已验证");

    expect(verifiedGroup?.children).toHaveLength(1);
    expect(verifiedGroup?.children[0]).toMatchObject({
      id: 44,
      type: "report_ref",
      name: "支付超时复盘",
      feature_id: 7,
    });
  });
});

describe("groupWikiSearchHits", () => {
  it("groups hits by fixed wiki priority order", () => {
    const hits: WikiSearchHitRead[] = [
      {
        kind: "document",
        node_id: 13,
        title: "History hit",
        path: "历史特性/History hit",
        feature_id: 3,
        group_key: "history_features",
        group_label: "历史特性",
        snippet: "history",
        score: 2,
      },
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
      {
        kind: "document",
        node_id: 14,
        title: "Other current hit",
        path: "其它当前特性/Other current hit",
        feature_id: 2,
        group_key: "other_current_features",
        group_label: "其它当前特性",
        snippet: "other",
        score: 2.5,
      },
    ];

    const grouped = groupWikiSearchHits(hits);
    expect(grouped.map((group) => group.label)).toEqual([
      "当前特性",
      "问题定位报告",
      "其它当前特性",
      "历史特性",
    ]);
    expect(grouped[0].items[0].title).toBe("Doc hit");
    expect(grouped[1].items[0].report_id).toBe(99);
  });
});

describe("formatWikiSearchHitHeading", () => {
  it("returns the matched heading path when present", () => {
    expect(
      formatWikiSearchHitHeading({
        heading_path: "回调 Runbook > 排查步骤",
      }),
    ).toBe("回调 Runbook > 排查步骤");
  });

  it("returns null when the hit does not include a heading path", () => {
    expect(
      formatWikiSearchHitHeading({
        heading_path: null,
      }),
    ).toBeNull();
  });
});
