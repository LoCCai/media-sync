import { describe, expect, it, vi } from 'vitest';
import type { Job } from '$lib/types/api';
import {
  JobReportReader,
  jobBusinessSummary,
  jobOperationPhase,
  jobReportArtifact,
  jobReportObservations,
  parseJobReport
} from './job-report';

const A = '11111111-1111-4111-8111-111111111111';
const B = '22222222-2222-4222-8222-222222222222';
const RUN = '33333333-3333-4333-8333-333333333333';
const SUB = '44444444-4444-4444-8444-444444444444';
const OP = '55555555-5555-4555-8555-555555555555';
const AT = '2026-09-05T12:00:00+00:00';
const SECRET = 'DO_NOT_RENDER_cookie_SQL_C:/private/profile?signature=secret';

function fixture(jobId = A) {
  return {
    schema_version: 1,
    application_version: '0.1.0',
    generated_at: AT,
    database: {
      expected_revision: '0009_subscription_removal',
      observed_revision: '0009_subscription_removal',
      revision_matches: true
    },
    job: {
      id: jobId,
      subscription_id: SUB,
      run_id: RUN,
      platform: 'bili',
      status: 'failed_terminal',
      attempt: 1,
      max_attempts: 5,
      error: { code: 'scheduler_heartbeat_storage_busy', availability: 'recognized' },
      available_at: AT,
      created_at: AT,
      started_at: AT,
      finished_at: AT,
      updated_at: AT
    },
    run_found: true,
    run_matches_subscription: true,
    run: {
      id: RUN,
      status: 'running',
      error: { code: null, availability: 'not_recorded' },
      attempt: 1,
      discovered_count: 0,
      updated_count: 0,
      asset_count: 0,
      started_at: AT,
      finished_at: null
    },
    operations: [
      {
        id: OP,
        kind: 'scheduler-run',
        state: 'succeeded',
        phase: 'completed',
        correlation_id: SUB,
        error: { code: null, availability: 'not_recorded' },
        requested_at: AT,
        started_at: AT,
        finished_at: AT
      }
    ],
    operations_truncated: false,
    observations: ['job_terminal_run_nonterminal', 'worker_completed_job_failed']
  };
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

describe('closed exact-Job report projection', () => {
  it('retains the actual failed Job/running Run tuple without guessing a process or credential cause', () => {
    const report = parseJobReport(fixture(), A)!;
    expect(report.job.status).toBe('failed_terminal');
    expect(report.run?.status).toBe('running');
    expect(report.run?.error).toEqual({ code: null, availability: 'not_recorded' });
    expect(report.job.error.code).toBe('scheduler_heartbeat_storage_busy');
    expect(jobReportObservations(report).join(' ')).toContain('不代表仍有进程运行');
    expect(jobReportObservations(report).join(' ')).toContain('两者含义不同');
    const artifact = jobReportArtifact(report, A)!;
    expect(artifact.filename).toBe(`media-sync-job-${A}.json`);
    expect(JSON.parse(artifact.text)).toEqual(report);
    expect(jobReportArtifact(report, B)).toBeNull();
  });

  it('rebuilds nested allowlists and removes arbitrary raw fields and sentinel text from artifacts', () => {
    const value = fixture();
    const dirty = {
      ...value,
      raw_exception: SECRET,
      application_version: SECRET,
      database: { ...value.database, observed_revision: SECRET, path: SECRET },
      job: {
        ...value.job,
        platform: SECRET,
        updated_at: SECRET,
        account_cookie: SECRET,
        error: { code: SECRET, availability: 'recognized', message: SECRET }
      },
      run: {
        ...value.run,
        status: SECRET,
        finished_at: SECRET,
        discovered_count: Number.MAX_SAFE_INTEGER + 1,
        payload: SECRET
      },
      operations: [
        {
          ...value.operations[0],
          phase: SECRET,
          correlation_id: SECRET,
          request_payload: SECRET,
          error: { code: SECRET, availability: 'recognized' }
        }
      ],
      observations: [SECRET, ...value.observations]
    };
    const report = parseJobReport(dirty, A)!;
    expect(report).not.toBeNull();
    expect(report.application_version).toBeNull();
    expect(report.database.revision_matches).toBe(false);
    expect(report.run?.status).toBeNull();
    expect(report.run?.discovered_count).toBeNull();
    expect(report.job.error).toEqual({ code: null, availability: 'unrecognized' });
    expect(report.operations[0].error).toEqual({ code: null, availability: 'ineligible_state' });
    const text = jobReportArtifact(report, A)!.text;
    expect(text).not.toContain(SECRET);
    expect(text).not.toContain('request_payload');
    expect(text).not.toContain('raw_exception');
  });

  it.each([
    null,
    [],
    {},
    { ...fixture(), schema_version: 2 },
    { ...fixture(), job: { ...fixture().job, id: B } },
    { ...fixture(), run: { ...fixture().run, id: B } },
    { ...fixture(), run_matches_subscription: false },
    { ...fixture(), operations: Array.from({ length: 6 }, () => fixture().operations[0]) },
    { ...fixture(), operations: [fixture().operations[0], fixture().operations[0]] },
    { ...fixture(), generated_at: SECRET },
    { ...fixture(), run_found: 'true' },
    { ...fixture(), database: { ...fixture().database, revision_matches: 'true' } }
  ])('rejects wrong versions, identities, unbounded evidence and invalid structural flags', (value) => {
    expect(parseJobReport(value, A)).toBeNull();
  });

  it.each(['attached_run_missing', 'attached_run_scope_mismatch', 'no_attached_run'])(
    'preserves missing or mismatched Run evidence: %s',
    (observation) => {
      const report = parseJobReport(
        {
          ...fixture(),
          run: null,
          run_found: observation === 'attached_run_scope_mismatch',
          run_matches_subscription: false,
          observations: [observation],
          operations_truncated: true
        },
        A
      )!;
      expect(report.run).toBeNull();
      expect(report.observations).toEqual([observation]);
      expect(report.operations_truncated).toBe(true);
    }
  );

  it('never upgrades an explicitly false database match and hides success-state error codes', () => {
    const value = fixture();
    const report = parseJobReport(
      {
        ...value,
        database: { ...value.database, revision_matches: false },
        job: { ...value.job, status: 'succeeded' }
      },
      A
    )!;
    expect(report.database.revision_matches).toBe(false);
    expect(report.job.error).toEqual({ code: null, availability: 'ineligible_state' });
  });

  it.each(['0001_core', '0002_checkpoint'])(
    'preserves real migration identity %s and fixed scheduler operation evidence',
    (revision) => {
      const value = fixture();
      const report = parseJobReport(
        {
          ...value,
          database: { expected_revision: revision, observed_revision: revision, revision_matches: true },
          operations: [
            {
              ...value.operations[0],
              state: 'failed_retryable',
              phase: 'claiming_jobs',
              error: { code: 'scheduler_run_failed', availability: 'recognized' }
            }
          ]
        },
        A
      )!;
      expect(report.database).toEqual({
        expected_revision: revision,
        observed_revision: revision,
        revision_matches: true
      });
      expect(report.operations[0].phase).toBe('claiming_jobs');
      expect(report.operations[0].error.code).toBe('scheduler_run_failed');
      expect(jobOperationPhase('jobs_processed')).toBe('任务批次已处理');
      expect(jobOperationPhase(SECRET)).toBe('阶段待确认');
    }
  );
});

describe('report request lifetime', () => {
  it('does nothing until explicitly read and does not fetch for invalid or unauthenticated requests', async () => {
    let authenticated = false;
    const fetchReport = vi.fn(async () => fixture());
    const reader = new JobReportReader(fetchReport, () => ({ authenticated, epoch: 1 }));
    expect(fetchReport).not.toHaveBeenCalled();
    expect(await reader.read(A)).toEqual({ kind: 'failed' });
    authenticated = true;
    expect(await reader.read(SECRET)).toEqual({ kind: 'failed' });
    expect(fetchReport).not.toHaveBeenCalled();
    expect((await reader.read(A)).kind).toBe('fulfilled');
    expect(fetchReport).toHaveBeenCalledOnce();
  });

  it.each(['success', 'failure'])('ignores Job A late %s after selecting Job B', async (outcome) => {
    const first = deferred<unknown>();
    const reader = new JobReportReader(
      (id) => (id === A ? first.promise : Promise.resolve(fixture(B))),
      () => ({ authenticated: true, epoch: 1 })
    );
    const pending = reader.read(A);
    expect((await reader.read(B)).kind).toBe('fulfilled');
    if (outcome === 'success') first.resolve(fixture());
    else first.reject(new Error(SECRET));
    expect(await pending).toEqual({ kind: 'superseded' });
  });

  it.each(['close', 'switch-operation', 'unmount', 'logout', 'new-session'])(
    'fences a response after %s',
    async (reason) => {
      const pending = deferred<unknown>();
      let session = { authenticated: true, epoch: 1 };
      let requestSignal: AbortSignal | undefined;
      const reader = new JobReportReader(
        (_id, signal) => {
          requestSignal = signal;
          return pending.promise;
        },
        () => session
      );
      const result = reader.read(A);
      if (reason === 'logout') session = { authenticated: false, epoch: 2 };
      else if (reason === 'new-session') session = { authenticated: true, epoch: 2 };
      else {
        reader.invalidate();
        expect(requestSignal?.aborted).toBe(true);
      }
      pending.resolve(fixture());
      expect(await result).toEqual({ kind: 'superseded' });
    }
  );

  it('returns a fixed failure for raw transport exceptions or a wrong Job', async () => {
    const reader = new JobReportReader(
      async () => {
        throw new Error(SECRET);
      },
      () => ({ authenticated: true, epoch: 1 })
    );
    expect(await reader.read(A)).toEqual({ kind: 'failed' });
    const wrong = new JobReportReader(
      async () => fixture(B),
      () => ({ authenticated: true, epoch: 1 })
    );
    expect(await wrong.read(A)).toEqual({ kind: 'failed' });
  });
});

describe('Chinese business-first Job summaries', () => {
  it.each(['queued', 'claimed', 'running', 'succeeded', 'cancelled', 'failed_terminal', 'unexpected'])(
    'provides a next action for %s without raw text',
    (status) => {
      const summary = jobBusinessSummary({ job_id: A, status, last_error_code: SECRET } as Job);
      expect(summary.title).toBeTruthy();
      expect(summary.next).toBeTruthy();
      expect(JSON.stringify(summary)).not.toContain(SECRET);
    }
  );
  it('does not promote scheduler completion into download/export/playback success', () => {
    expect(jobBusinessSummary({ job_id: A, status: 'succeeded' } as Job).detail).toContain(
      '不证明下载、导出或播放完成'
    );
  });
  it('does not promote a cancelled record into process-cleanup evidence', () => {
    expect(jobBusinessSummary({ job_id: A, status: 'cancelled' } as Job).detail).toContain(
      '不能据此证明进程清理完成'
    );
  });
});
