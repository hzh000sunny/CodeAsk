import type { SystemSettingsResponse } from "../types/api";
import { apiRequest } from "./api-client";

export function getSystemSettings() {
  return apiRequest<SystemSettingsResponse>("/api/system-settings");
}

export function updateSystemSettings(payload: Partial<SystemSettingsResponse>) {
  return apiRequest<SystemSettingsResponse>("/api/system-settings", {
    method: "PATCH",
    body: payload,
  });
}
