export interface WikiSpaceRead {
  id: number;
  feature_id: number;
  scope: string;
  display_name: string;
  slug: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface WikiNodeRead {
  id: number;
  space_id: number;
  parent_id: number | null;
  type: "folder" | "document" | "asset" | "report_ref" | string;
  name: string;
  path: string;
  system_role: string | null;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface WikiNodePermissions {
  read: boolean;
  write: boolean;
  admin: boolean;
}

export interface WikiNodeDetailRead extends WikiNodeRead {
  permissions: WikiNodePermissions;
}

export interface WikiTreeRead {
  space: WikiSpaceRead;
  nodes: WikiNodeRead[];
}

export interface WikiDocumentResolvedRef {
  target: string;
  kind: "image" | "link" | string;
  resolved_path: string;
  resolved_node_id: number | null;
  broken: boolean;
}

export interface WikiDocumentBrokenRefs {
  links: WikiDocumentResolvedRef[];
  assets: WikiDocumentResolvedRef[];
}

export interface WikiDocumentDetailRead {
  document_id: number;
  node_id: number;
  title: string;
  current_version_id: number | null;
  current_body_markdown: string | null;
  draft_body_markdown: string | null;
  index_status: string;
  broken_refs_json: WikiDocumentBrokenRefs;
  resolved_refs_json: WikiDocumentResolvedRef[];
  provenance_json: Record<string, unknown> | null;
  permissions: WikiNodePermissions;
}

export interface WikiDocumentVersionRead {
  id: number;
  document_id: number;
  version_no: number;
  body_markdown: string;
  created_by_subject_id: string;
  created_at: string;
  updated_at: string;
}

export interface WikiDocumentVersionListRead {
  versions: WikiDocumentVersionRead[];
}

export interface WikiDocumentDiffRead {
  from_version_id: number;
  from_version_no: number;
  to_version_id: number;
  to_version_no: number;
  patch: string;
}

export interface WikiImportPreflightIssueRead {
  severity: string;
  code: string;
  message: string;
  target: string | null;
  resolved_path: string | null;
}

export interface WikiImportPreflightItemRead {
  relative_path: string;
  kind: string;
  target_path: string;
  status: string;
  issues: WikiImportPreflightIssueRead[];
}

export interface WikiImportPreflightSummaryRead {
  total_files: number;
  document_count: number;
  asset_count: number;
  conflict_count: number;
  warning_count: number;
}

export interface WikiImportPreflightRead {
  ready: boolean;
  summary: WikiImportPreflightSummaryRead;
  items: WikiImportPreflightItemRead[];
}

export interface WikiImportJobRead {
  id: number;
  space_id: number;
  status: string;
  requested_by_subject_id: string;
  created_at: string;
  updated_at: string;
  summary: WikiImportPreflightSummaryRead;
}

export interface WikiImportJobItemRead {
  id: number;
  source_path: string;
  target_path: string | null;
  item_kind: string | null;
  status: string;
  warnings: Array<Record<string, unknown>>;
  staging_path: string | null;
  result_node_id: number | null;
}

export interface WikiImportJobItemsRead {
  items: WikiImportJobItemRead[];
}

export interface WikiCreateNodePayload {
  space_id: number;
  parent_id?: number | null;
  type: "folder" | "document";
  name: string;
}

export interface WikiUpdateNodePayload {
  parent_id?: number | null;
  name?: string | null;
  sort_order?: number | null;
}
