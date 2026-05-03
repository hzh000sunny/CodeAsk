import { useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  ListChecks,
  MoreHorizontal,
  Pencil,
  Pin,
  Share2,
  Trash2,
} from "lucide-react";

import type { SessionResponse } from "../../types/api";

export function SessionListItem({
  active,
  bulkMode,
  checked,
  menuOpen,
  onClick,
  onDelete,
  onMenuToggle,
  onRename,
  onShare,
  onToggleBulkMode,
  onTogglePin,
  onToggleSelect,
  pendingDelete,
  session,
}: {
  active: boolean;
  bulkMode: boolean;
  checked: boolean;
  menuOpen: boolean;
  onClick: () => void;
  onDelete: () => void;
  onMenuToggle: () => void;
  onRename: () => void;
  onShare: () => void;
  onToggleBulkMode: () => void;
  onTogglePin: () => void;
  onToggleSelect: () => void;
  pendingDelete: boolean;
  session: SessionResponse;
}) {
  const menuButtonRef = useRef<HTMLButtonElement | null>(null);
  const [menuPosition, setMenuPosition] = useState({ left: 0, top: 0 });

  useLayoutEffect(() => {
    if (!menuOpen || !menuButtonRef.current) {
      return;
    }

    function updatePosition() {
      const rect = menuButtonRef.current?.getBoundingClientRect();
      if (!rect) {
        return;
      }
      setMenuPosition({
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
  }, [menuOpen]);

  const menu = menuOpen ? (
    <div
      className="row-menu"
      role="menu"
      style={{ left: menuPosition.left, top: menuPosition.top }}
    >
      <button onClick={onRename} role="menuitem" type="button">
        <Pencil aria-hidden="true" size={15} />
        编辑名称
      </button>
      <button onClick={onShare} role="menuitem" type="button">
        <Share2 aria-hidden="true" size={15} />
        分享
      </button>
      <button onClick={onTogglePin} role="menuitem" type="button">
        <Pin aria-hidden="true" size={15} />
        {session.pinned ? "取消置顶" : "置顶"}
      </button>
      <button onClick={onToggleBulkMode} role="menuitem" type="button">
        <ListChecks aria-hidden="true" size={15} />
        批量操作
      </button>
      <button
        className="danger"
        onClick={onDelete}
        role="menuitem"
        type="button"
      >
        <Trash2 aria-hidden="true" size={15} />
        删除
      </button>
    </div>
  ) : null;

  return (
    <div className="list-row" data-active={active}>
      {bulkMode ? (
        <label className="row-checkbox">
          <input checked={checked} onChange={onToggleSelect} type="checkbox" />
        </label>
      ) : null}
      <button
        aria-label={session.title}
        className="list-item"
        data-active={active}
        onClick={onClick}
        type="button"
      >
        <span className="item-title">
          {session.pinned ? <Pin aria-hidden="true" size={13} /> : null}
          {session.title}
        </span>
        <span className="item-meta">
          {new Date(session.updated_at).toLocaleString()}
        </span>
      </button>
      <button
        aria-label={`打开会话 ${session.title} 的更多操作`}
        className="list-menu-button"
        disabled={pendingDelete}
        onClick={onMenuToggle}
        ref={menuButtonRef}
        title="更多操作"
        type="button"
      >
        <MoreHorizontal aria-hidden="true" size={16} />
      </button>
      {menu ? createPortal(menu, document.body) : null}
    </div>
  );
}
