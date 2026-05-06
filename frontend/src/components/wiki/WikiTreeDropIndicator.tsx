import type { DragEvent as ReactDragEvent } from "react";

export function WikiTreeDropIndicator({
  active,
  nodeId,
  onDragOver,
  onDrop,
  position,
}: {
  active: boolean;
  nodeId: number;
  onDragOver: (event: ReactDragEvent<HTMLDivElement>) => void;
  onDrop: (event: ReactDragEvent<HTMLDivElement>) => void;
  position: "before" | "after";
}) {
  return (
    <div
      className="wiki-tree-drop-indicator"
      data-active={active}
      data-drop-zone={position}
      data-node-id={nodeId}
      onDragOver={onDragOver}
      onDrop={onDrop}
      role="presentation"
    />
  );
}
