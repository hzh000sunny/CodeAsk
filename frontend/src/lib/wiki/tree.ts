import type { WikiNodeRead } from "../../types/wiki";

export interface WikiTreeNodeRecord extends WikiNodeRead {
  children: WikiTreeNodeRecord[];
}

const STORED_PATH_ROOT_LABELS = new Map<string, string>([
  ["knowledge-base", "知识库"],
  ["reports", "问题定位报告"],
]);

export function buildWikiTree(nodes: WikiNodeRead[]): WikiTreeNodeRecord[] {
  const byId = new Map<number, WikiTreeNodeRecord>();
  const roots: WikiTreeNodeRecord[] = [];
  for (const node of nodes) {
    byId.set(node.id, {
      ...node,
      children: [],
    });
  }
  for (const node of byId.values()) {
    if (node.parent_id == null) {
      roots.push(node);
      continue;
    }
    const parent = byId.get(node.parent_id);
    if (parent) {
      parent.children.push(node);
    } else {
      roots.push(node);
    }
  }
  sortTree(roots);
  return roots;
}

export function findFirstReadableDocument(
  roots: WikiTreeNodeRecord[],
): WikiTreeNodeRecord | null {
  const knowledgeRoot =
    roots.find((node) => node.system_role === "knowledge_base") ?? roots[0] ?? null;
  if (!knowledgeRoot) {
    return null;
  }
  const fromKnowledge = findFirstDocumentInSubtree(knowledgeRoot);
  if (fromKnowledge) {
    return fromKnowledge;
  }
  for (const root of roots) {
    const node = findFirstDocumentInSubtree(root);
    if (node) {
      return node;
    }
  }
  return null;
}

export function filterWikiTreeByQuery(
  roots: WikiTreeNodeRecord[],
  query: string,
): WikiTreeNodeRecord[] {
  const needle = query.trim().toLowerCase();
  if (!needle) {
    return roots;
  }

  return roots
    .map((node) => filterNode(node, needle))
    .filter((node): node is WikiTreeNodeRecord => node != null);
}

export function flattenTree(roots: WikiTreeNodeRecord[]): WikiTreeNodeRecord[] {
  const values: WikiTreeNodeRecord[] = [];
  for (const root of roots) {
    values.push(root);
    values.push(...flattenTree(root.children));
  }
  return values;
}

export function findNodeById(
  roots: WikiTreeNodeRecord[],
  nodeId: number | null,
): WikiTreeNodeRecord | null {
  if (nodeId == null) {
    return null;
  }
  for (const node of flattenTree(roots)) {
    if (node.id === nodeId) {
      return node;
    }
  }
  return null;
}

export function buildWikiNodeDisplayPath(
  roots: WikiTreeNodeRecord[],
  nodeId: number | null,
): string | null {
  if (nodeId == null) {
    return null;
  }
  const chain = findNodeChain(roots, nodeId);
  if (chain == null) {
    return null;
  }
  const visibleNames = chain
    .filter((node) => !isSyntheticNode(node.system_role))
    .map((node) => node.name.trim())
    .filter(Boolean);
  if (visibleNames.length > 0) {
    return visibleNames.join(" / ");
  }
  const terminalName = chain[chain.length - 1]?.name.trim();
  return terminalName || null;
}

export function formatWikiStoredPath(path: string | null | undefined): string | null {
  const normalized = path?.trim();
  if (!normalized) {
    return null;
  }
  const segments = normalized
    .split("/")
    .map((segment) => segment.trim())
    .filter(Boolean);
  if (segments.length === 0) {
    return null;
  }
  return segments
    .map((segment, index) =>
      index === 0 ? (STORED_PATH_ROOT_LABELS.get(segment) ?? segment) : segment,
    )
    .join(" / ");
}

export function formatWikiPathMentions(message: string | null | undefined): string {
  if (!message) {
    return "";
  }
  return message.replace(/\b(?:knowledge-base|reports)(?:\/[^\s"'<>()[\],:;]+)*/g, (match) => {
    return formatWikiStoredPath(match) ?? match;
  });
}

export function findFirstDocumentInSubtree(
  node: WikiTreeNodeRecord,
): WikiTreeNodeRecord | null {
  if (node.type === "document") {
    return node;
  }
  for (const child of node.children) {
    const match = findFirstDocumentInSubtree(child);
    if (match) {
      return match;
    }
  }
  return null;
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

function findNodeChain(
  roots: WikiTreeNodeRecord[],
  nodeId: number,
): WikiTreeNodeRecord[] | null {
  for (const root of roots) {
    const chain = findNodeChainInSubtree(root, nodeId);
    if (chain) {
      return chain;
    }
  }
  return null;
}

function findNodeChainInSubtree(
  node: WikiTreeNodeRecord,
  nodeId: number,
): WikiTreeNodeRecord[] | null {
  if (node.id === nodeId) {
    return [node];
  }
  for (const child of node.children) {
    const chain = findNodeChainInSubtree(child, nodeId);
    if (chain) {
      return [node, ...chain];
    }
  }
  return null;
}

function isSyntheticNode(systemRole: string | null) {
  return (
    systemRole === "feature_group_current" ||
    systemRole === "feature_group_history" ||
    systemRole === "feature_space_current" ||
    systemRole === "feature_space_history"
  );
}

function filterNode(
  node: WikiTreeNodeRecord,
  needle: string,
): WikiTreeNodeRecord | null {
  const haystack = `${node.name} ${node.path}`.toLowerCase();
  if (haystack.includes(needle)) {
    return cloneSubtree(node);
  }

  const children = node.children
    .map((child) => filterNode(child, needle))
    .filter((child): child is WikiTreeNodeRecord => child != null);
  if (children.length === 0) {
    return null;
  }

  return {
    ...node,
    children,
  };
}

function cloneSubtree(node: WikiTreeNodeRecord): WikiTreeNodeRecord {
  return {
    ...node,
    children: node.children.map((child) => cloneSubtree(child)),
  };
}
