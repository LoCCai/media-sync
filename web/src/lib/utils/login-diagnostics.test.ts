import { describe, expect, it } from 'vitest';
import type { Account, LoginPreflight, LoginStatus, Operation, PlatformCapability } from '$lib/types/api';
import {
  accountLoginExplanation,
  LOGIN_READINESS_NOTICE,
  operationLoginExplanation,
  operationLoginSession,
  safeLoginDiagnostic,
  trackedLoginOperation
} from './login-diagnostics';
import { accountCompositeState } from './workbench';
import { safeOperationResult } from './operations';

const accountId = '11111111-1111-4111-8111-111111111111';
const operationId = '22222222-2222-4222-8222-222222222222';
const sessionId = '33333333-3333-4333-8333-333333333333';
const otherId = '44444444-4444-4444-8444-444444444444';
const status: LoginStatus = {
  account_id: accountId,
  auth_status: 'failed',
  auth_updated_at: null,
  login_session_id: sessionId,
  login_session_status: 'failed',
  expires_at: null,
  completed_at: null,
  created_at: null,
  updated_at: null,
  diagnostic: {
    operation_id: operationId,
    operation_state: 'failed_terminal',
    runner_status: 'browser_launch_failed',
    error_code: 'operation_login_browser_launch_failed'
  }
};
const operation = {
  id: operationId,
  kind: 'account-login',
  state: 'failed_terminal',
  target: { type: 'account', id: accountId },
  subjects: [{ type: 'login_session', role: 'execution', id: sessionId, created_at: '' }],
  requested_at: '',
  started_at: null,
  finished_at: null,
  phase: null,
  progress: null,
  retryable: false,
  correlation_id: operationId,
  cancel_requested_at: null,
  allowed_actions: [],
  event_sequence: 1,
  result: {
    account_id: accountId,
    login_session_id: sessionId,
    runner_status: 'browser_launch_failed',
    login_session_status: 'failed',
    auth_status: 'failed'
  },
  error_code: 'operation_login_browser_launch_failed'
} as Operation;

