import { describe, expect, it, vi } from "vitest";

import {
  defaultAppRouteState,
  mergeFeaturesRouteState,
  mergeWikiRouteState,
  readRouteStateFromLocation,
  writeRouteStateToLocation,
} from "../src/lib/wiki/routing";

describe("wiki routing heading anchors", () => {
  it("reads heading from wiki hash routes", () => {
    window.history.replaceState(
      null,
      "",
      "#/wiki?feature=7&node=25&heading=%E6%8E%92%E6%9F%A5%E6%AD%A5%E9%AA%A4",
    );

    const state = readRouteStateFromLocation();

    expect(state.wiki.featureId).toBe(7);
    expect(state.wiki.nodeId).toBe(25);
    expect(state.wiki.heading).toBe("排查步骤");
  });

  it("writes heading back into the wiki hash route", () => {
    const pushState = vi
      .spyOn(window.history, "pushState")
      .mockImplementation(() => undefined);

    writeRouteStateToLocation({
      view: "wiki",
      sessions: {
        sessionId: null,
      },
      settings: {
        adminPageId: null,
      },
      features: {
        featureId: null,
        tab: null,
        nodeId: null,
      },
      wiki: {
        featureId: 7,
        nodeId: 25,
        heading: "排查步骤",
        mode: "view",
        drawer: null,
      },
    });

    expect(pushState).toHaveBeenCalledWith(
      null,
      "",
      "#/wiki?feature=7&node=25&heading=%E6%8E%92%E6%9F%A5%E6%AD%A5%E9%AA%A4",
    );
    pushState.mockRestore();
  });

  it("clears heading when merge patch sets a new node without one", () => {
    const next = mergeWikiRouteState(
      {
        view: "wiki",
        sessions: {
          sessionId: null,
        },
        settings: {
          adminPageId: null,
        },
        features: {
          featureId: null,
          tab: null,
          nodeId: null,
        },
        wiki: {
          featureId: 7,
          nodeId: 25,
          heading: "排查步骤",
          mode: "view",
          drawer: null,
        },
      },
      { nodeId: 26, heading: null },
    );

    expect(next.wiki.nodeId).toBe(26);
    expect(next.wiki.heading).toBeNull();
  });
});

describe("feature tab routing", () => {
  it("reads selected feature, tab, and knowledge node from the features hash route", () => {
    window.history.replaceState(
      null,
      "",
      "#/features?feature=7&tab=knowledge&node=703",
    );

    const state = readRouteStateFromLocation();

    expect(state.view).toBe("features");
    expect(state.features.featureId).toBe(7);
    expect(state.features.tab).toBe("knowledge");
    expect(state.features.nodeId).toBe(703);
  });

  it("ignores an unknown tab token", () => {
    window.history.replaceState(null, "", "#/features?feature=7&tab=bogus");

    expect(readRouteStateFromLocation().features.tab).toBeNull();
  });

  it("writes feature and tab back into the features hash route", () => {
    const pushState = vi
      .spyOn(window.history, "pushState")
      .mockImplementation(() => undefined);

    writeRouteStateToLocation({
      ...defaultAppRouteState,
      view: "features",
      features: { featureId: 7, tab: "knowledge", nodeId: 703 },
    });

    expect(pushState).toHaveBeenCalledWith(
      null,
      "",
      "#/features?feature=7&tab=knowledge&node=703",
    );
    pushState.mockRestore();
  });

  it("merges a feature patch and switches the view to features", () => {
    const next = mergeFeaturesRouteState(defaultAppRouteState, { tab: "repos" });

    expect(next.view).toBe("features");
    expect(next.features.tab).toBe("repos");
    expect(next.features.featureId).toBeNull();
  });
});
