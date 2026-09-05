import { describe, expect, it } from 'vitest';
import type { Job } from '$lib/types/api';
import {
  schedulerJobDetailRows,
  schedulerJobDiagnostic,
  schedulerJobErrorCode
} from './scheduler-job-diagnostics';

const job: Job = {
  job_id: '11111111-1111-4111-8111-111111111111',
  subscription_id: '22222222-2222-4222-8222-222222222222',
  account_id: '33333333-3333-4333-8333-333333333333',
  platform: 'bili',
  status: 'failed_terminal',
  attempt: 1,
  max_attempts: 5,
  available_at: '2026-09-05T12:00:00+00:00',
  scheduled_for: null,
  run_id: '44444444-4444-4444-8444-444444444444',
  created_at: '2026-09-05T12:00:00Z',
  updated_at: '2026-09-05T12:00:01.123456+00:00',
  started_at: '2026-09-05T12:00:00+00:00',
  finished_at: '2026-09-05T12:00:01+00:00',
  last_error_code: 'schema_invalid'
};
const codes = [
  'rate_limited',
  'risk_controlled',
  'temporary_upstream',
  'upstream_timeout',
  'upstream_unavailable',
  'account_busy',
  'auth_expired',
  'credentials_unavailable',
  'captcha_required',
  'interactive_required',
  'license_acknowledgement_required',
  'qr_required',
  'configuration_invalid',
  'handler_unsupported',
  'output_security_failed',
  'schema_invalid',
  'unexpected_handler_failure',
  'scheduler_heartbeat_failed',
  'scheduler_heartbeat_storage_busy',
  'scheduler_finalize_failed'
];

