import { describe, expect, it } from 'vitest';

import type { Operation, OperationEvent } from '$lib/types/api';

import {
  createOperationStreamCursor,
  createOperationStreamHealth,
  fallbackPollDelay,
  markOperationSnapshotLoaded,
  mergeOperationEvent,
  mergeOperationSnapshot,
  mergeOperationSnapshots,
  mergeOperationTimeline,
  operationCanCancel,
  operationIsActive,
  operationIsTerminal,
  operationMatches,
  operationStreamConnected,
  operationStreamFailed,
  parseOperationStreamMessage,
  reduceOperationStreamMessage,
  safeOperationContextRows
} from './operations';

const operation: Operation = {
  id: '11111111-1111-4111-8111-111111111111',
  kind: 'scheduler-run',
  state: 'running',
  requested_at: '2026-09-04T12:00:00+00:00',
  started_at: '2026-09-04T12:00:01+00:00',
  finished_at: null,
  phase: 'worker',
  progress: { current: 1, total: 3, unit: 'jobs' },
  target: null,
  retryable: false,
  result: null,
  error_code: null,
  correlation_id: '22222222-2222-4222-8222-222222222222',
  cancel_requested_at: null,
  allowed_actions: ['cancel'],
  event_sequence: 2
};

const event: OperationEvent = {
  stream_sequence: 8,
  operation_id: operation.id,
  operation_sequence: 3,
  created_at: '2026-09-04T12:00:02+00:00',
  level: 'info',
  event_code: 'operation_progressed',
  phase: 'worker',
  message_key: 'operation.progressed',
  from_state: null,
  to_state: null,
  subject: null,
  context: {
    job_id: '33333333-3333-4333-8333-333333333333',
    processed_count: 2,
    local_path: 'C:\\Users\\secret\\archive.mp4',
    signed_url: 'https://example.invalid/video?token=do-not-render'
  },
  operation: { ...operation, progress: { current: 2, total: 3, unit: 'jobs' }, event_sequence: 3 }
};

describe('persistent operation state', () => {
  it('uses the closed active and terminal sets for action gates', () => {
    expect(operationIsActive('queued')).toBe(true);
    expect(operationIsActive('running')).toBe(true);
    expect(operationIsTerminal('interrupted')).toBe(true);
    expect(operationCanCancel(operation)).toBe(true);
    expect(operationCanCancel({ ...operation, cancel_requested_at: operation.requested_at })).toBe(false);
    expect(operationCanCancel({ ...operation, state: 'succeeded', allowed_actions: [] })).toBe(false);
  });

  it('filters by state, kind, identifiers, and fixed error code', () => {
    expect(operationMatches(operation, { state: 'running', kind: 'scheduler-run' })).toBe(true);
    expect(operationMatches(operation, { state: 'failed_terminal' })).toBe(false);
    expect(operationMatches(operation, { query: '22222222' })).toBe(true);
    expect(operationMatches({ ...operation, error_code: 'worker_failed' }, { query: 'worker_failed' })).toBe(
      true
    );
    expect(
      operationMatches(
        {
          ...operation,
          subjects: [
            {
              type: 'job',
              id: '77777777-7777-4777-8777-777777777777',
              role: 'execution',
              created_at: operation.requested_at
            }
          ]
        },
        { query: '77777777' }
      )
    ).toBe(true);
  });

  it('merges only non-stale snapshots in stable newest-first order', () => {
    const older = { ...operation, event_sequence: 1 };
    expect(mergeOperationSnapshot([operation], older)).toEqual([operation]);
    const merged = mergeOperationEvent([operation], event);
    expect(merged[0].event_sequence).toBe(3);
    expect(merged[0].progress?.current).toBe(2);
  });

  it('preserves detail-only subjects when a newer list or stream snapshot arrives', () => {
    const detailed = {
      ...operation,
      subjects: [
        {
          type: 'job',
          id: '77777777-7777-4777-8777-777777777777',
          role: 'execution',
          created_at: operation.requested_at
        }
      ]
    };
    expect(
      mergeOperationSnapshot([detailed], {
        ...operation,
        event_sequence: detailed.event_sequence + 1,
        subjects: undefined
      })[0].subjects
    ).toEqual(detailed.subjects);
  });

  it('merges bounded snapshots and operation-local events without duplicates', () => {
    const second = {
      ...operation,
      id: '99999999-9999-4999-8999-999999999999',
      requested_at: '2026-09-04T12:01:00+00:00'
    };
    expect(mergeOperationSnapshots([operation], [second], 1)).toEqual([second]);
    expect(mergeOperationTimeline([event], event)).toEqual([event]);
    expect(
      mergeOperationTimeline([event], {
        ...event,
        stream_sequence: 9,
        operation_sequence: 4,
        event_code: 'operation_succeeded'
      }).map((item) => item.operation_sequence)
    ).toEqual([3, 4]);
  });
});

