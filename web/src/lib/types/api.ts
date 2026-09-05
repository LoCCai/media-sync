export type Platform = 'bili' | 'xhs' | 'dy' | 'ks' | 'wb' | 'tieba' | 'zhihu';
export type ContentKind = 'video' | 'image' | 'gallery' | 'text' | 'article' | 'audio' | 'dynamic' | 'mixed';
export type AssetKind = 'image' | 'video' | 'audio' | 'subtitle' | 'cover' | 'avatar' | 'attachment';
export type AssetStatus =
  | 'discovered'
  | 'queued'
  | 'downloading'
  | 'downloaded'
  | 'verified'
  | 'exported'
  | 'failed_retryable'
  | 'failed_terminal';
export type ArchiveState = 'empty' | 'pending' | 'partial' | 'complete';
export type AssetArchiveState = 'eligible' | 'not_ready';
export type AssetAction = 'preview' | 'download' | 'export_author';
export type CheckState = 'pass' | 'fail' | 'not_run';
export type LoginMethod = 'qr' | 'cookie' | 'saved_session';
export type AccountLoginMethod = LoginMethod | 'phone';
export type CreatorInputKind = 'profile_id' | 'sec_user_id' | 'user_id' | 'uid' | 'portrait_id' | 'url_token';
export type OperationKind =
  | 'account-login'
  | 'account-cookie-login'
  | 'creator-profile'
  | 'asset-download'
  | 'scheduler-run'
  | 'pipeline-run'
  | 'emby-export'
  | 'media-server-probe'
  | 'media-server-scan';
export type OperationState =
  | 'queued'
  | 'running'
  | 'succeeded'
  | 'failed_retryable'
  | 'failed_terminal'
  | 'cancelled'
  | 'interrupted';
export type OperationAction = 'cancel' | 'retry';
export type LoginRunnerStatus =
  | 'authenticated'
  | 'expired'
  | 'failed'
  | 'timed_out'
  | 'cancelled'
  | 'account_busy'
  | 'configuration_invalid'
  | 'start_failed'
  | 'result_invalid'
  | 'browser_launch_failed';

export interface LoginDiagnostic {
  operation_id: string;
  operation_state: OperationState;
  runner_status: LoginRunnerStatus;
  error_code: string | null;
}

export interface PlatformCapability {
  platform: Platform;
  display_name: string;
  login_methods: LoginMethod[];
  qr_login: boolean;
  pasted_cookie_login: boolean;
  creator_input: {
    kind: CreatorInputKind;
    label: string;
    placeholder: string;
    examples: string[];
    allows_secret_reference: boolean;
  };
  requires_full_history_acknowledgement: boolean;
  bounded_capture?: BiliBoundedCapture | null;
  offline_shapes: string[];
  limitations: string[];
  live_qualification: 'NOT_RUN';
}

export interface BiliBoundedCapture {
  version: 1;
  feed: 'ordinary_uploads';
  order: 'pubdate';
  page_size: 30;
  max_items_per_unit: 30;
  max_list_attempts_per_unit: 2;
  alternating_lanes: ['head', 'history'];
  browser_setup_separate: true;
  download_scope_bounded: false;
  history_completeness_claimed: false;
  legacy_requires_full_history_acknowledgement: true;
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
  media_server: MediaServerConfiguration;
}

export interface Account {
  id: string;
  platform: Platform;
  adapter: string;
  display_name: string;
  login_method: AccountLoginMethod | null;
  auth_status: string;
  auth_revision: number;
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
  diagnostic?: LoginDiagnostic | null;
}

export interface Subscription {
  id: string;
  account_id: string;
  platform: Platform;
  account_display_name: string;
  author_id: string;
  creator_remote_id: string;
  creator_display_name: string;
  local_alias?: string | null;
  creator_profile?: CreatorProfile | null;
  enabled: boolean;
  deleted_at: string | null;
  interval_seconds: number;
  max_items: number;
  watermarked_at: string | null;
  last_success_at: string | null;
  next_run_at: string | null;
  policy_summary?: SubscriptionPolicySummary;
  created?: boolean;
}

export interface SubscriptionLifecycleResult {
  id: string;
  status: 'deleted' | 'paused';
  changed: boolean;
  cancelled_jobs: number;
  media_preserved: true;
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
  bili_scope?: 'uploads' | 'dynamics' | 'both';
  request_delay_seconds?: number | null;
  headless?: boolean | null;
  creator_reference_configured?: boolean;
}