describe('fixed scheduler Job diagnostics', () => {
  it.each(codes)('accepts only the classified fixed code %s with an explanation', (last_error_code) => {
    const value = { ...job, last_error_code };
    expect(schedulerJobErrorCode(value)).toBe(last_error_code);
    const diagnostic = schedulerJobDiagnostic(value);
    expect(diagnostic).toMatchObject({ code: last_error_code, tone: 'danger' });
    expect(diagnostic?.title).toBeTruthy();
    expect(diagnostic?.next).toBeTruthy();
  });

  it.each(['failed_retryable', 'failed_terminal', 'retry_wait', 'waiting_auth', 'waiting_user', 'fenced'])(
    'shows a fixed error only in eligible status %s',
    (status) => {
      expect(schedulerJobErrorCode({ ...job, status })).toBe('schema_invalid');
      expect(schedulerJobDiagnostic({ ...job, status })?.tone).toBe(
        status.startsWith('failed_') ? 'danger' : 'warning'
      );
    }
  );

  it.each([
    'failed',
    'queued',
    'claimed',
    'running',
    'cancelled',
    'succeeded',
    'idle',
    'unknown',
    'DO_NOT_RENDER'
  ])('does not promote a stale failure code in noneligible status %s', (status) => {
    const value = { ...job, status };
    expect(schedulerJobErrorCode(value)).toBeNull();
    expect(schedulerJobDiagnostic(value)).toBeNull();
    expect(schedulerJobDetailRows(value).find((row) => row.key === 'last_error_code')?.value).toBeNull();
  });

  it.each([
    undefined,
    null,
    '',
    'well_formed_unknown',
    'SCHEMA_INVALID',
    'DO_NOT_RENDER',
    'https://synthetic.invalid/?cookie=DO_NOT_RENDER',
    'constructor',
    '__proto__',
    'toString',
    true,
    7,
    [],
    { code: 'schema_invalid', detail: 'DO_NOT_RENDER' }
  ])('keeps old, unknown and malformed code %j unavailable without reflecting it', (last_error_code) => {
    const value = { ...job, last_error_code } as unknown as Job;
    expect(schedulerJobErrorCode(value)).toBeNull();
    expect(schedulerJobDiagnostic(value)).toMatchObject({ code: null, title: '未保存更细诊断' });
    expect(JSON.stringify(schedulerJobDiagnostic(value))).not.toContain('DO_NOT_RENDER');
    expect(JSON.stringify(schedulerJobDetailRows(value))).not.toContain('DO_NOT_RENDER');
  });

  it('retains exact legacy schema ambiguity rather than inventing a Cookie or network cause', () => {
    const diagnostic = schedulerJobDiagnostic(job);
    expect(diagnostic?.title).toBe('任务失败阶段未明确');
    expect(diagnostic?.detail).toContain('可能来自内部检查，也可能来自旧版心跳或收尾兜底');
    expect(diagnostic?.detail).toContain('不能确定失败阶段或 Cookie／网络问题');
    expect(diagnostic?.next).toContain('不要按这个历史错误码替换凭据或直接重试');
  });

  it.each([
    ['scheduler_heartbeat_failed', '调度心跳维护失败'],
    ['scheduler_heartbeat_storage_busy', '调度心跳写入遇到存储忙'],
    ['scheduler_finalize_failed', '任务结果收尾失败']
  ])('separates the confirmed scheduler stage %s', (last_error_code, title) => {
    const diagnostic = schedulerJobDiagnostic({ ...job, last_error_code });
    expect(diagnostic?.title).toBe(title);
    expect(diagnostic?.next).toBeTruthy();
  });

  it('does not call SQLite contention corruption or invalid credentials', () => {
    const diagnostic = schedulerJobDiagnostic({
      ...job,
      last_error_code: 'scheduler_heartbeat_storage_busy'
    });
    expect(diagnostic?.detail).toContain('不等于数据库损坏');
    expect(diagnostic?.detail).toContain('不证明平台凭据无效');
    expect(diagnostic?.next).toContain('不要删除数据库');
  });

  it('does not borrow another Job identity or mutate records', () => {
    const before = JSON.stringify(job);
    expect(schedulerJobDiagnostic(job, '55555555-5555-4555-8555-555555555555')).toBeNull();
    expect(schedulerJobDiagnostic({ ...job, job_id: 'DO_NOT_RENDER' })).toBeNull();
    schedulerJobDetailRows(job);
    expect(JSON.stringify(job)).toBe(before);
  });

  it('projects the existing fourteen fields plus sanitized error only', () => {
    const value = {
      ...job,
      raw_exception: 'DO_NOT_RENDER',
      payload: { cookie: 'DO_NOT_RENDER' },
      run: { error: 'DO_NOT_RENDER' }
    } as Job;
    const rows = schedulerJobDetailRows(value);
    expect(rows.map((row) => row.key)).toEqual([
      'job_id',
      'subscription_id',
      'account_id',
      'platform',
      'status',
      'attempt',
      'max_attempts',
      'available_at',
      'scheduled_for',
      'run_id',
      'created_at',
      'updated_at',
      'started_at',
      'finished_at',
      'last_error_code'
    ]);
    expect(rows).toContainEqual({ key: 'attempt', value: 1 });
    expect(rows).toContainEqual({ key: 'created_at', value: job.created_at });
    expect(rows).toContainEqual({ key: 'last_error_code', value: 'schema_invalid' });
    expect(JSON.stringify(rows)).not.toContain('DO_NOT_RENDER');
    expect(JSON.stringify(schedulerJobDiagnostic(value))).not.toContain('DO_NOT_RENDER');
  });

  it('does not echo malformed values hidden inside known fields', () => {
    const value = {
      ...job,
      job_id: 'DO_NOT_RENDER',
      subscription_id: 'DO_NOT_RENDER',
      account_id: 'DO_NOT_RENDER',
      platform: 'DO_NOT_RENDER',
      status: 'DO_NOT_RENDER',
      attempt: 'DO_NOT_RENDER',
      max_attempts: false,
      run_id: 'DO_NOT_RENDER',
      created_at: 'DO_NOT_RENDER',
      updated_at: {},
      last_error_code: 'DO_NOT_RENDER'
    } as unknown as Job;
    expect(JSON.stringify(schedulerJobDetailRows(value))).not.toContain('DO_NOT_RENDER');
  });
});
