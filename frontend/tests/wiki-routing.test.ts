import { describe, expect, it, vi } from "vitest";

import {
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
