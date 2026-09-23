import { describe, expect, it, vi } from 'vitest';

import {
  NATIVE_QR_FRESH_SECONDS,
  NativeQrRelayMonitor,
  initialNativeQrView,
  type NativeQrView
} from './native-qr-relay';
import type { ApiBlobResult } from './client';

const imageBlob = new Blob([new Uint8Array([1, 2, 3])], { type: 'image/png' });

function fixture(readQr = vi.fn(async (): Promise<ApiBlobResult> => ({ status: 404, blob: null }))) {
  const views: NativeQrView[] = [];
  let clockMs = 1_000_000;
  const created: string[] = [];
  const revoked: string[] = [];
  const monitor = new NativeQrRelayMonitor({
    readQr,
    changed: (view) => views.push(view),
    createImageUrl: (blob) => {
      created.push(`blob:${blob.size}`);
      return `blob:${blob.size}`;
    },
    revokeImageUrl: (url) => revoked.push(url),
    now: () => clockMs,
    guidanceAfterMisses: 3
  });
  return { monitor, views, readQr, advance: (seconds: number) => (clockMs += seconds * 1000) };
}

describe('NativeQrRelayMonitor', () => {
  it('starts in the waiting view without any request', () => {
    expect(initialNativeQrView().state).toBe('waiting');
    expect(initialNativeQrView().imageUrl).toBe('');
  });

  it('shows the image and revokes the previous one on silent refresh', async () => {
    let status: 'missing' | 'present' = 'missing';
    const { monitor, views, advance } = fixture(
      vi.fn(
        async (): Promise<ApiBlobResult> =>
          status === 'present' ? { status: 200, blob: imageBlob } : { status: 404, blob: null }
      )
    );
    await monitor.poll();
    expect(views.at(-1)?.state).toBe('waiting');

    status = 'present';
    await monitor.poll();
    expect(views.at(-1)?.state).toBe('showing');
    expect(views.at(-1)?.imageUrl).toBe('blob:3');

    advance(2);
    await monitor.poll();
    expect(views.at(-1)?.imageUrl).toBe('blob:3');

    status = 'missing';
    advance(NATIVE_QR_FRESH_SECONDS);
    await monitor.poll();
    expect(views.at(-1)?.state).toBe('waiting');
    expect(views.at(-1)?.imageUrl).toBe('');
    expect(views.at(-1)?.hint).toContain('180');
    monitor.dispose();
  });

  it('surfaces platform guidance only after the configured consecutive misses', async () => {
    const { monitor, views } = fixture();
    await monitor.poll();
    await monitor.poll();
    expect(views.at(-1)?.state).toBe('waiting');
    expect(views.at(-1)?.hint).toContain('/crawler/');
    await monitor.poll();
    expect(views.at(-1)?.state).toBe('guidance');
    expect(views.at(-1)?.hint).toContain('Cookie 粘贴');
    monitor.dispose();
  });

  it('keeps polling after transient read failures without claiming a new login', async () => {
    let failures = 2;
    const { monitor, views } = fixture(
      vi.fn(async (): Promise<ApiBlobResult> => {
        if (failures > 0) {
          failures -= 1;
          throw new Error('network');
        }
        return { status: 200, blob: imageBlob };
      })
    );
    await monitor.poll();
    expect(views.at(-1)?.hint).toContain('不会重新发起登录');
    await monitor.poll();
    await monitor.poll();
    expect(views.at(-1)?.state).toBe('showing');
    monitor.dispose();
  });

  it('dispose stops updates and revokes the image', async () => {
    const { monitor, views } = fixture(
      vi.fn(async (): Promise<ApiBlobResult> => ({ status: 200, blob: imageBlob }))
    );
    await monitor.poll();
    expect(views.at(-1)?.imageUrl).toBe('blob:3');
    monitor.dispose();
    const count = views.length;
    await monitor.poll();
    expect(views.length).toBe(count);
  });
});
