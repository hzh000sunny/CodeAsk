import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  adminLogin,
  apiRequest,
  listSessionTraces,
  listSessionTurns,
  promoteSessionAttachmentToWiki,
  uploadSessionAttachment,
} from "../src/lib/api";
import { getSubjectId } from "../src/lib/identity";

describe("frontend api client", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("persists a stable self-reported subject id", () => {
    const first = getSubjectId();
    const second = getSubjectId();

    expect(first).toBe(second);
    expect(first).toMatch(/^client_[A-Za-z0-9._-]+$/);
  });

  it("injects X-Subject-Id into every API request", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(JSON.stringify({ ok: true }), {
          headers: { "Content-Type": "application/json" },
        }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await apiRequest<{ ok: boolean }>("/api/healthz");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, init] = fetchMock.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    expect(new Headers(init.headers).get("X-Subject-Id")).toBe(getSubjectId());
  });

  it("uploads session attachments as form data with the selected kind", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            id: "att_1",
            session_id: "sess_1",
            kind: "log",
            display_name: "app.log",
            original_filename: "app.log",
            file_path: "/tmp/app.log",
            mime_type: "text/plain",
            size_bytes: 5,
            created_at: "2026-04-30T10:00:00",
            updated_at: "2026-04-30T10:00:00",
          }),
          {
            headers: { "Content-Type": "application/json" },
          },
        ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await uploadSessionAttachment(
      "sess_1",
      new File(["hello"], "app.log", { type: "text/plain" }),
      "log",
    );

    const [path, init] = fetchMock.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    expect(path).toBe("/api/sessions/sess_1/attachments");
    expect(init.method).toBe("POST");
    expect(init.body).toBeInstanceOf(FormData);
    expect(new Headers(init.headers).get("X-Subject-Id")).toBe(getSubjectId());
  });

  it("posts session attachment promotion payload to the wiki promotion endpoint", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            node: {
              id: 701,
              space_id: 70,
              feature_id: 7,
              parent_id: 700,
              type: "document",
              name: "数据库节点 A 日志",
              path: "knowledge-base/db-node-a-log",
              system_role: null,
              sort_order: 0,
              created_at: "2026-05-06T10:00:00",
              updated_at: "2026-05-06T10:00:00",
            },
            document_id: 1701,
            source_id: 33,
          }),
          {
            headers: { "Content-Type": "application/json" },
          },
        ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await promoteSessionAttachmentToWiki({
      sessionId: "sess_1",
      attachmentId: "att_1",
      spaceId: 70,
      parentId: 700,
      targetKind: "document",
      name: "数据库节点 A 日志",
    });

    const [path, init] = fetchMock.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    expect(path).toBe("/api/wiki/promotions/session-attachment");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({
      session_id: "sess_1",
      attachment_id: "att_1",
      space_id: 70,
      parent_id: 700,
      target_kind: "document",
      name: "数据库节点 A 日志",
    });
  });

  it("posts bootstrap admin username and password when logging in", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            subject_id: "admin",
            display_name: "Admin",
            role: "admin",
            authenticated: true,
          }),
          {
            headers: { "Content-Type": "application/json" },
          },
        ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await adminLogin({ username: "admin", password: "admin" });

    const [path, init] = fetchMock.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    expect(path).toBe("/api/auth/admin/login");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({
      username: "admin",
      password: "admin",
    });
  });

  it("loads persisted session turns by session id", async () => {
    const fetchMock = vi.fn(async () => jsonResponse([{ id: "turn_1" }]));
    vi.stubGlobal("fetch", fetchMock);

    await listSessionTurns("sess_1");

    const [path, init] = fetchMock.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    expect(path).toBe("/api/sessions/sess_1/turns");
    expect(init.method).toBeUndefined();
    expect(new Headers(init.headers).get("X-Subject-Id")).toBe(getSubjectId());
  });

  it("loads persisted session runtime traces by session id", async () => {
    const fetchMock = vi.fn(async () => jsonResponse([{ id: "tr_1" }]));
    vi.stubGlobal("fetch", fetchMock);

    await listSessionTraces("sess_1");

    const [path, init] = fetchMock.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    expect(path).toBe("/api/sessions/sess_1/traces");
    expect(init.method).toBeUndefined();
    expect(new Headers(init.headers).get("X-Subject-Id")).toBe(getSubjectId());
  });
});

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
