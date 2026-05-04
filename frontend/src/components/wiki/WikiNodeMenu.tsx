import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  FilePlus2,
  FolderPlus,
  MoreHorizontal,
  Pencil,
  Trash2,
} from "lucide-react";

import type { WikiTreeNodeRecord } from "../../lib/wiki/tree";

function canCreateChildren(node: WikiTreeNodeRecord) {
  return node.type === "folder" && !node.path.startsWith("问题定位报告");
}

function canMutateNode(node: WikiTreeNodeRecord) {
  return node.system_role == null && (node.type === "folder" || node.type === "document");
}

export function WikiNodeMenu({
  canManage,
  node,
  onCreateDocument,
  onCreateFolder,
  onDelete,
  onRename,
}: {
  canManage: boolean;
  node: WikiTreeNodeRecord;
  onCreateDocument: (node: WikiTreeNodeRecord) => void;
  onCreateFolder: (node: WikiTreeNodeRecord) => void;
  onDelete: (node: WikiTreeNodeRecord) => void;
  onRename: (node: WikiTreeNodeRecord) => void;
}) {
  const allowCreateChildren = canCreateChildren(node);
  const allowMutate = canMutateNode(node);
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ left: 0, top: 0 });
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    function onPointerDown(event: PointerEvent) {
      const target = event.target as Node;
      if (menuRef.current?.contains(target) || buttonRef.current?.contains(target)) {
        return;
      }
      setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  useLayoutEffect(() => {
    if (!open || !buttonRef.current) {
      return;
    }

    function updatePosition() {
      const rect = buttonRef.current?.getBoundingClientRect();
      if (!rect) {
        return;
      }
      setPosition({
        left: Math.max(8, rect.right - 166),
        top: rect.bottom + 6,
      });
    }

    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [open]);

  if (!canManage || (!allowCreateChildren && !allowMutate)) {
    return null;
  }

  const menu = open ? (
    <div className="row-menu" ref={menuRef} role="menu" style={position}>
      {allowCreateChildren ? (
        <>
          <button
            onClick={() => {
              setOpen(false);
              onCreateFolder(node);
            }}
            role="menuitem"
            type="button"
          >
            <FolderPlus aria-hidden="true" size={15} />
            新建目录
          </button>
          <button
            onClick={() => {
              setOpen(false);
              onCreateDocument(node);
            }}
            role="menuitem"
            type="button"
          >
            <FilePlus2 aria-hidden="true" size={15} />
            新建 Wiki
          </button>
        </>
      ) : null}
      {allowMutate ? (
        <>
          <button
            onClick={() => {
              setOpen(false);
              onRename(node);
            }}
            role="menuitem"
            type="button"
          >
            <Pencil aria-hidden="true" size={15} />
            重命名
          </button>
          <button
            className="danger"
            onClick={() => {
              setOpen(false);
              onDelete(node);
            }}
            role="menuitem"
            type="button"
          >
            <Trash2 aria-hidden="true" size={15} />
            删除
          </button>
        </>
      ) : null}
    </div>
  ) : null;

  return (
    <>
      <button
        aria-label={`打开节点 ${node.name} 的更多操作`}
        className="list-menu-button wiki-tree-menu-button"
        onClick={(event) => {
          event.stopPropagation();
          setOpen((value) => !value);
        }}
        ref={buttonRef}
        type="button"
      >
        <MoreHorizontal aria-hidden="true" size={15} />
      </button>
      {menu ? createPortal(menu, document.body) : null}
    </>
  );
}
