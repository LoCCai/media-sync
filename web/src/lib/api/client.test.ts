import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { operatorAuth } from '../stores/operator-auth';
import { api, apiBlob, ApiError, LatestRequestGate, type LatestRequestResult } from './client';

interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

beforeEach(async () => {
  vi.stubGlobal('window', {
    setTimeout: globalThis.setTimeout.bind(globalThis),
    clearTimeout: globalThis.clearTimeout.bind(globalThis)
  });
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({ authenticated: true, csrf_token: 'c'.repeat(43), expires_in_seconds: 60 }),
          { headers: { 'Content-Type': 'application/json' } }
        )
    )
  );
  await operatorAuth.checkSession();
});
afterEach(() => {
  operatorAuth.dispose();
  vi.unstubAllGlobals();
});

describe('latest request gate', () => {
  it('aborts the superseded request and prevents its late result from replacing the latest value', async () => {
    const gate = new LatestRequestGate();
    const first = deferred<string>();
    const second = deferred<string>();
    let firstSignal = new AbortController().signal;
    let value = 'initial';

    const apply = async (result: Promise<LatestRequestResult<string>>): Promise<void> => {
      const settled = await result;
      if (settled.status === 'fulfilled') value = settled.value;
    };
    const firstApply = apply(
      gate.run((signal) => {
        firstSignal = signal;
        return first.promise;
      })
    );
    const secondApply = apply(gate.run(() => second.promise));

    expect(firstSignal.aborted).toBe(true);
    second.resolve('latest');
    await secondApply;
    first.resolve('stale');
    await firstApply;

    expect(value).toBe('latest');
  });

  it('invalidates a late response when its owning catalogue snapshot is replaced', async () => {
    const gate = new LatestRequestGate();
    const inspection = deferred<string>();
    let inspectionSignal = new AbortController().signal;
    let grantedAuthorization: string | null = null;
    const applyInspection = (async (): Promise<void> => {
      const result = await gate.run((signal) => {
        inspectionSignal = signal;
        return inspection.promise;
      });
      if (result.status === 'fulfilled') grantedAuthorization = result.value;
    })();

    gate.cancel();
    grantedAuthorization = null;
    expect(inspectionSignal.aborted).toBe(true);

    inspection.resolve('refresh_and_verify');
    await applyInspection;
    expect(grantedAuthorization).toBeNull();
  });

  it('keeps independently loaded resource outcomes separate', async () => {
    const settingsRequest = new LatestRequestGate();
    const qualificationsRequest = new LatestRequestGate();
    const failure = new Error('qualification_store_unavailable');

    const [settings, qualifications] = await Promise.all([
      settingsRequest.run(async () => 'settings'),
      qualificationsRequest.run(async () => Promise.reject(failure))
    ]);
    const previousQualifications = 'previous qualifications';
    const nextSettings = settings.status === 'fulfilled' ? settings.value : 'previous settings';
    const nextQualifications =
      qualifications.status === 'fulfilled' ? qualifications.value : previousQualifications;

    expect(settings).toEqual({ status: 'fulfilled', value: 'settings' });
    expect(qualifications).toEqual({ status: 'rejected', reason: failure });
    expect(nextSettings).toBe('settings');
    expect(nextQualifications).toBe(previousQualifications);
  });

  it('skips a background request while the previous request is unsettled without aborting it', async () => {
    const gate = new LatestRequestGate();
    const first = deferred<string>();
    let firstSignal = new AbortController().signal;
    const firstResult = gate.run((signal) => {
      firstSignal = signal;
      return first.promise;
    });
    const backgroundRequest = vi.fn(async () => 'background');

    await expect(gate.runIfIdle(backgroundRequest)).resolves.toEqual({ status: 'busy' });
    expect(backgroundRequest).not.toHaveBeenCalled();
    expect(firstSignal.aborted).toBe(false);

    first.resolve('first');
    await expect(firstResult).resolves.toEqual({ status: 'fulfilled', value: 'first' });
    await expect(gate.runIfIdle(backgroundRequest)).resolves.toEqual({
      status: 'fulfilled',
      value: 'background'
    });
    expect(backgroundRequest).toHaveBeenCalledOnce();
  });
});

