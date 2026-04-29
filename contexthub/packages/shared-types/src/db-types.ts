/**
 * DB row types for all §5 tables (ARCHITECTURE.md).
 *
 * Hand-authored and kept in sync with the SQLAlchemy models in
 * contexthub/backend/contexthub_backend/db/models.py.
 * These are the shapes the API returns in JSON responses.
 */

// ---------------------------------------------------------------------------
// Enums
// ---------------------------------------------------------------------------

export type SourcePlatform = "claude_ai" | "chatgpt" | "gemini";
export type PushStatus = "pending" | "processing" | "ready" | "failed";
export type SummaryLayer =
  | "title"
  | "summary"
  | "details"
  | "raw_transcript";
export type RelationType = "continuation" | "reference" | "supersession";
export type TargetPlatform = "claude_ai";
export type PullOrigin = "extension" | "dashboard";
export type PullResolution =
  | "title"
  | "summary"
  | "details"
  | "raw_transcript";

// ---------------------------------------------------------------------------
// Row types (ISO 8601 string for all timestamps; UUID as string)
// ---------------------------------------------------------------------------

export interface ProfileRow {
  user_id: string;
  display_name: string | null;
  avatar_url: string | null;
  created_at: string;
}

export interface ApiTokenRow {
  id: string;
  user_id: string;
  name: string;
  /** token_hash is never returned to clients — omitted from API responses */
  scopes: string[];
  last_used_at: string | null;
  created_at: string;
  revoked_at: string | null;
}

export interface WorkspaceRow {
  id: string;
  /** Derived presentation field, not stored in DB */
  short_id: string;
  user_id: string;
  name: string;
  slug: string;
  settings_json: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

export interface InterchangeFormatVersionRow {
  version: string;
  json_schema: Record<string, unknown>;
  created_at: string;
  deprecated_at: string | null;
}

export interface PushRow {
  id: string;
  workspace_id: string;
  user_id: string;
  source_platform: SourcePlatform;
  source_url: string | null;
  source_conversation_id: string | null;
  interchange_version: string;
  title: string | null;
  status: PushStatus;
  failure_reason: string | null;
  idempotency_key: string | null;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

export interface SummaryRow {
  id: string;
  push_id: string;
  layer: SummaryLayer;
  content_json: Record<string, unknown>;
  content_markdown: string | null;
  model: string | null;
  prompt_version: string | null;
  latency_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  cost_usd: string | null;
  quality_score: number | null;
  failure_reason: string | null;
  superseded_by: string | null;
  created_at: string;
}

export interface TranscriptRow {
  push_id: string;
  storage_path: string;
  sha256: string;
  size_bytes: number;
  message_count: number;
  created_at: string;
}

export interface TagRow {
  id: string;
  workspace_id: string;
  name: string;
  slug: string;
  created_at: string;
}

export interface PushTagRow {
  push_id: string;
  tag_id: string;
}

export interface PushRelationshipRow {
  id: string;
  from_push_id: string;
  to_push_id: string;
  relation_type: RelationType;
  created_at: string;
}

export interface SummaryFeedbackRow {
  id: string;
  summary_id: string;
  user_id: string | null;
  score: number;
  comment: string | null;
  created_at: string;
}

export interface PullRow {
  id: string;
  user_id: string;
  target_platform: TargetPlatform;
  origin: PullOrigin;
  resolution: PullResolution;
  push_ids: string[];
  workspace_ids: string[];
  token_estimate: number | null;
  created_at: string;
}

export interface AuditLogRow {
  id: string;
  user_id: string | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  request_id: string | null;
  ip: string | null;
  user_agent: string | null;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
}
