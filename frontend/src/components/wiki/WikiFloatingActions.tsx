import {
  Clock3,
  FilePenLine,
  Info,
  Link2,
  MoreHorizontal,
  Orbit,
  Upload,
} from "lucide-react";
import { createPortal } from "react-dom";
import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { Button } from "../ui/button";

export function WikiFloatingActions({
  canEdit,
  onCopyLink,
  onEdit,
  onOpenDetail,
  onOpenHistory,
  onOpenImport,
  onOpenSources,
}: {
  canEdit: boolean;
  onCopyLink: () => void;
  onEdit: () => void;
  onOpenDetail: () => void;
  onOpenHistory: () => void;
  onOpenImport: () => void;
  onOpenSources: () => void;
}) {
  const [moreOpen, setMoreOpen] = useState(false);
  const [morePosition, setMorePosition] = useState({ left: 0, top: 0 });
  const moreButtonRef = useRef<HTMLButtonElement | null>(null);
  const moreMenuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!moreOpen) {
      return;
    }
    function onPointerDown(event: PointerEvent) {
      const target = event.target as Node;
      if (
        moreMenuRef.current?.contains(target) ||
        moreButtonRef.current?.contains(target)
      ) {
        return;
      }
      setMoreOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [moreOpen]);

  useLayoutEffect(() => {
    if (!moreOpen || !moreButtonRef.current) {
      return;
    }

    function updatePosition() {
      const rect = moreButtonRef.current?.getBoundingClientRect();
      if (!rect) {
        return;
      }
      setMorePosition({
        left: Math.max(8, rect.right - 196),
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
  }, [moreOpen]);

  return (
    <div className="wiki-floating-actions">
      <Button icon={<Info size={15} />} onClick={onOpenDetail} type="button" variant="secondary">
        详情
      </Button>
      <Button
        icon={<Link2 size={15} />}
        onClick={onCopyLink}
        type="button"
        variant="secondary"
      >
        复制链接
      </Button>
      {canEdit ? (
        <Button
          icon={<FilePenLine size={15} />}
          onClick={onEdit}
          type="button"
          variant="primary"
        >
          编辑
        </Button>
      ) : null}
      <button
        aria-haspopup="menu"
        aria-expanded={moreOpen}
        aria-label="更多"
        className="button button-secondary wiki-more-button"
        onClick={() => setMoreOpen((value) => !value)}
        ref={moreButtonRef}
        type="button"
      >
        <span className="button-icon" aria-hidden="true">
          <MoreHorizontal size={15} />
        </span>
        更多
      </button>
      {moreOpen
        ? createPortal(
            <div className="row-menu wiki-floating-menu" ref={moreMenuRef} role="menu" style={morePosition}>
              <button
                onClick={() => {
                  setMoreOpen(false);
                  onOpenSources();
                }}
                role="menuitem"
                type="button"
              >
                <Orbit aria-hidden="true" size={15} />
                来源治理
              </button>
              <button
                onClick={() => {
                  setMoreOpen(false);
                  onOpenHistory();
                }}
                role="menuitem"
                type="button"
              >
                <Clock3 aria-hidden="true" size={15} />
                历史版本
              </button>
              {canEdit ? (
                <button
                  onClick={() => {
                    setMoreOpen(false);
                    onOpenImport();
                  }}
                  role="menuitem"
                  type="button"
                >
                  <Upload aria-hidden="true" size={15} />
                  导入
                </button>
              ) : null}
            </div>,
            document.body,
          )
        : null}
    </div>
  );
}
