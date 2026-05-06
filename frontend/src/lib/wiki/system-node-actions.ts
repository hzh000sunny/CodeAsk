import type { ReportRead } from "../../types/api";
import type { WikiTreeNodeRecord } from "./tree";

const CLEARABLE_SYSTEM_ROLES = new Set([
  "knowledge_base",
  "reports",
  "feature_space_current",
  "feature_space_history",
  "report_group",
]);

const REINDEX_BLOCKED_SYSTEM_ROLES = new Set([
  "feature_group_current",
  "feature_group_history",
  "feature_space_current",
  "feature_space_history",
  "report_group",
]);

export function canCreateChildrenInWikiNode(node: WikiTreeNodeRecord) {
  return (
    node.type === "folder" &&
    node.system_role !== "feature_group_current" &&
    node.system_role !== "feature_group_history" &&
    node.system_role !== "reports" &&
    node.system_role !== "report_group"
  );
}

export function canRenameWikiNode(node: WikiTreeNodeRecord) {
  return node.system_role == null && (node.type === "folder" || node.type === "document");
}

export function isClearOnlyWikiNode(node: WikiTreeNodeRecord) {
  return CLEARABLE_SYSTEM_ROLES.has(node.system_role ?? "");
}

export function canDeleteWikiNode(node: WikiTreeNodeRecord) {
  return (
    (node.system_role == null && (node.type === "folder" || node.type === "document")) ||
    isClearOnlyWikiNode(node)
  );
}

export function canReindexWikiNode(node: WikiTreeNodeRecord) {
  return (
    (node.type === "folder" || node.type === "document") &&
    !REINDEX_BLOCKED_SYSTEM_ROLES.has(node.system_role ?? "")
  );
}

export function canRestoreArchivedWikiSpace(node: WikiTreeNodeRecord) {
  return node.system_role === "feature_space_history";
}

export function buildWikiSystemClearPlan(
  node: WikiTreeNodeRecord,
  reports: ReportRead[],
): {
  nodeIds: number[];
  reportIds: number[];
} {
  const nodeIds = new Set<number>();
  const reportIds = new Set<number>();

  function visit(current: WikiTreeNodeRecord) {
    if (current.system_role === "reports") {
      for (const report of reports) {
        reportIds.add(report.id);
      }
      return;
    }
    if (current.system_role === "report_group") {
      const groupKey = reportGroupKeyFromLabel(current.name);
      for (const report of reports) {
        if (groupKey == null || reportStatusGroup(report) === groupKey) {
          reportIds.add(report.id);
        }
      }
      return;
    }
    for (const child of current.children) {
      if (child.system_role != null) {
        visit(child);
        continue;
      }
      if (child.type === "report_ref") {
        continue;
      }
      nodeIds.add(child.id);
    }
  }

  visit(node);
  return {
    nodeIds: [...nodeIds].sort((left, right) => left - right),
    reportIds: [...reportIds].sort((left, right) => left - right),
  };
}

export function reportStatusGroup(report: Pick<ReportRead, "status" | "verified">) {
  if (report.verified) {
    return "verified";
  }
  if (report.status === "rejected") {
    return "rejected";
  }
  return "draft";
}

function reportGroupKeyFromLabel(label: string) {
  if (label === "草稿") {
    return "draft";
  }
  if (label === "已验证") {
    return "verified";
  }
  if (label === "未通过") {
    return "rejected";
  }
  return null;
}
