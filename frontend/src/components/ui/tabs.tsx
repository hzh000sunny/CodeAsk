import type { ReactNode } from "react";

interface TabItem {
  id: string;
  label: string;
}

interface TabsProps {
  tabs: TabItem[];
  value: string;
  onChange: (value: string) => void;
  children: ReactNode;
}

export function Tabs({ tabs, value, onChange, children }: TabsProps) {
  return (
    <>
      <div className="tab-list" role="tablist" aria-label="特性详情选项">
        {tabs.map((tab) => (
          <button
            aria-selected={value === tab.id}
            className="tab-button"
            key={tab.id}
            onClick={() => onChange(tab.id)}
            role="tab"
            type="button"
          >
            {tab.label}
          </button>
        ))}
      </div>
      {children}
    </>
  );
}