describe('api cancellation', () => {
  it('forwards a caller abort without reporting it as a timeout', async () => {
    vi.stubGlobal('window', {
      setTimeout: globalThis.setTimeout.bind(globalThis),
      clearTimeout: globalThis.clearTimeout.bind(globalThis)
    });
    const fetchMock = vi.fn((_path: string, init: RequestInit) => {
      const signal = init.signal;
      return new Promise<Response>((_resolve, reject) => {
        const abort = (): void => reject(new DOMException('Aborted', 'AbortError'));
        if (signal?.aborted) abort();
        else signal?.addEventListener('abort', abort, { once: true });
      });
    });
    vi.stubGlobal('fetch', fetchMock);
    const controller = new AbortController();

    const pending = api('/api/v1/media-server', { signal: controller.signal });
    controller.abort();

    await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
    expect((fetchMock.mock.calls[0][1].signal as AbortSignal).aborted).toBe(true);
  });

  it('continues to translate its own timeout abort into a request timeout', async () => {
    vi.stubGlobal('window', {
      setTimeout: globalThis.setTimeout.bind(globalThis),
      clearTimeout: globalThis.clearTimeout.bind(globalThis)
    });
    vi.stubGlobal(
      'fetch',
      vi.fn((_path: string, init: RequestInit) => {
        const signal = init.signal;
        return new Promise<Response>((_resolve, reject) => {
          const abort = (): void => reject(new DOMException('Aborted', 'AbortError'));
          if (signal?.aborted) abort();
          else signal?.addEventListener('abort', abort, { once: true });
        });
      })
    );

    await expect(api('/api/v1/media-server', {}, 0)).rejects.toMatchObject({
      status: 408,
      code: 'request_timeout'
    });
  });
});

describe('media-server error copy', () => {
  it('keeps lookup incompleteness distinct from not found', () => {
    const error = new ApiError(503, 'media_server_item_lookup_incomplete', {
      detail: 'media_server_item_lookup_incomplete'
    });

    expect(error.message).toContain('未能证明结果完整');
    expect(error.message).toContain('不会把它当作“未找到”');
  });

  it('states that accepted-but-unobserved completion is unknown and must not be retried', () => {
    const error = new ApiError(503, 'media_server_scan_completion_unknown', {
      detail: 'media_server_scan_completion_unknown'
    });

    expect(error.message).toContain('刷新已接受');
    expect(error.message).toContain('勿自动重试');
  });
});

