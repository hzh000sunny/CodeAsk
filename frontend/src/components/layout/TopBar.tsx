import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { LogIn, LogOut, Settings, UserCircle, UserRound } from "lucide-react";

import { getMe, logout } from "../../lib/api";
import type { AuthMeResponse } from "../../types/api";
import type { SectionId } from "./Sidebar";

interface TopBarProps {
  onLoginRequest: () => void;
  onNavigate: (section: SectionId) => void;
}

export function TopBar({ onLoginRequest, onNavigate }: TopBarProps) {
  const queryClient = useQueryClient();
  const [menuOpen, setMenuOpen] = useState(false);
  const [notice, setNotice] = useState("");
  const menuRef = useRef<HTMLDivElement | null>(null);
  const { data: me } = useQuery({
    queryKey: ["auth", "me"],
    queryFn: getMe,
  });
  const logoutMutation = useMutation({
    mutationFn: logout,
    onSuccess: () => {
      setNotice("");
      void queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
      void queryClient.invalidateQueries({ queryKey: ["admin-llm-configs"] });
    },
  });

  useEffect(() => {
    function onPointerDown(event: PointerEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, []);

  const displayName = displayNameFor(me);

  return (
    <header className="global-topbar">
      <div className="topbar-brand" aria-label="CodeAsk">
        <div className="brand-mark">C</div>
        <span>CodeAsk</span>
      </div>
      <div className="account-menu" ref={menuRef}>
        <button
          aria-expanded={menuOpen}
          aria-haspopup="menu"
          className="account-button"
          onClick={() => setMenuOpen((value) => !value)}
          type="button"
        >
          <UserCircle aria-hidden="true" size={20} />
          <span>{displayName}</span>
        </button>
        {menuOpen ? (
          <div className="account-popover" role="menu">
            {!me?.authenticated ? (
              <button
                className="menu-item"
                onClick={() => {
                  setMenuOpen(false);
                  onLoginRequest();
                }}
                role="menuitem"
                type="button"
              >
                <LogIn aria-hidden="true" size={16} />
                <span>登录</span>
              </button>
            ) : (
              <>
                <div className="account-summary">
                  <strong>{displayName}</strong>
                  <span>管理员</span>
                </div>
                {notice ? (
                  <div className="menu-notice" role="status">
                    {notice}
                  </div>
                ) : null}
                <button
                  className="menu-item"
                  onClick={() => setNotice("暂不支持")}
                  role="menuitem"
                  type="button"
                >
                  <UserRound aria-hidden="true" size={16} />
                  <span>个人信息</span>
                </button>
                <button
                  className="menu-item"
                  onClick={() => {
                    onNavigate("settings");
                    setMenuOpen(false);
                  }}
                  role="menuitem"
                  type="button"
                >
                  <Settings aria-hidden="true" size={16} />
                  <span>设置</span>
                </button>
                <button
                  className="menu-item"
                  onClick={() => {
                    logoutMutation.mutate();
                    setMenuOpen(false);
                  }}
                  role="menuitem"
                  type="button"
                >
                  <LogOut aria-hidden="true" size={16} />
                  <span>退出</span>
                </button>
              </>
            )}
          </div>
        ) : null}
      </div>
    </header>
  );
}

function displayNameFor(me: AuthMeResponse | undefined) {
  if (me?.role === "admin") {
    return "Admin";
  }
  return "未登录";
}
