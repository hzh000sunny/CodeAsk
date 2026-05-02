import { useEffect, useState } from "react";

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

type ViewId = SectionId | "login";

export function AppShell() {
  const [initialView] = useState(readViewFromLocation);
  const [activeSection, setActiveSection] = useState<SectionId>(
    sectionForView(initialView),
  );
  const [activeView, setActiveView] = useState<ViewId>(initialView);
  const [primaryCollapsed, setPrimaryCollapsed] = useState(false);
  const [reportTarget, setReportTarget] = useState<ReportTarget | null>(null);

  useEffect(() => {
    function syncViewFromLocation() {
      const nextView = readViewFromLocation();
      setActiveView(nextView);
      if (isSectionId(nextView)) {
        setActiveSection(nextView);
      }
    }

    window.addEventListener("hashchange", syncViewFromLocation);
    window.addEventListener("popstate", syncViewFromLocation);
    return () => {
      window.removeEventListener("hashchange", syncViewFromLocation);
      window.removeEventListener("popstate", syncViewFromLocation);
    };
  }, []);

  function showView(view: ViewId) {
    if (isSectionId(view)) {
      setActiveSection(view);
    }
    setActiveView(view);
    writeViewToLocation(view);
  }

  function navigate(section: SectionId) {
    showView(section);
  }

  return (
    <div className="app-shell">
      <TopBar
        onLoginRequest={() => showView("login")}
        onNavigate={navigate}
      />
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
                showView("features");
              }}
            />
          ) : null}
          {activeView === "features" ? (
            <FeatureWorkbench reportTarget={reportTarget} />
          ) : null}
          {activeView === "settings" ? <SettingsPage /> : null}
          {activeView === "login" ? (
            <AdminLoginPage
              onSuccess={() => {
                showView("settings");
              }}
            />
          ) : null}
        </main>
      </div>
    </div>
  );
}

function readViewFromLocation(): ViewId {
  if (typeof window === "undefined") {
    return "sessions";
  }
  const value = window.location.hash.replace(/^#\/?/, "");
  if (value === "login") {
    return "login";
  }
  return isSectionId(value) ? value : "sessions";
}

function writeViewToLocation(view: ViewId) {
  if (typeof window === "undefined") {
    return;
  }
  const nextHash = `#/${view}`;
  if (window.location.hash === nextHash) {
    return;
  }
  window.history.pushState(null, "", nextHash);
}

function isSectionId(value: string): value is SectionId {
  return value === "sessions" || value === "features" || value === "settings";
}

function sectionForView(view: ViewId): SectionId {
  return isSectionId(view) ? view : "sessions";
}
