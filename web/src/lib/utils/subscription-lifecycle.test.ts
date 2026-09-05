import { describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { ApiError } from '../api/client';
import type { Subscription, SubscriptionLifecycleResult } from '$lib/types/api';
import {
  isRemovedSubscription,
  isSubscriptionId,
  LOCAL_CREATOR_PREVIEW_NOTICE,
  SUBSCRIPTION_REMOVAL_NOTICE,
  SUBSCRIPTION_RESTORE_NOTICE,
  SUBSCRIPTION_REQUEST_UNAVAILABLE,
  subscriptionFailure,
  subscriptionLifecyclePath,
  subscriptionMatchesView,
  SubscriptionRequestGate,
  validSubscriptionLifecycleResult
} from './subscription-lifecycle';

const firstId = '11111111-1111-4111-8111-111111111111';
const secondId = '22222222-2222-4222-8222-222222222222';
const sentinel = 'PRIVATE_COOKIE_SIGNED_URL_SQL_PROFILE_DO_NOT_RENDER';
const active = { id: firstId, enabled: true, deleted_at: null } as Subscription;
const removed = { ...active, enabled: false, deleted_at: '2026-09-05T15:00:00+00:00' };
const deletedResult: SubscriptionLifecycleResult = {
  id: firstId,
  status: 'deleted',
  changed: true,
  cancelled_jobs: 3,
  media_preserved: true
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((done, fail) => {
    resolve = done;
    reject = fail;
  });
  return { promise, resolve, reject };
}

describe('subscription lifecycle request and response contract', () => {
  it('selects exact DELETE and restore paths without query, purge or media flags', () => {
    expect(subscriptionLifecyclePath(firstId, 'delete')).toBe(`/api/v1/subscriptions/${firstId}`);
    expect(subscriptionLifecyclePath(firstId, 'restore')).toBe(`/api/v1/subscriptions/${firstId}/restore`);
  });

  it.each([
    '',
    '../other',
    `${firstId}/restore`,
    `${firstId}?purge=true`,
    firstId.toUpperCase().replace('11111111', 'AAAAAAAA'),
    sentinel
  ])('rejects an invalid identity before it becomes a request path: %s', (id) => {
    expect(isSubscriptionId(id)).toBe(false);
    expect(subscriptionLifecyclePath(id, 'delete')).toBeNull();
    expect(subscriptionLifecyclePath(id, 'restore')).toBeNull();
  });

  it('accepts exact idempotent and changed removal while requiring media preservation', () => {
    expect(validSubscriptionLifecycleResult(deletedResult, firstId, 'delete')).toBe(true);
    expect(
      validSubscriptionLifecycleResult(
        { ...deletedResult, changed: false, cancelled_jobs: 0 },
        firstId,
        'delete'
      )
    ).toBe(true);
    expect(
      validSubscriptionLifecycleResult(
        { ...deletedResult, status: 'paused', cancelled_jobs: 0 },
        firstId,
        'restore'
      )
    ).toBe(true);
  });

  it.each([
    null,
    undefined,
    [],
    sentinel,
    { ...deletedResult, id: secondId },
    { ...deletedResult, media_preserved: false },
    { ...deletedResult, media_preserved: 1 },
    { ...deletedResult, changed: 1 },
    { ...deletedResult, status: 'running' },
    { ...deletedResult, status: 'paused' },
    { ...deletedResult, cancelled_jobs: -1 },
    { ...deletedResult, cancelled_jobs: 1.5 },
    { ...deletedResult, cancelled_jobs: Number.MAX_SAFE_INTEGER + 1 },
    { ...deletedResult, cancelled_jobs: '3' },
    { ...deletedResult, private: sentinel }
  ])('does not announce deletion from malformed or foreign response %j', (value) => {
    expect(validSubscriptionLifecycleResult(value, firstId, 'delete')).toBe(false);
  });

  it('restore is paused with no revived or newly cancelled Jobs', () => {
    expect(validSubscriptionLifecycleResult(deletedResult, firstId, 'restore')).toBe(false);
    expect(validSubscriptionLifecycleResult({ ...deletedResult, status: 'paused' }, firstId, 'restore')).toBe(
      false
    );
    expect(
      validSubscriptionLifecycleResult(
        { ...deletedResult, status: 'enabled', cancelled_jobs: 0 },
        firstId,
        'restore'
      )
    ).toBe(false);
  });

  it('separates active and explicitly removed lists without treating pause as deletion', () => {
    expect(subscriptionMatchesView(active, false)).toBe(true);
    expect(subscriptionMatchesView({ ...active, enabled: false }, false)).toBe(true);
    expect(subscriptionMatchesView(active, true)).toBe(false);
    expect(subscriptionMatchesView(removed, true)).toBe(true);
    expect(subscriptionMatchesView(removed, false)).toBe(false);
    expect(isRemovedSubscription(removed)).toBe(true);
    expect(isRemovedSubscription(active)).toBe(false);
  });

  it.each([
    null,
    [],
    {},
    { ...active, id: '../x' },
    { ...active, deleted_at: undefined },
    { ...active, deleted_at: sentinel },
    { ...removed, enabled: true }
  ])('fails closed for invalid lifecycle state %j', (value) => {
    expect(subscriptionMatchesView(value, false)).toBe(false);
    expect(subscriptionMatchesView(value, true)).toBe(false);
  });
});

describe('closed subscription failure messages', () => {
  it('busy points to Jobs and makes no process-termination claim', () => {
    const error = subscriptionFailure(new ApiError(409, 'subscription_busy', { detail: sentinel }));
    expect(error.destination).toBe('jobs');
    expect(error.message).toContain('本次未删除');
    expect(error.message).toContain('任务页面');
    expect(error.message).not.toContain(sentinel);
  });

  it('removed conflict and 404 offer the removed view without silent re-creation', () => {
    expect(subscriptionFailure(new ApiError(409, 'subscription_removed', sentinel)).destination).toBe(
      'deleted'
    );
    expect(subscriptionFailure(new ApiError(404, sentinel, sentinel)).destination).toBe('deleted');
    expect(subscriptionFailure(new ApiError(409, 'subscription_removed', sentinel)).message).toContain(
      '不会重新创建'
    );
  });

  it.each([
    new Error(sentinel),
    new ApiError(500, sentinel, { detail: sentinel }),
    new ApiError(409, 'constructor', sentinel),
    new ApiError(500, '__proto__', sentinel),
    { code: 'subscription_busy', message: sentinel },
    sentinel,
    null
  ])('never reflects unknown errors %j', (error) => {
    expect(subscriptionFailure(error)).toEqual({
      message: SUBSCRIPTION_REQUEST_UNAVAILABLE,
      destination: null
    });
    expect(JSON.stringify(subscriptionFailure(error))).not.toContain(sentinel);
  });
});

describe('subscription request generations', () => {
  it.each(['success', 'failure'])('late active-list %s cannot overwrite removed view', async (outcome) => {
    const pending = deferred<Subscription[]>();
    const gate = new SubscriptionRequestGate();
    let oldSignal!: AbortSignal;
    const old = gate.run(
      (signal) => {
        oldSignal = signal;
        return pending.promise;
      },
      (rows) => rows.every((row) => subscriptionMatchesView(row, false))
    );
    expect(
      await gate.run(
        async () => [removed],
        (rows) => rows.every((row) => subscriptionMatchesView(row, true))
      )
    ).toEqual({ kind: 'fulfilled', value: [removed] });
    expect(oldSignal.aborted).toBe(true);
    if (outcome === 'success') pending.resolve([active]);
    else pending.reject(new Error(sentinel));
    expect(await old).toEqual({ kind: 'superseded' });
  });

  it.each([
    'detail switch',
    'modal close',
    'same-ID reopen',
    'delete/restore',
    'logout/unmount',
    'creator input change'
  ])('invalidates pending work on %s without retry or a success claim', async () => {
    const pending = deferred<SubscriptionLifecycleResult>();
    const request = vi.fn((_signal: AbortSignal) => pending.promise);
    const gate = new SubscriptionRequestGate();
    const old = gate.run(request, (value) => validSubscriptionLifecycleResult(value, firstId, 'delete'));
    gate.cancel();
    pending.resolve(deletedResult);
    expect(await old).toEqual({ kind: 'superseded' });
    expect(request).toHaveBeenCalledOnce();
    expect(request.mock.calls[0][0].aborted).toBe(true);
  });

  it('wrong-identity deletion result cannot claim that the requested subscription was deleted', async () => {
    const gate = new SubscriptionRequestGate();
    const request = vi.fn(async () => ({ ...deletedResult, id: secondId }));
    expect(
      await gate.run(request, (value) => validSubscriptionLifecycleResult(value, firstId, 'delete'))
    ).toEqual({ kind: 'failed', failure: subscriptionFailure(null) });
    expect(request).toHaveBeenCalledOnce();
  });

  it('busy response is fixed, not retried, and does not become fulfilled', async () => {
    const gate = new SubscriptionRequestGate();
    const request = vi.fn(async () => {
      throw new ApiError(409, 'subscription_busy', sentinel);
    });
    const result = await gate.run(request);
    expect(result).toEqual({
      kind: 'failed',
      failure: subscriptionFailure(new ApiError(409, 'subscription_busy', null))
    });
    expect(request).toHaveBeenCalledOnce();
    expect(JSON.stringify(result)).not.toContain(sentinel);
  });

  it('exceptions from response validators use only the fixed unavailable result', async () => {
    expect(
      await new SubscriptionRequestGate().run(
        async () => deletedResult,
        () => {
          throw new Error(sentinel);
        }
      )
    ).toEqual({ kind: 'failed', failure: subscriptionFailure(null) });
  });
});

describe('honest subscription confirmation and local preview copy', () => {
  it('dashboard counts enabled subscriptions without claiming they are running', () => {
    const source = readFileSync(new URL('../../routes/+page.svelte', import.meta.url), 'utf8');
    expect(source).toContain('{subscriptions.filter((item) => item.enabled).length} 个已启用');
    expect(source).not.toContain('{subscriptions.filter((item) => item.enabled).length} 个运行中');
  });
  it('names retained media/history/checkpoints and only eligible unstarted cancellation', () => {
    for (const text of ['未开始', '媒体文件', '导出目录', '任务历史', '检查点', '不会清理磁盘文件'])
      expect(SUBSCRIPTION_REMOVAL_NOTICE).toContain(text);
  });
  it('restore retains identity but is paused and does not restart cancelled Jobs', () => {
    for (const text of ['原订阅 ID', '先暂停', '不会恢复已取消任务', '自动开始采集'])
      expect(SUBSCRIPTION_RESTORE_NOTICE).toContain(text);
  });
  it('local preview is not remote nickname/avatar lookup or creator identity verification', () => {
    for (const text of ['本地格式', '不访问平台', '不会自动获取真实昵称或头像', '本地备注'])
      expect(LOCAL_CREATOR_PREVIEW_NOTICE).toContain(text);
  });
});
