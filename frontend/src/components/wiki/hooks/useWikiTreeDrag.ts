import type { DragEvent as ReactDragEvent } from "react";
import { useMemo, useState } from "react";

import type { WikiMoveNodePayload } from "../../../types/wiki";
import { flattenTree, type WikiTreeNodeRecord } from "../../../lib/wiki/tree";
import { buildDropMovePayload, canMoveWikiNode } from "../../../lib/wiki/tree-ordering";

type DropPosition = "before" | "inside" | "after";

export function useWikiTreeDrag({
  onMoveNodeRequest,
  roots,
}: {
  onMoveNodeRequest?: (node: WikiTreeNodeRecord, payload: WikiMoveNodePayload) => void;
  roots: WikiTreeNodeRecord[];
}) {
  const [draggedNodeId, setDraggedNodeId] = useState<number | null>(null);
  const [dropTarget, setDropTarget] = useState<{ nodeId: number; position: DropPosition } | null>(
    null,
  );

  const flatNodes = useMemo(() => flattenTree(roots), [roots]);

  function handleDragStart(node: WikiTreeNodeRecord) {
    if (!canMoveWikiNode(node)) {
      return;
    }
    setDraggedNodeId(node.id);
  }

  function handleDragEnd() {
    setDraggedNodeId(null);
    setDropTarget(null);
  }

  function handleDragOver(
    targetNode: WikiTreeNodeRecord,
    position: DropPosition,
    event: ReactDragEvent<HTMLElement>,
  ) {
    if (draggedNodeId == null) {
      return;
    }
    const payload = buildDropMovePayload(roots, {
      draggedNodeId,
      targetNodeId: targetNode.id,
      position,
    });
    if (!payload) {
      return;
    }
    event.preventDefault();
    setDropTarget({ nodeId: targetNode.id, position });
  }

  function handleDrop(
    targetNode: WikiTreeNodeRecord,
    position: DropPosition,
    event: ReactDragEvent<HTMLElement>,
  ) {
    if (draggedNodeId == null || !onMoveNodeRequest) {
      handleDragEnd();
      return;
    }
    const payload = buildDropMovePayload(roots, {
      draggedNodeId,
      targetNodeId: targetNode.id,
      position,
    });
    event.preventDefault();
    if (!payload) {
      handleDragEnd();
      return;
    }
    const draggedNode = flatNodes.find((node) => node.id === draggedNodeId) ?? null;
    if (draggedNode) {
      onMoveNodeRequest(draggedNode, payload);
    }
    handleDragEnd();
  }

  return {
    draggedNodeId,
    dropTarget,
    handleDragEnd,
    handleDragOver,
    handleDragStart,
    handleDrop,
  };
}