export interface SubscriptionCheckpointSummary extends Record<string, unknown> {
  bili_scan?: unknown;
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
  local_alias?: string | null;
  profile_lookup_id?: string | null;
  interval_seconds: number;
  max_items: number;
  policy_summary: SubscriptionPolicySummary;
  exists: boolean;
}

export interface CreatorIdentity {
  account_id: string;
  platform: Platform;
  creator_remote_id: string;
}

export interface CreatorLookupScope extends CreatorIdentity {
  frontend_generation: string;
}

export interface CreatorProfile extends CreatorIdentity {
  id: string;
  nickname: string;
  profile_url: string;
  revision: number;
  observed_at: string;
  avatar_revision: number;
  avatar_observed_at: string | null;
  avatar_state: 'current' | 'retained' | 'absent';
  avatar_url: string | null;
}

export interface CreatorLookupResponse {
  operation_id: string;
  state: OperationState;
  error_code: string | null;
  lookup:
    | (CreatorLookupScope & {
        generation: number;
        operation_id: string;
        result_profile_revision: number | null;
      })
    | null;
  profile: CreatorProfile | null;
  profile_source: 'lookup_result' | 'previous_success' | null;
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
  last_error_code?: string | null;
}

export interface Operation {
  id: string;
  kind: OperationKind;
  state: OperationState;
  requested_at: string;
  started_at: string | null;
  finished_at: string | null;
  phase: string | null;
  progress: {
    current: number | null;
    total: number | null;
    unit: string | null;
  } | null;
  target: {
    type: string;
    id: string;
  } | null;
  retryable: boolean;
  result: Record<string, unknown> | null;
  error_code: string | null;
  correlation_id: string;
  cancel_requested_at: string | null;
  allowed_actions: OperationAction[];
  event_sequence: number;
  subjects?: OperationSubject[];
}

export interface OperationSubject {
  type: string;
  id: string;
  role: string;
  created_at: string;
}

export interface OperationEvent {
  stream_sequence: number;
  operation_id: string;
  operation_sequence: number;
  created_at: string;
  level: 'info' | 'warning' | 'error';
  event_code: string;
  phase: string | null;
  message_key: string | null;
  from_state: OperationState | null;
  to_state: OperationState | null;
  subject: {
    type: string;
    id: string;
  } | null;
  context: Record<string, string | number | boolean | null>;
  operation?: Operation;
}

export interface OperationStreamReady {
  type: 'ready';
  high_water: number;
}

export interface OperationStreamEvent {
  type: 'operation';
  event: OperationEvent;
}

export type OperationStreamMessage = OperationStreamReady | OperationStreamEvent;

export interface Asset {
  id: string;
  author_id: string;
  author_display_name: string;
  content_id: string;
  content_title: string | null;
  platform: Platform;
  kind: AssetKind;
  position: number;
  generation: number;
  status: AssetStatus;
  mime_type: string | null;
  size_bytes: number | null;
  verified_at: string | null;
  archive: {
    state: AssetArchiveState;
    eligible: boolean;
    preview_url: string | null;
    recovery_url: string;
  };
  allowed_actions: AssetAction[];
}

export interface ContentItem {
  id: string;
  author_id: string;
  author_display_name: string;
  platform: Platform;
  remote_type: string;
  remote_id: string;
  kind: ContentKind;
  title: string | null;
  body_excerpt: string | null;
  canonical_url: string | null;
  published_at: string | null;
  asset_count: number;
  archived_count: number;
  export_count: number;
  archive_state: ArchiveState;
  tombstoned: boolean;
}

export interface ContentDetail extends ContentItem {
  body: string | null;
  remote_updated_at: string | null;
  first_seen_at: string;
  last_seen_at: string;
  assets: Asset[];
  exports: {
    succeeded_count: number;
    last_exported_at: string | null;
  };
}

export interface AssetDetail extends Asset {
  checksum_sha256: string | null;
  width: number | null;
  height: number | null;
  duration_ms: number | null;
  downloaded_at: string | null;
  created_at: string;
  updated_at: string;
  last_error_code: string | null;
  content: {
    id: string;
    remote_id: string;
    kind: ContentKind;
    title: string | null;
    published_at: string | null;
  };
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
  archive_state: ArchiveState;
}

export type LibraryFreshness = 'not_published' | 'current' | 'outdated' | 'blocked';
export type LibraryIntegrity =
  | 'not_available'
  | 'unchecked'
  | 'page_verified'
  | 'complete'
  | 'budget_exhausted'
  | 'drifted'
  | 'inconsistent';