describe('browser session transport', () => {
  it('normalizes Headers, sends memory CSRF only for unsafe methods, and consumes 204', async () => {
    const fetchMock = vi.fn(async (_path: string, _init: RequestInit) => new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetchMock);
    const headers = new Headers({ 'X-Example': 'retained', 'X-Media-Sync-Csrf': 'caller-forged' });
    await expect(api('/api/v1/example', { method: 'post', headers, body: '{}' })).resolves.toBeUndefined();
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.credentials).toBe('same-origin');
    expect(init.redirect).toBe('error');
    expect((init.headers as Headers).get('x-media-sync-csrf')).toBe('c'.repeat(43));
    expect((init.headers as Headers).get('x-example')).toBe('retained');
    await api('/api/v1/example', { headers });
    expect((fetchMock.mock.calls[1][1].headers as Headers).has('x-media-sync-csrf')).toBe(false);
  });

  it('does not dispatch anonymous, external, backslash, or Bearer requests', async () => {
    const transport = vi.fn();
    vi.stubGlobal('fetch', transport);
    for (const path of [
      'https://example.invalid/api/v1/test',
      '//example.invalid/api/test',
      '/api/\\example'
    ]) {
      await expect(api(path)).rejects.toMatchObject({ code: 'operator_request_forbidden' });
    }
    await expect(
      api('/api/v1/test', { headers: { Authorization: 'Bearer forbidden' } })
    ).rejects.toMatchObject({ code: 'operator_request_forbidden' });
    operatorAuth.dispose();
    await expect(api('/api/v1/test')).rejects.toMatchObject({ code: 'operator_auth_required' });
    expect(transport).not.toHaveBeenCalled();
  });

  it('locks on 401 without replaying the write', async () => {
    const transport = vi.fn(
      async () =>
        new Response(JSON.stringify({ detail: 'operator_auth_required' }), {
          status: 401,
          headers: { 'Content-Type': 'application/json' }
        })
    );
    vi.stubGlobal('fetch', transport);
    await expect(api('/api/v1/example', { method: 'POST', body: '{}' })).rejects.toMatchObject({
      status: 401
    });
    expect(operatorAuth.snapshot.phase).toBe('anonymous');
    expect(transport).toHaveBeenCalledOnce();
  });

  it('locks on a malformed 401 body without attempting JSON parsing', async () => {
    const response = new Response('not-json', {
      status: 401,
      headers: { 'Content-Type': 'application/json' }
    });
    const parse = vi.spyOn(response, 'json');
    const transport = vi.fn(async () => response);
    vi.stubGlobal('fetch', transport);
    await expect(api('/api/v1/example')).rejects.toMatchObject({
      status: 401,
      code: 'operator_auth_required',
      payload: null
    });
    expect(parse).not.toHaveBeenCalled();
    expect(operatorAuth.snapshot.phase).toBe('anonymous');
    expect(transport).toHaveBeenCalledOnce();
  });

  it('locks immediately when a 401 body and its cancellation never settle', async () => {
    const cancellation = vi.fn(() => new Promise<void>(() => undefined));
    const response = new Response(new ReadableStream({ cancel: cancellation }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' }
    });
    const parse = vi.spyOn(response, 'json');
    const transport = vi.fn(async () => response);
    vi.stubGlobal('fetch', transport);
    await expect(api('/api/v1/example', { method: 'POST' })).rejects.toMatchObject({
      status: 401,
      code: 'operator_auth_required',
      payload: null
    });
    expect(parse).not.toHaveBeenCalled();
    expect(cancellation).toHaveBeenCalledOnce();
    expect(operatorAuth.snapshot.phase).toBe('anonymous');
    expect(transport).toHaveBeenCalledOnce();
  });

  it('rechecks CSRF denial but never replays the rejected write', async () => {
    const transport = vi.fn(async (path: string) =>
      path.endsWith('/session')
        ? new Response(
            JSON.stringify({ authenticated: true, csrf_token: 'd'.repeat(43), expires_in_seconds: 60 }),
            { headers: { 'Content-Type': 'application/json' } }
          )
        : new Response(JSON.stringify({ detail: 'operator_csrf_forbidden' }), {
            status: 403,
            headers: { 'Content-Type': 'application/json' }
          })
    );
    vi.stubGlobal('fetch', transport);
    await expect(api('/api/v1/example', { method: 'POST' })).rejects.toMatchObject({ status: 403 });
    await operatorAuth.checkSession();
    expect(transport.mock.calls.filter(([path]) => path === '/api/v1/example')).toHaveLength(1);
    expect(operatorAuth.snapshot.phase).toBe('authenticated');
  });

  it.each([200, 401])('ignores an old epoch late HTTP %s after a new login', async (status) => {
    const old = deferred<Response>();
    vi.stubGlobal(
      'fetch',
      vi.fn(() => old.promise)
    );
    const pending = api('/api/v1/example');
    operatorAuth.dispose();
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({ authenticated: true, csrf_token: 'd'.repeat(43), expires_in_seconds: 60 })
          )
      )
    );
    await operatorAuth.checkSession();
    const epoch = operatorAuth.snapshot.epoch;
    const response = new Response(JSON.stringify({ detail: 'operator_auth_required' }), {
      status,
      headers: { 'Content-Type': 'application/json' }
    });
    const parse = vi.spyOn(response, 'json');
    old.resolve(response);
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
    expect(parse).not.toHaveBeenCalled();
    expect(operatorAuth.snapshot).toMatchObject({ phase: 'authenticated', epoch });
  });

  it('does not release QR bytes when the session expires during body consumption', async () => {
    const body = deferred<Blob>();
    const consuming = deferred<boolean>();
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'image/png' }),
        blob: () => {
          consuming.resolve(true);
          return body.promise;
        }
      }))
    );
    const pending = apiBlob('/api/v1/login-sessions/example/qr.png');
    await consuming.promise;
    operatorAuth.dispose();
    body.resolve(new Blob(['synthetic'], { type: 'image/png' }));
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
  });

  it.each([202, 404, 410])('keeps QR HTTP %s as a non-image state', async (status) => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('{}', { status }))
    );
    await expect(apiBlob('/api/v1/login-sessions/example/qr.png')).resolves.toEqual({ status, blob: null });
  });
});
