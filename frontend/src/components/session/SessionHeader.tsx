import type { SessionResponse } from "../../types/api";
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
    <div className="page-header compact session-header">
      <div className="session-header-main">
        <div className="session-title-row">
          <h1 title={selected?.title ?? undefined}>
            {selected?.title ?? "新会话"}
          </h1>
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
        <p className="session-header-description">
          描述你遇到的问题，或粘贴关键日志片段。CodeAsk
          会检索 Wiki、问题报告与代码仓库，并把调查过程实时展示在这里。
        </p>
      </div>
    </div>
  );
}
