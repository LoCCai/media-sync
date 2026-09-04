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
  'failed_count',
  'job_id',
  'processed_count',
  'run_id',
  'skipped_count',
  'status',
  'subscription_id',
  'succeeded_count',
  'total_count'
]);

export interface OperationFilter {
  state?: OperationState | 'all';
  kind?: Operation['kind'] | 'all';
  query?: string;
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
    operation.target?.id ?? ''
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
  return [...operations.filter((item) => item.id !== incoming.id), incoming]
    .sort((left, right) => {
      const byTime = requestedTime(right) - requestedTime(left);
      return byTime || right.id.localeCompare(left.id);
    })
    .slice(0, boundedLimit);
}

export function mergeOperationEvent(operations: Operation[], event: OperationEvent): Operation[] {
  return event.operation ? mergeOperationSnapshot(operations, event.operation) : operations;
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
