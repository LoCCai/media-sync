import type { Operation, OperationEvent, OperationState, OperationStreamMessage } from '$lib/types/api';

const ACTIVE_STATES = new Set<OperationState>(['queued', 'running']);
const TERMINAL_STATES = new Set<OperationState>([
  'succeeded',
  'failed_retryable',
  'failed_terminal',
  'cancelled',
  'interrupted'
]);

const DISPLAY_CONTEXT_KEYS = new Set([
  'account_id',
  'asset_id',
  'author_id',
  'cancel_observed',
  'completed_count',
  'error_code',
  'failed_count',
  'job_id',
  'kind',
  'processed_count',
  'progress_current',
  'progress_total',
  'progress_unit',
  'retryable',
  'role',
  'run_id',
  'skipped_count',
  'status',
  'subject_state',
  'subject_type',
  'subscription_id',
  'succeeded_count',
  'target_id',
  'target_type',
  'total_count'
]);

export const LOGIN_RUNNER_STATUSES = new Set([
  'authenticated',
  'expired',
  'failed',
  'timed_out',
  'cancelled',
  'account_busy',
  'configuration_invalid',
  'start_failed',
  'result_invalid',
  'browser_launch_failed'
]);
const LOGIN_SESSION_STATUSES = new Set([
  'pending',
  'waiting_user',
  'succeeded',
  'expired',
  'failed',
  'cancelled'
]);
const AUTH_STATUSES = new Set([
  'unknown',
  'required',
  'authenticating',
  'authenticated',
  'expired',
  'failed'
]);
const ASSET_STATUSES = new Set([
  'blocked',
  'failed',
  'discovered',
  'queued',
  'downloading',
  'downloaded',
  'verified',
  'exported',
  'failed_retryable',
  'failed_terminal'
]);
const ASSET_DISPOSITIONS = new Set(['not_started', 'downloaded', 'already_verified']);
const BATCH_STATUSES = new Set([
  'idle',
  'fenced',
  'queued',
  'claimed',
  'running',
  'retry_wait',
  'waiting_auth',
  'waiting_user',
  'succeeded',
  'failed_retryable',
  'failed_terminal',
  'cancelled'
]);
const MEDIA_SERVER_PROVIDERS = new Set(['emby', 'jellyfin']);
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const SHA256 = /^[0-9a-f]{64}$/;
const SERVER_VERSION = /^\d+(?:\.\d+){0,3}$/;

export interface OperationFilter {
  state?: OperationState | 'all';
  kind?: Operation['kind'] | 'all';
  query?: string;
}

export interface OperationStreamCursorState {
  lastSequence: number;
  readyHighWater: number | null;
  readyGeneration: number;
  snapshotGeneration: number;
}

export interface OperationStreamReduction {
  state: OperationStreamCursorState;
  operations: Operation[];
  acceptedEvent: OperationEvent | null;
  snapshotRequired: boolean;
}

export type OperationStreamMode = 'connecting' | 'live' | 'fallback';

export interface OperationStreamHealth {
  mode: OperationStreamMode;
  failureCount: number;
  pollDelayMs: number;
}

export interface OperationTruthNotice {
  tone: 'success' | 'warning' | 'danger' | 'info';
  title: string;
  detail: string;
}

export type SafeOperationResult = Record<string, string | number | boolean | Record<string, number>>;

export function operationIsMediaServerObservation(operation: Operation): boolean {
  return operation.kind === 'media-server-scan' && operation.target?.type === 'author';
}

export function operationDisplayLabel(operation: Operation): string {
  if (operation.kind !== 'media-server-scan') return operation.kind;
  return operationIsMediaServerObservation(operation) ? '媒体库刷新并核验' : '媒体库定向刷新（仅确认接受）';
}

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function copyString(
  source: Record<string, unknown>,
  target: SafeOperationResult,
  key: string,
  allowed: Set<string> | RegExp
): void {
  const value = source[key];
  if (typeof value !== 'string') return;
  if (allowed instanceof RegExp ? allowed.test(value) : allowed.has(value)) target[key] = value;
}

