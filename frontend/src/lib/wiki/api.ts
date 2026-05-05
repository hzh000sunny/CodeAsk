import type {
  WikiCreateNodePayload,
  WikiDocumentDetailRead,
  WikiDocumentDiffRead,
  WikiDocumentVersionListRead,
  WikiImportJobItemsRead,
  WikiImportJobRead,
  WikiImportPreflightRead,
  WikiImportSessionItemsRead,
  WikiImportSessionRead,
  WikiReportDetailRead,
  WikiReportProjectionListRead,
  WikiNodeDetailRead,
  WikiNodeRead,
  WikiSpaceRead,
  WikiSearchResultsRead,
  WikiTreeRead,
  WikiUpdateNodePayload,
} from "../../types/wiki";
import { ApiError, apiRequest } from "../api-client";
import { getSubjectId } from "../identity";

export function getWikiSpaceByFeature(featureId: number) {
  return apiRequest<WikiSpaceRead>(`/api/wiki/spaces/by-feature/${featureId}`);
}

export function getWikiTree(featureId?: number | null) {
  const params = new URLSearchParams();
  if (featureId != null) {
    params.set("feature_id", String(featureId));
  }
  const query = params.toString();
  return apiRequest<WikiTreeRead>(query ? `/api/wiki/tree?${query}` : "/api/wiki/tree");
}

export function getWikiNode(nodeId: number) {
  return apiRequest<WikiNodeDetailRead>(`/api/wiki/nodes/${nodeId}`);
}

export function createWikiNode(payload: WikiCreateNodePayload) {
  return apiRequest<WikiNodeRead>("/api/wiki/nodes", {
    method: "POST",
    body: payload,
  });
}

export function updateWikiNode(nodeId: number, payload: WikiUpdateNodePayload) {
  return apiRequest<WikiNodeRead>(`/api/wiki/nodes/${nodeId}`, {
    method: "PUT",
    body: payload,
  });
}

export function deleteWikiNode(nodeId: number) {
  return apiRequest<void>(`/api/wiki/nodes/${nodeId}`, {
    method: "DELETE",
  });
}

export function getWikiDocument(nodeId: number) {
  return apiRequest<WikiDocumentDetailRead>(`/api/wiki/documents/${nodeId}`);
}

export function saveWikiDraft(nodeId: number, bodyMarkdown: string) {
  return apiRequest<WikiDocumentDetailRead>(`/api/wiki/documents/${nodeId}/draft`, {
    method: "PUT",
    body: { body_markdown: bodyMarkdown },
  });
}

export function deleteWikiDraft(nodeId: number) {
  return apiRequest<void>(`/api/wiki/documents/${nodeId}/draft`, {
    method: "DELETE",
  });
}

export function publishWikiDocument(nodeId: number, bodyMarkdown?: string | null) {
  return apiRequest<WikiDocumentDetailRead>(`/api/wiki/documents/${nodeId}/publish`, {
    method: "POST",
    body: { body_markdown: bodyMarkdown ?? null },
  });
}

export function listWikiVersions(nodeId: number) {
  return apiRequest<WikiDocumentVersionListRead>(`/api/wiki/documents/${nodeId}/versions`);
}

export function getWikiDiff(nodeId: number, fromVersionId: number, toVersionId: number) {
  return apiRequest<WikiDocumentDiffRead>(
    `/api/wiki/documents/${nodeId}/diff?from_version_id=${fromVersionId}&to_version_id=${toVersionId}`,
  );
}

export function rollbackWikiVersion(nodeId: number, versionId: number) {
  return apiRequest<WikiDocumentDetailRead>(
    `/api/wiki/documents/${nodeId}/versions/${versionId}/rollback`,
    {
      method: "POST",
    },
  );
}

export function getWikiImportJob(jobId: number) {
  return apiRequest<WikiImportJobRead>(`/api/wiki/imports/${jobId}`);
}

export function listWikiImportJobItems(jobId: number) {
  return apiRequest<WikiImportJobItemsRead>(`/api/wiki/imports/${jobId}/items`);
}

export function preflightWikiImport(payload: {
  spaceId: number;
  parentId?: number | null;
  files: File[];
}) {
  const body = new FormData();
  body.set("space_id", String(payload.spaceId));
  if (payload.parentId != null) {
    body.set("parent_id", String(payload.parentId));
  }
  for (const file of payload.files) {
    body.append("files", file, file.webkitRelativePath || file.name);
  }
  return apiRequest<WikiImportPreflightRead>("/api/wiki/imports/preflight", {
    method: "POST",
    body,
  });
}

export function createWikiImportJob(payload: {
  spaceId: number;
  parentId?: number | null;
  files: File[];
}) {
  const body = new FormData();
  body.set("space_id", String(payload.spaceId));
  if (payload.parentId != null) {
    body.set("parent_id", String(payload.parentId));
  }
  for (const file of payload.files) {
    body.append("files", file, file.webkitRelativePath || file.name);
  }
  return apiRequest<WikiImportJobRead>("/api/wiki/imports", {
    method: "POST",
    body,
  });
}

export function applyWikiImportJob(jobId: number) {
  return apiRequest<WikiImportJobRead>(`/api/wiki/imports/${jobId}/apply`, {
    method: "POST",
  });
}

