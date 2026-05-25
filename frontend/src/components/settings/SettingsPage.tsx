import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  ChevronLeft,
  ChevronRight,
  GitBranch,
  KeyRound,
  Paperclip,
  Radar,
  ScrollText,
  Settings2,
  UserRound,
  UsersRound,
} from "lucide-react";

import { getMe } from "../../lib/api";
import type { SettingsAdminPageId } from "../../lib/wiki/routing";
import {
  AdminLlmSettings,
  AdminPolicySettings,
  AdminRepoSettings,
  AdminRuntimeSettings,
  AdminUsersSettings,
  SessionAttachmentSettings,
} from "./GlobalSettings";
import { OpenVikingDashboard } from "./OpenVikingDashboard";
import { UserSettings } from "./UserSettings";

type AdminSettingsPageId = SettingsAdminPageId;

interface SettingsNavItem {
  description: string;
  icon: typeof Activity;
  id: AdminSettingsPageId;
  label: string;
}

const adminSettingsPages: SettingsNavItem[] = [
  {
    id: "runtime",
    label: "运行状态",
    description: "opencode 后端、端口和会话数",
    icon: Activity,
  },
  {
    id: "attachments",
    label: "会话附件",
    description: "上传能力的全局开关",
    icon: Paperclip,
  },
  {
    id: "users",
    label: "用户管理",
    description: "搜索用户和重置密码",
    icon: UsersRound,
  },
  {
    id: "llm",
    label: "LLM 配置",
    description: "全局模型账号与连通性",
    icon: KeyRound,
  },
  {
    id: "repos",
    label: "仓库管理",
    description: "Git 与本地目录代码仓",
    icon: GitBranch,
  },
  {
    id: "policies",
    label: "全局分析策略",
    description: "注入 Agent 的管理策略",
    icon: ScrollText,
  },
  {
    id: "openviking",
    label: "OpenViking",
    description: "RAG 后端、同步队列和调优",
    icon: Radar,
  },
];

const pageDescriptions: Record<AdminSettingsPageId, string> = {
  runtime: "查看 opencode 兼容后端的实时健康状态，不会触发进程启动或配置变更。",
  attachments: "管理会话附件上传入口的全局可用性。",
  users: "面向管理员的用户检索和密码记录清理能力。",
  llm: "维护全局 LLM 配置、Agent 适配方式和连接测试状态。",
  repos: "维护 Agent 可以准备和读取的全局代码仓库。",
  policies: "维护全局分析策略，约束问题定位、代码调查和最终回答。",
  openviking: "查看 OpenViking 语义检索后端、同步任务、事件流和调优参数。",
};

export function SettingsPage({
  onAdminPageChange,
  routeAdminPageId,
}: {
  onAdminPageChange?: (pageId: AdminSettingsPageId) => void;
  routeAdminPageId?: AdminSettingsPageId | null;
}) {
  const [indexCollapsed, setIndexCollapsed] = useState(false);
  const { data: me } = useQuery({ queryKey: ["auth", "me"], queryFn: getMe });
  const isAdmin = me?.role === "admin";
  const adminPageId = routeAdminPageId ?? "runtime";
  const activeAdminPage =
    adminSettingsPages.find((page) => page.id === adminPageId) ?? adminSettingsPages[0];

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
              <SettingsIndexButton
                active
                description="账号、密码和个人模型配置"
                icon={UserRound}
                label="用户设置"
              />
            ) : null}
            {isAdmin ? (
              <>
                <div className="settings-index-section-label">全局配置</div>
                {adminSettingsPages.map((page) => (
                  <SettingsIndexButton
                    active={page.id === activeAdminPage.id}
                    description={page.description}
                    icon={page.icon}
                    key={page.id}
                    label={page.label}
                    onClick={() => onAdminPageChange?.(page.id)}
                  />
                ))}
              </>
            ) : null}
          </>
        )}
      </aside>

      <section className="settings-content" data-scroll-region="true">
        {!me ? <SettingsLoading /> : null}
        {me && !isAdmin ? <UserSettings /> : null}
        {isAdmin ? (
          <AdminSettingsContent
            activePage={activeAdminPage}
            pageId={activeAdminPage.id}
          />
        ) : null}
      </section>
    </section>
  );
}

function SettingsIndexButton({
  active,
  description,
  icon: Icon,
  label,
  onClick,
}: {
  active: boolean;
  description: string;
  icon: typeof Activity;
  label: string;
  onClick?: () => void;
}) {
  return (
    <button
      aria-label={label}
      aria-current={active ? "page" : undefined}
      className="settings-index-item"
      data-active={active ? "true" : "false"}
      onClick={onClick}
      type="button"
    >
      <Icon aria-hidden="true" size={17} />
      <span className="settings-index-item-copy">
        <span>{label}</span>
        <small>{description}</small>
      </span>
    </button>
  );
}

function AdminSettingsContent({
  activePage,
  pageId,
}: {
  activePage: SettingsNavItem;
  pageId: AdminSettingsPageId;
}) {
  return (
    <div className="settings-stack">
      <header className="settings-page-header">
        <div className="settings-page-heading">
          <span className="settings-page-kicker">
            <Settings2 aria-hidden="true" size={15} />
            管理员设置
          </span>
          <h1>{activePage.label}</h1>
          <p>{pageDescriptions[pageId]}</p>
        </div>
      </header>
      {pageId === "runtime" ? <AdminRuntimeSettings /> : null}
      {pageId === "attachments" ? <SessionAttachmentSettings /> : null}
      {pageId === "users" ? <AdminUsersSettings /> : null}
      {pageId === "llm" ? <AdminLlmSettings /> : null}
      {pageId === "repos" ? <AdminRepoSettings /> : null}
      {pageId === "policies" ? <AdminPolicySettings /> : null}
      {pageId === "openviking" ? <OpenVikingDashboard /> : null}
    </div>
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
