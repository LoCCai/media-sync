import { describe, expect, it, vi } from 'vitest';
import type { Job } from '$lib/types/api';
import { JOB_DETAIL_UNAVAILABLE, SchedulerJobDetailReader } from './scheduler-job-detail';
import { schedulerJobDetailRows, schedulerJobDiagnostic } from '../utils/scheduler-job-diagnostics';

const firstId = '11111111-1111-4111-8111-111111111111';
const secondId = '22222222-2222-4222-8222-222222222222';
const job = { job_id: firstId, status: 'failed_terminal', last_error_code: 'schema_invalid' } as Job;

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((done, fail) => {
    resolve = done;
    reject = fail;
  });
  return { promise, resolve, reject };
}

describe('exact-request scheduler Job detail', () => {
  it('reads the exact requested Job through an abortable dependency', async () => {
    const read = vi.fn(async (_id: string, _signal: AbortSignal) => job);
    const reader = new SchedulerJobDetailReader(read);
    expect(await reader.read(firstId)).toEqual({ kind: 'fulfilled', job });
    expect(read).toHaveBeenCalledWith(firstId, expect.any(AbortSignal));
    expect(read).toHaveBeenCalledOnce();
  });

  it.each(['success', 'failure'])('does not let Job A late %s replace Job B', async (outcome) => {
    const first = deferred<Job>();
    const second = deferred<Job>();
    const signals: AbortSignal[] = [];
    const reader = new SchedulerJobDetailReader((id, signal) => {
      signals.push(signal);
      return id === firstId ? first.promise : second.promise;
    });
    const old = reader.read(firstId);
    const current = reader.read(secondId);
    expect(signals[0].aborted).toBe(true);
    const nextJob = { ...job, job_id: secondId, last_error_code: 'scheduler_finalize_failed' };
    second.resolve(nextJob);
    expect(await current).toEqual({ kind: 'fulfilled', job: nextJob });
    if (outcome === 'success') first.resolve(job);
    else first.reject(new Error('DO_NOT_RENDER'));
    expect(await old).toEqual({ kind: 'superseded' });
  });

  it.each(['close', 'select Operation', 'unmount', '401/session change'])(
    'discards pending Job result after %s invalidates the UI generation',
    async () => {
      const pending = deferred<Job>();
      const reader = new SchedulerJobDetailReader(() => pending.promise);
      const result = reader.read(firstId);
      reader.invalidate();
      pending.resolve(job);
      expect(await result).toEqual({ kind: 'superseded' });
    }
  );

  it('fences close and reopen of the same Job', async () => {
    const first = deferred<Job>();
    const read = vi.fn().mockReturnValueOnce(first.promise).mockResolvedValueOnce(job);
    const reader = new SchedulerJobDetailReader(read);
    const old = reader.read(firstId);
    reader.invalidate();
    expect(await reader.read(firstId)).toEqual({ kind: 'fulfilled', job });
    first.resolve({ ...job, last_error_code: 'scheduler_heartbeat_failed' });
    expect(await old).toEqual({ kind: 'superseded' });
  });

  it.each([null, undefined, [], 'DO_NOT_RENDER', { ...job, job_id: secondId }, { detail: 'DO_NOT_RENDER' }])(
    'rejects wrong-identity and malformed response %j without echo',
    async (value) => {
      const reader = new SchedulerJobDetailReader(async () => value as Job);
      expect(await reader.read(firstId)).toEqual({ kind: 'failed', message: JOB_DETAIL_UNAVAILABLE });
    }
  );

  it('rejects unsafe requested identities before transport', async () => {
    const read = vi.fn(async () => job);
    const reader = new SchedulerJobDetailReader(read);
    expect(await reader.read('https://synthetic.invalid/?secret=DO_NOT_RENDER')).toEqual({
      kind: 'failed',
      message: JOB_DETAIL_UNAVAILABLE
    });
    expect(read).not.toHaveBeenCalled();
  });

  it('does not reflect errors or initiate retries', async () => {
    const read = vi.fn(async () => {
      throw new Error('DO_NOT_RENDER');
    });
    const reader = new SchedulerJobDetailReader(read);
    expect(await reader.read(firstId)).toEqual({ kind: 'failed', message: JOB_DETAIL_UNAVAILABLE });
    expect(read).toHaveBeenCalledOnce();
  });

  it('keeps unknown detail fields and error text out of visible projections', async () => {
    const value = { ...job, last_error_code: 'DO_NOT_RENDER', raw_exception: 'DO_NOT_RENDER' };
    const reader = new SchedulerJobDetailReader(async () => value);
    const result = await reader.read(firstId);
    expect(result.kind).toBe('fulfilled');
    if (result.kind !== 'fulfilled') throw new Error('expected synthetic Job');
    expect(JSON.stringify(schedulerJobDetailRows(result.job))).not.toContain('DO_NOT_RENDER');
    expect(JSON.stringify(schedulerJobDiagnostic(result.job, firstId))).not.toContain('DO_NOT_RENDER');
  });
});
