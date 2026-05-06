import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  ArrowDown,
  ArrowUp,
  FilePlus2,
  FolderPlus,
  FolderUp,
  MoreHorizontal,
  Pencil,
  RefreshCw,
  RotateCcw,
  Trash2,
} from "lucide-react";

import type { WikiTreeNodeRecord } from "../../lib/wiki/tree";
import {
  canCreateChildrenInWikiNode,
  canDeleteWikiNode,
  canReindexWikiNode,
  canRenameWikiNode,
  canRestoreArchivedWikiSpace,
} from "../../lib/wiki/system-node-actions";

export function WikiNodeMenu({
  canManage,
  canRestoreArchivedSpace,
  canMoveDown,
  canMoveUp,
  node,
  onCreateDocument,
  onCreateFolder,
  onDelete,
  onImport,
  onMoveDown,
  onMoveUp,
  onReindex,
  onRename,
  onRestoreArchivedSpace,
}: {
  canManage: boolean;
  canRestoreArchivedSpace?: boolean;
  canMoveDown?: boolean;
  canMoveUp?: boolean;
  node: WikiTreeNodeRecord;
  onCreateDocument: (node: WikiTreeNodeRecord) => void;
  onCreateFolder: (node: WikiTreeNodeRecord) => void;
  onDelete: (node: WikiTreeNodeRecord) => void;
  onImport: (node: WikiTreeNodeRecord) => void;
  onMoveDown?: (node: WikiTreeNodeRecord) => void;
  onMoveUp?: (node: WikiTreeNodeRecord) => void;
  onReindex?: (node: WikiTreeNodeRecord) => void;
  onRename: (node: WikiTreeNodeRecord) => void;
  onRestoreArchivedSpace?: (node: WikiTreeNodeRecord) => void;
}) {
  const allowCreateChildren = canCreateChildrenInWikiNode(node);
  const allowRename = canRenameWikiNode(node);
  const allowDelete = canDeleteWikiNode(node);
  const allowReindex = canReindexWikiNode(node) && onReindex != null;
  const allowRestoreArchivedSpace =
    Boolean(canRestoreArchivedSpace) &&
    canRestoreArchivedWikiSpace(node) &&
    onRestoreArchivedSpace != null;
  const allowMoveUp = Boolean(canMoveUp && onMoveUp);
  const allowMoveDown = Boolean(canMoveDown && onMoveDown);
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

  if (
    !canManage ||
    (!allowCreateChildren &&
      !allowRename &&
      !allowDelete &&
      !allowMoveUp &&
      !allowMoveDown &&
      !allowReindex &&
      !allowRestoreArchivedSpace)
  ) {
    return null;
  }

  const menu = open ? (
    <div className="row-menu" ref={menuRef} role="menu" style={position}>
      {allowMoveUp ? (
        <button
          onClick={() => {
            setOpen(false);
            onMoveUp?.(node);
          }}
          role="menuitem"
          type="button"
        >
          <ArrowUp aria-hidden="true" size={15} />
          上移
        </button>
      ) : null}
      {allowMoveDown ? (
        <button
          onClick={() => {
            setOpen(false);
            onMoveDown?.(node);
          }}
          role="menuitem"
          type="button"
        >
          <ArrowDown aria-hidden="true" size={15} />
          下移
        </button>
      ) : null}
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
              onImport(node);
            }}
            role="menuitem"
            type="button"
          >
            <FolderUp aria-hidden="true" size={15} />
            导入 Wiki
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
      {allowRestoreArchivedSpace ? (
        <button
          onClick={() => {
            setOpen(false);
            onRestoreArchivedSpace?.(node);
          }}
          role="menuitem"
          type="button"
        >
          <RotateCcw aria-hidden="true" size={15} />
          恢复特性
        </button>
      ) : null}
      {allowReindex ? (
        <button
          onClick={() => {
            setOpen(false);
            onReindex?.(node);
          }}
          role="menuitem"
          type="button"
        >
          <RefreshCw aria-hidden="true" size={15} />
          重新索引
        </button>
      ) : null}
      {allowRename || allowDelete ? (
        <>
          {allowRename ? (
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
          ) : null}
          {allowDelete ? (
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
          ) : null}
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
