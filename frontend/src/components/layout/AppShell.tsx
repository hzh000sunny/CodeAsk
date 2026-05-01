import { useState } from "react";

import { AdminLoginPage } from "../auth/AdminLoginPage";
import { FeatureWorkbench } from "../features/FeatureWorkbench";
import { SessionWorkspace } from "../session/SessionWorkspace";
import { SettingsPage } from "../settings/SettingsPage";
import { Sidebar, type SectionId } from "./Sidebar";
import { TopBar } from "./TopBar";

interface ReportTarget {
  featureId: number;
  reportId: number;
}

export function AppShell() {
  const [activeSection, setActiveSection] = useState<SectionId>("sessions");
  const [activeView, setActiveView] = useState<SectionId | "login">("sessions");
  const [primaryCollapsed, setPrimaryCollapsed] = useState(false);
  const [reportTarget, setReportTarget] = useState<ReportTarget | null>(null);

  function navigate(section: SectionId) {
    setActiveSection(section);
    setActiveView(section);
  }

  return (
    <div className="app-shell">
      <TopBar onLoginRequest={() => setActiveView("login")} onNavigate={navigate} />
      <div className="app-body" data-primary-collapsed={primaryCollapsed}>
        <Sidebar
          activeSection={activeSection}
          collapsed={primaryCollapsed}
          onSectionChange={navigate}
          onToggleCollapsed={() => setPrimaryCollapsed((value) => !value)}
        />
        <main className="app-main">
          {activeView === "sessions" ? (
            <SessionWorkspace
              onOpenReport={(target) => {
                setReportTarget(target);
                setActiveSection("features");
                setActiveView("features");
              }}
            />
          ) : null}
          {activeView === "features" ? <FeatureWorkbench reportTarget={reportTarget} /> : null}
          {activeView === "settings" ? <SettingsPage /> : null}
          {activeView === "login" ? (
            <AdminLoginPage
              onSuccess={() => {
                setActiveSection("settings");
                setActiveView("settings");
              }}
            />
          ) : null}
        </main>
      </div>
    </div>
  );
}
