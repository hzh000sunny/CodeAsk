import type { AuditLogResponse } from "../types/api";
import { apiRequest } from "./api-client";

export function listAuditLog(entityType: string, entityId: string, limit = 50) {
  const params = new URLSearchParams({
    entity_type: entityType,
    entity_id: entityId,
    limit: String(limit),
  });
  return apiRequest<AuditLogResponse>(`/api/audit-log?${params.toString()}`);
}
