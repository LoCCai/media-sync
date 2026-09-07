import { readFileSync } from 'node:fs';

import { describe, expect, it, vi } from 'vitest';

import { ApiError } from '../api/client';
import type { SubscriptionDetail, SubscriptionPolicyUpdateResult } from '../types/api';
import {
  subscriptionPolicyChanged,
  subscriptionPolicyDraft,
  subscriptionPolicyFailure,
  subscriptionPolicyRequest,
  SubscriptionPolicyRequestGate,
  validSubscriptionPolicyResult
} from './subscription-policy';

const firstId = '11111111-1111-4111-8111-111111111111';
const sentinel = 'PRIVATE_POLICY_SENTINEL';

function detail(platform: SubscriptionDetail['platform'] = 'xhs'): SubscriptionDetail {
  return {
    id: firstId,
    account_id: '22222222-2222-4222-8222-222222222222',
    platform,
    account_display_name: 'Account',
    author_id: '33333333-3333-4333-8333-333333333333',
    creator_remote_id: 'creator',
    creator_display_name: 'Creator',
    enabled: false,
    deleted_at: null,
    interval_seconds: 3_600,
    max_items: 12,
    watermarked_at: null,
    last_success_at: null,
    next_run_at: null,
    policy_summary: {
      adapter: 'mediacrawler',
      schema_version: platform === 'bili' ? 2 : 1,
      allow_full_history: false,
      ...(platform === 'bili' ? { bili_scope: 'uploads' as const } : {}),
      request_delay_seconds: 5,
      headless: true,
      creator_reference_configured: true
    },
    schedule: {
      subscription_id: firstId,
      status: 'paused',
      interval_seconds: 3_600,
      next_run_at: null,
      last_run_at: null,
      last_success_at: null,
      schedule_revision: 7,
      consecutive_failures: 0
    },
    recent_runs: [],
    recent_jobs: []
  };
}

function request(target = detail()) {
  const draft = subscriptionPolicyDraft(target)!;
  draft.interval_seconds = 7_200;
  draft.max_items = 18;
  draft.request_delay_seconds = 8.5;
  draft.headless = false;
  return subscriptionPolicyRequest(target, draft)!;
}

function response(target = detail()): SubscriptionPolicyUpdateResult {
  const payload = request(target);
  return {
    id: target.id,
    platform: target.platform,
    status: 'paused',
    enabled: false,
    interval_seconds: payload.interval_seconds,
    max_items: payload.max_items,
    schedule_revision: payload.expected_schedule_revision + 1,
    checkpoint_revision: 4,
    next_run_at: null,
    policy_summary: {
      adapter: 'mediacrawler',
      schema_version: target.platform === 'bili' ? 2 : 1,
      allow_full_history: false,
      ...(target.platform === 'bili' ? { bili_scope: payload.bili_scope! } : {}),
      request_delay_seconds: payload.request_delay_seconds,
      headless: payload.headless,
      creator_reference_configured: true
    },
    changed: true,
    checkpoint_preserved: true,
    media_preserved: true
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => (resolve = done));
  return { promise, resolve };
}

describe('paused subscription policy draft', () => {
  it('normalizes a legacy Bili uploads policy without inventing another platform scope', () => {
    const bili = detail('bili');
    bili.policy_summary = { ...bili.policy_summary!, schema_version: 1 };
    delete bili.policy_summary.bili_scope;
    expect(subscriptionPolicyDraft(bili)?.bili_scope).toBe('uploads');
    expect(subscriptionPolicyDraft(detail('xhs'))?.bili_scope).toBeNull();
  });

  it('requires a real change, paused current detail, valid bounds and Bili coupled limits', () => {
    const target = detail('bili');
    const draft = subscriptionPolicyDraft(target)!;
    expect(subscriptionPolicyChanged(target, draft)).toBe(false);
    expect(subscriptionPolicyRequest(target, draft)).toBeNull();
    draft.bili_scope = 'both';
    draft.max_items = 1;
    expect(subscriptionPolicyRequest(target, draft)).toBeNull();
    draft.max_items = 2;
    expect(subscriptionPolicyRequest(target, draft)).toEqual({
      ...draft,
      expected_schedule_revision: 7
    });
    expect(subscriptionPolicyRequest({ ...target, enabled: true }, draft)).toBeNull();
    expect(subscriptionPolicyRequest({ ...target, deleted_at: '2026-09-07T00:00:00Z' }, draft)).toBeNull();
  });

  it.each([
    { policy_summary: undefined },
    { policy_summary: { adapter: 'fake' } },
    { interval_seconds: 59 },
    { max_items: 0 },
    { schedule: { ...detail().schedule, subscription_id: sentinel } },
    { schedule: { ...detail().schedule, interval_seconds: 99 } },
    { policy_summary: { ...detail().policy_summary!, request_delay_seconds: Number.NaN } },
    { policy_summary: { ...detail().policy_summary!, creator_reference_configured: sentinel } },
    { policy_summary: { ...detail().policy_summary!, private: sentinel } }
  ])('fails closed for malformed server detail %j', (patch) => {
    expect(subscriptionPolicyDraft({ ...detail(), ...patch } as unknown as SubscriptionDetail)).toBeNull();
  });
});

