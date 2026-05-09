import {
  BookOpenText,
  ChevronLeft,
  ChevronRight,
  Github,
  MessageSquareText,
  Settings,
  Sparkles,
} from "lucide-react";

export type SectionId = "sessions" | "features" | "wiki" | "settings";

interface SidebarProps {
  activeSection: SectionId;
  collapsed: boolean;
  onSectionChange: (section: SectionId) => void;
  onToggleCollapsed: () => void;
}

const items = [
  { id: "sessions", label: "会话", icon: MessageSquareText },
  { id: "features", label: "特性", icon: Sparkles },
  { id: "wiki", label: "Wiki", icon: BookOpenText },
  { id: "settings", label: "设置", icon: Settings },
] satisfies Array<{
  id: SectionId;
  label: string;
  icon: typeof MessageSquareText;
}>;

export function Sidebar({
  activeSection,
  collapsed,
  onSectionChange,
  onToggleCollapsed,
}: SidebarProps) {
  return (
    <aside className="source-sidebar" data-collapsed={collapsed}>
      <nav aria-label="主导航" className="source-nav">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <button
              aria-current={activeSection === item.id ? "page" : undefined}
              aria-label={item.label}
              className="source-nav-item"
              data-active={activeSection === item.id}
              key={item.id}
              onClick={() => onSectionChange(item.id)}
              type="button"
            >
              <Icon aria-hidden="true" size={18} strokeWidth={1.9} />
              {!collapsed ? <span>{item.label}</span> : null}
            </button>
          );
        })}
      </nav>
      <nav aria-label="外部链接" className="source-nav-external">
        <a
          aria-label="打开 CodeAsk GitHub 项目"
          className="source-nav-item source-nav-link"
          href="https://github.com/hzh000sunny/CodeAsk"
          rel="noreferrer"
          target="_blank"
          title="打开 CodeAsk GitHub 项目"
        >
          <Github aria-hidden="true" size={18} strokeWidth={1.9} />
          {!collapsed ? <span>GitHub</span> : null}
        </a>
      </nav>
      <button
        aria-label={collapsed ? "展开主导航" : "收起主导航"}
        className="edge-collapse-button primary"
        data-collapsed={collapsed}
        onClick={onToggleCollapsed}
        title={collapsed ? "展开主导航" : "收起主导航"}
        type="button"
      >
        {collapsed ? (
          <ChevronRight aria-hidden="true" size={15} />
        ) : (
          <ChevronLeft aria-hidden="true" size={15} />
        )}
      </button>
    </aside>
  );
}
