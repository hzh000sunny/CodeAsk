import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { UserRound } from "lucide-react";

import { getCurrentUser, getMe, updateCurrentUser, updateCurrentUserPassword } from "../../lib/api";
import { resetSubjectScopedQueries } from "../../lib/auth-cache";
import { getSubjectId } from "../../lib/identity";
import { useAppFeedback } from "../feedback/AppFeedback";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { GuestLlmConfig } from "./GuestLlmConfig";
import { LlmConfigManager } from "./llm/LlmConfigManager";
import { messageFromApiError } from "./settings-utils";

export function UserSettings() {
  const queryClient = useQueryClient();
  const { showError, showSuccess } = useAppFeedback();
  const { data: me } = useQuery({ queryKey: ["auth", "me"], queryFn: getMe });
  const { data: user } = useQuery({
    queryKey: ["users", "me"],
    queryFn: getCurrentUser,
    enabled: me?.authenticated === true,
  });
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const effectiveUsername = username || user?.username || "";
  const canRename = me?.authenticated === true && me.role !== "admin";

  const renameMutation = useMutation({
    mutationFn: updateCurrentUser,
    onSuccess: (updated) => {
      showSuccess("用户名已更新");
      setUsername(updated.username);
      queryClient.setQueryData(["users", "me"], updated);
      void queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
      resetSubjectScopedQueries(queryClient);
    },
    onError: (error) => showError(`修改用户名失败：${messageFromApiError(error)}`),
  });
  const passwordMutation = useMutation({
    mutationFn: updateCurrentUserPassword,
    onSuccess: () => {
      showSuccess("密码已更新，请重新登录");
      setPassword("");
      resetSubjectScopedQueries(queryClient);
      void queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
    },
    onError: (error) => showError(`修改密码失败：${messageFromApiError(error)}`),
  });

  return (
    <div className="settings-stack">
      <section className="surface">
        <div className="section-title">
          <UserRound aria-hidden="true" size={18} />
          <h2>用户配置</h2>
        </div>
        <dl className="meta-grid">
          <dt>{me?.authenticated ? "用户 ID" : "浏览器 ID"}</dt>
          <dd>{me?.authenticated ? me.subject_id : getSubjectId()}</dd>
          <dt>当前状态</dt>
          <dd>{me?.authenticated ? me.display_name : "未登录访客"}</dd>
        </dl>
        <div className="user-profile-form">
          <label className="user-profile-field" htmlFor="user-nickname">
            <span>用户名</span>
            <Input
              disabled={!canRename}
              id="user-nickname"
              onChange={(event) => setUsername(event.target.value)}
              placeholder={me?.authenticated ? "用户名" : "登录后可修改"}
              value={effectiveUsername}
            />
          </label>
          {me?.authenticated ? (
            <label className="user-profile-field" htmlFor="user-password">
              <span>新密码</span>
              <Input
                id="user-password"
                minLength={6}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="至少 6 位"
                type="password"
                value={password}
              />
            </label>
          ) : null}
          <div className="form-actions user-profile-actions">
            <Button
              disabled={!canRename || !effectiveUsername.trim() || renameMutation.isPending}
              onClick={() => {
                renameMutation.mutate({ username: effectiveUsername.trim() });
              }}
              type="button"
              variant="primary"
            >
              保存用户名
            </Button>
            {me?.authenticated ? (
              <Button
                disabled={password.trim().length < 6 || passwordMutation.isPending}
                onClick={() => passwordMutation.mutate({ password })}
                type="button"
                variant="secondary"
              >
                修改密码
              </Button>
            ) : null}
          </div>
        </div>
      </section>
      {me?.authenticated ? (
        me.role === "admin" ? null : (
          <LlmConfigManager scope="user" />
        )
      ) : (
        <GuestLlmConfig />
      )}
    </div>
  );
}
