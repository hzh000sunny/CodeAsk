import type { WikiNodeRead } from "../../types/wiki";

export interface WikiTreeNodeRecord extends WikiNodeRead {
  children: WikiTreeNodeRecord[];
}

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
