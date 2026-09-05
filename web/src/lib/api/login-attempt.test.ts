import { describe, expect, it, vi } from 'vitest';
import type { Operation, OperationState } from '$lib/types/api';
import type { ApiBlobResult } from './client';
import { LoginAttemptMonitor, type LoginAttemptView } from './login-attempt';

const accountId = '11111111-1111-4111-8111-111111111111';
const operationId = '22222222-2222-4222-8222-222222222222';
const sessionId = '33333333-3333-4333-8333-333333333333';
const otherId = '44444444-4444-4444-8444-444444444444';
const terminalStates: OperationState[] = [
  'succeeded',
  'failed_retryable',
  'failed_terminal',
  'cancelled',
  'interrupted'
];

function operation(state: OperationState = 'running', patch: Partial<Operation> = {}): Operation {
  return {
    id: operationId,
    kind: 'account-login',
    state,
    target: { type: 'account', id: accountId },
    subjects: [{ type: 'login_session', role: 'execution', id: sessionId, created_at: '' }],
    error_code: state === 'succeeded' || state === 'cancelled' ? null : 'operation_login_failed',
    result: {
      account_id: accountId,
      login_session_id: sessionId,
      runner_status: state === 'succeeded' ? 'authenticated' : 'failed',
      login_session_status: state === 'succeeded' ? 'succeeded' : 'failed',
      auth_status: state === 'succeeded' ? 'authenticated' : 'failed'
    },
    ...patch
  } as Operation;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((done, fail) => {
    resolve = done;
    reject = fail;
  });
  return { promise, resolve, reject };
}

async function settle(): Promise<void> {
  for (let index = 0; index < 8; index++) await Promise.resolve();
}

function fixture(
  readQr = vi.fn(
    async (_session: string, _signal: AbortSignal): Promise<ApiBlobResult> => ({ status: 202, blob: null })
  )
) {
  let current = operation();
  const changes: LoginAttemptView[] = [];
  const readOperation = vi.fn(async (_id: string, _signal: AbortSignal) => current);
  const terminal = vi.fn();
  const createImageUrl = vi.fn(() => 'blob:fixture-image');
  const revokeImageUrl = vi.fn();
  const monitor = new LoginAttemptMonitor(accountId, operationId, {
    readOperation,
    readQr,
    changed: (view) => changes.push(view),
    terminal,
    createImageUrl,
    revokeImageUrl
  });
  return {
    monitor,
    changes,
    readOperation,
    readQr,
    terminal,
    createImageUrl,
    revokeImageUrl,
    update: (next: Operation) => {
      current = next;
    },
    latest: () => changes[changes.length - 1]
  };
}

