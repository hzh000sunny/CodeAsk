import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Settings2, UserRound } from "lucide-react";

import { getMe } from "../../lib/api";
import { GlobalSettings } from "./GlobalSettings";
import { UserSettings } from "./UserSettings";

export function SettingsPage() {
  const [indexCollapsed, setIndexCollapsed] = useState(false);
  const { data: me } = useQuery({ queryKey: ["auth", "me"], queryFn: getMe });
  const isAdmin = me?.role === "admin";

  return (
    <section
      className="settings-workspace"
      data-index-collapsed={indexCollapsed}
      aria-label="设置工作台"
    >
      <aside className="settings-index" data-collapsed={indexCollapsed}>
        <button
          aria-label={indexCollapsed ? "展开设置导航" : "收起设置导航"}
          className="edge-collapse-button secondary"
          data-collapsed={indexCollapsed}
          onClick={() => setIndexCollapsed((value) => !value)}
          title={indexCollapsed ? "展开设置导航" : "收起设置导航"}
          type="button"
        >
          {indexCollapsed ? (
            <ChevronRight aria-hidden="true" size={15} />
          ) : (
            <ChevronLeft aria-hidden="true" size={15} />
          )}
        </button>
        {indexCollapsed ? (
          <div className="collapsed-panel-label">设置</div>
        ) : (
          <>
            {!me ? <p className="empty-note">正在加载设置</p> : null}
            {me && !isAdmin ? (
              <button
                aria-current="page"
                className="settings-index-item"
                data-active="true"
                type="button"
              >
                <UserRound aria-hidden="true" size={17} />
                <span>用户设置</span>
              </button>
            ) : null}
            {isAdmin ? (
              <button
                aria-current="page"
                className="settings-index-item"
                data-active="true"
                type="button"
              >
                <Settings2 aria-hidden="true" size={17} />
                <span>全局配置</span>
              </button>
            ) : null}
          </>
        )}
      </aside>

      <section className="settings-content" data-scroll-region="true">
        {!me ? <SettingsLoading /> : null}
        {me && !isAdmin ? <UserSettings /> : null}
        {isAdmin ? <GlobalSettings /> : null}
      </section>
    </section>
  );
}

function SettingsLoading() {
  return (
    <div className="settings-stack">
      <section className="surface">
        <p className="empty-note">正在加载设置</p>
      </section>
    </div>
  );
}
