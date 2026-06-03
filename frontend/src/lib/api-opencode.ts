import { apiRequest } from "./api-client";

export interface OpencodeStatusResponse {
  active_session_count?: number | null;
  base_url?: string | null;
  configured_bin?: string | null;
  last_error?: string | null;
  last_error_code?: string | null;
  last_health_at?: string | null;
  log_file?: string | null;
  pid?: number | null;
  port?: number | null;
  resolved_bin?: string | null;
  returncode?: number | null;
  running: boolean;
  version?: string | null;
}

export function getOpencodeStatus() {
  return apiRequest<OpencodeStatusResponse>("/api/admin/opencode/status");
}

export type OpencodePermissionValue = "allow" | "deny";
export type OpencodeBashMode = "allow" | "deny" | "whitelist";

export interface OpencodeToolCatalogItem {
  key: string;
  label: string;
  purpose: string;
  group: string;
  openviking: boolean;
}

export interface OpencodeBashPermission {
  mode: OpencodeBashMode;
  patterns: string[];
}

export interface OpencodePermissionsConfig {
  tools: Record<string, OpencodePermissionValue>;
  bash: OpencodeBashPermission;
}

export interface OpencodePermissionsResponse extends OpencodePermissionsConfig {
  openviking_enabled: boolean;
  catalog: {
    tools: OpencodeToolCatalogItem[];
    bash_suggestions: string[];
  };
  defaults: OpencodePermissionsConfig & { version?: number };
}

export interface OpencodePermissionsUpdateRequest {
  tools: Record<string, OpencodePermissionValue>;
  bash: OpencodeBashPermission;
}

export function getOpencodePermissions() {
  return apiRequest<OpencodePermissionsResponse>("/api/admin/opencode/permissions");
}

export function updateOpencodePermissions(payload: OpencodePermissionsUpdateRequest) {
  return apiRequest<OpencodePermissionsResponse>("/api/admin/opencode/permissions", {
    method: "PUT",
    body: payload,
  });
}
