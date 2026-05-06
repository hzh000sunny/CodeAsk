export type AppViewId = "sessions" | "features" | "wiki" | "settings" | "login";
export type WikiMode = "view" | "edit";
export type WikiDrawer = "detail" | "history" | "import" | "sources" | null;

export interface WikiRouteState {
  featureId: number | null;
  nodeId: number | null;
  heading: string | null;
  mode: WikiMode;
  drawer: WikiDrawer;
}

export interface AppRouteState {
  view: AppViewId;
  wiki: WikiRouteState;
}

export const defaultWikiRouteState: WikiRouteState = {
  featureId: null,
  nodeId: null,
  heading: null,
  mode: "view",
  drawer: null,
};

export const defaultAppRouteState: AppRouteState = {
  view: "sessions",
  wiki: defaultWikiRouteState,
};

export function readRouteStateFromLocation(): AppRouteState {
  if (typeof window === "undefined") {
    return defaultAppRouteState;
  }
  const rawHash = window.location.hash.replace(/^#\/?/, "");
  const [viewToken, queryString = ""] = rawHash.split("?");
  const view = isAppViewId(viewToken) ? viewToken : "sessions";
  const search = new URLSearchParams(queryString);
  return {
    view,
    wiki: {
      featureId: readInt(search.get("feature")),
      nodeId: readInt(search.get("node")),
      heading: readString(search.get("heading")),
      mode: search.get("mode") === "edit" ? "edit" : "view",
      drawer: readDrawer(search.get("drawer")),
    },
  };
}

export function writeRouteStateToLocation(state: AppRouteState) {
  if (typeof window === "undefined") {
    return;
  }
  const params = new URLSearchParams();
  if (state.view === "wiki") {
    if (state.wiki.featureId != null) {
      params.set("feature", String(state.wiki.featureId));
    }
    if (state.wiki.nodeId != null) {
      params.set("node", String(state.wiki.nodeId));
    }
    if (state.wiki.heading) {
      params.set("heading", state.wiki.heading);
    }
    if (state.wiki.mode === "edit") {
      params.set("mode", "edit");
    }
    if (state.wiki.drawer) {
      params.set("drawer", state.wiki.drawer);
    }
  }
  const query = params.toString();
  const nextHash = query ? `#/${state.view}?${query}` : `#/${state.view}`;
  if (window.location.hash === nextHash) {
    return;
  }
  window.history.pushState(null, "", nextHash);
}

export function mergeWikiRouteState(
  current: AppRouteState,
  patch: Partial<WikiRouteState>,
): AppRouteState {
  return {
    ...current,
    view: "wiki",
    wiki: {
      ...current.wiki,
      ...patch,
    },
  };
}

function readInt(raw: string | null): number | null {
  if (!raw) {
    return null;
  }
  const value = Number.parseInt(raw, 10);
  return Number.isFinite(value) ? value : null;
}

function readDrawer(raw: string | null): WikiDrawer {
  if (raw === "detail" || raw === "history" || raw === "import" || raw === "sources") {
    return raw;
  }
  return null;
}

function readString(raw: string | null) {
  return typeof raw === "string" && raw.length > 0 ? raw : null;
}

function isAppViewId(raw: string): raw is AppViewId {
  return raw === "sessions" || raw === "features" || raw === "wiki" || raw === "settings" || raw === "login";
}
