import { useEffect, useRef, useState } from "react";

import { AdminLoginPage } from "../auth/AdminLoginPage";
import { FeatureWorkbench } from "../features/FeatureWorkbench";
import type { FeatureWikiOpenOptions } from "../features/FeatureTabs";
import { SessionWorkspace } from "../session/SessionWorkspace";
import { SettingsPage } from "../settings/SettingsPage";
import { WikiPage } from "../wiki/WikiPage";
import {
  mergeFeaturesRouteState,
  mergeWikiRouteState,
  readInitialAppRouteState,
  readRouteStateFromLocation,
  writePersistedFeatureRoute,
  writePersistedWikiRoute,
  writeRouteStateToLocation,
  type AppRouteState,
  type AppViewId,
  type FeatureRouteState,
  type SettingsAdminPageId,
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
  const [routeState, setRouteState] = useState<AppRouteState>(readInitialAppRouteState);
  const activeSection = sectionForView(routeState.view);
  const [primaryCollapsed, setPrimaryCollapsed] = useState(false);
  const [reportTarget, setReportTarget] = useState<ReportTarget | null>(null);
  const [backgroundImportSession, setBackgroundImportSession] = useState<{
    sessionId: number;
    featureId: number | null;
  } | null>(null);
  const wikiImportNavigationGuardRef = useRef<WikiImportNavigationGuard | null>(null);
  const loginReturnViewRef = useRef<AppViewId>("sessions");
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

  // 只在停留在 Wiki 页时持久化当前选中；离开 Wiki 不写入，避免把已保存的选中清掉。
  useEffect(() => {
    if (routeState.view !== "wiki") {
      return;
    }
    writePersistedWikiRoute(routeState.wiki);
  }, [routeState.view, routeState.wiki]);

  // 同理：停留在特性页时持久化选中的特性与子 tab，跨页面刷新后仍能恢复。
  useEffect(() => {
    if (routeState.view !== "features") {
      return;
    }
    writePersistedFeatureRoute(routeState.features);
  }, [routeState.view, routeState.features]);

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
          : // 离开 Wiki 时保留选中（featureId/nodeId/heading），切回来仍是同一篇；
            // 只收掉临时态，避免把编辑器/抽屉一起带回。
            { ...routeState.wiki, mode: "view", drawer: null },
    };
    setRouteState(nextState);
    writeRouteStateToLocation(nextState);
  }

  function navigate(section: SectionId) {
    showView(section);
  }

  function requestLogin() {
    loginReturnViewRef.current =
      routeState.view === "login" ? "sessions" : routeState.view;
    showView("login");
  }

  function navigateWiki(patch: Partial<AppRouteState["wiki"]>) {
    const nextState = mergeWikiRouteState(routeState, patch);
    setRouteState(nextState);
    writeRouteStateToLocation(nextState);
  }

  function navigateFeatures(patch: Partial<FeatureRouteState>) {
    const nextState = mergeFeaturesRouteState(routeState, patch);
    setRouteState(nextState);
    writeRouteStateToLocation(nextState);
  }

  function navigateSession(sessionId: string | null) {
    const nextState: AppRouteState = {
      ...routeState,
      view: "sessions",
      sessions: {
        sessionId,
      },
    };
    setRouteState(nextState);
    writeRouteStateToLocation(nextState);
  }

  function navigateSettingsPage(adminPageId: SettingsAdminPageId) {
    const nextState: AppRouteState = {
      ...routeState,
      view: "settings",
      settings: {
        adminPageId,
      },
    };
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
        onLoginRequest={requestLogin}
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
          <div
            className="app-view-surface"
            hidden={routeState.view !== "sessions"}
          >
            <SessionWorkspace
              routeSelectedSessionId={routeState.sessions.sessionId}
              onSelectedSessionChange={navigateSession}
              onOpenReport={(target) => {
                setReportTarget(target);
                navigateFeatures({ featureId: target.featureId, tab: "reports" });
              }}
              onOpenWiki={({ featureId, nodeId }) => {
                setReportTarget(null);
                navigateWiki({
                  featureId,
                  nodeId,
                  mode: "view",
                  drawer: null,
                });
              }}
            />
          </div>
          {routeState.view === "features" ? (
            <FeatureWorkbench
              onOpenWiki={openWikiFromFeature}
              onRouteChange={navigateFeatures}
              reportTarget={reportTarget}
              routeFeatureId={routeState.features.featureId}
              routeTab={routeState.features.tab}
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
                  features: {
                    ...routeState.features,
                    featureId,
                  },
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
          {routeState.view === "settings" ? (
            <SettingsPage
              routeAdminPageId={routeState.settings.adminPageId}
              onAdminPageChange={navigateSettingsPage}
            />
          ) : null}
          {routeState.view === "login" ? (
            <AdminLoginPage
              onSuccess={() => {
                showView(loginReturnViewRef.current);
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
