import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff, LogIn, UserRound } from "lucide-react";

import { adminLogin } from "../../lib/api";
import { Button } from "../ui/button";
import { Input } from "../ui/input";

interface AdminLoginPageProps {
  onSuccess: () => void;
}

export function AdminLoginPage({ onSuccess }: AdminLoginPageProps) {
  const queryClient = useQueryClient();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const loginMutation = useMutation({
    mutationFn: adminLogin,
    onSuccess: () => {
      setError("");
      void queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
      void queryClient.invalidateQueries({ queryKey: ["admin-llm-configs"] });
      onSuccess();
    },
    onError: () => {
      setError("登录失败，请检查用户名和密码");
    }
  });

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
            <p>输入账号信息后继续使用 CodeAsk。</p>
          </div>
        </div>
        <label className="field-label" htmlFor="login-username">
          用户名
          <Input
            autoComplete="username"
            id="login-username"
            onChange={(event) => setUsername(event.target.value)}
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
              {showPassword ? <EyeOff aria-hidden="true" size={16} /> : <Eye aria-hidden="true" size={16} />}
            </button>
          </span>
        </div>
        {error ? <div className="inline-alert danger in-dialog" role="alert">{error}</div> : null}
        <Button
          disabled={!username.trim() || !password || loginMutation.isPending}
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
