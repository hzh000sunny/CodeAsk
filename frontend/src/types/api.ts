export interface SessionResponse {
  id: string;
  title: string;
  created_by_subject_id: string;
  status: string;
  pinned: boolean;
  title_source: "default" | "auto" | "manual";
  title_generated_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface SessionTurnResponse {
  id: string;
  session_id: string;
  turn_index: number;
  role: "user" | "agent";
  content: string;
  evidence: unknown | null;
  stopped_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface AgentTraceResponse {
  id: string;
  session_id: string;
  turn_id: string;
  stage: string;
  event_type: string;
  payload: unknown;
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

export interface SessionReportPrepared {
  existing_report_id: number | null;
  feature_id: number | null;
  inferred_feature_ids: number[];
  title: string;
  body_markdown: string;
}

export interface SessionReportPrepareStatus {
  request_id: string;
  status: "running" | "succeeded" | "failed";
  draft: SessionReportPrepared | null;
  error: string | null;
}

export type FeedbackVerdict = "solved" | "partial" | "wrong";

export interface FeedbackAck {
  ok: true;
}

export interface FrontendEventAck {
  ok: true;
  id: string;
}

export interface AuditLogEntry {
  id: string;
  entity_type: string;
  entity_id: string;
  action: string;
  from_status: string | null;
  to_status: string | null;
  subject_id: string;
  at: string;
}

export interface AuditLogResponse {
  entries: AuditLogEntry[];
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
  stage: string;
  enabled: boolean;
  priority: number;
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
  reasoning_profile: string;
  reasoning_profile_json: string | null;
  agent_runtime_backend: string;
  agent_runtime_profile: string | null;
  agent_runtime_status: string;
  agent_runtime_tested_at: string | null;
  agent_runtime_error: string | null;
  agent_runtime_test_result_json: unknown | null;
  opencode_provider_profile: string | null;
  opencode_provider_status: string;
  opencode_provider_tested_at: string | null;
  opencode_provider_error: string | null;
  opencode_provider_test_result_json: unknown | null;
}

export interface LLMConfigTestResponse {
  status: "ok" | "failed";
  profile_id: string | null;
  provider_npm: string | null;
  text_preview: string | null;
  error: string | null;
  tested_at: string;
  result: unknown | null;
}

export interface AuthMeResponse {
  subject_id: string;
  display_name: string;
  role: "member" | "admin";
  authenticated: boolean;
}

export interface UserResponse {
  id: string;
  username: string;
  role: "member" | "admin";
  last_login_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface UserCandidateResponse {
  id: string;
  username: string;
}

export interface OpenVikingStatusResponse {
  running: boolean;
  available?: boolean;
  degraded?: boolean;
  base_url?: string | null;
  port?: number | null;
  pid?: number | null;
  version?: string | null;
  installed_version?: string | null;
  verified_version?: string | null;
  last_error?: string | null;
  last_error_code?: string | null;
  consecutive_failures?: number | null;
  log_tail?: string | null;
  config_file?: string | null;
  workspace_path?: string | null;
  log_file?: string | null;
  queue: Record<string, number>;
  indexing?: {
    phase: "idle" | "syncing" | "embedding" | "indexed" | "blocked" | "degraded";
    message: string;
    sync_jobs: {
      total: number;
      pending: number;
      running: number;
      indexed: number;
      failed: number;
      cancelled: number;
    };
    embedding_queue: {
      pending: number;
      processing: number;
      completed?: number;
      failed?: number;
      total_visible: number;
      oldest_pending_age_seconds?: number | null;
      current_processing_age_seconds?: number | null;
      error?: string | null;
    };
    progress_percent: number | null;
    eta_seconds: number | null;
    eta_label: string | null;
    items_per_minute?: number | null;
    eta_sample_seconds?: number | null;
    eta_safety_factor?: number | null;
    updated_at: string;
  };
  metrics_5min?: {
    collected: boolean;
    window_seconds: number;
    throughput_per_min: number | null;
    latency_p95_ms: number | null;
    latency_samples?: number | null;
    breaker_trips: number | null;
    message: string | null;
  };
  health?: {
    healthy: boolean;
    version: string | null;
    error: string | null;
  };
  ollama?: {
    configured?: boolean;
    healthy: boolean;
    model_available: boolean;
    required_model: string | null;
    models: string[];
    error: string | null;
  };
  embedding?: {
    provider: string;
    model: string;
    dimension?: number | null;
    healthy?: boolean;
    max_concurrent?: number | null;
  };
  vlm?: {
    enabled: boolean;
    provider: string | null;
    model: string | null;
  };
  doctor?: OpenVikingDoctorReport;
}

export interface OpenVikingDoctorCheck {
  ok: boolean;
  detail: string | null;
  fix: string | null;
}

export interface OpenVikingDoctorReport {
  embedding?: OpenVikingDoctorCheck;
  vlm?: OpenVikingDoctorCheck;
  ollama?: OpenVikingDoctorCheck;
}

export interface OpenVikingConfigTestResponse {
  doctor: OpenVikingDoctorReport;
}

export interface OpenVikingSyncJob {
  id: string;
  source_type: string;
  source_id: string;
  display_name: string | null;
  feature_slug: string | null;
  viking_uri: string | null;
  status: string;
  attempts: number;
  next_retry_at: string | null;
  last_synced_at: string | null;
  last_indexed_at: string | null;
  error: string | null;
  progress: unknown | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface OpenVikingSyncJobsResponse {
  items: OpenVikingSyncJob[];
  total: number;
  page: number;
  limit: number;
}

export interface OpenVikingSyncJobsSummaryResponse {
  counts: Record<string, number>;
}

export interface OpenVikingDashboardEvent {
  id: number;
  event_type: string;
  source_type: string | null;
  source_id: string | null;
  sync_job_id: string | null;
  triggered_by: string | null;
  payload: unknown | null;
  outcome: "info" | "success" | "warning" | "error";
  created_at: string | null;
}

export interface OpenVikingEventsResponse {
  event_types?: string[];
  items: OpenVikingDashboardEvent[];
  limit: number;
  next_before_id: number | null;
  page: number;
  total: number;
  total_pages: number;
}

export type OpenVikingEmbeddingProvider =
  | "local"
  | "ollama"
  | "openai"
  | "azure"
  | "volcengine"
  | "vikingdb"
  | "jina"
  | "gemini"
  | "voyage"
  | "dashscope"
  | "minimax"
  | "cohere"
  | "litellm";

export interface OpenVikingLocalCacheStatus {
  model_cached: boolean;
  will_download_on_start: boolean;
  cache_path: string | null;
}

export interface OpenVikingEmbeddingResponse {
  id: number;
  provider: string;
  base_url: string | null;
  model: string;
  dimension: number | null;
  input: string;
  max_concurrent: number;
  api_key_configured: boolean;
  api_key_masked: string | null;
  local_cache: OpenVikingLocalCacheStatus | null;
  local_model_cache_dir?: string | null;
  rebuild_status: string;
  rebuild_progress: unknown | null;
}

export interface OpenVikingEmbeddingCandidate {
  provider: string;
  base_url: string;
  model: string;
  source: string;
}

export interface OpenVikingEmbeddingSecretRef {
  provider: string;
  base_url: string;
}

export interface OpenVikingEmbeddingCandidatesResponse {
  items: OpenVikingEmbeddingCandidate[];
  configured_secrets?: OpenVikingEmbeddingSecretRef[];
  providers?: string[];
  ollama: {
    base_url?: string;
    healthy: boolean;
    model_available: boolean;
    error: string | null;
  };
}

export interface OpenVikingEmbeddingApplyRequest {
  provider: string;
  base_url?: string | null;
  model: string;
  dimension?: number | null;
  max_concurrent?: number;
  input?: string;
  api_key?: string | null;
  extra?: Record<string, unknown> | null;
}

export interface OpenVikingVLMResponse {
  id: number | null;
  enabled: boolean;
  provider: string | null;
  model: string | null;
  base_url: string | null;
  temperature: number;
  timeout: number;
  max_retries: number;
  api_key_configured: boolean;
  api_key_masked: string | null;
  extra: Record<string, unknown> | null;
  activated_at: string | null;
  activated_by: string | null;
}

export interface OpenVikingVLMApplyRequest {
  enabled?: boolean;
  provider: string;
  base_url?: string | null;
  model: string;
  api_key?: string | null;
  temperature?: number;
  timeout?: number;
  max_retries?: number;
  extra?: Record<string, unknown> | null;
}

export interface OpenVikingTuningItem {
  key: string;
  value: string;
  activated_at: string;
  activated_by: string | null;
  previous_value: string | null;
  recommended: string | null;
  notes: string | null;
}

export interface OpenVikingTuningResponse {
  scopes: Record<string, OpenVikingTuningItem[]>;
  preset: string;
}

export interface OpenVikingTuningChange {
  scope: string;
  key: string;
  value: string;
  notes?: string | null;
}

export interface OpenVikingTuningApplyRequest {
  changes: OpenVikingTuningChange[];
}

export interface OpenVikingTuningApplyResponse {
  applied: Array<{
    scope: string;
    key: string;
    value: string;
    previous_value: string | null;
  }>;
  rejected: Array<{
    scope: string;
    key: string;
    reason: string;
  }>;
  estimated_downtime_seconds: number;
}

export interface OpenVikingTuningPresetResponse {
  preset: string;
  detected_host: Record<string, unknown>;
  preset_values: Array<{
    scope: string;
    key: string;
    value: string;
    recommended: string;
  }>;
}

export interface OpenVikingOllamaSnippetResponse {
  snippet: string;
  num_parallel: string;
  num_thread: string;
}

export interface OpenVikingOllamaVerifyResponse {
  verified: boolean;
  expected_num_parallel: number;
  observed_parallel: number | null;
  error: string | null;
}

export interface OpenVikingMutationCountResponse {
  queued: number;
  rebuild_status?: number | string;
}

export interface FeatureAdminRead {
  feature_id: number;
  user_id: string;
  username: string;
  created_by_user_id: string;
  created_at: string;
}

export interface SystemSettingsResponse {
  session_attachments_enabled: boolean;
}
