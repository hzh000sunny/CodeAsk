import { useEffect, useRef, useState } from "react";

import { AdminLoginPage } from "../auth/AdminLoginPage";
import { FeatureWorkbench } from "../features/FeatureWorkbench";
import type { FeatureWikiOpenOptions } from "../features/FeatureTabs";
import { SessionWorkspace } from "../session/SessionWorkspace";
import { SettingsPage } from "../settings/SettingsPage";
import { WikiPage } from "../wiki/WikiPage";
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
import { Button } from "../ui/button";

interface ReportTarget {
  featureId: number;
  reportId: number;
}

interface WikiImportNavigationGuard {
  blocking: boolean;
  continueInBackground: () => void;
  cancelImport: () => Promise<boolean>;
}

export function AppShell() {
  const [routeState, setRouteState] = useState<AppRouteState>(
    typeof window === "undefined" ? defaultAppRouteState : readRouteStateFromLocation(),
  );
  const activeSection = sectionForView(routeState.view);
  const [primaryCollapsed, setPrimaryCollapsed] = useState(false);
  const [reportTarget, setReportTarget] = useState<ReportTarget | null>(null);
  const [backgroundImportSession, setBackgroundImportSession] = useState<{
    sessionId: number;
    featureId: number | null;
  } | null>(null);
  const wikiImportNavigationGuardRef = useRef<WikiImportNavigationGuard | null>(null);
  const [pendingView, setPendingView] = useState<AppViewId | null>(null);

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

  function showView(view: AppViewId, options?: { force?: boolean }) {
    if (
      !options?.force &&
      routeState.view === "wiki" &&
      view !== "wiki" &&
      wikiImportNavigationGuardRef.current?.blocking
    ) {
      setPendingView(view);
      return;
    }
    const nextState: AppRouteState = {
      ...routeState,
      view,
      wiki:
        view === "wiki"
          ? {
              ...routeState.wiki,
              featureId:
                routeState.wiki.featureId ?? backgroundImportSession?.featureId ?? routeState.wiki.featureId,
            }
          : defaultAppRouteState.wiki,
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

  function openWikiFromFeature(featureId: number, options?: FeatureWikiOpenOptions) {
    setReportTarget(null);
    navigateWiki({
      featureId,
      nodeId: options?.nodeId ?? null,
      mode: "view",
      drawer: options?.drawer ?? null,
    });
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
              onOpenWiki={openWikiFromFeature}
              reportTarget={reportTarget}
            />
          ) : null}
          {routeState.view === "wiki" ? (
            <WikiPage
              backgroundImportSession={backgroundImportSession}
              onBackgroundImportChange={(session) => {
                setBackgroundImportSession((current) => {
                  if (
                    current?.sessionId === session?.sessionId &&
                    current?.featureId === session?.featureId
                  ) {
                    return current;
                  }
                  return session;
                });
              }}
              onImportNavigationGuardChange={(guard) => {
                wikiImportNavigationGuardRef.current = guard;
              }}
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
      {pendingView ? (
        <div className="dialog-backdrop">
          <section
            aria-labelledby="app-import-leave-title"
            aria-modal="true"
            className="confirm-dialog wiki-node-dialog wiki-leave-dialog"
            role="dialog"
          >
            <div className="dialog-content">
              <h2 id="app-import-leave-title">导入尚未完成</h2>
              <p>离开当前页面前，需要先决定是继续后台上传，还是直接取消本次导入。</p>
              <div className="dialog-actions wiki-dialog-actions-stack">
                <Button
                  onClick={() => setPendingView(null)}
                  type="button"
                  variant="secondary"
                >
                  继续留在 Wiki
                </Button>
                <Button
                  onClick={() => {
                    wikiImportNavigationGuardRef.current?.continueInBackground();
                    const nextView = pendingView;
                    setPendingView(null);
                    if (nextView) {
                      showView(nextView, { force: true });
                    }
                  }}
                  type="button"
                  variant="secondary"
                >
                  继续后台
                </Button>
                <Button
                  onClick={async () => {
                    const nextView = pendingView;
                    const success = await wikiImportNavigationGuardRef.current?.cancelImport();
                    if (!success || !nextView) {
                      return;
                    }
                    setPendingView(null);
                    showView(nextView, { force: true });
                  }}
                  type="button"
                  variant="danger"
                >
                  取消上传
                </Button>
              </div>
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}

function sectionForView(view: AppViewId): SectionId {
  if (view === "login") {
    return "sessions";
  }
  return view;
}
