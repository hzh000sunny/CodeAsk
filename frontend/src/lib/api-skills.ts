import type { SkillResponse } from "../types/api";
import { apiRequest } from "./api-client";

export function listSkills() {
  return apiRequest<SkillResponse[]>("/api/skills");
}

export function createSkill(payload: {
  name: string;
  scope: "global" | "feature";
  feature_id?: number | null;
  stage?: string;
  enabled?: boolean;
  priority?: number;
  prompt_template: string;
}) {
  return apiRequest<SkillResponse>("/api/skills", {
    method: "POST",
    body: payload,
  });
}

export function updateSkill(
  skillId: string,
  payload: Partial<{
    name: string;
    stage: string;
    enabled: boolean;
    priority: number;
    prompt_template: string;
  }>,
) {
  return apiRequest<SkillResponse>(`/api/skills/${skillId}`, {
    method: "PATCH",
    body: payload,
  });
}

export function deleteSkill(skillId: string) {
  return apiRequest<void>(`/api/skills/${skillId}`, {
    method: "DELETE",
  });
}
