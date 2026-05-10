import type { FeatureAdminRead, UserCandidateResponse } from "../types/api";
import { apiRequest } from "./api-client";

export function listFeatureAdmins(featureId: number) {
  return apiRequest<FeatureAdminRead[]>(`/api/features/${featureId}/admins`);
}

export function searchFeatureAdminCandidates(
  featureId: number,
  query: string,
  limit = 10,
) {
  const params = new URLSearchParams({
    q: query,
    limit: String(limit),
  });
  return apiRequest<UserCandidateResponse[]>(
    `/api/features/${featureId}/admin-candidates?${params.toString()}`,
  );
}

export function addFeatureAdmin(featureId: number, userId: string) {
  return apiRequest<FeatureAdminRead>(`/api/features/${featureId}/admins`, {
    method: "POST",
    body: { user_id: userId },
  });
}

export function removeFeatureAdmin(featureId: number, userId: string) {
  return apiRequest<void>(`/api/features/${featureId}/admins/${userId}`, {
    method: "DELETE",
  });
}
