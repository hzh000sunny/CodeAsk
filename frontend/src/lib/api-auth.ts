import type { AuthMeResponse } from "../types/api";
import { apiRequest } from "./api-client";

export function getMe() {
  return apiRequest<AuthMeResponse>("/api/auth/me");
}

export function adminLogin(payload: { username: string; password: string }) {
  return apiRequest<AuthMeResponse>("/api/auth/admin/login", {
    method: "POST",
    body: payload,
  });
}

export function logout() {
  return apiRequest<void>("/api/auth/logout", {
    method: "POST",
  });
}
