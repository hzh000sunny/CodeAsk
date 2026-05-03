import { describe, expect, it } from "vitest";

import { ApiError } from "../src/lib/api";
import { messageFromError } from "../src/components/features/feature-utils";

describe("feature workbench utilities", () => {
  it("surfaces FastAPI detail messages from API errors", () => {
    const error = new ApiError(422, {
      detail: "report must include at least one log or code evidence before verification",
    });

    expect(messageFromError(error)).toBe(
      "report must include at least one log or code evidence before verification",
    );
  });
});
