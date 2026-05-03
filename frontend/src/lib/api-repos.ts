import type { RepoOut } from "../types/api";
import { apiRequest } from "./api-client";

export function listRepos() {
  return apiRequest<{ repos: RepoOut[] }>("/api/repos").then(
    (payload) => payload.repos,
  );
}

export function listFeatureRepos(featureId: number) {
  return apiRequest<{ repos: RepoOut[] }>(
    `/api/features/${featureId}/repos`,
  ).then((payload) => payload.repos);
}

export function linkFeatureRepo(featureId: number, repoId: string) {
  return apiRequest<RepoOut>(`/api/features/${featureId}/repos/${repoId}`, {
    method: "POST",
  });
}

export function unlinkFeatureRepo(featureId: number, repoId: string) {
  return apiRequest<void>(`/api/features/${featureId}/repos/${repoId}`, {
    method: "DELETE",
  });
}

export function createRepo(payload: {
  name: string;
  source: "git" | "local_dir";
  url?: string | null;
  local_path?: string | null;
}) {
  return apiRequest<RepoOut>("/api/repos", {
    method: "POST",
    body: payload,
  });
}

export function updateRepo(
  repoId: string,
  payload: Partial<{
    name: string;
    source: "git" | "local_dir";
    url: string | null;
    local_path: string | null;
  }>,
) {
  return apiRequest<RepoOut>(`/api/repos/${repoId}`, {
    method: "PATCH",
    body: payload,
  });
}

export function deleteRepo(repoId: string) {
  return apiRequest<void>(`/api/repos/${repoId}`, {
    method: "DELETE",
  });
}

export function refreshRepo(repoId: string) {
  return apiRequest<RepoOut>(`/api/repos/${repoId}/refresh`, {
    method: "POST",
  });
}
