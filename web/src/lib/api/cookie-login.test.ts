import { afterEach, describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { ApiError } from './client';
import type { Account, LoginStatus, Operation, Platform, PlatformCapability } from '$lib/types/api';
import {
  COOKIE_LOGIN_FOLLOW_UP,
  COOKIE_LOGIN_LICENSE_REQUIRED,
  COOKIE_LOGIN_SUCCESS,
  COOKIE_LOGIN_UNKNOWN,
  CookieLoginController,
  cookieInputIssue,
  cookieLoginEligibility,
  cookieLoginFailure,
  parseCookieLoginOperation,
  safeCookieLoginErrorCode,
  type CookieLoginScope,
  type CookieLoginView
} from './cookie-login';
import { accountCompositeState, loginPreflightDisposition } from '../utils/workbench';
import { operationErrorLabel, operationTruthNotice, safeOperationResult } from '../utils/operations';
import { operationLabel } from '../utils/format';

const accountId = '11111111-1111-4111-8111-111111111111';
const operationId = '22222222-2222-4222-8222-222222222222';
const otherId = '33333333-3333-4333-8333-333333333333';
const generationId = '44444444-4444-4444-8444-444444444444';
const sentinel = 'PRIVATE_COOKIE_VALUE_MUST_NEVER_ENTER_VIEW';
const account: Account = {
  id: accountId,
  platform: 'bili',
  adapter: 'mediacrawler',
  display_name: 'synthetic account',
  login_method: 'qr',
  auth_status: 'required',
  auth_revision: 5,
  created_at: null
};
const capability = {
  platform: 'bili',
  pasted_cookie_login: true,
  qr_login: true,
  login_methods: ['qr', 'cookie', 'saved_session']
} as PlatformCapability;
const scope: CookieLoginScope = {
  account_id: accountId,
  platform: 'bili',
  expected_auth_revision: 5,
  frontend_generation: generationId
};
const success = {
  account_id: accountId,
  auth_status: 'authenticated',
  login_method: 'cookie',
  auth_revision: 6
};
function operation(changes: Record<string, unknown> = {}) {
  return {
    id: operationId,
    kind: 'account-cookie-login',
    target: { type: 'account', id: accountId },
    state: 'succeeded',
    result: success,
    error_code: null,
    ...changes
  };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
function setup() {
  let generation = 0;
  const session = { epoch: 1, authenticated: true };
  const views: CookieLoginView[] = [];
  const transport = {
    session: () => session,
    licenseConfirmed: vi.fn(() => true),
    start: vi.fn(
      async (_scope: CookieLoginScope, _candidate: string, _signal: AbortSignal): Promise<unknown> => ({
        operation_id: operationId,
        state: 'queued'
      })
    ),
    read: vi.fn(async (_id: string, _signal: AbortSignal): Promise<unknown> => operation())
  };
  const controller = new CookieLoginController(
    transport,
    (view) => views.push(view),
    () => `aaaaaaaa-aaaa-4aaa-8aaa-${String(++generation).padStart(12, '0')}`
  );
  controller.setContext(account, capability, 1);
  return { controller, transport, session, views };
}
afterEach(() => vi.useRealTimers());

describe('explicit bounded Cookie submission', () => {
  it('never submits on context setup and preserves first-equals values exactly', async () => {
    const { controller, transport, views } = setup();
    expect(transport.start).not.toHaveBeenCalled();
    const candidate = `a=${sentinel}==; b=abc=def`;
    await controller.submit(candidate);
    expect(transport.start).toHaveBeenCalledExactlyOnceWith(
      expect.objectContaining({ account_id: accountId, platform: 'bili', expected_auth_revision: 5 }),
      candidate,
      expect.any(AbortSignal)
    );
    expect(controller.snapshot).toMatchObject({
      phase: 'saved',
      result: success,
      message: COOKIE_LOGIN_SUCCESS
    });
    expect(JSON.stringify(views)).not.toContain(sentinel);
    expect(transport.read).toHaveBeenCalledExactlyOnceWith(operationId, expect.any(AbortSignal));
  });
  it.each(['', ' ', 'a=中文', 'a=x\n', 'a=x\r', 'a=\t', 'a=\x7f', 'a=' + 'x'.repeat(16_383)])(
    'refuses invalid local input without a request',
    async (candidate) => {
      const { controller, transport } = setup();
      await controller.submit(candidate);
      expect(controller.snapshot.phase).toBe('not_started');
      expect(transport.start).not.toHaveBeenCalled();
    }
  );
  it('accepts the 16 KiB boundary without trimming or destructive parsing', () => {
    expect(cookieInputIssue('a=' + 'x'.repeat(16_382))).toBe('');
    expect(cookieInputIssue('a=abc==; b=def')).toBe('');
  });
  it('does not create an attempt or HTTP request before local license consent', async () => {
    const { controller, transport } = setup();
    transport.licenseConfirmed.mockReturnValue(false);
    const generation = controller.snapshot.scope?.frontend_generation;
    await controller.submit(`a=${sentinel}`);
    expect(controller.snapshot).toMatchObject({
      phase: 'not_started',
      operation_id: null,
      message: COOKIE_LOGIN_LICENSE_REQUIRED
    });
    expect(controller.snapshot.scope?.frontend_generation).toBe(generation);
    expect(transport.start).not.toHaveBeenCalled();
    transport.licenseConfirmed.mockReturnValue(true);
    await controller.submit('a=synthetic');
    expect(controller.snapshot.phase).toBe('saved');
  });
  it.each(['bili', 'xhs', 'wb', 'zhihu', 'tieba'] as Platform[])(
    'allows capability-enabled %s accounts and replacements',
    (platform) => {
      const current = { ...account, platform, login_method: 'cookie' as const, auth_status: 'authenticated' };
      expect(cookieLoginEligibility(current, { ...capability, platform })).toBe('');
    }
  );
  it.each(['dy', 'ks'] as Platform[])('does not pretend %s has a pasted validator', (platform) => {
    expect(cookieLoginEligibility({ ...account, platform }, { ...capability, platform })).not.toBe('');
  });
  it.each([
    [null, capability],
    [account, null],
    [account, { ...capability, platform: 'xhs' }],
    [account, { ...capability, pasted_cookie_login: false }],
    [account, { ...capability, pasted_cookie_login: undefined }],
    [{ ...account, adapter: 'fake' }, capability],
    [{ ...account, auth_revision: undefined }, capability],
    [{ ...account, auth_revision: -1 }, capability],
    [{ ...account, auth_revision: 1.5 }, capability],
    [{ ...account, auth_revision: Number.MAX_SAFE_INTEGER }, capability],
    [{ ...account, auth_status: 'authenticating' }, capability]
  ])('rejects unavailable or stale context', (current, cap) => {
    expect(cookieLoginEligibility(current as Account | null, cap as PlatformCapability | null)).not.toBe('');
  });
});

describe('exact atomic outcome and safe error projection', () => {
  it('requires exact operation id, kind, target and revision, with no extra public result properties', () => {
    expect(parseCookieLoginOperation(operation(), scope, operationId)?.result).toEqual(success);
    for (const changes of [
      { id: otherId },
      { kind: 'account-login' },
      { target: null },
      { target: { type: 'subscription', id: accountId } },
      { target: { type: 'account', id: otherId } },
      { state: 'unknown' },
      { error_code: sentinel },
      { result: { ...success, account_id: otherId } },
      { result: { ...success, auth_status: 'required' } },
      { result: { ...success, login_method: 'saved_session' } },
      { result: { ...success, auth_revision: 5 } },
      { result: { ...success, auth_revision: 7 } },
      { result: { ...success, auth_revision: true } },
      { result: { ...success, cookie: sentinel } },
      { result: null }
    ])
      expect(parseCookieLoginOperation(operation(changes), scope, operationId)).toBeNull();
  });
  it('known rejection preserves the prior account without mutating its local status', async () => {
    const { controller, transport } = setup();
    transport.read.mockResolvedValue(
      operation({ state: 'failed_terminal', result: null, error_code: 'cookie_login_rejected' })
    );
    await controller.submit(`a=${sentinel}`);
    expect(controller.snapshot.phase).toBe('not_saved');
    expect(controller.snapshot.message).toContain('本次未替换原认证');
    expect(account.auth_revision).toBe(5);
    expect(account.auth_status).toBe('required');
  });
  it.each([
    new Error(sentinel),
    new ApiError(500, sentinel, { cookie: sentinel }),
    new ApiError(408, 'request_timeout', sentinel),
    new ApiError(500, 'cookie_login_save_failed', sentinel)
  ])('does not reflect unknown submission errors or promise rollback', async (error) => {
    const { controller, transport, views } = setup();
    transport.start.mockRejectedValue(error);
    await controller.submit(`a=${sentinel}`);
    expect(controller.snapshot).toMatchObject({ phase: 'unknown', message: COOKIE_LOGIN_UNKNOWN });
    expect(JSON.stringify(views)).not.toContain(sentinel);
    await controller.submit('a=new');
    expect(transport.start).toHaveBeenCalledTimes(1);
  });
  it('an exact pre-start rejection is safe, but losing a read never means rejection', async () => {
    const first = setup();
    first.transport.start.mockRejectedValue(new ApiError(409, 'cookie_login_conflict', sentinel));
    await first.controller.submit('a=synthetic');
    expect(first.controller.snapshot.phase).toBe('not_saved');
    const second = setup();
    second.transport.read.mockRejectedValue(new ApiError(404, 'cookie_login_account_not_found', sentinel));
    await second.controller.submit('a=synthetic');
    expect(second.controller.snapshot.phase).toBe('unknown');
  });
  it.each([
    'operation_execution_failed',
    'cookie_login_save_failed',
    'cookie_login_unlisted',
    sentinel,
    '__proto__',
    'constructor'
  ])('does not treat unknown terminal errors as confirmed unchanged credentials', async (code) => {
    const { controller, transport, views } = setup();
    transport.read.mockResolvedValue(operation({ state: 'failed_terminal', result: null, error_code: code }));
    await controller.submit('a=synthetic');
    expect(controller.snapshot.phase).toBe('unknown');
    expect(JSON.stringify(views)).not.toContain(sentinel);
  });
  it('interrupted outcome stays unknown even if a stale fixed failure code is present', async () => {
    const { controller, transport } = setup();
    transport.read.mockResolvedValue(
      operation({ state: 'interrupted', result: null, error_code: 'cookie_login_rejected' })
    );
    await controller.submit('a=synthetic');
    expect(controller.snapshot.phase).toBe('unknown');
  });
  it('unknown values cannot enter fixed error displays', () => {
    for (const value of [
      sentinel,
      'cookie_login_' + sentinel,
      '__proto__',
      'constructor',
      new Error(sentinel)
    ]) {
      expect(safeCookieLoginErrorCode(value)).toBeNull();
      expect(cookieLoginFailure(value)).toBe(COOKIE_LOGIN_UNKNOWN);
    }
  });
});

describe('bounded local lifetime and stale response isolation', () => {
  it('does not duplicate an in-flight or completed submission', async () => {
    const { controller, transport } = setup();
    const start = deferred<unknown>();
    transport.start.mockReturnValue(start.promise);
    const pending = controller.submit('a=first');
    await controller.submit('a=second');
    expect(transport.start).toHaveBeenCalledTimes(1);
    start.resolve({ operation_id: operationId, state: 'queued' });
    await pending;
    await controller.submit('a=third');
    expect(transport.start).toHaveBeenCalledTimes(1);
  });
  it.each(['close', 'dispose', 'account', 'platform', 'revision', 'session', 'logout'])(
    'invalidates %s before accepting a late successful result',
    async (change) => {
      const { controller, transport, session, views } = setup();
      const read = deferred<unknown>();
      transport.read.mockReturnValue(read.promise);
      const pending = controller.submit(`a=${sentinel}`);
      await Promise.resolve();
      if (change === 'close') controller.setContext(null, null, 1);
      if (change === 'dispose') controller.dispose();
      if (change === 'account') controller.setContext({ ...account, id: otherId }, capability, 1);
      if (change === 'platform')
        controller.setContext({ ...account, platform: 'xhs' }, { ...capability, platform: 'xhs' }, 1);
      if (change === 'revision') controller.setContext({ ...account, auth_revision: 6 }, capability, 1);
      if (change === 'session') session.epoch = 2;
      if (change === 'logout') session.authenticated = false;
      const count = views.length;
      read.resolve(operation());
      await pending;
      expect(views).toHaveLength(count);
      expect(controller.snapshot.phase).not.toBe('saved');
      expect(JSON.stringify(views)).not.toContain(sentinel);
    }
  );
  it.each(['account', 'modal', 'session'])('rejects A to B to A reuse for %s scopes', async (change) => {
    const { controller, transport } = setup();
    const read = deferred<unknown>();
    transport.read.mockReturnValueOnce(read.promise);
    const pending = controller.submit('a=old');
    await Promise.resolve();
    const oldGeneration = controller.snapshot.scope?.frontend_generation;
    if (change === 'account') controller.setContext({ ...account, id: otherId }, capability, 1);
    if (change === 'modal') controller.setContext(null, null, 1);
    if (change === 'session') controller.setContext(account, capability, 2);
    controller.setContext(account, capability, 1);
    expect(controller.snapshot.scope?.frontend_generation).not.toBe(oldGeneration);
    await controller.submit('a=new');
    const latest = controller.snapshot;
    read.resolve(operation({ result: { ...success, auth_revision: 99 } }));
    await pending;
    expect(controller.snapshot).toBe(latest);
    expect(controller.snapshot.phase).toBe('saved');
  });
  it('ends stalled local observation at 90 seconds without resubmission or rollback claims', async () => {
    vi.useFakeTimers();
    const { controller, transport } = setup();
    const start = deferred<unknown>();
    transport.start.mockReturnValue(start.promise);
    const pending = controller.submit('a=synthetic');
    await vi.advanceTimersByTimeAsync(90_000);
    expect(controller.snapshot).toMatchObject({ phase: 'unknown', message: COOKIE_LOGIN_UNKNOWN });
    expect(transport.start.mock.calls[0][2].aborted).toBe(true);
    start.resolve({ operation_id: operationId, state: 'queued' });
    await pending;
    expect(transport.read).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });
  it('clears deadlines immediately on close, even while transport ignores abort', async () => {
    vi.useFakeTimers();
    const { controller, transport } = setup();
    const start = deferred<unknown>();
    transport.start.mockReturnValue(start.promise);
    const pending = controller.submit('a=synthetic');
    controller.setContext(null, null, 1);
    expect(vi.getTimerCount()).toBe(0);
    start.resolve({ operation_id: operationId, state: 'queued' });
    await pending;
    expect(transport.read).not.toHaveBeenCalled();
  });
  it('can explicitly retry rejected input with a fresh frontend generation, never automatically', async () => {
    const { controller, transport } = setup();
    transport.read.mockResolvedValueOnce(
      operation({ state: 'failed_terminal', result: null, error_code: 'cookie_login_rejected' })
    );
    await controller.submit('a=old');
    expect(transport.start).toHaveBeenCalledTimes(1);
    const generation = controller.snapshot.scope?.frontend_generation;
    await controller.submit('a=new');
    expect(transport.start).toHaveBeenCalledTimes(2);
    expect(controller.snapshot.scope?.frontend_generation).not.toBe(generation);
    expect(controller.snapshot.phase).toBe('saved');
  });
});

describe('UI integration and truthful status', () => {
  it('does not let historical QR failure overwrite current Cookie account authentication', () => {
    const current = { ...account, login_method: 'cookie' as const, auth_status: 'authenticated' };
    const historical = {
      account_id: accountId,
      auth_status: 'failed',
      login_session_status: 'failed'
    } as LoginStatus;
    expect(accountCompositeState(current, historical, capability, null).status).toBe('authenticated');
    expect(accountCompositeState(current, null, capability, null).status).toBe('authenticated');
    expect(loginPreflightDisposition(current, historical)).toBe('not_needed');
    expect(cookieLoginEligibility(current, capability)).toBe('');
  });
  it('projects only four safe Operation result fields and closed error codes', () => {
    const entry = operation({
      result: { ...success, cookie: sentinel, credential_ref: sentinel }
    }) as unknown as Operation;
    expect(safeOperationResult(entry)).toEqual(success);
    expect(operationLabel(entry.kind)).toBe('Cookie 校验与保存');
    expect(operationTruthNotice(entry)?.detail).toBe(COOKIE_LOGIN_SUCCESS);
    expect(operationErrorLabel({ ...entry, error_code: sentinel })).toBe('结果未能确认');
    expect(operationErrorLabel({ ...entry, error_code: 'cookie_login_rejected' })).toBe(
      'cookie_login_rejected'
    );
  });
  it('keeps explicit-click input separate, synchronously clears DOM and never uses raw error rendering', () => {
    const source = readFileSync(new URL('../components/CookieLoginDialog.svelte', import.meta.url), 'utf8');
    expect(source).toContain('on:click={submit}');
    expect(source).toContain("inputElement.value = ''");
    expect(source).toContain('onDestroy(() =>');
    expect(source).toContain('controller.dispose()');
    expect(source).toContain('controller.setContext(null, null');
    expect(source).toContain('...mediaCrawlerGate()');
    expect(source).toContain('licenseConfirmed: () => $onboardingAccepted');
    expect(source).toContain('expected_auth_revision: scope.expected_auth_revision');
    expect(source).not.toMatch(/on:(?:blur|paste)|apiMessage|localStorage|sessionStorage|console\.|\{@html/);
    expect(source).not.toMatch(/api\([^\n]*(?:\/login[`,]|\/contents|\/qr)/);
    expect(COOKIE_LOGIN_FOLLOW_UP).toContain('真实平台端到端验收尚未运行');
  });
});
