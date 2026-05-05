import type {
  WikiNodeRead,
  WikiReportProjectionRead,
  WikiSearchHitRead,
} from "../../types/wiki";
import { buildWikiTree, type WikiTreeNodeRecord } from "./tree";

export interface WikiSearchHitGroup {
  key: string;
  label: string;
  items: WikiSearchHitRead[];
}

export function formatWikiSearchHitHeading(
  hit: Pick<WikiSearchHitRead, "heading_path">,
) {
  const headingPath = hit.heading_path?.trim();
  return headingPath && headingPath.length > 0 ? headingPath : null;
}

const SEARCH_GROUP_ORDER = new Map<string, number>([
  ["current_feature", 0],
  ["current_feature_reports", 1],
  ["other_current_features", 2],
  ["history_features", 3],
]);

const REPORT_GROUP_DEFINITIONS: Array<{
  key: WikiReportProjectionRead["status_group"];
  label: string;
  sortOrder: number;
}> = [
  { key: "draft", label: "草稿", sortOrder: 0 },
  { key: "verified", label: "已验证", sortOrder: 1 },
  { key: "rejected", label: "未通过", sortOrder: 2 },
];

export function injectWikiReportProjections(
  roots: WikiTreeNodeRecord[],
  projections: WikiReportProjectionRead[],
  featureId?: number | null,
): WikiTreeNodeRecord[] {
  const tree = cloneTree(roots);
  const byId = new Map<number, WikiTreeNodeRecord>();
  indexTree(tree, byId);

  const reportsRoot = findReportsRoot(tree, featureId);
  if (!reportsRoot) {
    return tree;
  }

  const projectionsByStatus = new Map<string, WikiReportProjectionRead[]>();
  for (const definition of REPORT_GROUP_DEFINITIONS) {
    projectionsByStatus.set(definition.key, []);
  }
  for (const projection of projections) {
    const bucket = projectionsByStatus.get(projection.status_group) ?? [];
    bucket.push(projection);
    projectionsByStatus.set(projection.status_group, bucket);
  }

  reportsRoot.children = reportsRoot.children.filter((child) => child.type !== "report_ref");

  const groups = REPORT_GROUP_DEFINITIONS.map((definition, index) => {
    const groupPath = `${reportsRoot.path}/${definition.label}`;
    const group: WikiTreeNodeRecord = {
      id: -1000 - index,
      space_id: reportsRoot.space_id,
      parent_id: reportsRoot.id,
      type: "folder",
      name: definition.label,
      path: groupPath,
      system_role: "report_group",
      sort_order: definition.sortOrder,
      created_at: reportsRoot.created_at,
      updated_at: reportsRoot.updated_at,
      children: [],
    };

    for (const projection of projectionsByStatus.get(definition.key) ?? []) {
      const node =
        byId.get(projection.node_id) ??
        ({
          id: projection.node_id,
          space_id: reportsRoot.space_id,
          feature_id: projection.feature_id,
          parent_id: group.id,
          type: "report_ref",
          name: projection.title,
          path: `${group.path}/${projection.title}`,
          system_role: null,
          sort_order: group.children.length,
          created_at: projection.updated_at,
          updated_at: projection.updated_at,
          children: [],
        } satisfies WikiTreeNodeRecord);
      if (node) {
        node.parent_id = group.id;
        node.path = `${group.path}/${node.name}`;
        group.children.push(node);
      }
    }

    return group;
  });

  reportsRoot.children.push(...groups);
  sortTree(reportsRoot.children);
  return tree;
}

export function groupWikiSearchHits(hits: WikiSearchHitRead[]): WikiSearchHitGroup[] {
  const groups = new Map<string, WikiSearchHitGroup>();
  for (const hit of hits) {
    const existing = groups.get(hit.group_key);
    if (existing) {
      existing.items.push(hit);
      continue;
    }
    groups.set(hit.group_key, {
      key: hit.group_key,
      label: hit.group_label,
      items: [hit],
    });
  }
  return Array.from(groups.values()).sort((left, right) => {
    const leftOrder = SEARCH_GROUP_ORDER.get(left.key) ?? Number.MAX_SAFE_INTEGER;
    const rightOrder = SEARCH_GROUP_ORDER.get(right.key) ?? Number.MAX_SAFE_INTEGER;
    if (leftOrder !== rightOrder) {
      return leftOrder - rightOrder;
    }
    return left.label.localeCompare(right.label, "zh-CN");
  });
}

function cloneTree(roots: WikiTreeNodeRecord[]): WikiTreeNodeRecord[] {
  return roots.map((node) => ({
    ...node,
    children: cloneTree(node.children),
  }));
}

function indexTree(roots: WikiTreeNodeRecord[], byId: Map<number, WikiTreeNodeRecord>) {
  for (const node of roots) {
    byId.set(node.id, node);
    indexTree(node.children, byId);
  }
}

function sortTree(nodes: WikiTreeNodeRecord[]) {
  nodes.sort((left, right) => {
    if (left.sort_order !== right.sort_order) {
      return left.sort_order - right.sort_order;
    }
    return left.path.localeCompare(right.path);
  });
  for (const node of nodes) {
    sortTree(node.children);
  }
}

function findReportsRoot(
  roots: WikiTreeNodeRecord[],
  featureId?: number | null,
): WikiTreeNodeRecord | null {
  for (const node of roots) {
    if (
      node.system_role === "reports" &&
      (featureId == null || node.feature_id === featureId)
    ) {
      return node;
    }
    const child = findReportsRoot(node.children, featureId);
    if (child) {
      return child;
    }
  }
  return null;
}
