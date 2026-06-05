import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";

import { queryClient } from "../src/lib/query-client";

// jsdom 没有布局引擎，CodeMirror 测量选区/光标坐标时会抛 getClientRects 异常
// （CM 内部已 try/catch，不影响功能，但污染测试输出）。补一个空实现消音。
if (typeof Range !== "undefined" && !Range.prototype.getClientRects) {
  Range.prototype.getClientRects = function getClientRects() {
    return {
      length: 0,
      item: () => null,
      [Symbol.iterator]: Array.prototype[Symbol.iterator],
    } as unknown as DOMRectList;
  };
  Range.prototype.getBoundingClientRect = function getBoundingClientRect() {
    return {
      bottom: 0,
      height: 0,
      left: 0,
      right: 0,
      top: 0,
      width: 0,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    } as DOMRect;
  };
}

beforeEach(() => {
  localStorage.clear();
  window.history.replaceState(null, "", "/");
});

afterEach(() => {
  queryClient.clear();
});
