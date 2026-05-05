import { useEffect, useMemo, useRef, useState, type CSSProperties, type MouseEvent as ReactMouseEvent } from "react";

export function useWikiTreeLayout(mode: "view" | "edit") {
  const [treeCollapsed, setTreeCollapsed] = useState(mode === "edit");
  const [treeWidth, setTreeWidth] = useState(328);
  const treeCollapsedBeforeEditRef = useRef<boolean | null>(null);
  const treeModeRef = useRef(mode);

  useEffect(() => {
    const enteringEdit = mode === "edit" && treeModeRef.current !== "edit";
    const leavingEdit = mode !== "edit" && treeModeRef.current === "edit";

    if (enteringEdit) {
      treeCollapsedBeforeEditRef.current = treeCollapsed;
      setTreeCollapsed(true);
    } else if (leavingEdit) {
      if (treeCollapsedBeforeEditRef.current != null) {
        setTreeCollapsed(treeCollapsedBeforeEditRef.current);
      }
      treeCollapsedBeforeEditRef.current = null;
    }

    treeModeRef.current = mode;
  }, [mode, treeCollapsed]);

  function startTreeResize(
    event: ReactMouseEvent<HTMLButtonElement>,
    options?: { onClick?: () => void },
  ) {
    event.preventDefault();
    const doc = event.currentTarget.ownerDocument;
    const startX = event.clientX;
    const startWidth = treeWidth;
    let moved = false;
    doc.body.style.userSelect = "none";

    function resizeFromClientX(clientX: number) {
      const delta = clientX - startX;
      if (Math.abs(delta) >= 3) {
        moved = true;
      }
      const nextWidth = Math.min(520, Math.max(280, startWidth + delta));
      setTreeWidth(nextWidth);
    }

    function onMouseMove(nextEvent: MouseEvent) {
      resizeFromClientX(nextEvent.clientX);
    }

    function teardown() {
      doc.body.style.userSelect = "";
      doc.removeEventListener("mousemove", onMouseMove);
      doc.removeEventListener("mouseup", onMouseUp);
    }

    function onMouseUp() {
      if (!moved) {
        options?.onClick?.();
      }
      teardown();
    }

    doc.addEventListener("mousemove", onMouseMove);
    doc.addEventListener("mouseup", onMouseUp, { once: true });
  }

  const workspaceStyle = useMemo(
    () =>
      ({
        "--wiki-tree-width": treeCollapsed ? "52px" : `${treeWidth}px`,
      }) as CSSProperties,
    [treeCollapsed, treeWidth],
  );

  return {
    treeCollapsed,
    setTreeCollapsed,
    startTreeResize,
    workspaceStyle,
  };
}