export function createWikiImportSession(payload: {
  spaceId: number;
  parentId?: number | null;
  mode: "markdown" | "directory";
}) {
  return apiRequest<WikiImportSessionRead>("/api/wiki/import-sessions", {
    method: "POST",
    body: {
      space_id: payload.spaceId,
      parent_id: payload.parentId ?? null,
      mode: payload.mode,
    },
  });
}

export function getWikiImportSession(sessionId: number) {
  return apiRequest<WikiImportSessionRead>(`/api/wiki/import-sessions/${sessionId}`);
}

export function scanWikiImportSession(
  sessionId: number,
  payload: {
    items: Array<{
      relative_path: string;
      item_kind: string;
      included: boolean;
      ignore_reason?: string | null;
    }>;
  },
) {
  return apiRequest<WikiImportSessionRead>(`/api/wiki/import-sessions/${sessionId}/scan`, {
    method: "POST",
    body: payload,
  });
}

export function listWikiImportSessionItems(sessionId: number) {
  return apiRequest<WikiImportSessionItemsRead>(`/api/wiki/import-sessions/${sessionId}/items`);
}

export function uploadWikiImportSessionItem(payload: {
  sessionId: number;
  itemId: number;
  file: File;
  onProgress?: (progressPercent: number) => void;
}) {
  const body = new FormData();
  body.set("file", payload.file, payload.file.name);
  return uploadWithProgress<
    { session: WikiImportSessionRead; item: WikiImportSessionItemsRead["items"][number] }
  >(
    `/api/wiki/import-sessions/${payload.sessionId}/items/${payload.itemId}/upload`,
    body,
    payload.onProgress,
  );
}

export function resolveWikiImportSessionItem(payload: {
  sessionId: number;
  itemId: number;
  action: "skip" | "overwrite";
}) {
  return apiRequest<{ session: WikiImportSessionRead; item: WikiImportSessionItemsRead["items"][number] }>(
    `/api/wiki/import-sessions/${payload.sessionId}/items/${payload.itemId}/resolve`,
    {
      method: "POST",
      body: { action: payload.action },
    },
  );
}

export function bulkResolveWikiImportSession(payload: {
  sessionId: number;
  action: "skip_all" | "overwrite_all";
}) {
  return apiRequest<WikiImportSessionRead>(
    `/api/wiki/import-sessions/${payload.sessionId}/bulk-resolve`,
    {
      method: "POST",
      body: { action: payload.action },
    },
  );
}

export function cancelWikiImportSession(sessionId: number) {
  return apiRequest<WikiImportSessionRead>(`/api/wiki/import-sessions/${sessionId}/cancel`, {
    method: "POST",
  });
}

export function retryWikiImportSessionItem(payload: {
  sessionId: number;
  itemId: number;
}) {
  return apiRequest<{ session: WikiImportSessionRead; item: WikiImportSessionItemsRead["items"][number] }>(
    `/api/wiki/import-sessions/${payload.sessionId}/items/${payload.itemId}/retry`,
    {
      method: "POST",
    },
  );
}

export function retryFailedWikiImportSession(sessionId: number) {
  return apiRequest<WikiImportSessionRead>(`/api/wiki/import-sessions/${sessionId}/retry`, {
    method: "POST",
  });
}

function uploadWithProgress<T>(
  path: string,
  body: FormData,
  onProgress?: (progressPercent: number) => void,
) {
  return new Promise<T>((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", path);
    request.withCredentials = true;
    request.setRequestHeader("X-Subject-Id", getSubjectId());
    request.upload.addEventListener("progress", (event) => {
      if (!event.lengthComputable || onProgress == null || event.total <= 0) {
        return;
      }
      onProgress(Math.max(0, Math.min(100, Math.round((event.loaded / event.total) * 100))));
    });
    request.addEventListener("load", () => {
      const contentType = request.getResponseHeader("Content-Type") ?? "";
      const detail = parseXhrResponseBody(request.responseText, contentType);
      if (request.status < 200 || request.status >= 300) {
        reject(new ApiError(request.status, detail));
        return;
      }
      resolve(detail as T);
    });
    request.addEventListener("error", () => {
      reject(new Error("Network request failed"));
    });
    request.send(body);
  });
}

function parseXhrResponseBody(body: string, contentType: string) {
  if (contentType.includes("application/json")) {
    return JSON.parse(body) as unknown;
  }
  return body;
}

export function listWikiReportProjections(featureId: number) {
  return apiRequest<WikiReportProjectionListRead>(
    `/api/wiki/reports/projections?feature_id=${featureId}`,
  );
}

export function getWikiReportByNode(nodeId: number) {
  return apiRequest<WikiReportDetailRead>(`/api/wiki/reports/by-node/${nodeId}`);
}

export function searchWiki(
  query: string,
  options?: {
    featureId?: number | null;
    currentFeatureId?: number | null;
    limit?: number;
  },
) {
  const featureId = options?.featureId;
  const currentFeatureId = options?.currentFeatureId;
  const limit = options?.limit ?? 20;
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  if (featureId != null) {
    params.set("feature_id", String(featureId));
  }
  if (currentFeatureId != null) {
    params.set("current_feature_id", String(currentFeatureId));
  }
  return apiRequest<WikiSearchResultsRead>(`/api/wiki/search?${params.toString()}`);
}

export function getWikiAssetContentUrl(nodeId: number) {
  return `/api/wiki/assets/${nodeId}/content`;
}
