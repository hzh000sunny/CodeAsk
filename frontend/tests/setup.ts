import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";

import { queryClient } from "../src/lib/query-client";

beforeEach(() => {
  localStorage.clear();
  window.history.replaceState(null, "", "/");
});

afterEach(() => {
  queryClient.clear();
});
