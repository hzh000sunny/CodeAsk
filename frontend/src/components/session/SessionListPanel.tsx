import { ChevronLeft, ChevronRight, Plus, Search } from "lucide-react";

import type { SessionResponse } from "../../types/api";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { SessionListItem } from "./SessionListItem";

export function SessionListPanel({
  bulkMode,
  bulkSelectedIds,
  createPending,
  deleteError,
  isLoading,
  listCollapsed,
  menuSessionId,
  onCancelBulkMode,
  onCreateSession,
  onDelete,
  onMenuToggle,
  onQueryChange,
  onRename,
  onSelect,
  onShare,
  onToggleBulkMode,
  onToggleCollapsed,
  onTogglePin,
  onToggleSelect,
  onConfirmBulkDelete,
  pendingDelete,
  query,
  selectedSessionId,
  visibleSessions,
}: {
  bulkMode: boolean;
  bulkSelectedIds: string[];
  createPending: boolean;
  deleteError: string;
  isLoading: boolean;
  listCollapsed: boolean;
  menuSessionId: string | null;
  onCancelBulkMode: () => void;
  onCreateSession: () => void;
  onDelete: (session: SessionResponse) => void;
  onMenuToggle: (sessionId: string) => void;
  onQueryChange: (value: string) => void;
  onRename: (session: SessionResponse) => void;
  onSelect: (sessionId: string) => void;
  onShare: () => void;
  onToggleBulkMode: (sessionId: string) => void;
  onToggleCollapsed: () => void;
  onTogglePin: (session: SessionResponse) => void;
  onToggleSelect: (sessionId: string) => void;
  onConfirmBulkDelete: () => void;
  pendingDelete: boolean;
  query: string;
  selectedSessionId: string | null;
  visibleSessions: SessionResponse[];
}) {
  return (
    <aside
      className="list-panel"
      data-collapsed={listCollapsed}
      role="region"
      aria-label="会话列表"
    >
      <button
        aria-label={listCollapsed ? "展开会话列表" : "收起会话列表"}
        className="edge-collapse-button secondary"
        data-collapsed={listCollapsed}
        onClick={onToggleCollapsed}
        title={listCollapsed ? "展开会话列表" : "收起会话列表"}
        type="button"
      >
        {listCollapsed ? (
          <ChevronRight aria-hidden="true" size={15} />
        ) : (
          <ChevronLeft aria-hidden="true" size={15} />
        )}
      </button>
      {listCollapsed ? (
        <div className="collapsed-panel-label">会话</div>
      ) : (
        <>
          <div className="list-toolbar">
            <label className="search-field">
              <Search aria-hidden="true" size={16} />
              <Input
                aria-label="搜索会话"
                onChange={(event) => onQueryChange(event.target.value)}
                placeholder="搜索会话"
                value={query}
              />
            </label>
            <Button
              aria-label="新建会话"
              className="icon-only"
              disabled={createPending}
              icon={<Plus size={17} />}
              onClick={onCreateSession}
              title="新建会话"
              type="button"
            />
          </div>
          {bulkMode ? (
            <div className="bulk-toolbar">
              <span>已选择 {bulkSelectedIds.length} 个</span>
              <div className="row-actions">
                <Button
                  disabled={bulkSelectedIds.length === 0}
                  onClick={onConfirmBulkDelete}
                  type="button"
                  variant="danger"
                >
                  批量删除
                </Button>
                <Button onClick={onCancelBulkMode} type="button" variant="secondary">
                  取消
                </Button>
              </div>
            </div>
          ) : null}
          {deleteError ? (
            <div className="inline-alert danger" role="alert">
              {deleteError}
            </div>
          ) : null}

          <div className="list-scroll">
            {isLoading ? <p className="empty-note">正在加载会话</p> : null}
            {!isLoading && visibleSessions.length === 0 ? (
              <div className="empty-block">
                <p>暂无会话</p>
                <span>点击右上角加号创建一次新的研发问答。</span>
              </div>
            ) : null}
            {visibleSessions.map((session) => (
              <SessionListItem
                active={selectedSessionId === session.id}
                bulkMode={bulkMode}
                checked={bulkSelectedIds.includes(session.id)}
                key={session.id}
                onClick={() => onSelect(session.id)}
                onDelete={() => onDelete(session)}
                onMenuToggle={() => onMenuToggle(session.id)}
                onRename={() => onRename(session)}
                onShare={onShare}
                onToggleBulkMode={() => onToggleBulkMode(session.id)}
                onTogglePin={() => onTogglePin(session)}
                onToggleSelect={() => onToggleSelect(session.id)}
                menuOpen={menuSessionId === session.id}
                pendingDelete={pendingDelete}
                session={session}
              />
            ))}
          </div>
        </>
      )}
    </aside>
  );
}
