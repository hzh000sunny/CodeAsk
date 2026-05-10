import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff, LogIn, UserRound } from "lucide-react";

import { login } from "../../lib/api";
import { resetSubjectScopedQueries } from "../../lib/auth-cache";
import { useAppFeedback } from "../feedback/AppFeedback";
import { Button } from "../ui/button";
import { Input } from "../ui/input";

interface AdminLoginPageProps {
  onSuccess: () => void;
}

export function AdminLoginPage({ onSuccess }: AdminLoginPageProps) {
  const queryClient = useQueryClient();
  const { showError } = useAppFeedback();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const loginMutation = useMutation({
    mutationFn: login,
    onSuccess: (me) => {
      queryClient.setQueryData(["auth", "me"], me);
      resetSubjectScopedQueries(queryClient);
      onSuccess();
    },
    onError: () => {
      showError("登录失败，请检查用户名和密码", { title: "登录失败" });
    },
  });

  const passwordTooShort = username.trim() !== "admin" && password.trim().length < 6;

  return (
    <section className="login-page" aria-label="登录页">
      <form
        className="login-card"
        onSubmit={(event) => {
          event.preventDefault();
          loginMutation.mutate({ username: username.trim(), password });
        }}
      >
        <div className="login-heading">
          <div className="dialog-icon">
            <UserRound aria-hidden="true" size={18} />
          </div>
          <div>
            <h1>登录</h1>
            <p>首次使用会自动创建账号，用户名和密码大小写敏感。</p>
          </div>
        </div>
        <label className="field-label" htmlFor="login-username">
          用户名
          <Input
            autoComplete="username"
            id="login-username"
            onChange={(event) => setUsername(event.target.value)}
            placeholder="输入用户名"
            value={username}
          />
        </label>
        <div className="field-label">
          <label htmlFor="login-password">密码</label>
          <span className="input-with-action">
            <Input
              autoComplete="current-password"
              id="login-password"
              onChange={(event) => setPassword(event.target.value)}
              type={showPassword ? "text" : "password"}
              value={password}
            />
            <button
              aria-label={showPassword ? "隐藏密码" : "显示密码"}
              className="input-action-button"
              onClick={() => setShowPassword((value) => !value)}
              type="button"
            >
              {showPassword ? (
                <EyeOff aria-hidden="true" size={16} />
              ) : (
                <Eye aria-hidden="true" size={16} />
              )}
            </button>
          </span>
        </div>
        <Button
          disabled={!username.trim() || !password || passwordTooShort || loginMutation.isPending}
          icon={<LogIn size={16} />}
          type="submit"
          variant="primary"
        >
          登录
        </Button>
      </form>
    </section>
  );
}
