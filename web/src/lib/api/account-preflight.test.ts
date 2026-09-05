import { describe, expect, it, vi } from 'vitest';
import type { Account, LoginPreflight, LoginStatus } from '$lib/types/api';
import { AccountPreflightReader, LOGIN_PREFLIGHT_UNAVAILABLE } from './account-preflight';

const account: Account = {
  id: '11111111-1111-4111-8111-111111111111',
  platform: 'bili',
  adapter: 'mediacrawler',
  display_name: 'synthetic account',
  login_method: 'qr',
  auth_status: 'unknown',
  auth_revision: 0,
  created_at: null
};
const status: LoginStatus = {
  account_id: account.id,
  auth_status: 'unknown',
  auth_updated_at: null,
  login_session_id: null,
  login_session_status: null,
  expires_at: null,
  completed_at: null,
  created_at: null,
  updated_at: null
};
const report: LoginPreflight = {
  ok: true,
  code: 'ready',
  status: 'ready',
  retryable: false,
  account_id: account.id,
  platform: account.platform,
  checks: [],
  live_qualification: 'NOT_RUN'
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((done, fail) => {
    resolve = done;
    reject = fail;
  });
  return { promise, resolve, reject };
}

describe('account-scoped login-start preflight reader', () => {
  it.each([null, { ...status, auth_status: 'authenticated' }, { ...status, account_id: 'other' }])(
    'does not dispatch preflight for absent, authenticated or foreign status',
    async (snapshot) => {
      const readReport = vi.fn(async () => report);
      const reader = new AccountPreflightReader(readReport);
      expect(await reader.read(account, snapshot)).toEqual({ kind: 'skipped' });
      expect(readReport).not.toHaveBeenCalled();
    }
  );

  it.each(['late success', 'late failure'])(
    'authentication invalidates a previous %s response',
    async (outcome) => {
      const deferredReport = deferred<LoginPreflight>();
      let signal: AbortSignal | undefined;
      const readReport = vi.fn((_id: string, requestSignal: AbortSignal) => {
        signal = requestSignal;
        return deferredReport.promise;
      });
      const reader = new AccountPreflightReader(readReport);
      const pending = reader.read(account, status);
      expect(
        await reader.read(
          { ...account, login_method: 'saved_session' },
          { ...status, auth_status: 'authenticated' }
        )
      ).toEqual({ kind: 'skipped' });
      expect(signal?.aborted).toBe(true);
      if (outcome === 'late success') deferredReport.resolve(report);
      else deferredReport.reject(new Error('DO_NOT_RENDER'));
      expect(await pending).toEqual({ kind: 'superseded' });
      expect(readReport).toHaveBeenCalledOnce();
    }
  );

  it.each(['refresh', 'selection change', 'unmount'])('invalidates a pending request on %s', async () => {
    const deferredReport = deferred<LoginPreflight>();
    const reader = new AccountPreflightReader(() => deferredReport.promise);
    const pending = reader.read(account, status);
    reader.invalidate();
    deferredReport.resolve(report);
    expect(await pending).toEqual({ kind: 'superseded' });
  });

  it('does not let an overlapping older preflight replace the latest result', async () => {
    const first = deferred<LoginPreflight>();
    const second = deferred<LoginPreflight>();
    const readReport = vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const reader = new AccountPreflightReader(readReport);
    const old = reader.read(account, status);
    const current = reader.read(account, status);
    const blocked = { ...report, ok: false, code: 'browser_launch_failed' };
    second.resolve(blocked);
    expect(await current).toEqual({ kind: 'fulfilled', report: blocked });
    first.resolve(report);
    expect(await old).toEqual({ kind: 'superseded' });
  });

  it('retains normal preflight for an expired saved session without changing its report', async () => {
    const readReport = vi.fn(async () => report);
    const reader = new AccountPreflightReader(readReport);
    expect(
      await reader.read({ ...account, login_method: 'saved_session' }, { ...status, auth_status: 'expired' })
    ).toEqual({ kind: 'fulfilled', report });
    expect(readReport).toHaveBeenCalledOnce();
    expect(report.live_qualification).toBe('NOT_RUN');
  });

  it.each([{ ...report, account_id: 'other' }, { ...report, platform: 'dy' }, null])(
    'rejects a wrong-identity or missing report without reflecting input',
    async (value) => {
      const reader = new AccountPreflightReader(async () => value as LoginPreflight);
      expect(await reader.read(account, status)).toEqual({
        kind: 'failed',
        message: LOGIN_PREFLIGHT_UNAVAILABLE
      });
    }
  );

  it('keeps genuine read failure fixed and never reflects the exception', async () => {
    const reader = new AccountPreflightReader(async () => {
      throw new Error('DO_NOT_RENDER');
    });
    expect(await reader.read(account, status)).toEqual({
      kind: 'failed',
      message: LOGIN_PREFLIGHT_UNAVAILABLE
    });
  });
});