describe('fixed login diagnostics', () => {
  it('persists the exact latest-session explanation after JSON reload', () => {
    const restored = JSON.parse(JSON.stringify(status)) as LoginStatus;
    expect(safeLoginDiagnostic(restored, accountId)).toEqual(status.diagnostic);
    const explanation = accountLoginExplanation(restored, accountId);
    expect(explanation?.title).toBe('登录浏览器启动失败');
    expect(explanation?.next).toContain('Xvfb');
    expect(safeOperationResult(operation)?.runner_status).toBe('browser_launch_failed');
    expect(operationLoginExplanation(operation)).toEqual(explanation);
  });

  it.each([undefined, null])('keeps legacy %s diagnostics explicitly unknown', (diagnostic) => {
    const result = accountLoginExplanation({ ...status, diagnostic }, accountId);
    expect(result?.title).toBe('最近登录失败');
    expect(result?.detail).toContain('未保存更细诊断');
    expect(result?.detail).toContain('不能判断');
  });

  it.each([
    { operation_id: 'https://private.invalid/?token=DO_NOT_RENDER' },
    { operation_state: 'DO_NOT_RENDER' },
    { runner_status: 'DO_NOT_RENDER' },
    { runner_status: null },
    { runner_status: undefined },
    { error_code: 'DO_NOT_RENDER' },
    { error_code: null },
    { operation_state: 'running' }
  ])('fails closed for malformed diagnostics: %j', (patch) => {
    const unsafe = { ...status, diagnostic: { ...status.diagnostic, ...patch } } as unknown as LoginStatus;
    expect(safeLoginDiagnostic(unsafe, accountId)).toBeNull();
    expect(JSON.stringify(accountLoginExplanation(unsafe, accountId))).not.toContain('DO_NOT_RENDER');
  });

  it('ignores raw exception fields and rejects a different account', () => {
    const unsafe = {
      ...status,
      diagnostic: { ...status.diagnostic, stderr: 'DO_NOT_RENDER', cookie: 'DO_NOT_RENDER' }
    } as LoginStatus;
    expect(JSON.stringify(safeLoginDiagnostic(unsafe, accountId))).not.toContain('DO_NOT_RENDER');
    expect(JSON.stringify(accountLoginExplanation(unsafe, accountId))).not.toContain('DO_NOT_RENDER');
    expect(accountLoginExplanation(unsafe, otherId)).toBeNull();
    expect(safeLoginDiagnostic({ ...status, login_session_id: 'unknown' }, accountId)).toBeNull();
  });

  it.each([
    ['timed_out', 'expired', 'operation_login_expired', '登录等待超时'],
    ['expired', 'expired', 'operation_login_expired', '登录会话已过期'],
    ['configuration_invalid', 'failed', 'operation_login_failed', '登录环境配置未就绪'],
    ['start_failed', 'failed', 'operation_login_failed', '登录进程未能启动'],
    ['result_invalid', 'failed', 'operation_login_failed', '登录结果无法确认'],
    ['account_busy', 'failed', 'operation_login_failed', '账户登录存在冲突'],
    ['failed', 'failed', 'operation_login_failed', '最近登录失败']
  ])(
    'explains the closed %s disposition without inventing a cause',
    (runner_status, login_session_status, error_code, title) => {
      const incoming = {
        ...status,
        login_session_status,
        auth_status: login_session_status === 'expired' ? 'required' : 'failed',
        diagnostic: { ...status.diagnostic, runner_status, error_code }
      } as LoginStatus;
      expect(safeLoginDiagnostic(incoming, accountId)).toEqual(incoming.diagnostic);
      expect(accountLoginExplanation(incoming, accountId)?.title).toBe(title);
    }
  );

  it.each([
    ['authenticated', 'succeeded', 'authenticated', '登录成功'],
    ['cancelled', 'cancelled', 'required', '登录已取消']
  ])('accepts consistent %s completion with a null error', (runner_status, state, auth_status, title) => {
    const incoming = {
      ...status,
      auth_status,
      login_session_status: state,
      diagnostic: { ...status.diagnostic, runner_status, operation_state: state, error_code: null }
    } as LoginStatus;
    expect(safeLoginDiagnostic(incoming, accountId)).toEqual(incoming.diagnostic);
    expect(accountLoginExplanation(incoming, accountId)?.title).toBe(title);
  });

  it.each([
    ['browser_launch_failed', 'succeeded', 'failed', null],
    ['browser_launch_failed', 'failed_terminal', 'succeeded', 'operation_login_browser_launch_failed'],
    ['browser_launch_failed', 'failed_terminal', 'failed', 'operation_login_failed'],
    ['browser_launch_failed', 'failed_retryable', 'failed', 'operation_login_browser_launch_failed'],
    ['browser_launch_failed', 'interrupted', 'failed', 'operation_interrupted'],
    ['browser_launch_failed', 'cancelled', 'cancelled', null],
    ['authenticated', 'failed_terminal', 'failed', 'operation_login_failed'],
    ['authenticated', 'succeeded', 'failed', null],
    ['authenticated', 'cancelled', 'cancelled', null],
    ['cancelled', 'succeeded', 'succeeded', null],
    ['cancelled', 'cancelled', 'failed', null],
    ['cancelled', 'failed_terminal', 'cancelled', 'operation_login_failed'],
    ['expired', 'failed_terminal', 'expired', 'operation_login_failed'],
    ['timed_out', 'failed_terminal', 'failed', 'operation_login_expired'],
    ['failed', 'failed_terminal', 'failed', 'operation_login_expired'],
    ['configuration_invalid', 'failed_terminal', 'failed', 'account_login_configuration_invalid'],
    ['start_failed', 'failed_terminal', 'failed', 'account_login_start_failed'],
    ['result_invalid', 'failed_terminal', 'failed', 'account_login_result_invalid'],
    ['account_busy', 'failed_terminal', 'failed', 'account_login_busy']
  ])(
    'rejects contradictory runner/state/session/error tuple %s/%s/%s/%s',
    (runner_status, operation_state, login_session_status, error_code) => {
      const incoming = {
        ...status,
        login_session_status,
        diagnostic: { ...status.diagnostic, runner_status, operation_state, error_code }
      } as LoginStatus;
      expect(safeLoginDiagnostic(incoming, accountId)).toBeNull();
    }
  );

  it('does not let a passing preflight replace a failed latest session', () => {
    const account = { id: accountId, platform: 'bili', login_method: 'qr' } as Account;
    const capability = { login_methods: ['qr'], qr_login: true } as PlatformCapability;
    const preflight = { ok: true, checks: [] } as unknown as LoginPreflight;
    expect(accountCompositeState(account, status, capability, preflight).label).toBe('登录浏览器启动失败');
    const ready = accountCompositeState(account, null, capability, preflight);
    expect(ready.label).toBe('允许启动登录');
    expect(ready.detail).toBe(LOGIN_READINESS_NOTICE);
    expect(ready.detail).toContain('不代表已经登录');
  });
});

describe('current operation QR identity', () => {
  it('accepts only the current login operation and exact account target', () => {
    expect(trackedLoginOperation(operation, accountId, operationId)).toBe(operation);
    for (const wrong of [
      { ...operation, id: otherId },
      { ...operation, kind: 'scheduler-run' },
      { ...operation, target: { type: 'author', id: accountId } },
      { ...operation, target: { type: 'account', id: otherId } },
      { ...operation, state: 'DO_NOT_RENDER' }
    ])
      expect(trackedLoginOperation(wrong, accountId, operationId)).toBeNull();
  });

  it('requires exactly one execution login-session subject, never a latest-account fallback', () => {
    expect(operationLoginSession(operation)).toBe(sessionId);
    for (const subjects of [
      undefined,
      [],
      [...operation.subjects!, ...operation.subjects!],
      [{ type: 'login_session', role: 'related', id: sessionId }],
      [{ type: 'login_session', role: 'execution', id: 'DO_NOT_RENDER' }],
      [{ type: 'job', role: 'execution', id: sessionId }]
    ])
      expect(operationLoginSession({ ...operation, subjects } as Operation)).toBeNull();
    const latestAccount = { ...status, login_session_id: otherId };
    expect(latestAccount.login_session_id).not.toBe(operationLoginSession(operation));
  });

  it('requires exact success summary before saying authenticated', () => {
    const success = {
      ...operation,
      state: 'succeeded',
      error_code: null,
      result: {
        ...operation.result,
        runner_status: 'authenticated',
        login_session_status: 'succeeded',
        auth_status: 'authenticated'
      }
    } as Operation;
    expect(operationLoginExplanation(success).tone).toBe('success');
    expect(
      operationLoginExplanation({ ...success, result: { ...success.result, login_session_id: otherId } }).tone
    ).toBe('warning');
    expect(operationLoginExplanation({ ...success, result: null }).tone).toBe('warning');
  });
});
