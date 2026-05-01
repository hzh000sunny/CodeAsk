export interface SessionResponse {
  id: string;
  title: string;
  created_by_subject_id: string;
  status: string;
  pinned: boolean;
  created_at: string;
  updated_at: string;
}

export interface AttachmentResponse {
  id: string;
  session_id: string;
  kind: "log" | "image" | "doc" | "other";
  display_name: string;
  original_filename: string;
  aliases: string[];
  reference_names: string[];
  description: string | null;
  file_path: string;
  mime_type: string;
  size_bytes: number | null;
  created_at: string;
  updated_at: string;
}

export interface FeatureRead {
  id: number;
  name: string;
  slug: string;
  description: string | null;
  owner_subject_id: string;
  summary_text: string | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentRead {
  id: number;
  feature_id: number;
  kind: string;
  title: string;
  path: string;
  tags_json: string[] | null;
  summary: string | null;
  is_deleted: boolean;
  uploaded_by_subject_id: string;
  created_at: string;
  updated_at: string;
}

export interface ReportRead {
  id: number;
  feature_id: number | null;
  title: string;
  body_markdown: string;
  metadata_json: Record<string, unknown>;
  status: string;
  verified: boolean;
  verified_by: string | null;
  verified_at: string | null;
  created_by_subject_id: string;
  created_at: string;
  updated_at: string;
}

export type RepoSource = "git" | "local_dir";
export type RepoStatus = "registered" | "cloning" | "ready" | "failed";

export interface RepoOut {
  id: string;
  name: string;
  source: RepoSource;
  url: string | null;
  local_path: string | null;
  bare_path: string;
  status: RepoStatus;
  error_message: string | null;
  last_synced_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface SkillResponse {
  id: string;
  name: string;
  scope: string;
  feature_id: number | null;
  prompt_template: string;
}

export interface LLMConfigResponse {
  id: string;
  name: string;
  scope: "global" | "user";
  owner_subject_id: string | null;
  protocol: string;
  base_url: string | null;
  api_key_masked: string;
  model_name: string;
  max_tokens: number;
  temperature: number;
  is_default: boolean;
  enabled: boolean;
  rpm_limit: number | null;
  quota_remaining: number | null;
}

export interface AuthMeResponse {
  subject_id: string;
  display_name: string;
  role: "member" | "admin";
  authenticated: boolean;
}
