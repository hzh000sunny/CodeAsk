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
export type FeatureTabId =
  | "settings"
  | "knowledge"
  | "reports"
  | "repos"
  | "skill"
  | "admins";

export interface WikiRouteState {
  featureId: number | null;
  nodeId: number | null;
  heading: string | null;
  mode: WikiMode;
  drawer: WikiDrawer;
}

export interface FeatureRouteState {
  featureId: number | null;
  tab: FeatureTabId | null;
  // 知识库 tab 里当前预览的 wiki 节点；与 wiki 视图共用 node 参数（语义一致：wiki 树节点 id）。
  nodeId: number | null;
}

export interface AppRouteState {
  view: AppViewId;
  sessions: {
    sessionId: string | null;
  };
  settings: {
    adminPageId: SettingsAdminPageId | null;
  };
  features: FeatureRouteState;
  wiki: WikiRouteState;
}

export const defaultWikiRouteState: WikiRouteState = {
  featureId: null,
  nodeId: null,
  heading: null,
  mode: "view",
  drawer: null,
};

export const defaultFeatureRouteState: FeatureRouteState = {
  featureId: null,
  tab: null,
  nodeId: null,
};

export const defaultAppRouteState: AppRouteState = {
  view: "sessions",
  sessions: {
    sessionId: null,
  },
  settings: {
    adminPageId: null,
  },
  features: defaultFeatureRouteState,
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
    features: {
      featureId: readInt(search.get("feature")),
      tab: readFeatureTab(search.get("tab")),
      nodeId: readInt(search.get("node")),
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
  if (state.view === "features") {
    if (state.features.featureId != null) {
      params.set("feature", String(state.features.featureId));
    }
    if (state.features.tab) {
      params.set("tab", state.features.tab);
    }
    if (state.features.nodeId != null) {
      params.set("node", String(state.features.nodeId));
    }
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

const FEATURE_ROUTE_STORAGE_KEY = "codeask:feature-route";

// 把「上次的特性选中 + 子 tab」持久化到 localStorage，使其在「切到别的页面再刷新浏览器」
// 这种 URL 不携带特性参数的场景下仍能恢复。
export function writePersistedFeatureRoute(features: FeatureRouteState) {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(
      FEATURE_ROUTE_STORAGE_KEY,
      JSON.stringify({
        featureId: features.featureId,
        tab: features.tab,
        nodeId: features.nodeId,
      }),
    );
  } catch {
    // 忽略隐私模式 / 配额等存储异常，持久化只是增强、不是必须。
  }
}

export function readPersistedFeatureRoute(): FeatureRouteState | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const raw = window.localStorage.getItem(FEATURE_ROUTE_STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as Partial<FeatureRouteState>;
    return {
      featureId: typeof parsed.featureId === "number" ? parsed.featureId : null,
      tab: readFeatureTab(typeof parsed.tab === "string" ? parsed.tab : null),
      nodeId: typeof parsed.nodeId === "number" ? parsed.nodeId : null,
    };
  } catch {
    return null;
  }
}

// 初始路由：URL 显式带选中（深链、或在对应页刷新）时以 URL 为准；
// 否则用 localStorage 里上次的选中补水，保证跨页面刷新仍记得选中的特性/文档。
export function readInitialAppRouteState(): AppRouteState {
  if (typeof window === "undefined") {
    return defaultAppRouteState;
  }
  const fromUrl = readRouteStateFromLocation();
  const hydrated: AppRouteState = { ...fromUrl };
  if (fromUrl.wiki.featureId == null && fromUrl.wiki.nodeId == null) {
    const persistedWiki = readPersistedWikiRoute();
    if (persistedWiki) {
      hydrated.wiki = persistedWiki;
    }
  }
  if (
    fromUrl.features.featureId == null &&
    fromUrl.features.tab == null &&
    fromUrl.features.nodeId == null
  ) {
    const persistedFeatures = readPersistedFeatureRoute();
    if (persistedFeatures) {
      hydrated.features = persistedFeatures;
    }
  }
  return hydrated;
}

export function mergeFeaturesRouteState(
  current: AppRouteState,
  patch: Partial<FeatureRouteState>,
): AppRouteState {
  return {
    ...current,
    view: "features",
    features: {
      ...current.features,
      ...patch,
    },
  };
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

function readFeatureTab(raw: string | null): FeatureTabId | null {
  if (
    raw === "settings" ||
    raw === "knowledge" ||
    raw === "reports" ||
    raw === "repos" ||
    raw === "skill" ||
    raw === "admins"
  ) {
    return raw;
  }
  return null;
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
