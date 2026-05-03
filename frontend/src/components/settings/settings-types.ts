export type LlmScope = "user" | "global";
export type LlmProtocol = "openai" | "anthropic";

export type LlmUpdatePayload = Partial<{
  name: string;
  protocol: LlmProtocol;
  base_url: string | null;
  api_key: string;
  model_name: string;
  enabled: boolean;
}>;

export type RepoSource = "git" | "local_dir";

export interface RepoUpdatePayload {
  name: string;
  source: RepoSource;
  url: string | null;
  local_path: string | null;
}