describe('independent login control and QR delivery', () => {
  it.each(terminalStates)('renders %s immediately, never starts QR and stops later polls', async (state) => {
    const test = fixture();
    test.update(operation(state));
    await test.monitor.poll();
    expect(test.latest().terminal).toBe(true);
    expect(test.latest().operationState).toBe(state);
    expect(test.latest().imageUrl).toBe('');
    expect(test.latest().explanation?.title).toBeTruthy();
    expect(test.readQr).not.toHaveBeenCalled();
    await test.monitor.poll();
    expect(test.readOperation).toHaveBeenCalledOnce();
    expect(test.terminal).toHaveBeenCalledOnce();
    test.monitor.dispose();
  });

  it.each(terminalStates)('handles %s while a QR fetch hangs, and discards its late blob', async (state) => {
    const pending = deferred<ApiBlobResult>();
    const readQr = vi.fn((_session: string, _signal: AbortSignal) => pending.promise);
    const test = fixture(readQr);
    await test.monitor.poll();
    await test.monitor.poll();
    expect(readQr).toHaveBeenCalledOnce();
    test.update(operation(state));
    await test.monitor.poll();
    expect(test.latest().terminal).toBe(true);
    expect(readQr.mock.calls[0][1].aborted).toBe(true);
    pending.resolve({ status: 200, blob: new Blob(['fixture']) });
    await settle();
    expect(test.createImageUrl).not.toHaveBeenCalled();
    expect(test.latest().terminal).toBe(true);
    expect(test.terminal).toHaveBeenCalledOnce();
    test.monitor.dispose();
  });

  it('QR errors remain fixed and cannot mask the next operation terminal state', async () => {
    const test = fixture(
      vi.fn(async (_session: string, _signal: AbortSignal): Promise<ApiBlobResult> => {
        throw new Error('DO_NOT_RENDER token=private');
      })
    );
    await test.monitor.poll();
    await settle();
    expect(test.latest().hint).toContain('仍在检查');
    test.update(operation('failed_terminal'));
    await test.monitor.poll();
    expect(test.latest().terminal).toBe(true);
    expect(JSON.stringify(test.changes)).not.toContain('DO_NOT_RENDER');
    test.monitor.dispose();
  });

  it('releases displayed QR bytes on terminal, close and replacement', async () => {
    const test = fixture(
      vi.fn(
        async (_session: string, _signal: AbortSignal): Promise<ApiBlobResult> => ({
          status: 200,
          blob: new Blob(['fixture'])
        })
      )
    );
    await test.monitor.poll();
    await settle();
    expect(test.latest().imageUrl).toBe('blob:fixture-image');
    test.update(operation('failed_terminal'));
    await test.monitor.poll();
    expect(test.latest().imageUrl).toBe('');
    expect(test.revokeImageUrl).toHaveBeenCalledExactlyOnceWith('blob:fixture-image');
    test.monitor.dispose();
    expect(test.revokeImageUrl).toHaveBeenCalledOnce();
    const closing = fixture(test.readQr);
    await closing.monitor.poll();
    await settle();
    closing.monitor.dispose();
    expect(closing.revokeImageUrl).toHaveBeenCalledOnce();
  });

  it('close/unmount cancels a pending QR and rejects late images without view updates', async () => {
    const pending = deferred<ApiBlobResult>();
    const test = fixture(vi.fn((_session: string, _signal: AbortSignal) => pending.promise));
    await test.monitor.poll();
    const count = test.changes.length;
    test.monitor.dispose();
    expect(test.readQr.mock.calls[0][1].aborted).toBe(true);
    pending.resolve({ status: 200, blob: new Blob(['fixture']) });
    await settle();
    expect(test.changes).toHaveLength(count);
    expect(test.createImageUrl).not.toHaveBeenCalled();
  });

  it('does not read a latest account session, and follows only unique current-operation subjects', async () => {
    const test = fixture();
    test.update(operation('running', { subjects: undefined, result: { login_session_id: otherId } }));
    await test.monitor.poll();
    expect(test.readQr).not.toHaveBeenCalled();
    test.update(operation('running', { result: { login_session_id: otherId } }));
    await test.monitor.poll();
    await settle();
    expect(test.readQr.mock.calls[0][0]).toBe(sessionId);
    expect(test.latest().sessionId).toBe(sessionId);
    test.update(operation('running', { subjects: [...operation().subjects!, ...operation().subjects!] }));
    await test.monitor.poll();
    expect(test.latest().sessionId).toBeNull();
    expect(test.readQr).toHaveBeenCalledOnce();
    test.monitor.dispose();
  });

  it.each([
    { id: otherId },
    { kind: 'asset-download' },
    { target: { type: 'account', id: otherId } },
    { target: { type: 'author', id: accountId } }
  ])('rejects mismatched tracked operation %j before reading QR', async (patch) => {
    const test = fixture();
    test.update(operation('running', patch as Partial<Operation>));
    await test.monitor.poll();
    expect(test.readQr).not.toHaveBeenCalled();
    expect(test.latest().hint).toContain('关联无法确认');
    test.monitor.dispose();
  });

  it('single-flights operation reads and discards a response after close', async () => {
    const pending = deferred<Operation>();
    const test = fixture();
    test.readOperation.mockImplementation(() => pending.promise);
    const first = test.monitor.poll();
    await test.monitor.poll();
    expect(test.readOperation).toHaveBeenCalledOnce();
    test.monitor.dispose();
    expect(test.readOperation.mock.calls[0][1].aborted).toBe(true);
    pending.resolve(operation('succeeded'));
    await first;
    expect(test.changes).toHaveLength(0);
    expect(test.terminal).not.toHaveBeenCalled();
  });

  it('a stale session image cannot replace the current tracked session', async () => {
    const pending = deferred<ApiBlobResult>();
    const test = fixture(vi.fn((_session: string, _signal: AbortSignal) => pending.promise));
    await test.monitor.poll();
    test.update(
      operation('running', {
        subjects: [{ type: 'login_session', role: 'execution', id: otherId, created_at: '' }]
      })
    );
    await test.monitor.poll();
    expect(test.readQr.mock.calls[0][1].aborted).toBe(true);
    expect(test.readQr.mock.calls[1][0]).toBe(otherId);
    test.monitor.dispose();
    pending.resolve({ status: 200, blob: new Blob(['fixture']) });
    await settle();
    expect(test.createImageUrl).not.toHaveBeenCalled();
  });
});