export type LibraryAction = 'export_author' | 'refresh_and_verify';

export interface ManagedLibraryFile {
  relative_path: string;
  sha256: string;
  size_bytes: number;
}

export interface LibraryInspection {
  schema_version: 2;
  author_id: string;
  publication: {
    layout_version: string;
    publication_scope: string;
    job_id: string;
    source_fingerprint: string;
    tree_sha256: string;
    manifest_sha256: string;
    managed_file_count: number;
  } | null;
  freshness: LibraryFreshness;
  freshness_reason_code: string | null;
  integrity: LibraryIntegrity;
  integrity_reason_code: string | null;
  user_changes_protected: boolean;
  files: ManagedLibraryFile[];
  page: {
    start_index: number;
    next_index: number;
    limit: number;
    returned_count: number;
    bytes_read: number;
    complete: boolean;
    budget_exhausted: boolean;
    next_cursor: string | null;
  };
  allowed_actions: LibraryAction[];
}

export type MediaServerProvider = 'emby' | 'jellyfin';
export type MediaServerAction = 'probe' | 'scan';

export interface MediaServerConfiguration {
  configured: boolean;
  provider: MediaServerProvider | null;
  origin: string | null;
  library_id_digest: string | null;
  profile_fingerprint: string | null;
  verify_tls: boolean;
  timeout_seconds: number;
  operations_enabled: boolean;
  allowed_network_count: number;
  library_path_configured: boolean;
  api_key_configured: boolean;
}

export interface MediaServerStatus {
  schema_version: 1;
  configuration: MediaServerConfiguration;
  latest_probe: Operation | null;
  latest_scan: Operation | null;
  allowed_actions: MediaServerAction[];
}

export interface MediaServerAuthorLookupBase {
  schema_version: 1;
  author_id: string;
  provider: MediaServerProvider;
  library_id_digest: string;
  publication_fingerprint: string;
  selector_fingerprint: string;
  observed_at: string;
  complete: true;
}

export type MediaServerAuthorLookup = MediaServerAuthorLookupBase &
  (
    | {
        lookup_state: 'not_found';
        match_count: 0;
        item_fingerprint?: never;
        observation_fingerprint?: never;
      }
    | {
        lookup_state: 'matched';
        match_count: 1;
        item_fingerprint: string;
        observation_fingerprint: string;
      }
  );

export type HumanQualificationStatus = 'PASS' | 'FAIL' | 'NOT_RUN' | 'BLOCKED_EXTERNAL';
export type ImplementationStatus = 'IMPLEMENTED' | 'NOT_IMPLEMENTED';

export interface HumanQualificationCapability {
  capability: string;
  implementation_status: ImplementationStatus;
  human_status: HumanQualificationStatus | null;
  reason?: 'provider_api_unsupported';
  scope?: 'author' | 'not_requested';
  author_id?: string | null;
}

export interface PlaybackEvidenceView {
  schema_version: 1;
  id: string;
  author_id: string;
  observed_at: string;
  confirmed_at: string;
  state: 'current' | 'stale' | 'unknown';
}

export interface PlaybackEvidenceProjection {
  schema_version: 1;
  scope: 'author' | 'not_requested';
  author_id: string | null;
  checked_at: string | null;
  current_state: 'matched' | 'not_found' | 'unavailable' | 'not_requested';
  human_status: 'PASS' | 'NOT_RUN';
  current: PlaybackEvidenceView | null;
  history: PlaybackEvidenceView[];
  history_truncated: boolean;
  limit: number;
}

export interface Qualifications {
  schema_version: 3;
  generated_at: string;
  policy: {
    automated_evidence_confers_human_pass: false;
    human_statuses: HumanQualificationStatus[];
    implementation_statuses: ImplementationStatus[];
  };
  platforms: Array<{
    platform: Platform;
    automated_evidence: Record<string, number>;
    human_qualification: HumanQualificationCapability[];
  }>;
  media_server: {
    configured: boolean;
    playback_evidence: PlaybackEvidenceProjection;
    automated_evidence: {
      latest_probe: Record<string, unknown> | null;
      latest_targeted_scan: Record<string, unknown> | null;
    };
    human_qualification: HumanQualificationCapability[];
  };
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
  state: OperationState;
  replayed?: boolean;
  correlation_id?: string;
}
