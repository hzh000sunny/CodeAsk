import { getSubjectId } from "./identity";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  requestId: string | null;

  constructor(status: number, detail: unknown, requestId: string | null = null) {
    super(apiErrorMessage(status, detail, requestId));
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.requestId = requestId;
  }
}

export type JsonBody = object | Array<unknown>;
export type ApiRequestInit = Omit<RequestInit, "body"> & {
  body?: BodyInit | JsonBody | null;
  requestId?: string;
};

export async function apiRequest<T>(
  path: string,
  init: ApiRequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("X-Subject-Id", getSubjectId());
  if (init.requestId?.trim()) {
    headers.set("X-CodeAsk-Request-Id", init.requestId.trim());
  }

  let body = init.body;
  if (body && !(body instanceof FormData) && typeof body !== "string") {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(body);
  }

  const { requestId: _requestId, ...requestInit } = init;
  const response = await fetch(path, {
    ...requestInit,
    headers,
    body: body as BodyInit | null | undefined,
    credentials: "same-origin",
  });

  if (!response.ok) {
    const detail = await readResponse(response);
    throw new ApiError(
      response.status,
      detail,
      response.headers.get("X-CodeAsk-Request-Id"),
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await readResponse(response)) as T;
}

async function readResponse(response: Response) {
  const contentType = response.headers.get("Content-Type") ?? "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return response.text();
}

function apiErrorMessage(
  status: number,
  detail: unknown,
  requestId?: string | null,
) {
  const message = apiErrorMessageBase(status, detail, requestId);
  return message;
}

function apiErrorMessageBase(status: number, detail: unknown, requestId?: string | null) {
  if (typeof detail === "string") {
    const text = detail.trim() || `API request failed with ${status}`;
    return appendRequestId(text, requestId);
  }
  if (typeof detail === "object" && detail !== null && "detail" in detail) {
    const nested = (detail as { detail?: unknown }).detail;
    if (typeof nested === "string" && nested.trim()) {
      return appendRequestId(nested, requestId);
    }
  }
  return appendRequestId(`API request failed with ${status}`, requestId);
}

function appendRequestId(message: string, requestId?: string | null) {
  if (!requestId?.trim()) {
    return message;
  }
  return `${message}（请求ID：${requestId.trim()}）`;
}
