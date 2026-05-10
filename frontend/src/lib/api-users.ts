import type { UserCandidateResponse, UserResponse } from "../types/api";
import { apiRequest } from "./api-client";

export function getCurrentUser() {
  return apiRequest<UserResponse>("/api/users/me");
}

export function updateCurrentUser(payload: { username: string }) {
  return apiRequest<UserResponse>("/api/users/me", {
    method: "PATCH",
    body: payload,
  });
}

export function updateCurrentUserPassword(payload: { password: string }) {
  return apiRequest<void>("/api/users/me/password", {
    method: "PATCH",
    body: payload,
  });
}

export function searchUsers(query: string, limit = 10) {
  const params = new URLSearchParams({
    q: query,
    limit: String(limit),
  });
  return apiRequest<UserCandidateResponse[]>(`/api/users/search?${params.toString()}`);
}

export function clearUserPassword(userId: string) {
  return apiRequest<UserResponse>(`/api/users/${userId}/password/clear`, {
    method: "POST",
  });
}
