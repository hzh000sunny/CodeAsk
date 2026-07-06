import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, LogIn, UserRound } from "lucide-react";

import { getCurrentUser, getMe, updateCurrentUser, updateCurrentUserPassword } from "../../lib/api";
import { resetSubjectScopedQueries } from "../../lib/auth-cache";
import { getSubjectId } from "../../lib/identity";
import { useAppFeedback } from "../feedback/AppFeedback";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { GuestLlmConfig } from "./GuestLlmConfig";
import { LlmConfigManager } from "./llm/LlmConfigManager";
import { messageFromApiError } from "./settings-utils";

export function UserSettings({ onLoginRequest }: { onLoginRequest?: () => void }) {
  const queryClient = useQueryClient();
  const { showError } = useAppFeedback();
  const { data: me } = useQuery({ queryKey: ["auth", "me"], queryFn: getMe });
  const { data: user } = useQuery({
    queryKey: ["users", "me"],
    queryFn: getCurrentUser,
    enabled: me?.authenticated === true,
  });
  const [username, setUsername] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  // Quiet, in-place confirmation for these inline saves (no global toast); each
  // clears as soon as the user edits that field again.
  const [renameSaved, setRenameSaved] = useState(false);
  const [passwordSaved, setPasswordSaved] = useState(false);
  const effectiveUsername = username ?? user?.username ?? "";
  const canRename = me?.authenticated === true && me.role !== "admin";

  useEffect(() => {
    if (me?.authenticated !== true) {
      setUsername(null);
      setPassword("");
      setRenameSaved(false);
      setPasswordSaved(false);
    }
  }, [me?.authenticated, me?.subject_id]);

  const renameMutation = useMutation({
    mutationFn: updateCurrentUser,
    onSuccess: (updated) => {
      setUsername(updated.username);
      setRenameSaved(true);
      setPasswordSaved(false);
      queryClient.setQueryData(["users", "me"], updated);
      void queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
      resetSubjectScopedQueries(queryClient);
    },
    onError: (error) => showError(`修改用户名失败：${messageFromApiError(error)}`),
  });
  const passwordMutation = useMutation({
    mutationFn: updateCurrentUserPassword,
    onSuccess: () => {
      // Keep the entered password in place; just acknowledge inline.
      setPasswordSaved(true);
      setRenameSaved(false);
      void queryClient.invalidateQueries({ queryKey: ["users", "me"] });
    },
    onError: (error) => showError(`修改密码失败：${messageFromApiError(error)}`),
  });

  return (
    <div className="settings-stack">
      {me?.authenticated ? (
        <section className="surface">
          <div className="section-title">
            <UserRound aria-hidden="true" size={18} />
            <h2>用户配置</h2>
          </div>
          <div className="profile-identity">
            <span aria-hidden="true" className="profile-avatar">
              {avatarInitial(me.display_name)}
            </span>
            <div className="profile-identity-copy">
              <strong className="profile-name">{me.display_name}</strong>
              <span className="profile-role">已登录用户</span>
            </div>
          </div>
          <div className="user-profile-form">
            <label className="user-profile-field" htmlFor="user-nickname">
              <span>用户名</span>
              <Input
                disabled={!canRename}
                id="user-nickname"
                onChange={(event) => {
                  setUsername(event.target.value);
                  setRenameSaved(false);
                }}
                placeholder="用户名"
                value={effectiveUsername}
              />
            </label>
            <label className="user-profile-field" htmlFor="user-password">
              <span>新密码</span>
              <Input
                id="user-password"
                minLength={6}
                onChange={(event) => {
                  setPassword(event.target.value);
                  setPasswordSaved(false);
                }}
                placeholder="至少 6 位"
                type="password"
                value={password}
              />
            </label>
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
              <Button
                disabled={password.trim().length < 6 || passwordMutation.isPending}
                onClick={() => passwordMutation.mutate({ password })}
                type="button"
                variant="secondary"
              >
                修改密码
              </Button>
              {renameSaved || passwordSaved ? (
                <span aria-live="polite" className="user-profile-saved">
                  <Check aria-hidden="true" size={14} />
                  {renameSaved ? "用户名已更新" : "密码已更新"}
                </span>
              ) : null}
            </div>
          </div>
          <dl className="profile-meta">
            <dt>用户 ID</dt>
            <dd className="console-mono">{me.subject_id}</dd>
          </dl>
        </section>
      ) : (
        <section className="surface guest-identity">
          <div className="section-title">
            <UserRound aria-hidden="true" size={18} />
            <h2>用户配置</h2>
          </div>
          <div className="guest-identity-panel">
            <div className="guest-identity-copy">
              <p className="guest-identity-lead">以访客身份使用 CodeAsk</p>
              <p className="guest-identity-note">
                会话与模型配置仅保存在当前浏览器。登录后可为账号命名，并在个人配置下统一管理模型；首次登录会自动创建账号。
              </p>
            </div>
            <Button
              className="guest-identity-cta"
              icon={<LogIn size={16} />}
              onClick={() => onLoginRequest?.()}
              type="button"
              variant="primary"
            >
              登录 / 注册
            </Button>
          </div>
          <dl className="guest-identity-meta">
            <dt>浏览器 ID</dt>
            <dd className="console-mono">{getSubjectId()}</dd>
          </dl>
        </section>
      )}
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

/** First visible character of the display name, upper-cased, for the letter avatar. */
function avatarInitial(name: string | null | undefined): string {
  const trimmed = name?.trim() ?? "";
  return trimmed ? trimmed[0].toUpperCase() : "U";
}