function copyCount(source: Record<string, unknown>, target: SafeOperationResult, key: string): void {
  const value = source[key];
  if (isNonNegativeInteger(value)) target[key] = value;
}

function copyBoolean(source: Record<string, unknown>, target: SafeOperationResult, key: string): void {
  const value = source[key];
  if (typeof value === 'boolean') target[key] = value;
}

function copyBatchCounts(source: Record<string, unknown>, target: SafeOperationResult): void {
  const values = record(source.status_counts);
  if (!values) return;
  const safe = Object.entries(values)
    .filter(([key, value]) => BATCH_STATUSES.has(key) && isNonNegativeInteger(value))
    .sort(([left], [right]) => left.localeCompare(right));
  if (safe.length > 0) target.status_counts = Object.fromEntries(safe) as Record<string, number>;
}

/**
 * Project an unchecked API/SSE result through the same closed vocabulary used by the backend.
 * Unknown fields are deliberately discarded so the Jobs page never reflects remote detail.
 */
export function safeOperationResult(operation: Operation): SafeOperationResult | null {
  const source = record(operation.result);
  if (!source) return null;
  const result: SafeOperationResult = {};

  if (operation.kind === 'account-login') {
    copyString(source, result, 'account_id', UUID);
    copyString(source, result, 'login_session_id', UUID);
    copyString(source, result, 'runner_status', LOGIN_RUNNER_STATUSES);
    copyString(source, result, 'login_session_status', LOGIN_SESSION_STATUSES);
    copyString(source, result, 'auth_status', AUTH_STATUSES);
  } else if (operation.kind === 'asset-download') {
    copyString(source, result, 'asset_id', UUID);
    copyString(source, result, 'job_id', UUID);
    copyBoolean(source, result, 'ok');
    copyString(source, result, 'status', ASSET_STATUSES);
    copyString(source, result, 'disposition', ASSET_DISPOSITIONS);
    copyCount(source, result, 'generation');
    copyCount(source, result, 'size_bytes');
  } else if (operation.kind === 'scheduler-run' || operation.kind === 'pipeline-run') {
    copyCount(source, result, 'processed_count');
    copyBatchCounts(source, result);
  } else if (operation.kind === 'emby-export') {
    copyString(source, result, 'author_id', UUID);
    copyString(source, result, 'job_id', UUID);
    copyBoolean(source, result, 'already_exported');
    copyCount(source, result, 'managed_file_count');
  } else if (operation.kind === 'media-server-probe') {
    copyString(source, result, 'provider', MEDIA_SERVER_PROVIDERS);
    copyString(source, result, 'server_version', SERVER_VERSION);
    copyString(source, result, 'library_id_digest', SHA256);
    copyBoolean(source, result, 'library_present');
  } else if (operationIsMediaServerObservation(operation)) {
    if (source.schema_version !== 2 || source.mode !== 'post_refresh_item_observation') return null;
    result.schema_version = 2;
    result.mode = 'post_refresh_item_observation';
    copyString(source, result, 'provider', MEDIA_SERVER_PROVIDERS);
    copyString(source, result, 'server_version', SERVER_VERSION);
    copyString(source, result, 'profile_fingerprint', SHA256);
    copyString(source, result, 'library_id_digest', SHA256);
    copyString(source, result, 'scan_state', new Set(['accepted']));
    copyString(source, result, 'publication_fingerprint', SHA256);
    copyString(source, result, 'selector_fingerprint', SHA256);
    copyString(source, result, 'baseline_state', new Set(['not_found']));
    copyString(source, result, 'observation_state', new Set(['pending', 'observed']));
    copyCount(source, result, 'match_count');
    copyCount(source, result, 'verification_count');
    copyString(source, result, 'item_fingerprint', SHA256);
  } else if (source.schema_version !== 2) {
    copyString(source, result, 'provider', MEDIA_SERVER_PROVIDERS);
    copyString(source, result, 'server_version', SERVER_VERSION);
    copyString(source, result, 'library_id_digest', SHA256);
    copyString(source, result, 'scan_state', new Set(['accepted']));
  }

  return Object.keys(result).length > 0 ? result : null;
}