describe('operation event safety and reconnect helpers', () => {
  it('renders only the frontend event-context allowlist', () => {
    const serialized = JSON.stringify(safeOperationContextRows(event));
    expect(serialized).toContain('processed_count');
    expect(serialized).toContain('job_id');
    expect(serialized).not.toContain('secret');
    expect(serialized).not.toContain('token=');
    expect(serialized).not.toContain('local_path');
    expect(serialized).not.toContain('signed_url');
  });

  it('parses bounded ready and event messages and rejects malformed cursors', () => {
    expect(parseOperationStreamMessage('{"type":"ready","high_water":9}')).toEqual({
      type: 'ready',
      high_water: 9
    });
    expect(parseOperationStreamMessage(JSON.stringify({ type: 'operation', event }))).not.toBeNull();
    expect(parseOperationStreamMessage('{"type":"ready","high_water":-1}')).toBeNull();
    expect(parseOperationStreamMessage('{"type":"operation","event":{"stream_sequence":0}}')).toBeNull();
    expect(parseOperationStreamMessage('not-json')).toBeNull();
  });

  it('backs polling off to a fixed ceiling', () => {
    expect(fallbackPollDelay(0)).toBe(3_000);
    expect(fallbackPollDelay(2)).toBe(12_000);
    expect(fallbackPollDelay(99)).toBe(30_000);
  });

  it('reduces ready, new, duplicate, and reconnect stream messages monotonically', () => {
    const initial = createOperationStreamCursor();
    const ready = reduceOperationStreamMessage(initial, [operation], {
      type: 'ready',
      high_water: 7
    });
    expect(ready.snapshotRequired).toBe(true);
    expect(ready.state.lastSequence).toBe(7);

    const accepted = reduceOperationStreamMessage(ready.state, ready.operations, {
      type: 'operation',
      event
    });
    expect(accepted.acceptedEvent).toEqual(event);
    expect(accepted.state.lastSequence).toBe(8);
    expect(accepted.operations[0].event_sequence).toBe(3);

    const duplicate = reduceOperationStreamMessage(accepted.state, accepted.operations, {
      type: 'operation',
      event
    });
    expect(duplicate.acceptedEvent).toBeNull();
    expect(duplicate.operations).toBe(accepted.operations);

    const loaded = markOperationSnapshotLoaded(duplicate.state);
    const reconnect = reduceOperationStreamMessage(
      { ...loaded, lastSequence: 5, readyHighWater: 5 },
      duplicate.operations,
      {
        type: 'ready',
        high_water: 9
      }
    );
    expect(reconnect.state.lastSequence).toBe(5);
    expect(reconnect.state.readyGeneration).toBe(2);
    expect(reconnect.snapshotRequired).toBe(true);

    const replay = reduceOperationStreamMessage(reconnect.state, reconnect.operations, {
      type: 'operation',
      event: { ...event, stream_sequence: 6 }
    });
    expect(replay.acceptedEvent?.stream_sequence).toBe(6);
  });

  it('models reconnect fallback backoff and resets only after stream activity', () => {
    const initial = createOperationStreamHealth();
    const firstFailure = operationStreamFailed(initial);
    const secondFailure = operationStreamFailed(firstFailure);
    expect(firstFailure).toEqual({ mode: 'fallback', failureCount: 1, pollDelayMs: 3_000 });
    expect(secondFailure.pollDelayMs).toBe(6_000);
    expect(
      operationStreamFailed(operationStreamFailed(operationStreamFailed(secondFailure))).pollDelayMs
    ).toBe(30_000);
    expect(operationStreamConnected(secondFailure)).toEqual({
      mode: 'live',
      failureCount: 0,
      pollDelayMs: 3_000
    });
  });
});
