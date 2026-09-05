import { afterEach, describe, expect, it, vi } from 'vitest';
import { OperatorAuthController, operatorReturnPath } from './operator-auth';

const csrf = 'c'.repeat(43);
const authenticated = () =>
  new Response(JSON.stringify({ authenticated: true, csrf_token: csrf, expires_in_seconds: 60 }));
function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void } {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
const controllers: OperatorAuthController[] = [];
function controller(
  transport: (path: string, init: RequestInit) => Promise<Response>
): OperatorAuthController {
  const instance = new OperatorAuthController(transport);
  controllers.push(instance);
  return instance;
}
afterEach(() => {
  controllers.splice(0).forEach((instance) => instance.dispose());
  vi.useRealTimers();
});

describe('operator auth lifecycle', () => {
  it('starts locked and single-flights bootstrap without requesting business data', async () => {
    const response = deferred<Response>();
    const transport = vi.fn((_path: string, _init: RequestInit) => response.promise);
    const auth = controller(transport);
    expect(auth.snapshot.phase).toBe('checking');
    expect(() => auth.beginRequest()).toThrow('operator_auth_required');
    const first = auth.checkSession();
    const second = auth.checkSession();
    expect(first).toBe(second);
    response.resolve(new Response(JSON.stringify({ authenticated: false })));
    await first;
    expect(transport).toHaveBeenCalledOnce();
    expect(transport.mock.calls[0][0]).toBe('/api/v1/operator-auth/session');
    expect(auth.snapshot.phase).toBe('anonymous');
  });

  it('waits for login then valid session, without placing secrets in published state', async () => {
    const session = deferred<Response>();
    const reached = deferred<boolean>();
    const transport = vi.fn(async (path: string) => {
      if (path.endsWith('/login'))
        return new Response(JSON.stringify({ authenticated: true, expires_in_seconds: 60 }));
      reached.resolve(true);
      return session.promise;
    });
    const auth = controller(transport);
    const pending = auth.login('synthetic-only-login-credential');
    await reached.promise;
    expect(auth.snapshot.phase).toBe('checking');
    session.resolve(authenticated());
    expect(await pending).toBe(true);
    expect(transport.mock.calls.map(([path]) => path)).toEqual([
      '/api/v1/operator-auth/login',
      '/api/v1/operator-auth/session'
    ]);
    expect(auth.snapshot.phase).toBe('authenticated');
    expect(JSON.stringify(auth.snapshot)).not.toContain(csrf);
    expect(JSON.stringify(auth.snapshot)).not.toContain('credential');
  });

  it('finishes an old cookie-clearing bootstrap before dispatching a new login', async () => {
    const old = deferred<Response>();
    const entered = deferred<boolean>();
    let count = 0;
    const transport = vi.fn(async (path: string) => {
      count += 1;
      if (count === 1) {
        entered.resolve(true);
        return old.promise;
      }
      return path.endsWith('/login') ? new Response('{}') : authenticated();
    });
    const auth = controller(transport);
    const initial = auth.checkSession();
    await entered.promise;
    const login = auth.login('synthetic-only-login-credential');
    await Promise.resolve();
    expect(transport).toHaveBeenCalledOnce();
    old.resolve(
      new Response(JSON.stringify({ authenticated: false }), {
        headers: { 'Set-Cookie': 'example=; Max-Age=0' }
      })
    );
    await initial;
    await login;
    expect(transport.mock.calls.map(([path]) => path)).toEqual([
      '/api/v1/operator-auth/session',
      '/api/v1/operator-auth/login',
      '/api/v1/operator-auth/session'
    ]);
    expect(auth.snapshot.phase).toBe('authenticated');
  });

  it.each([
    { authenticated: true },
    { authenticated: true, csrf_token: 'invalid', expires_in_seconds: 60 },
    { authenticated: true, csrf_token: csrf, expires_in_seconds: 0 },
    { authenticated: true, csrf_token: csrf, expires_in_seconds: 28_801 }
  ])('fails closed for malformed session %j', async (payload) => {
    const auth = controller(async () => new Response(JSON.stringify(payload)));
    expect(await auth.checkSession()).toBe(false);
    expect(auth.snapshot).toMatchObject({ phase: 'error', code: 'operator_session_invalid' });
    expect(() => auth.beginRequest()).toThrow();
  });

  it('expires the session and aborts every protected request', async () => {
    vi.useFakeTimers();
    const auth = controller(async () => authenticated());
    await auth.checkSession();
    const grant = auth.beginRequest();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(auth.snapshot).toMatchObject({ phase: 'anonymous', code: 'operator_session_expired' });
    expect(grant.signal.aborted).toBe(true);
    expect(() => grant.assertCurrent()).toThrow();
  });

  it('keeps logout unconfirmed on network failure, and retries without reopening private state', async () => {
    let fail = true;
    const transport = vi.fn(async (path: string, _init: RequestInit) => {
      if (path.endsWith('/logout')) {
        if (fail) throw new Error('transport');
        return new Response(null, { status: 204 });
      }
      return authenticated();
    });
    const auth = controller(transport);
    await auth.checkSession();
    const grant = auth.beginRequest();
    const logout = auth.logout();
    expect(grant.signal.aborted).toBe(true);
    expect(auth.snapshot.phase).toBe('checking');
    expect(await logout).toBe(false);
    expect(auth.snapshot.phase).toBe('logout_unconfirmed');
    fail = false;
    expect(await auth.logout()).toBe(true);
    expect(auth.snapshot).toMatchObject({ phase: 'anonymous', code: 'operator_logged_out' });
    const request = transport.mock.calls.find(([path]) => path.endsWith('/logout'))!;
    expect((request[1].headers as Record<string, string>)['x-media-sync-csrf']).toBe(csrf);
  });

  it('queues a new CSRF recheck behind an obsolete pending check', async () => {
    let count = 0;
    const delayed = deferred<Response>();
    const entered = deferred<boolean>();
    const auth = controller(async () => {
      count += 1;
      if (count === 2) {
        entered.resolve(true);
        return delayed.promise;
      }
      return authenticated();
    });
    await auth.checkSession();
    const epoch = auth.snapshot.epoch;
    const old = auth.checkSession();
    await entered.promise;
    auth.rejectSession(epoch, 'operator_csrf_forbidden');
    delayed.resolve(authenticated());
    await old;
    await auth.checkSession();
    expect(count).toBe(3);
    expect(auth.snapshot.phase).toBe('authenticated');
  });
});

describe('fixed login return paths', () => {
  it.each(['accounts', 'subscriptions', 'contents', 'assets', 'library', 'jobs', 'settings', 'diagnostics'])(
    'accepts only the exact /%s path',
    (path) => {
      expect(operatorReturnPath(`?return_to=%2F${path}`)).toBe(`/${path}`);
    }
  );
  it.each([
    '?return_to=https://example.invalid',
    '?return_to=//example.invalid',
    '?return_to=/accounts?secret=x',
    '?return_to=/legacy',
    '?return_to=/jobs&return_to=/accounts',
    '?return_to=/accounts/'
  ])('rejects unsafe or ambiguous destinations %s', (search) => {
    expect(operatorReturnPath(search)).toBeNull();
  });
});
