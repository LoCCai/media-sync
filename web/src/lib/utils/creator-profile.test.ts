import { afterEach, describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { ApiError } from '../api/client';
import type {
  Account,
  CreatorLookupResponse,
  CreatorLookupScope,
  CreatorProfile,
  Operation,
  Subscription
} from '$lib/types/api';
import {
  CREATOR_LOOKUP_NOTICE,
  CREATOR_LOOKUP_LICENSE_REQUIRED,
  CREATOR_LOOKUP_UNAVAILABLE,
  CREATOR_LOOKUP_WAIT_ENDED,
  CreatorLookupController,
  creatorLookupButtonLabel,
  creatorAvatarEventMatches,
  creatorAvatarKey,
  creatorLookupEligibility,
  creatorLookupFailure,
  creatorLookupIdentity,
  parseCreatorLookup,
  parseCreatorProfile,
  safeCreatorAvatarUrl,
  subscriptionCreatorLabel,
  subscriptionCreatorProfile
} from './creator-profile';
import { operationLabel } from './format';
import { operationTruthNotice, safeOperationResult } from './operations';
import { subscriptionWizardGates } from './workbench';

const accountId = '11111111-1111-4111-8111-111111111111';
const operationId = '22222222-2222-4222-8222-222222222222';
const profileId = '33333333-3333-4333-8333-333333333333';
const otherId = '44444444-4444-4444-8444-444444444444';
const frontendId = '55555555-5555-4555-8555-555555555555';
const sentinel = 'PRIVATE_COOKIE_SIGNED_URL_SQL_PROFILE_MUST_NOT_RENDER';
const account = {
  id: accountId,
  platform: 'bili',
  adapter: 'mediacrawler',
  login_method: 'saved_session',
  auth_status: 'authenticated'
} as Account;
const scope: CreatorLookupScope = {
  account_id: accountId,
  platform: 'bili',
  creator_remote_id: '123456',
  frontend_generation: frontendId
};
const profile: CreatorProfile = {
  id: profileId,
  account_id: accountId,
  platform: 'bili',
  creator_remote_id: '123456',
  nickname: '真实平台昵称',
  profile_url: 'https://space.bilibili.com/123456',
  revision: 2,
  observed_at: '2026-09-05T12:00:00+00:00',
  avatar_revision: 1,
  avatar_observed_at: '2026-09-04T12:00:00+00:00',
  avatar_state: 'retained',
  avatar_url: `/api/v1/creator-profiles/${profileId}/avatar/1`
};

function result(binding = scope, changes: Partial<CreatorLookupResponse> = {}): CreatorLookupResponse {
  return {
    operation_id: operationId,
    state: 'succeeded',
    error_code: null,
    lookup: { ...binding, generation: 3, operation_id: operationId, result_profile_revision: 2 },
    profile: {
      ...profile,
      account_id: binding.account_id,
      creator_remote_id: binding.creator_remote_id,
      profile_url: `https://space.bilibili.com/${binding.creator_remote_id}`
    },
    profile_source: 'lookup_result',
    ...changes
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((done, fail) => {
    resolve = done;
    reject = fail;
  });
  return { promise, resolve, reject };
}

function generationFactory() {
  let index = 0;
  return () => `aaaaaaaa-aaaa-4aaa-8aaa-${String(++index).padStart(12, '0')}`;
}

afterEach(() => vi.useRealTimers());

describe('Bili saved-session eligibility and closed profile projection', () => {
  it('keeps UID a canonical string, including values larger than JavaScript safe integers', () => {
    expect(creatorLookupIdentity(account, ' 123456 ')).toMatchObject({ creator_remote_id: '123456' });
    expect(creatorLookupIdentity(account, '9007199254740993')?.creator_remote_id).toBe('9007199254740993');
    for (const id of [
      '',
      '0',
      '0123',
      '1.2',
      '-1',
      'https://space.bilibili.com/123',
      '12?cookie=x',
      '1'.repeat(21)
    ])
      expect(creatorLookupIdentity(account, id)).toBeNull();
  });

  it.each([
    null,
    { ...account, platform: 'dy' },
    { ...account, adapter: 'fake' },
    { ...account, login_method: 'cookie' },
    { ...account, login_method: 'qr' },
    { ...account, login_method: null },
    { ...account, auth_status: 'expired' },
    { ...account, auth_status: 'authenticating' }
  ])('does not query an unsupported or unauthenticated account %j', (candidate) => {
    expect(creatorLookupIdentity(candidate as Account | null, '123456')).toBeNull();
    expect(creatorLookupEligibility(candidate as Account | null)).not.toBe('');
  });

  it('projects only exact-account public fields and retains independent avatar observation time', () => {
    expect(parseCreatorProfile({ ...profile, raw: sentinel }, scope)).toEqual(profile);
    expect(parseCreatorProfile(profile, { ...scope, account_id: otherId })).toBeNull();
    expect(parseCreatorProfile(profile, { ...scope, creator_remote_id: '42' })).toBeNull();
    expect(parseCreatorProfile(profile, { ...scope, platform: 'xhs' })).toBeNull();
    expect(profile.avatar_observed_at).not.toBe(profile.observed_at);
  });

  it.each([
    null,
    [],
    {},
    { ...profile, nickname: '' },
    { ...profile, nickname: 'x\nCookie: hidden' },
    { ...profile, nickname: 'x'.repeat(513) },
    { ...profile, revision: 0 },
    { ...profile, observed_at: sentinel },
    { ...profile, observed_at: null },
    { ...profile, avatar_state: 'current', avatar_observed_at: null },
    { ...profile, profile_url: 'https://evil.invalid/' },
    { ...profile, profile_url: 'https://space.bilibili.com/123456?cookie=x' }
  ])('rejects malformed profiles %j', (candidate) => {
    expect(parseCreatorProfile(candidate, scope)).toBeNull();
  });

  it('accepts explicit absence, never a remote URL or arbitrary same-origin route', () => {
    const absent = {
      ...profile,
      avatar_state: 'absent',
      avatar_revision: 0,
      avatar_observed_at: null,
      avatar_url: null
    };
    expect(parseCreatorProfile(absent, scope)?.avatar_state).toBe('absent');
    for (const url of [
      'https://i0.hdslb.com/bfs/face/x.png',
      '//evil.invalid/x',
      'data:image/png;base64,abcd',
      'blob:untrusted',
      `/api/v1/creator-profiles/${otherId}/avatar/1`,
      `/api/v1/creator-profiles/${profileId}/avatar/2`,
      `${profile.avatar_url}?url=https://evil.invalid`,
      `/api/v1/creator-profiles/${profileId}/avatar/01`,
      '/api/v1/operator-auth/session',
      `${profile.avatar_url}#x`
    ]) {
      expect(safeCreatorAvatarUrl({ ...profile, avatar_url: url })).toBeNull();
      expect(parseCreatorProfile({ ...profile, avatar_url: url }, scope)).toBeNull();
    }
  });

  it('separates subscription alias from remote nickname and rejects another account profile', () => {
    const subscription = {
      ...scope,
      creator_display_name: '旧名称',
      local_alias: '我写的备注',
      creator_profile: profile
    } as unknown as Subscription;
    expect(subscriptionCreatorLabel(subscription)).toBe('我写的备注');
    expect(subscriptionCreatorLabel({ ...subscription, local_alias: null })).toBe(profile.nickname);
    expect(subscriptionCreatorProfile({ ...subscription, account_id: otherId })).toBeNull();
    expect(subscriptionCreatorLabel({ ...subscription, local_alias: null, creator_profile: null })).toBe(
      '旧名称'
    );
  });
});

describe('exact lookup identity and successful-revision binding', () => {
  it('requires the entire account/platform/creator/frontend/backend/operation tuple', () => {
    expect(parseCreatorLookup(result(), scope, operationId, 3)).toEqual(result());
    for (const changes of [
      { account_id: otherId },
      { platform: 'dy' },
      { creator_remote_id: '42' },
      { frontend_generation: otherId },
      { generation: 4 },
      { operation_id: otherId }
    ])
      expect(
        parseCreatorLookup(
          result(scope, { lookup: { ...result().lookup!, ...changes } as CreatorLookupResponse['lookup'] }),
          scope,
          operationId,
          3
        )
      ).toBeNull();
    expect(parseCreatorLookup(result(scope, { operation_id: otherId }), scope, operationId, 3)).toBeNull();
  });

  it('allows a preparing null lookup, not loss of an already frozen generation', () => {
    const waiting = {
      operation_id: operationId,
      state: 'running',
      error_code: null,
      lookup: null,
      profile: null,
      profile_source: null
    };
    expect(parseCreatorLookup(waiting, scope, operationId, null)?.lookup).toBeNull();
    expect(parseCreatorLookup(waiting, scope, operationId, 3)).toBeNull();
    expect(parseCreatorLookup({ ...waiting, state: 'succeeded' }, scope, operationId, null)).toBeNull();
  });

  it('cannot use a later or earlier revision, or failed operation, as this lookup result', () => {
    expect(
      parseCreatorLookup(result(scope, { profile: { ...profile, revision: 3 } }), scope, operationId, 3)
    ).toBeNull();
    expect(parseCreatorLookup(result(scope, { state: 'failed_terminal' }), scope, operationId, 3)).toBeNull();
    expect(
      parseCreatorLookup(
        result(scope, { lookup: { ...result().lookup!, result_profile_revision: null } }),
        scope,
        operationId,
        3
      )
    ).toBeNull();
    expect(
      parseCreatorLookup(result(scope, { profile_source: 'previous_success' }), scope, operationId, 3)
        ?.profile_source
    ).toBe('previous_success');
  });
});

describe('bounded lookup controller and late-response fences', () => {
  it('a local license refusal sends no lookup, consumes no automatic attempt and claims no history', async () => {
    vi.useFakeTimers();
    let confirmed = false;
    let sent = scope;
    const start = vi.fn(async (value: CreatorLookupScope) => {
      sent = value;
      return { operation_id: operationId, state: 'queued' };
    });
    const read = vi.fn(async () => result(sent));
    const controller = new CreatorLookupController(
      {
        licenseConfirmed: () => confirmed,
        start,
        read
      },
      vi.fn(),
      generationFactory()
    );
    controller.setIdentity(scope);
    await controller.query();
    await controller.query();
    expect(confirmed).toBe(false);
    expect(start).not.toHaveBeenCalled();
    expect(read).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
    expect(controller.snapshot.phase).toBe('not_started');
    expect(controller.snapshot.message).toBe(CREATOR_LOOKUP_LICENSE_REQUIRED);
    expect(controller.snapshot.message).toContain('本次未发起查询');
    expect(controller.snapshot.message).not.toContain('已有资料');
    expect(controller.snapshot.profile).toBeNull();
    expect(controller.snapshot.operation_id).toBeNull();
    expect(controller.snapshot.receipt).toBeNull();
    expect(creatorLookupButtonLabel(controller.snapshot.phase)).toBe('查询作者资料');
    // Only an explicit, externally supplied consent change unlocks a later attempt.
    confirmed = true;
    await controller.query();
    expect(start).toHaveBeenCalledOnce();
    expect(controller.snapshot.receipt).toBe(operationId);
    controller.dispose();
  });

  it('changing input alone sends nothing; Enter/blur and repeated completion submit only once', async () => {
    let sentScope = scope;
    const transport = {
      start: vi.fn(async (sent: CreatorLookupScope) => {
        sentScope = sent;
        return { operation_id: operationId, state: 'queued' };
      }),
      read: vi.fn(async () => result(sentScope))
    };
    const publish = vi.fn();
    const controller = new CreatorLookupController(transport, publish, generationFactory());
    controller.setIdentity(scope);
    expect(transport.start).not.toHaveBeenCalled();
    const first = controller.query();
    await controller.query();
    await first;
    await controller.query();
    expect(transport.start).toHaveBeenCalledOnce();
    expect(transport.read).toHaveBeenCalledOnce();
    expect(controller.snapshot.receipt).toBe(operationId);
    expect(controller.snapshot.profile?.nickname).toBe(profile.nickname);
    expect(Object.keys(sentScope).sort()).toEqual([
      'account_id',
      'creator_remote_id',
      'frontend_generation',
      'platform'
    ]);
    controller.dispose();
  });

  it.each(['success', 'failure'])(
    'A→B→A discards old A %s despite transport ignoring abort',
    async (outcome) => {
      const delayed = deferred<unknown>();
      let firstScope = scope;
      let requests = 0;
      let currentScope = scope;
      const transport = {
        start: vi.fn(async (sent: CreatorLookupScope) => {
          currentScope = sent;
          if (++requests === 1) firstScope = sent;
          return { operation_id: operationId, state: 'queued' };
        }),
        read: vi.fn(async () => (requests === 1 ? delayed.promise : result(currentScope)))
      };
      const controller = new CreatorLookupController(transport, vi.fn(), generationFactory());
      controller.setIdentity(scope);
      const old = controller.query();
      await Promise.resolve();
      controller.setIdentity({ ...scope, creator_remote_id: '42' });
      controller.setIdentity(scope);
      await controller.query();
      const latest = controller.snapshot;
      expect(latest.scope?.frontend_generation).not.toBe(firstScope.frontend_generation);
      if (outcome === 'success')
        delayed.resolve(result(firstScope, { profile: { ...profile, nickname: '过期结果' } }));
      else delayed.reject(new ApiError(500, sentinel, sentinel));
      await old;
      expect(controller.snapshot).toBe(latest);
      expect(JSON.stringify(controller.snapshot)).not.toContain(sentinel);
      controller.dispose();
    }
  );

  it.each(['account', 'session', 'close', 'dispose'])(
    'invalidates pending result after %s change',
    async (change) => {
      const delayed = deferred<unknown>();
      let sent = scope;
      let signal!: AbortSignal;
      const controller = new CreatorLookupController(
        {
          start: async (value, abort) => {
            sent = value;
            signal = abort;
            return { operation_id: operationId, state: 'queued' };
          },
          read: () => delayed.promise
        },
        vi.fn(),
        generationFactory()
      );
      controller.setIdentity(scope, 1);
      const pending = controller.query();
      await Promise.resolve();
      if (change === 'account') controller.setIdentity({ ...scope, account_id: otherId }, 1);
      if (change === 'session') controller.setIdentity(scope, 2);
      if (change === 'close') controller.setIdentity(null);
      if (change === 'dispose') controller.dispose();
      const stopped = controller.snapshot;
      delayed.resolve(result(sent));
      await pending;
      expect(signal.aborted).toBe(true);
      expect(controller.snapshot).toBe(stopped);
      expect(controller.snapshot.receipt).toBeNull();
      controller.dispose();
    }
  );

  it('manual refresh makes a new frontend UUID and preserves previous profile after failure without a receipt', async () => {
    let sent = scope;
    let number = 0;
    const controller = new CreatorLookupController(
      {
        start: async (value) => {
          sent = value;
          number += 1;
          return { operation_id: operationId, state: 'queued' };
        },
        read: async () =>
          number === 1
            ? result(sent)
            : result(sent, {
                state: 'failed_terminal',
                error_code: sentinel,
                profile: null,
                profile_source: null
              })
      },
      vi.fn(),
      generationFactory()
    );
    controller.setIdentity(scope);
    await controller.query();
    const firstGeneration = controller.snapshot.scope?.frontend_generation;
    await controller.query(true);
    expect(controller.snapshot.phase).toBe('failed');
    expect(controller.snapshot.scope?.frontend_generation).not.toBe(firstGeneration);
    expect(controller.snapshot.profile).toEqual(profile);
    expect(controller.snapshot.profile_source).toBe('previous_success');
    expect(controller.snapshot.receipt).toBeNull();
    expect(controller.snapshot.message).toBe(CREATOR_LOOKUP_UNAVAILABLE);
    controller.dispose();
  });

  it('previous_success from a succeeded operation never yields a new creation receipt', async () => {
    let sent = scope;
    const controller = new CreatorLookupController(
      {
        start: async (value) => {
          sent = value;
          return { operation_id: operationId, state: 'queued' };
        },
        read: async () => result(sent, { profile_source: 'previous_success' })
      },
      vi.fn(),
      generationFactory()
    );
    controller.setIdentity(scope);
    await controller.query();
    expect(controller.snapshot.profile).toEqual(profile);
    expect(controller.snapshot.receipt).toBeNull();
    expect(controller.snapshot.phase).not.toBe('succeeded');
    controller.dispose();
  });

  it('stops bounded local waiting and ignores a late success without claiming server cancellation', async () => {
    vi.useFakeTimers();
    const delayed = deferred<unknown>();
    let sent = scope;
    const controller = new CreatorLookupController(
      {
        start: async (value) => {
          sent = value;
          return { operation_id: operationId, state: 'queued' };
        },
        read: () => delayed.promise
      },
      vi.fn(),
      generationFactory()
    );
    controller.setIdentity(scope);
    const pending = controller.query();
    await vi.advanceTimersByTimeAsync(75_000);
    expect(controller.snapshot.phase).toBe('wait_ended');
    expect(controller.snapshot.message).toBe(CREATOR_LOOKUP_WAIT_ENDED);
    delayed.resolve(result(sent));
    await pending;
    expect(controller.snapshot.receipt).toBeNull();
    controller.dispose();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('does not repeat submission after unknown failure', async () => {
    const start = vi.fn(async () => {
      throw new ApiError(500, sentinel, { message: sentinel });
    });
    const read = vi.fn();
    const controller = new CreatorLookupController({ start, read }, vi.fn(), generationFactory());
    controller.setIdentity(scope);
    await controller.query();
    await controller.query();
    expect(start).toHaveBeenCalledOnce();
    expect(read).not.toHaveBeenCalled();
    expect(JSON.stringify(controller.snapshot)).not.toContain(sentinel);
    controller.dispose();
  });

  it('freezes the first backend generation and stops polling when it changes', async () => {
    vi.useFakeTimers();
    let sent = scope;
    let reads = 0;
    const controller = new CreatorLookupController(
      {
        start: async (value) => {
          sent = value;
          return { operation_id: operationId, state: 'queued' };
        },
        read: async () => {
          reads += 1;
          if (reads === 1)
            return result(sent, {
              state: 'running',
              profile: null,
              profile_source: null,
              lookup: { ...sent, operation_id: operationId, generation: 3, result_profile_revision: null }
            });
          return result(sent, {
            lookup: { ...sent, operation_id: operationId, generation: 4, result_profile_revision: 2 }
          });
        }
      },
      vi.fn(),
      generationFactory()
    );
    controller.setIdentity(scope);
    const pending = controller.query();
    await vi.advanceTimersByTimeAsync(1_500);
    await pending;
    expect(reads).toBe(2);
    expect(controller.snapshot.generation).toBe(3);
    expect(controller.snapshot.phase).toBe('failed');
    expect(controller.snapshot.receipt).toBeNull();
    expect(controller.snapshot.profile).toBeNull();
    expect(vi.getTimerCount()).toBe(0);
    controller.dispose();
  });

  it('closing cancels the deadline immediately even when a transport ignores abort', async () => {
    vi.useFakeTimers();
    const delayed = deferred<unknown>();
    const read = vi.fn();
    const controller = new CreatorLookupController(
      { start: () => delayed.promise, read },
      vi.fn(),
      generationFactory()
    );
    controller.setIdentity(scope);
    const pending = controller.query();
    expect(vi.getTimerCount()).toBe(1);
    controller.setIdentity(null);
    expect(vi.getTimerCount()).toBe(0);
    delayed.resolve({ operation_id: operationId, state: 'queued' });
    await pending;
    expect(read).not.toHaveBeenCalled();
    expect(controller.snapshot.scope).toBeNull();
    controller.dispose();
  });
});

describe('creation, image and operation presentation integration', () => {
  it('allows no alias only with an exact receipt preview and preserves full-history consent independently', () => {
    const state = {
      accountId,
      capability: { platform: 'bili', requires_full_history_acknowledgement: true } as never,
      creatorId: '123456',
      creatorName: '',
      profileLookupId: operationId,
      fullHistoryAcknowledged: true,
      preview: {
        ...scope,
        creator_display_name: profile.nickname,
        local_alias: null,
        profile_lookup_id: operationId
      } as never
    };
    expect(subscriptionWizardGates(state).canCreate).toBe(true);
    expect(subscriptionWizardGates({ ...state, profileLookupId: otherId }).canCreate).toBe(false);
    expect(subscriptionWizardGates({ ...state, profileLookupId: null }).canRequestPreview).toBe(false);
    expect(subscriptionWizardGates({ ...state, fullHistoryAcknowledged: false }).canCreate).toBe(false);
  });

  it('keeps image callbacks bound and source URLs same-origin without HTML interpolation or fallback', () => {
    const source = readFileSync(new URL('../components/CreatorProfileCard.svelte', import.meta.url), 'utf8');
    expect(source).toContain('{#key imageKey}');
    expect(source).toContain('creatorAvatarEventMatches(renderedKey, profile, contextKey)');
    expect(source).toContain('safeCreatorAvatarUrl(profile)');
    expect(source).toContain('profile.avatar_observed_at');
    expect(source).not.toContain('{@html');
    expect(source).not.toContain('Date.now');
  });

  it('uses independent completed-input hooks and existing consent, with no login or content calls', () => {
    const source = readFileSync(new URL('../../routes/subscriptions/+page.svelte', import.meta.url), 'utf8');
    expect(source).toContain('on:blur={() => completeCreatorInput()}');
    expect(source).toContain('on:keydown={creatorInputKeydown}');
    expect(source).toContain('...mediaCrawlerGate()');
    expect(source).toContain('licenseConfirmed: () => $onboardingAccepted');
    expect(source).toContain('profile_lookup_id: lookupView.receipt');
    expect(source).not.toContain('creatorName = next.profile');
    expect(source).not.toMatch(/api\([^\n]*(?:\/login|\/contents|\/qr)/);
    expect(CREATOR_LOOKUP_NOTICE).toContain('不扫码、不采集内容');
  });

  it('generic failures do not invent previous data when there has never been a successful observation', () => {
    for (const message of [
      CREATOR_LOOKUP_UNAVAILABLE,
      creatorLookupFailure('creator_profile_failed'),
      creatorLookupFailure('creator_profile_cancelled')
    ]) {
      expect(message).not.toContain('已有资料');
      expect(message).not.toContain('保留上次成功资料');
    }
    expect(creatorLookupButtonLabel('idle')).toBe('查询作者资料');
    expect(creatorLookupButtonLabel('failed')).toBe('重新查询');
  });

  it('labels creator-profile operations and projects only safe IDs/counts, never nicknames or URLs', () => {
    const operation = {
      kind: 'creator-profile',
      state: 'succeeded',
      result: {
        account_id: accountId,
        profile_id: profileId,
        generation: 3,
        revision: 2,
        nickname: sentinel,
        avatar_url: sentinel,
        raw: sentinel
      }
    } as unknown as Operation;
    expect(operationLabel('creator-profile')).toBe('作者资料查询');
    expect(safeOperationResult(operation)).toEqual({
      profile_id: profileId,
      generation: 3,
      revision: 2
    });
    expect(operationTruthNotice(operation)?.detail).toContain('不扫码、不抓取内容');
  });

  it('rejects image errors from a previous identity, avatar revision, operation or session', () => {
    const key = creatorAvatarKey(profile, frontendId);
    expect(creatorAvatarEventMatches(key, profile, frontendId)).toBe(true);
    for (const next of [
      { ...profile, account_id: otherId },
      { ...profile, creator_remote_id: '42' },
      { ...profile, avatar_revision: 2 },
      { ...profile, id: otherId }
    ])
      expect(creatorAvatarEventMatches(key, next, frontendId)).toBe(false);
    expect(creatorAvatarEventMatches(key, profile, otherId)).toBe(false);
  });

  it.each([new Error(sentinel), new ApiError(500, sentinel, sentinel), '__proto__', 'constructor', null])(
    'never reflects unknown errors %j',
    (error) => {
      expect(creatorLookupFailure(error)).toBe(CREATOR_LOOKUP_UNAVAILABLE);
    }
  );
});
