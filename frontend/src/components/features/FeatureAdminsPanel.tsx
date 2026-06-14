import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldCheck, Trash2, UserPlus } from "lucide-react";

import {
  addFeatureAdmin,
  listFeatureAdmins,
  searchFeatureAdminCandidates,
  removeFeatureAdmin,
} from "../../lib/api";
import { useAppFeedback } from "../feedback/AppFeedback";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { messageFromError } from "./feature-utils";
import { useFeaturePermissions } from "./useFeaturePermissions";

export function FeatureAdminsPanel({ featureId }: { featureId?: number }) {
  const queryClient = useQueryClient();
  const { showError, showSuccess } = useAppFeedback();
  const { isAdmin } = useFeaturePermissions(featureId);
  const [query, setQuery] = useState("");
  const adminsQueryKey = ["feature-admins", featureId] as const;
  const { data: admins = [], isLoading } = useQuery({
    queryKey: adminsQueryKey,
    queryFn: () => listFeatureAdmins(featureId as number),
    enabled: Boolean(featureId),
  });
  const candidateQuery = useQuery({
    queryKey: ["feature-admin-candidates", featureId, query.trim()],
    queryFn: () => searchFeatureAdminCandidates(featureId as number, query.trim()),
    enabled: Boolean(featureId && isAdmin && query.trim()),
  });
  const addMutation = useMutation({
    mutationFn: (userId: string) => addFeatureAdmin(featureId as number, userId),
    onSuccess: (created) => {
      queryClient.setQueryData<typeof admins>(adminsQueryKey, (current = []) => {
        if (current.some((item) => item.user_id === created.user_id)) {
          return current;
        }
        return [...current, created].sort((a, b) => a.username.localeCompare(b.username));
      });
      setQuery("");
      showSuccess("特性管理员已添加");
      void queryClient.invalidateQueries({ queryKey: adminsQueryKey });
      void queryClient.invalidateQueries({
        queryKey: ["feature-admin-candidates", featureId],
      });
    },
    onError: (error) => showError(`添加特性管理员失败：${messageFromError(error)}`),
  });
  const removeMutation = useMutation({
    mutationFn: (userId: string) => removeFeatureAdmin(featureId as number, userId),
    onSuccess: (_unused, userId) => {
      queryClient.setQueryData<typeof admins>(adminsQueryKey, (current = []) =>
        current.filter((item) => item.user_id !== userId),
      );
      showSuccess("特性管理员已移除");
      void queryClient.invalidateQueries({ queryKey: adminsQueryKey });
    },
    onError: (error) => showError(`移除特性管理员失败：${messageFromError(error)}`),
  });

  const trimmedQuery = query.trim();
  const candidates = candidateQuery.data ?? [];

  return (
    <div className="tab-content">
      <section className="surface feature-admins-panel">
        <div className="admins-head">
          <div className="section-title">
            <ShieldCheck aria-hidden="true" size={18} />
            <h2>特性管理员</h2>
          </div>
          {featureId && admins.length > 0 ? (
            <span className="admins-count">{admins.length} 位管理员</span>
          ) : null}
        </div>
        {!featureId ? (
          <div className="empty-block wide">
            <p>先选择一个特性，再查看管理员。</p>
          </div>
        ) : (
          <>
            {isAdmin ? (
              <div className="feature-admin-search">
                <label className="field-label compact" htmlFor="feature-admin-search">
                  添加管理员
                  <Input
                    aria-label="搜索可添加用户"
                    id="feature-admin-search"
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="输入用户名搜索并添加"
                    value={query}
                  />
                </label>
                {trimmedQuery ? (
                  <div className="candidate-panel">
                    {candidateQuery.isFetching ? (
                      <p className="candidate-empty">正在搜索…</p>
                    ) : candidates.length ? (
                      <ul className="candidate-list">
                        {candidates.map((candidate) => (
                          <li key={candidate.id}>
                            <span className="user-cell">
                              <span aria-hidden="true" className="user-avatar">
                                {monogram(candidate.username)}
                              </span>
                              <span className="user-name">{candidate.username}</span>
                            </span>
                            <Button
                              disabled={addMutation.isPending}
                              icon={<UserPlus aria-hidden="true" size={15} />}
                              onClick={() => addMutation.mutate(candidate.id)}
                              type="button"
                              variant="secondary"
                            >
                              添加
                            </Button>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="candidate-empty">无匹配用户</p>
                    )}
                  </div>
                ) : null}
              </div>
            ) : null}
            {isLoading ? <p className="empty-note">正在加载特性管理员</p> : null}
            {!isLoading && admins.length === 0 ? (
              <div className="empty-block wide">
                <p>还没有特性管理员{isAdmin ? "，搜索用户添加。" : "。"}</p>
              </div>
            ) : (
              <ul className="data-list feature-admin-list">
                {admins.map((admin) => (
                  <li key={admin.user_id}>
                    <span className="user-cell">
                      <span aria-hidden="true" className="user-avatar">
                        {monogram(admin.username)}
                      </span>
                      <span className="user-meta">
                        <strong>{admin.username}</strong>
                        <small>
                          添加时间 {new Date(admin.created_at).toLocaleString()}
                        </small>
                      </span>
                    </span>
                    {isAdmin ? (
                      <Button
                        aria-label={`移除管理员 ${admin.username}`}
                        className="admin-remove"
                        disabled={removeMutation.isPending}
                        icon={<Trash2 aria-hidden="true" size={15} />}
                        onClick={() => removeMutation.mutate(admin.user_id)}
                        type="button"
                        variant="quiet"
                      />
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </section>
    </div>
  );
}

// 用户名首字符作字母头像（中文取首字、英文取首字母大写）
function monogram(username: string) {
  return [...username.trim()][0]?.toUpperCase() ?? "?";
}
