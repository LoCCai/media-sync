export type Platform = 'bili' | 'xhs' | 'dy' | 'ks' | 'wb' | 'tieba' | 'zhihu';
export type CheckState = 'pass' | 'fail' | 'not_run';
export type LoginMethod = 'qr' | 'cookie' | 'saved_session';
export type AccountLoginMethod = LoginMethod | 'phone';
export type CreatorInputKind = 'profile_id' | 'sec_user_id' | 'user_id' | 'uid' | 'portrait_id' | 'url_token';

export interface PlatformCapability {
  platform: Platform;
  display_name: string;
  login_methods: LoginMethod[];
  qr_login: boolean;
  creator_input: {
    kind: CreatorInputKind;
    label: string;
    placeholder: string;
    examples: string[];
    allows_secret_reference: boolean;
  };
  requires_full_history_acknowledgement: boolean;
  offline_shapes: string[];
  limitations: string[];
  live_qualification: 'NOT_RUN';
}

export interface PlatformCapabilities {
  version: number;
  platforms: PlatformCapability[];
}

export interface LoginPreflightCheck {
  name: string;
  status: CheckState;
  required: boolean;
  detail_code: string | null;
}

export interface LoginPreflight {
  ok: boolean;
  status: string;
  code: string;
  retryable: boolean;
  account_id: string;
  platform: Platform | null;
  checks: LoginPreflightCheck[];
  live_qualification: 'NOT_RUN';
}

export interface Settings {
  version: string;
  state_dir: string;
  archive_dir: string;
  export_dir: string;
  job_dir: string;
  api_bind: string;
  mediacrawler_python_executable: string | null;
}

export interface Account {
  id: string;
  platform: Platform;
  adapter: string;
  display_name: string;
  login_method: AccountLoginMethod | null;
  auth_status: string;
  created_at: string | null;
  created?: boolean;
}

export interface LoginStatus {
  account_id: string;
  auth_status: string;
  auth_updated_at: string | null;
  login_session_id: string | null;
  login_session_status: string | null;
  expires_at: string | null;
  completed_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface Subscription {
  id: string;
  account_id: string;
  platform: Platform;
  account_display_name: string;
  author_id: string;
  creator_remote_id: string;
  creator_display_name: string;
  enabled: boolean;
  interval_seconds: number;
  max_items: number;
  watermarked_at: string | null;
  last_success_at: string | null;
  next_run_at: string | null;
  policy_summary?: SubscriptionPolicySummary;
  created?: boolean;
}

export interface SubscriptionDetail extends Subscription {
  schedule: {
    subscription_id: string;
    status: string;
    interval_seconds: number;
    next_run_at: string | null;
    last_run_at: string | null;
    last_success_at: string | null;
    schedule_revision: number;
    consecutive_failures: number;
  };
  checkpoint_summary?: SubscriptionCheckpointSummary;
  recent_runs: Array<{
    run_id: string;
    status: string;
    attempt: number;
    discovered_count: number;
    asset_count: number;
    error_code: string | null;
    started_at: string | null;
    finished_at: string | null;
  }>;
  recent_jobs: Job[];
}

export interface SubscriptionPolicySummary extends Record<string, unknown> {
  adapter: string;
  schema_version?: number | null;
  allow_full_history?: boolean | null;
  request_delay_seconds?: number | null;
  headless?: boolean | null;
  creator_reference_configured?: boolean;
}

export interface SubscriptionCheckpointSummary extends Record<string, unknown> {
  has_checkpoint: boolean;
  has_forward_cursor: boolean;
  has_backfill_cursor: boolean;
  revision: number;
  cursor_version: number;
  watermarked_at: string | null;
  watermark_count: number;
  last_success_at: string | null;
}

export interface SubscriptionPreview {
  account_id: string;
  platform: Platform;
  account_display_name: string;
  creator_remote_id: string;
  creator_display_name: string;
  interval_seconds: number;
  max_items: number;
  policy_summary: SubscriptionPolicySummary;
  exists: boolean;
}

export interface Job {
  job_id: string;
  subscription_id: string | null;
  account_id: string | null;
  platform: Platform | null;
  status: string;
  attempt: number;
  max_attempts: number;
  available_at: string | null;
  scheduled_for: string | null;
  run_id: string | null;
  created_at: string | null;
  updated_at: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface Operation {
  id: string;
  kind: string;
  state: string;
  started_at: string;
  finished_at: string | null;
  result: Record<string, unknown> | null;
  error_code: string | null;
}

export interface Asset {
  id: string;
  author_id: string;
  content_id: string;
  platform: Platform;
  kind: string;
  position: number;
  generation: number;
  status: string;
  mime_type: string | null;
  size_bytes: number | null;
  verified_at: string | null;
}

export interface ContentItem {
  id: string;
  author_id: string;
  author_display_name: string;
  platform: Platform;
  remote_type: string;
  remote_id: string;
  kind: string;
  title: string | null;
  body_excerpt: string | null;
  canonical_url: string | null;
  published_at: string | null;
  asset_count: number;
  archived_count: number;
  export_count: number;
}

export interface LibraryAuthor {
  author_id: string;
  platform: Platform;
  display_name: string;
  remote_id: string;
  content_count: number;
  asset_count: number;
  archived_count: number;
  exported_count: number;
  last_published_at: string | null;
}

export interface ToolCheck {
  status: CheckState;
  available?: boolean;
  version?: string | null;
  detail_code?: string | null;
}

export interface DeepReadiness {
  ok: boolean;
  code: string;
  checked_at: string;
  cached: boolean;
  database: Record<string, unknown> & { ok?: boolean };
  tools: Record<string, ToolCheck>;
  paths: Record<string, { status: CheckState; exists: boolean; writable: boolean }>;
  mediacrawler: {
    ok: boolean;
    code: string | null;
    detail_code: string | null;
    upstream_sha: string | null;
    license: string;
    checkout_ready: boolean;
    runtime_configured: boolean;
    runtime_ready: boolean;
    checks: Record<string, CheckState>;
  };
  browser: {
    status: CheckState;
    version: string | null;
    detail_code: string | null;
  };
  build_manifest: {
    status: CheckState;
    present: boolean;
    facts: Record<string, string>;
  };
  security: {
    status: 'pass' | 'warn';
    code: string | null;
    safe: boolean;
    requires_operator_review: boolean;
    api_host: string;
    api_port: number;
    note: string;
  };
}

export interface StartedOperation {
  operation_id: string;
  state: string;
}
