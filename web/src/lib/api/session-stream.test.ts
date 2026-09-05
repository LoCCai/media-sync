import { describe, expect, it, vi } from 'vitest';
import { SessionStreamRecovery } from './session-stream';

describe('EventSource session recovery', () => {
  it('closes first and single-flights one session check before allowing fallback', async () => {
    let resolve!: (value: boolean) => void;
    const pending = new Promise<boolean>((done) => {
      resolve = done;
    });
    const events: string[] = [];
    const check = vi.fn(() => {
      events.push('check');
      return pending;
    });
    const recovery = new SessionStreamRecovery(check, () => events.push('fallback'));
    const first = recovery.recover(() => events.push('close'));
    const second = recovery.recover(() => events.push('close'));
    expect(first).toBe(second);
    expect(events).toEqual(['close', 'check', 'close']);
    resolve(true);
    await first;
    expect(events).toEqual(['close', 'check', 'close', 'fallback']);
    expect(check).toHaveBeenCalledOnce();
  });
  it.each([false, 'failure', 'disposed'])(
    'does not restart polling or reconnect for %s authority',
    async (mode) => {
      const fallback = vi.fn();
      const recovery = new SessionStreamRecovery(async () => {
        if (mode === 'failure') throw new Error('unavailable');
        return mode !== false;
      }, fallback);
      const pending = recovery.recover(vi.fn());
      if (mode === 'disposed') recovery.dispose();
      await pending;
      expect(fallback).not.toHaveBeenCalled();
    }
  );
});
