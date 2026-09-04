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
