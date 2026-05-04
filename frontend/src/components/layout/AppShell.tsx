import { useEffect, useState } from "react";

import { AdminLoginPage } from "../auth/AdminLoginPage";
import { FeatureWorkbench } from "../features/FeatureWorkbench";
import { SessionWorkspace } from "../session/SessionWorkspace";
import { SettingsPage } from "../settings/SettingsPage";
import { WikiWorkbench } from "../wiki/WikiWorkbench";
import {
  defaultAppRouteState,
  mergeWikiRouteState,
  readRouteStateFromLocation,
  writeRouteStateToLocation,
  type AppRouteState,
  type AppViewId,
} from "../../lib/wiki/routing";
import { Sidebar, type SectionId } from "./Sidebar";
import { TopBar } from "./TopBar";

interface ReportTarget {
  featureId: number;
  reportId: number;
}

export function AppShell() {
  const [routeState, setRouteState] = useState<AppRouteState>(
    typeof window === "undefined" ? defaultAppRouteState : readRouteStateFromLocation(),
  );
  const activeSection = sectionForView(routeState.view);
  const [primaryCollapsed, setPrimaryCollapsed] = useState(false);
  const [reportTarget, setReportTarget] = useState<ReportTarget | null>(null);

  useEffect(() => {
    function syncRouteFromLocation() {
      setRouteState(readRouteStateFromLocation());
    }

    window.addEventListener("hashchange", syncRouteFromLocation);
    window.addEventListener("popstate", syncRouteFromLocation);
    return () => {
      window.removeEventListener("hashchange", syncRouteFromLocation);
      window.removeEventListener("popstate", syncRouteFromLocation);
    };
  }, []);

  function showView(view: AppViewId) {
    const nextState: AppRouteState = {
      ...routeState,
      view,
      wiki: view === "wiki" ? routeState.wiki : defaultAppRouteState.wiki,
    };
    setRouteState(nextState);
    writeRouteStateToLocation(nextState);
  }

  function navigate(section: SectionId) {
    showView(section);
  }

  function navigateWiki(patch: Partial<AppRouteState["wiki"]>) {
    const nextState = mergeWikiRouteState(routeState, patch);
    setRouteState(nextState);
    writeRouteStateToLocation(nextState);
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
          {routeState.view === "sessions" ? (
            <SessionWorkspace
              onOpenReport={(target) => {
                setReportTarget(target);
                showView("features");
              }}
            />
          ) : null}
          {routeState.view === "features" ? (
            <FeatureWorkbench
              onOpenWiki={(featureId) => {
                setReportTarget(null);
                navigateWiki({
                  featureId,
                  nodeId: null,
                  mode: "view",
                  drawer: null,
                });
              }}
              reportTarget={reportTarget}
            />
          ) : null}
          {routeState.view === "wiki" ? (
            <WikiWorkbench
              routeState={routeState.wiki}
              onRouteChange={navigateWiki}
              onOpenFeature={(featureId) => {
                setReportTarget(null);
                const nextState: AppRouteState = {
                  ...routeState,
                  view: "features",
                  wiki: {
                    ...routeState.wiki,
                    featureId,
                  },
                };
                setRouteState(nextState);
                writeRouteStateToLocation(nextState);
              }}
            />
          ) : null}
          {routeState.view === "settings" ? <SettingsPage /> : null}
          {routeState.view === "login" ? (
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

function sectionForView(view: AppViewId): SectionId {
  if (view === "login") {
    return "sessions";
  }
  return view;
}
