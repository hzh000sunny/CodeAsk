import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AppFeedbackProvider } from "../src/components/feedback/AppFeedback";
import { FeatureAdminsPanel } from "../src/components/features/FeatureAdminsPanel";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderPanel(featureId = 7) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AppFeedbackProvider>
        <FeatureAdminsPanel featureId={featureId} />
      </AppFeedbackProvider>
    </QueryClientProvider>,
  );
}

describe("FeatureAdminsPanel", () => {
  it("lets non-admin users view feature admins without management actions", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path === "/api/auth/me") {
        return jsonResponse({
          subject_id: "user_member",
          display_name: "member",
          role: "member",
          authenticated: true,
        });
      }
      if (path === "/api/features/7/admins") {
        return jsonResponse([
          {
            feature_id: 7,
            user_id: "user_alice",
            username: "alice",
            created_by_user_id: "admin",
            created_at: "2026-05-10T10:00:00",
          },
        ]);
      }
      throw new Error(`unexpected request ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPanel();

    expect(await screen.findByText("alice")).toBeInTheDocument();
    expect(screen.queryByLabelText("搜索可添加用户")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /移除管理员/ }),
    ).not.toBeInTheDocument();
  });

  it("lets admin search, add, and remove feature admins", async () => {
    let admins = [
      {
        feature_id: 7,
        user_id: "user_alice",
        username: "alice",
        created_by_user_id: "admin",
        created_at: "2026-05-10T10:00:00",
      },
    ];
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        if (path === "/api/auth/me") {
          return jsonResponse({
            subject_id: "admin",
            display_name: "Admin",
            role: "admin",
            authenticated: true,
          });
        }
        if (path === "/api/features/7/admins" && !init?.method) {
          return jsonResponse(admins);
        }
        if (path === "/api/features/7/admin-candidates?q=bob&limit=10") {
          return jsonResponse([{ id: "user_bob", username: "bob" }]);
        }
        if (path === "/api/features/7/admins" && init?.method === "POST") {
          const created = {
            feature_id: 7,
            user_id: "user_bob",
            username: "bob",
            created_by_user_id: "admin",
            created_at: "2026-05-10T10:01:00",
          };
          admins = [...admins, created];
          return jsonResponse(created, 201);
        }
        if (
          path === "/api/features/7/admins/user_alice" &&
          init?.method === "DELETE"
        ) {
          admins = admins.filter((admin) => admin.user_id !== "user_alice");
          return new Response(null, { status: 204 });
        }
        throw new Error(`unexpected request ${path}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    renderPanel();

    expect(await screen.findByText("alice")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("搜索可添加用户"), {
      target: { value: "bob" },
    });
    fireEvent.click(await screen.findByRole("button", { name: "添加 bob" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/features/7/admins",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ user_id: "user_bob" }),
        }),
      );
    });
    expect(await screen.findByText("bob")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "移除管理员 alice" }));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/features/7/admins/user_alice",
        expect.objectContaining({ method: "DELETE" }),
      );
    });
  });
});