/** Merge a detail/cancel response without allowing it to roll back a newer SSE snapshot. */
export function mergeSelectedOperation(current: Operation | null, incoming: Operation): Operation {
  if (!current || current.id !== incoming.id) return incoming;
  return mergeOperationSnapshot([current], incoming, 1)[0] ?? current;
}

function isProgressCount(value: number | null | undefined): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;
}

export function operationProgressLabel(operation: Operation): string {
  const progress = operation.progress;
  if (!progress || !isProgressCount(progress.current)) return '—';
  if (operationIsMediaServerObservation(operation)) return `核验 ${progress.current} 次`;
  const unit = progress.unit ? ` ${progress.unit}` : '';
  return progress.total === null
    ? `${progress.current}${unit}`
    : `${progress.current} / ${progress.total}${unit}`;
}

export function operationProgressPercent(operation: Operation): number | null {
  if (operationIsMediaServerObservation(operation)) return null;
  const current = operation.progress?.current;
  const total = operation.progress?.total;
  if (!isProgressCount(current) || !isProgressCount(total) || total <= 0) return null;
  return Math.max(0, Math.min(100, (current / total) * 100));
}

export function operationTruthNotice(operation: Operation): OperationTruthNotice | null {
  if (!operationIsMediaServerObservation(operation)) return null;
  if (operation.error_code === 'media_server_scan_observation_precondition_failed') {
    return {
      tone: 'info',
      title: '刷新前项目已存在',
      detail: '严格观察模式未发送刷新；如只需请求刷新，请使用“定向刷新（仅确认接受）”。'
    };
  }
  if (operation.error_code === 'media_server_scan_acceptance_unknown') {
    return {
      tone: 'danger',
      title: '刷新接受状态未知',
      detail: '请求已进入传输，但无法确认服务器是否接受；该操作不可安全重试。'
    };
  }
  if (operation.error_code === 'media_server_scan_completion_unknown') {
    return {
      tone: 'warning',
      title: '刷新已接受，观察结果未知',
      detail: '已保留接受证据，但未能证明刷新后项目观察；请勿视为 provider task completion 或可播放。'
    };
  }

  const result = safeOperationResult(operation);
  const hasObservedEvidence =
    operation.phase === 'observed' &&
    result?.schema_version === 2 &&
    result.mode === 'post_refresh_item_observation' &&
    MEDIA_SERVER_PROVIDERS.has(String(result.provider)) &&
    result.scan_state === 'accepted' &&
    result.baseline_state === 'not_found' &&
    result.observation_state === 'observed' &&
    result.match_count === 1 &&
    typeof result.verification_count === 'number' &&
    result.verification_count >= 2 &&
    typeof result.profile_fingerprint === 'string' &&
    typeof result.library_id_digest === 'string' &&
    typeof result.publication_fingerprint === 'string' &&
    typeof result.selector_fingerprint === 'string' &&
    typeof result.item_fingerprint === 'string';
  if (hasObservedEvidence) {
    return {
      tone: 'success',
      title: '已观察到唯一媒体项目',
      detail: '连续两次核验观察到同一唯一项目；“已观察”不等于 provider task completion，也不等于可播放。'
    };
  }
  if (operation.phase === 'accepted' || operation.phase === 'polling') {
    return {
      tone: 'warning',
      title: '刷新已接受，等待观察',
      detail: '“已接受”不等于“已观察”，也不证明 provider task completion 或可播放。'
    };
  }
  return {
    tone: 'info',
    title: '刷新并核验状态',
    detail: '仅显示后端返回的受控阶段和安全摘要；不据此推断 provider task completion 或可播放。'
  };
}

export function operationIsActive(state: OperationState): boolean {
  return ACTIVE_STATES.has(state);
}

