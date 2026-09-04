import { afterEach, describe, expect, it, vi } from 'vitest';

import { api, LatestRequestGate, type LatestRequestResult } from './client';

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

afterEach(() => vi.unstubAllGlobals());

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
