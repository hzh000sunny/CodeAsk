import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Info, KeyRound, Search, SearchX, UsersRound } from "lucide-react";

import { clearUserPassword, searchUsers } from "../../../lib/api";
import { useAppFeedback } from "../../feedback/AppFeedback";
import { Button } from "../../ui/button";
import { Input } from "../../ui/input";
import { messageFromApiError } from "../settings-utils";

export function UserManager() {
  const queryClient = useQueryClient();
  const { showError, showSuccess } = useAppFeedback();
  const [query, setQuery] = useState("");
  const trimmed = query.trim();
  const usersQuery = useQuery({
    queryKey: ["users", "search", trimmed],
    queryFn: () => searchUsers(trimmed, 12),
    enabled: trimmed.length > 0,
  });
  const clearMutation = useMutation({
    mutationFn: clearUserPassword,
    onSuccess: () => {
      showSuccess("用户密码记录已清空");
      void queryClient.invalidateQueries({ queryKey: ["users", "search"] });
    },
    onError: (error) => showError(`清空密码失败：${messageFromApiError(error)}`),
  });

  const hits = usersQuery.data ?? [];

  return (
    <div className="console-stack">
      <section className="surface">
        <div className="section-title">
          <UsersRound aria-hidden="true" size={18} />
          <h2>用户管理</h2>
        </div>
        <label className="search-field settings-user-search">
          <Search aria-hidden="true" size={16} />
          <Input
            aria-label="搜索用户"
            onChange={(event) => setQuery(event.target.value)}
            placeholder="输入用户名"
            value={query}
          />
        </label>

        {!trimmed ? (
          <div className="console-status-line" data-tone="muted">
            <Info aria-hidden="true" size={15} />
            <span>输入用户名搜索，可查看其 ID 并清空密码记录。</span>
          </div>
        ) : usersQuery.isFetching ? (
          <p className="empty-note">正在搜索用户…</p>
        ) : hits.length ? (
          <>
            <p className="console-hit-count">命中 {hits.length} 个用户</p>
            <ul className="console-user-list">
              {hits.map((user) => (
                <li key={user.id}>
                  <span className="user-cell">
                    <span aria-hidden="true" className="user-avatar">
                      {monogram(user.username)}
                    </span>
                    <span className="user-meta">
                      <strong>{user.username}</strong>
                      <small className="console-mono">{user.id}</small>
                    </span>
                  </span>
                  <Button
                    disabled={clearMutation.isPending}
                    icon={<KeyRound aria-hidden="true" size={15} />}
                    onClick={() => clearMutation.mutate(user.id)}
                    type="button"
                    variant="secondary"
                  >
                    清空密码
                  </Button>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <div className="console-status-line" data-tone="muted">
            <SearchX aria-hidden="true" size={15} />
            <span>没有匹配「{trimmed}」的用户。</span>
          </div>
        )}
      </section>
    </div>
  );
}

// 用户名首字符作字母头像（中文取首字、英文取首字母大写）。
function monogram(username: string) {
  return [...username.trim()][0]?.toUpperCase() ?? "?";
}
