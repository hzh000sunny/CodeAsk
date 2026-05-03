import type { SessionResponse } from "../../types/api";
import { Badge } from "../ui/badge";
import { formatSessionIdPreview } from "./session-clipboard";

export function SessionHeader({
  copiedSessionId,
  onCopySessionId,
  selected,
}: {
  copiedSessionId: string | null;
  onCopySessionId: () => void;
  selected: SessionResponse | null;
}) {
  return (
    <div className="page-header compact">
      <div>
        <div className="session-title-row">
          <h1>{selected?.title ?? "新会话"}</h1>
          {selected ? (
            <button
              aria-label={`复制完整会话 ID ${selected.id}`}
              className="session-id-pill"
              onClick={onCopySessionId}
              title={`点击复制完整会话 ID：${selected.id}`}
              type="button"
            >
              <span>{formatSessionIdPreview(selected.id)}</span>
              {copiedSessionId === selected.id ? (
                <span className="session-copy-popover" role="status">
                  复制成功
                </span>
              ) : null}
            </button>
          ) : null}
        </div>
        <p>上传日志、绑定特性和仓库后，CodeAsk 会按阶段给出证据化回答。</p>
      </div>
      <div className="header-actions">
        <Badge>{selected?.status ?? "ready"}</Badge>
      </div>
    </div>
  );
}
