export type AppViewId = "sessions" | "features" | "wiki" | "settings" | "login";
export type SettingsAdminPageId =
  | "runtime"
  | "attachments"
  | "users"
  | "llm"
  | "repos"
  | "policies"
  | "openviking";
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
  sessions: {
    sessionId: string | null;
  };
  settings: {
    adminPageId: SettingsAdminPageId | null;
  };
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
  sessions: {
    sessionId: null,
  },
  settings: {
    adminPageId: null,
  },
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
    sessions: {
      sessionId: readString(search.get("session")),
    },
    settings: {
      adminPageId: readSettingsAdminPage(search.get("page")),
    },
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
  if (state.view === "sessions" && state.sessions.sessionId) {
    params.set("session", state.sessions.sessionId);
  }
  if (state.view === "settings" && state.settings.adminPageId) {
    params.set("page", state.settings.adminPageId);
  }
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

const WIKI_ROUTE_STORAGE_KEY = "codeask:wiki-route";

// 把「上次的 Wiki 选中」持久化到 localStorage，使其在「切到别的页面再刷新浏览器」
// 这种 URL 不携带 wiki 参数的场景下仍能恢复。只保存定位信息，不保存编辑/抽屉等临时态。
export function writePersistedWikiRoute(wiki: WikiRouteState) {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(
      WIKI_ROUTE_STORAGE_KEY,
      JSON.stringify({
        featureId: wiki.featureId,
        nodeId: wiki.nodeId,
        heading: wiki.heading,
      }),
    );
  } catch {
    // 忽略隐私模式 / 配额等存储异常，持久化只是增强、不是必须。
  }
}

export function readPersistedWikiRoute(): WikiRouteState | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const raw = window.localStorage.getItem(WIKI_ROUTE_STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as Partial<WikiRouteState>;
    return {
      featureId: typeof parsed.featureId === "number" ? parsed.featureId : null,
      nodeId: typeof parsed.nodeId === "number" ? parsed.nodeId : null,
      heading:
        typeof parsed.heading === "string" && parsed.heading.length > 0 ? parsed.heading : null,
      mode: "view",
      drawer: null,
    };
  } catch {
    return null;
  }
}

// 初始路由：URL 显式带 wiki 选中（深链、或在 Wiki 页刷新）时以 URL 为准；
// 否则用 localStorage 里上次的 Wiki 选中补水，保证跨页面刷新仍记得选中的文档。
export function readInitialAppRouteState(): AppRouteState {
  if (typeof window === "undefined") {
    return defaultAppRouteState;
  }
  const fromUrl = readRouteStateFromLocation();
  if (fromUrl.wiki.featureId != null || fromUrl.wiki.nodeId != null) {
    return fromUrl;
  }
  const persisted = readPersistedWikiRoute();
  if (!persisted) {
    return fromUrl;
  }
  return { ...fromUrl, wiki: persisted };
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

function readSettingsAdminPage(raw: string | null): SettingsAdminPageId | null {
  if (
    raw === "runtime" ||
    raw === "attachments" ||
    raw === "users" ||
    raw === "llm" ||
    raw === "repos" ||
    raw === "policies" ||
    raw === "openviking"
  ) {
    return raw;
  }
  return null;
}