describe('policy result and failure contract', () => {
  it('accepts only the exact identity, revision, fields and preservation claims', () => {
    const target = detail();
    const payload = request(target);
    const value = response(target);
    expect(validSubscriptionPolicyResult(value, target.id, target.platform, payload)).toBe(true);
    for (const changed of [
      { ...value, id: sentinel },
      { ...value, schedule_revision: 7 },
      { ...value, enabled: true },
      { ...value, changed: false },
      { ...value, checkpoint_preserved: false },
      { ...value, private: sentinel },
      { ...value, policy_summary: { ...value.policy_summary, request_delay_seconds: 99 } }
    ])
      expect(validSubscriptionPolicyResult(changed, target.id, target.platform, payload)).toBe(false);
  });

  it('maps only fixed errors and never reflects unknown payloads', () => {
    expect(subscriptionPolicyFailure(new ApiError(409, 'subscription_policy_busy', sentinel))).toEqual({
      message: expect.stringContaining('任务页面'),
      destination: 'jobs'
    });
    expect(
      subscriptionPolicyFailure(new ApiError(409, 'subscription_policy_revision_conflict', sentinel))
    ).toEqual({
      message: expect.stringContaining('重新打开详情'),
      destination: 'detail'
    });
    for (const error of [new Error(sentinel), new ApiError(500, sentinel, sentinel), { code: '__proto__' }]) {
      const failure = subscriptionPolicyFailure(error);
      expect(failure.message).toContain('无法确认');
      expect(JSON.stringify(failure)).not.toContain(sentinel);
    }
  });
});

describe('policy request generations', () => {
  it('cancels a stale save and cannot turn its late response into success', async () => {
    const target = detail();
    const payload = request(target);
    const pending = deferred<SubscriptionPolicyUpdateResult>();
    let signal!: AbortSignal;
    const gate = new SubscriptionPolicyRequestGate();
    const old = gate.run(
      (current) => {
        signal = current;
        return pending.promise;
      },
      { subscriptionId: target.id, platform: target.platform, payload }
    );
    gate.cancel();
    expect(signal.aborted).toBe(true);
    pending.resolve(response(target));
    expect(await old).toEqual({ kind: 'superseded' });
  });

  it('rejects wrong returned identity without retrying', async () => {
    const target = detail();
    const payload = request(target);
    const call = vi.fn(async () => ({ ...response(target), id: sentinel }));
    const result = await new SubscriptionPolicyRequestGate().run(call, {
      subscriptionId: target.id,
      platform: target.platform,
      payload
    });
    expect(result.kind).toBe('failed');
    expect(call).toHaveBeenCalledOnce();
    expect(JSON.stringify(result)).not.toContain(sentinel);
  });
});

describe('subscription page wiring', () => {
  it('uses the general PUT policy endpoint and no longer posts the narrow Bili scope editor', () => {
    const source = readFileSync(new URL('../../routes/subscriptions/+page.svelte', import.meta.url), 'utf8');
    expect(source).toContain('/policy`');
    expect(source).toContain("method: 'PUT'");
    expect(source).not.toContain('/bili-scope`');
    expect(source).not.toContain('saveBiliScope');
  });
});
