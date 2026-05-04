import type {
  WikiCreateNodePayload,
  WikiDocumentDetailRead,
  WikiDocumentDiffRead,
  WikiDocumentVersionListRead,
  WikiImportJobItemsRead,
  WikiImportJobRead,
  WikiImportPreflightRead,
  WikiNodeDetailRead,
  WikiNodeRead,
  WikiSpaceRead,
  WikiTreeRead,
  WikiUpdateNodePayload,
} from "../../types/wiki";
import { apiRequest } from "../api-client";

export function getWikiSpaceByFeature(featureId: number) {
  return apiRequest<WikiSpaceRead>(`/api/wiki/spaces/by-feature/${featureId}`);
}

export function getWikiTree(featureId: number) {
  return apiRequest<WikiTreeRead>(`/api/wiki/tree?feature_id=${featureId}`);
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

export function getWikiAssetContentUrl(nodeId: number) {
  return `/api/wiki/assets/${nodeId}/content`;
}
