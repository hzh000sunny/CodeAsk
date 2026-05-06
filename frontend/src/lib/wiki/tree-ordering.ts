import type { WikiMoveNodePayload, WikiUpdateNodePayload } from "../../types/wiki";
import { flattenTree, type WikiTreeNodeRecord } from "./tree";

const MOVABLE_NODE_TYPES = new Set(["folder", "document"]);

export function canMoveWikiNode(node: WikiTreeNodeRecord) {
  return node.system_role == null && MOVABLE_NODE_TYPES.has(node.type);
}

export function getNodeMoveFlags(
  roots: WikiTreeNodeRecord[],
  nodeId: number,
): { canMoveUp: boolean; canMoveDown: boolean } {
  const context = findSiblingContext(roots, nodeId);
  if (!context || !canMoveWikiNode(context.node)) {
    return { canMoveUp: false, canMoveDown: false };
  }
  const previous = context.siblings[context.index - 1] ?? null;
  const next = context.siblings[context.index + 1] ?? null;
  return {
    canMoveUp: canReorderAcrossSibling(previous),
    canMoveDown: canReorderAcrossSibling(next),
  };
}

export function buildMoveUpPayload(
  roots: WikiTreeNodeRecord[],
  nodeId: number,
): WikiMoveNodePayload | null {
  const context = findSiblingContext(roots, nodeId);
  if (!context || context.index <= 0) {
    return null;
  }
  const previous = context.siblings[context.index - 1] ?? null;
  if (!canReorderAcrossSibling(previous)) {
    return null;
  }
  return {
    target_parent_id: context.node.parent_id,
    target_index: context.index - 1,
  };
}

export function buildMoveDownPayload(
  roots: WikiTreeNodeRecord[],
  nodeId: number,
): WikiMoveNodePayload | null {
  const context = findSiblingContext(roots, nodeId);
  if (!context || context.index < 0 || context.index >= context.siblings.length - 1) {
    return null;
  }
  const next = context.siblings[context.index + 1] ?? null;
  if (!canReorderAcrossSibling(next)) {
    return null;
  }
  return {
    target_parent_id: context.node.parent_id,
    target_index: context.index + 1,
  };
}

export function buildDropMovePayload(
  roots: WikiTreeNodeRecord[],
  payload: {
    draggedNodeId: number;
    targetNodeId: number;
    position: "before" | "inside" | "after";
  },
): WikiMoveNodePayload | null {
  const nodes = flattenTree(roots);
  const dragged = nodes.find((candidate) => candidate.id === payload.draggedNodeId) ?? null;
  const target = nodes.find((candidate) => candidate.id === payload.targetNodeId) ?? null;
  if (!dragged || !target || !canMoveWikiNode(dragged)) {
    return null;
  }
  if (dragged.id === target.id || target.path.startsWith(`${dragged.path}/`)) {
    return null;
  }

  if (payload.position === "inside") {
    if (!canAcceptDropInside(target)) {
      return null;
    }
    const childCount = nodes.filter((candidate) => candidate.parent_id === target.id).length;
    return {
      target_parent_id: target.id,
      target_index: childCount,
    };
  }

  if (!canMoveWikiNode(target)) {
    return null;
  }

  const siblings = nodes
    .filter((candidate) => candidate.parent_id === target.parent_id)
    .sort(compareNodesForOrder);
  const remaining = siblings.filter((candidate) => candidate.id !== dragged.id);
  const targetIndex = remaining.findIndex((candidate) => candidate.id === target.id);
  if (targetIndex < 0) {
    return null;
  }
  return {
    target_parent_id: target.parent_id,
    target_index: payload.position === "after" ? targetIndex + 1 : targetIndex,
  };
}

export function buildLegacyMoveUpdates(
  roots: WikiTreeNodeRecord[],
  payload: {
    draggedNodeId: number;
    target_parent_id: number | null;
    target_index: number;
  },
): Array<{ nodeId: number; update: WikiUpdateNodePayload }> {
  const nodes = flattenTree(roots);
  const dragged = nodes.find((candidate) => candidate.id === payload.draggedNodeId) ?? null;
  if (!dragged) {
    return [];
  }

  const currentParentId = dragged.parent_id;
  const targetParentId = payload.target_parent_id ?? null;

  if (currentParentId === targetParentId) {
    const siblings = nodes
      .filter((candidate) => candidate.parent_id === currentParentId && canMoveWikiNode(candidate))
      .sort(compareNodesForOrder);
    const reordered = siblings.filter((candidate) => candidate.id !== dragged.id);
    reordered.splice(clampIndex(payload.target_index, reordered.length), 0, dragged);
    return reordered.map((node, index) => ({
      nodeId: node.id,
      update: { sort_order: index },
    }));
  }

  const oldSiblings = nodes
    .filter((candidate) => candidate.parent_id === currentParentId && canMoveWikiNode(candidate))
    .sort(compareNodesForOrder)
    .filter((candidate) => candidate.id !== dragged.id);
  const newSiblings = nodes
    .filter((candidate) => candidate.parent_id === targetParentId && canMoveWikiNode(candidate))
    .sort(compareNodesForOrder)
    .filter((candidate) => candidate.id !== dragged.id);
  newSiblings.splice(clampIndex(payload.target_index, newSiblings.length), 0, dragged);

  return [
    ...oldSiblings.map((node, index) => ({
      nodeId: node.id,
      update: { sort_order: index },
    })),
    ...newSiblings.map((node, index) => ({
      nodeId: node.id,
      update:
        node.id === dragged.id
          ? {
              parent_id: targetParentId,
              sort_order: index,
            }
          : { sort_order: index },
    })),
  ];
}

function findSiblingContext(roots: WikiTreeNodeRecord[], nodeId: number) {
  const nodes = flattenTree(roots);
  const node = nodes.find((candidate) => candidate.id === nodeId);
  if (!node) {
    return null;
  }
  const siblings = nodes
    .filter((candidate) => candidate.parent_id === node.parent_id)
    .sort(compareNodesForOrder);
  const index = siblings.findIndex((candidate) => candidate.id === node.id);
  if (index < 0) {
    return null;
  }
  return { node, siblings, index };
}

function compareNodesForOrder(left: WikiTreeNodeRecord, right: WikiTreeNodeRecord) {
  if (left.sort_order !== right.sort_order) {
    return left.sort_order - right.sort_order;
  }
  if (left.path !== right.path) {
    return left.path.localeCompare(right.path);
  }
  return left.id - right.id;
}

function canReorderAcrossSibling(node: WikiTreeNodeRecord | null) {
  return node != null && canMoveWikiNode(node);
}

function canAcceptDropInside(node: WikiTreeNodeRecord) {
  if (node.type !== "folder") {
    return false;
  }
  return node.system_role == null || node.system_role === "knowledge_base";
}

function clampIndex(index: number, size: number) {
  if (index < 0) {
    return 0;
  }
  if (index > size) {
    return size;
  }
  return index;
}