export function operationIsTerminal(state: OperationState): boolean {
  return TERMINAL_STATES.has(state);
}

export function operationCanCancel(operation: Operation): boolean {
  return (
    operationIsActive(operation.state) &&
    operation.cancel_requested_at === null &&
    operation.allowed_actions.includes('cancel')
  );
}

export function operationMatches(operation: Operation, filter: OperationFilter): boolean {
  if (filter.state && filter.state !== 'all' && operation.state !== filter.state) return false;
  if (filter.kind && filter.kind !== 'all' && operation.kind !== filter.kind) return false;
  const query = filter.query?.trim().toLocaleLowerCase();
  if (!query) return true;
  return [
    operation.id,
    operation.correlation_id,
    operation.kind,
    operation.error_code ?? '',
    operation.target?.id ?? '',
    ...(operation.subjects ?? []).flatMap((subject) => [subject.type, subject.id, subject.role])
  ].some((value) => value.toLocaleLowerCase().includes(query));
}

function requestedTime(operation: Operation): number {
  const parsed = Date.parse(operation.requested_at);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function mergeOperationSnapshot(
  operations: Operation[],
  incoming: Operation,
  limit = 200
): Operation[] {
  const boundedLimit = Number.isInteger(limit) && limit > 0 ? Math.min(limit, 1_000) : 200;
  const previous = operations.find((item) => item.id === incoming.id);
  if (previous && previous.event_sequence > incoming.event_sequence) return operations;
  const normalizedIncoming = previous
    ? { ...incoming, subjects: incoming.subjects ?? previous.subjects }
    : incoming;
  return [...operations.filter((item) => item.id !== incoming.id), normalizedIncoming]
    .sort((left, right) => {
      const byTime = requestedTime(right) - requestedTime(left);
      return byTime || right.id.localeCompare(left.id);
    })
    .slice(0, boundedLimit);
}

export function mergeOperationEvent(operations: Operation[], event: OperationEvent): Operation[] {
  return event.operation ? mergeOperationSnapshot(operations, event.operation) : operations;
}

export function mergeOperationSnapshots(
  operations: Operation[],
  snapshot: Operation[],
  limit = 200
): Operation[] {
  return snapshot.reduce(
    (current, operation) => mergeOperationSnapshot(current, operation, limit),
    operations
  );
}

export function mergeOperationTimeline(
  events: OperationEvent[],
  incoming: OperationEvent,
  limit = 200
): OperationEvent[] {
  const boundedLimit = Number.isInteger(limit) && limit > 0 ? Math.min(limit, 1_000) : 200;
  const unique = new Map<number, OperationEvent>();
  for (const event of [...events, incoming]) {
    const previous = unique.get(event.operation_sequence);
    if (!previous || previous.stream_sequence <= event.stream_sequence) {
      unique.set(event.operation_sequence, event);
    }
  }
  return [...unique.values()]
    .sort(
      (left, right) =>
        left.operation_sequence - right.operation_sequence || left.stream_sequence - right.stream_sequence
    )
    .slice(-boundedLimit);
}

export function createOperationStreamCursor(): OperationStreamCursorState {
  return { lastSequence: 0, readyHighWater: null, readyGeneration: 0, snapshotGeneration: 0 };
}

export function markOperationSnapshotLoaded(
  state: OperationStreamCursorState,
  generation = state.readyGeneration
): OperationStreamCursorState {
  return { ...state, snapshotGeneration: Math.max(state.snapshotGeneration, generation) };
}

export function reduceOperationStreamMessage(
  state: OperationStreamCursorState,
  operations: Operation[],
  message: OperationStreamMessage
): OperationStreamReduction {
  if (message.type === 'ready') {
    const readyGeneration = state.readyGeneration + 1;
    return {
      state: {
        ...state,
        // A first connection establishes its baseline through the bounded snapshot.
        // A reconnect must retain the old cursor so replayed missing events remain admissible.
        lastSequence:
          state.readyGeneration === 0 ? Math.max(state.lastSequence, message.high_water) : state.lastSequence,
        readyHighWater: Math.max(state.readyHighWater ?? 0, message.high_water),
        readyGeneration
      },
      operations,
      acceptedEvent: null,
      snapshotRequired: readyGeneration > state.snapshotGeneration
    };
  }
  if (message.event.stream_sequence <= state.lastSequence) {
    return {
      state,
      operations,
      acceptedEvent: null,
      snapshotRequired: false
    };
  }
  return {
    state: { ...state, lastSequence: message.event.stream_sequence },
    operations: mergeOperationEvent(operations, message.event),
    acceptedEvent: message.event,
    snapshotRequired: false
  };
}

export function safeOperationContextRows(
  event: OperationEvent
): Array<{ key: string; value: string | number | boolean }> {
  return Object.entries(event.context)
    .filter(
      (entry): entry is [string, string | number | boolean] =>
        DISPLAY_CONTEXT_KEYS.has(entry[0]) &&
        (typeof entry[1] === 'string' || typeof entry[1] === 'number' || typeof entry[1] === 'boolean')
    )
    .sort(([left], [right]) => left.localeCompare(right))
    .slice(0, 24)
    .map(([key, value]) => ({ key, value }));
}

function isNonNegativeInteger(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;
}

export function parseOperationStreamMessage(value: string): OperationStreamMessage | null {
  if (value.length > 64 * 1024) return null;
  let decoded: unknown;
  try {
    decoded = JSON.parse(value);
  } catch {
    return null;
  }
  if (!decoded || typeof decoded !== 'object') return null;
  const payload = decoded as Record<string, unknown>;
  if (payload.type === 'ready' && isNonNegativeInteger(payload.high_water)) {
    return { type: 'ready', high_water: payload.high_water };
  }
  if (payload.type !== 'operation' || !payload.event || typeof payload.event !== 'object') return null;
  const event = payload.event as Record<string, unknown>;
  if (
    !isNonNegativeInteger(event.stream_sequence) ||
    event.stream_sequence < 1 ||
    !isNonNegativeInteger(event.operation_sequence) ||
    event.operation_sequence < 1 ||
    typeof event.operation_id !== 'string' ||
    typeof event.event_code !== 'string'
  ) {
    return null;
  }
  return decoded as OperationStreamMessage;
}

export function fallbackPollDelay(failureCount: number): number {
  const failures = Number.isInteger(failureCount) ? Math.max(0, Math.min(failureCount, 4)) : 0;
  return Math.min(30_000, 3_000 * 2 ** failures);
}

export function createOperationStreamHealth(): OperationStreamHealth {
  return { mode: 'connecting', failureCount: 0, pollDelayMs: fallbackPollDelay(0) };
}

/** Explicit inputs keep the legacy Svelte reactive call subscribed to both state updates. */
export function operationStreamStatusCopy(
  health: OperationStreamHealth,
  cursor: OperationStreamCursorState
): { title: string; detail: string } {
  if (health.mode === 'live') {
    return {
      title: '实时事件流已连接',
      detail: `已处理到全局事件 #${cursor.lastSequence}；列表按事件序列去重。`
    };
  }
  if (health.mode === 'fallback') {
    return {
      title: '实时流重连中',
      detail: `当前使用有界轮询，下一次刷新间隔最多 ${Math.round(health.pollDelayMs / 1000)} 秒。`
    };
  }
  return { title: '正在连接实时事件流', detail: '连接就绪后会先读取一次有界操作快照。' };
}

export function operationStreamConnected(_state: OperationStreamHealth): OperationStreamHealth {
  return { mode: 'live', failureCount: 0, pollDelayMs: fallbackPollDelay(0) };
}

export function operationStreamFailed(state: OperationStreamHealth): OperationStreamHealth {
  return {
    mode: 'fallback',
    failureCount: Math.min(state.failureCount + 1, 5),
    pollDelayMs: fallbackPollDelay(state.failureCount)
  };
}
