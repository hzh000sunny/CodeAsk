import { buildWikiTree } from "../../src/lib/wiki/tree";
import {
  buildWikiSystemClearPlan,
  canCreateChildrenInWikiNode,
  canDeleteWikiNode,
  canReindexWikiNode,
  reportStatusGroup,
} from "../../src/lib/wiki/system-node-actions";
import type { ReportRead } from "../../src/types/api";
import type { WikiNodeRead } from "../../src/types/wiki";

function node(overrides: Partial<WikiNodeRead> & Pick<WikiNodeRead, "id" | "name" | "path">): WikiNodeRead {
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
  };
}

function report(overrides: Partial<ReportRead> & Pick<ReportRead, "id" | "title">): ReportRead {
  return {
    id: overrides.id,
    feature_id: overrides.feature_id ?? 7,
    title: overrides.title,
    body_markdown: overrides.body_markdown ?? "",
    metadata_json: overrides.metadata_json ?? {},
    status: overrides.status ?? "draft",
    verified: overrides.verified ?? false,
    verified_by: overrides.verified_by ?? null,
    verified_at: overrides.verified_at ?? null,
    created_by_subject_id: overrides.created_by_subject_id ?? "owner@test",
    created_at: overrides.created_at ?? "2026-05-04T00:00:00Z",
    updated_at: overrides.updated_at ?? "2026-05-04T00:00:00Z",
  };
}

describe("system wiki node actions", () => {
  it("allows delete for clear-only system nodes", () => {
    expect(
      canDeleteWikiNode(
        buildWikiTree([
          node({
            id: 1,
            name: "知识库",
            path: "knowledge-base",
            system_role: "knowledge_base",
          }),
        ])[0],
      ),
    ).toBe(true);
  });

  it("blocks child creation for report roots based on system role instead of raw path text", () => {
    expect(
      canCreateChildrenInWikiNode(
        buildWikiTree([
          node({
            id: 1,
            name: "问题定位报告",
            path: "reports",
            system_role: "reports",
          }),
        ])[0],
      ),
    ).toBe(false);
  });

  it("blocks reindex for synthetic feature and report grouping nodes", () => {
    const tree = buildWikiTree([
      node({
        id: -100007,
        name: "支付结算",
        path: "当前特性/payment",
        system_role: "feature_space_current",
      }),
      node({
        id: -100008,
        name: "历史支付",
        path: "历史特性/payment-history",
        system_role: "feature_space_history",
      }),
      node({
        id: -1001,
        name: "草稿",
        path: "reports/草稿",
        system_role: "report_group",
      }),
      node({
        id: 11,
        name: "知识库",
        path: "knowledge-base",
        system_role: "knowledge_base",
      }),
    ]);

    const currentFeatureRoot = tree.find((item) => item.system_role === "feature_space_current");
    const historyFeatureRoot = tree.find((item) => item.system_role === "feature_space_history");
    const reportGroup = tree.find((item) => item.system_role === "report_group");
    const knowledgeRoot = tree.find((item) => item.system_role === "knowledge_base");

    expect(currentFeatureRoot).toBeTruthy();
    expect(historyFeatureRoot).toBeTruthy();
    expect(reportGroup).toBeTruthy();
    expect(knowledgeRoot).toBeTruthy();

    expect(canReindexWikiNode(currentFeatureRoot!)).toBe(false);
    expect(canReindexWikiNode(historyFeatureRoot!)).toBe(false);
    expect(canReindexWikiNode(reportGroup!)).toBe(false);
    expect(canReindexWikiNode(knowledgeRoot!)).toBe(true);
  });

  it("builds a clear plan for the knowledge base root by deleting only its children", () => {
    const tree = buildWikiTree([
      node({ id: 1, name: "知识库", path: "knowledge-base", system_role: "knowledge_base" }),
      node({ id: 2, parent_id: 1, name: "运行手册", path: "knowledge-base/runbooks" }),
      node({
        id: 3,
        parent_id: 1,
        type: "document",
        name: "支付排查",
        path: "knowledge-base/payment",
      }),
    ]);

    expect(buildWikiSystemClearPlan(tree[0], [])).toEqual({
      nodeIds: [2, 3],
      reportIds: [],
    });
  });

  it("builds a clear plan for the feature root across wiki docs and reports", () => {
    const tree = buildWikiTree([
      node({
        id: 10,
        name: "支付结算",
        path: "当前特性/payment",
        system_role: "feature_space_current",
      }),
      node({
        id: 11,
        parent_id: 10,
        name: "知识库",
        path: "knowledge-base",
        system_role: "knowledge_base",
      }),
      node({
        id: 12,
        parent_id: 11,
        name: "接入说明",
        path: "knowledge-base/guide",
        type: "document",
      }),
      node({
        id: 13,
        parent_id: 10,
        name: "问题定位报告",
        path: "reports",
        system_role: "reports",
      }),
      node({
        id: -1000,
        parent_id: 13,
        name: "草稿",
        path: "reports/草稿",
        system_role: "report_group",
      }),
    ]);

    const reports = [
      report({ id: 21, title: "草稿报告", status: "draft", verified: false }),
      report({ id: 22, title: "已验证报告", status: "verified", verified: true }),
    ];

    expect(buildWikiSystemClearPlan(tree[0], reports)).toEqual({
      nodeIds: [12],
      reportIds: [21, 22],
    });
  });

  it("builds a clear plan for a single report group", () => {
    const tree = buildWikiTree([
      node({
        id: -1001,
        name: "已验证",
        path: "reports/已验证",
        system_role: "report_group",
      }),
    ]);

    const reports = [
      report({ id: 31, title: "草稿报告", status: "draft", verified: false }),
      report({ id: 32, title: "已验证报告", status: "verified", verified: true }),
      report({ id: 33, title: "未通过报告", status: "rejected", verified: false }),
    ];

    expect(buildWikiSystemClearPlan(tree[0], reports)).toEqual({
      nodeIds: [],
      reportIds: [32],
    });
  });

  it("maps report lifecycle to status groups", () => {
    expect(reportStatusGroup(report({ id: 1, title: "A", status: "draft", verified: false }))).toBe(
      "draft",
    );
    expect(reportStatusGroup(report({ id: 2, title: "B", status: "verified", verified: true }))).toBe(
      "verified",
    );
    expect(reportStatusGroup(report({ id: 3, title: "C", status: "rejected", verified: false }))).toBe(
      "rejected",
    );
  });
});
