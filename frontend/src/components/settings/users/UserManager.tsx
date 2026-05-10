import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Search, UsersRound } from "lucide-react";

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

  return (
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
      {trimmed && usersQuery.data?.length === 0 ? (
        <div className="empty-block wide">
          <p>没有匹配的用户。</p>
        </div>
      ) : null}
      {usersQuery.data?.length ? (
        <ul className="data-list settings-config-list">
          {usersQuery.data.map((user) => (
            <li key={user.id}>
              <div className="config-summary">
                <span>{user.username}</span>
                <small>{user.id}</small>
              </div>
              <div className="row-actions">
                <Button
                  disabled={clearMutation.isPending}
                  icon={<KeyRound aria-hidden="true" size={15} />}
                  onClick={() => clearMutation.mutate(user.id)}
                  type="button"
                  variant="secondary"
                >
                  清空密码
                </Button>
              </div>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
