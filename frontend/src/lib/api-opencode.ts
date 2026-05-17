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
