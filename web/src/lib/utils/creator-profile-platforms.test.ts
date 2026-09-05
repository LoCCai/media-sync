import { describe, expect, it, vi } from 'vitest';
import type { Account, CreatorLookupScope, CreatorProfile } from '$lib/types/api';
import {
  CreatorLookupController,
  creatorLookupEligibility,
  creatorLookupIdentity,
  parseCreatorProfile,
  validCreatorLookupId
} from './creator-profile';

const accountId = '11111111-1111-4111-8111-111111111111';
const operationId = '22222222-2222-4222-8222-222222222222';
const profileId = '33333333-3333-4333-8333-333333333333';
const generationId = '44444444-4444-4444-8444-444444444444';
const cases = [
  { platform: 'ks', id: '3xSynthetic_ID-9', homepage: 'https://www.kuaishou.com/profile/3xSynthetic_ID-9' },
  { platform: 'zhihu', id: 'test.user-token_9', homepage: 'https://www.zhihu.com/people/test.user-token_9' }
] as const;

describe.each(cases)('$platform exact opaque creator workflow', ({ platform, id, homepage }) => {
  const account = {
    id: accountId,
    platform,
    adapter: 'mediacrawler',
    login_method: 'saved_session',
    auth_status: 'authenticated'
  } as Account;
  const identity = { account_id: accountId, platform, creator_remote_id: id };
  const profile: CreatorProfile = {
    ...identity,
    id: profileId,
    nickname: '平台原始昵称',
    profile_url: homepage,
    revision: 1,
    observed_at: '2026-09-06T12:00:00+00:00',
    avatar_revision: 0,
    avatar_observed_at: null,
    avatar_state: 'absent',
    avatar_url: null
  };
  function result(scope: CreatorLookupScope) {
    return {
      operation_id: operationId,
      state: 'succeeded',
      error_code: null,
      lookup: { ...scope, generation: 1, operation_id: operationId, result_profile_revision: 1 },
      profile,
      profile_source: 'lookup_result'
    };
  }

  it('uses opaque IDs without numeric conversion and requires an eligible existing account', () => {
    expect(creatorLookupIdentity(account, ` ${id} `)).toEqual(identity);
    expect(creatorLookupEligibility(account)).toBe('');
    expect(creatorLookupIdentity({ ...account, login_method: 'cookie' }, id)).toEqual(identity);
    expect(creatorLookupIdentity({ ...account, auth_status: 'expired' }, id)).toBeNull();
    expect(creatorLookupIdentity({ ...account, login_method: 'qr' }, id)).toBeNull();
    expect(parseCreatorProfile(profile, identity)).toEqual(profile);
  });

  it.each(['', '.', '..', 'a/b', 'a%2fb', 'a?x=1', 'a#x', 'a\\b', '中文', 'a\n', 'a'.repeat(256)])(
    'rejects an unsafe exact child ID %j',
    (value) => {
      expect(validCreatorLookupId(platform, value)).toBe(false);
      expect(
        parseCreatorProfile(
          { ...profile, creator_remote_id: value },
          { ...identity, creator_remote_id: value }
        )
      ).toBeNull();
    }
  );

  it('rejects cross-platform homepages, absent-avatar lies and stale identity', () => {
    for (const changes of [
      { profile_url: `https://space.bilibili.com/${id}` },
      { profile_url: `${homepage}?token=private` },
      { platform: 'wb' },
      { creator_remote_id: id + 'other' },
      { avatar_url: 'https://unproven.invalid/avatar.jpg' },
      { avatar_state: 'current' }
    ])
      expect(parseCreatorProfile({ ...profile, ...changes }, identity)).toBeNull();
  });

  it('queries once and returns an exact creation receipt without a crawl or login call', async () => {
    let sent: CreatorLookupScope;
    const start = vi.fn(async (scope: CreatorLookupScope) => {
      sent = scope;
      return { operation_id: operationId, state: 'queued' };
    });
    const read = vi.fn(async () => result(sent));
    const controller = new CreatorLookupController(
      { start, read, licenseConfirmed: () => true },
      vi.fn(),
      () => generationId
    );
    controller.setIdentity(identity);
    await controller.query();
    await controller.query();
    expect(controller.snapshot).toMatchObject({ phase: 'succeeded', receipt: operationId, profile });
    expect(start).toHaveBeenCalledTimes(1);
    expect(read).toHaveBeenCalledTimes(1);
    controller.dispose();
  });

  it('does not publish a response arriving after the creator changes', async () => {
    let resolve!: (value: unknown) => void;
    let sent: CreatorLookupScope;
    const start = vi.fn(async (scope: CreatorLookupScope) => {
      sent = scope;
      return { operation_id: operationId, state: 'queued' };
    });
    const read = vi.fn(
      () =>
        new Promise<unknown>((done) => {
          resolve = done;
        })
    );
    const controller = new CreatorLookupController({ start, read }, vi.fn(), () => generationId);
    controller.setIdentity(identity);
    const pending = controller.query();
    await Promise.resolve();
    expect(read).toHaveBeenCalledTimes(1);
    controller.setIdentity({ ...identity, creator_remote_id: id + 'new' });
    resolve(result(sent!));
    await pending;
    expect(controller.snapshot.profile).toBeNull();
    expect(controller.snapshot.receipt).toBeNull();
    expect(controller.snapshot.scope?.creator_remote_id).toBe(id + 'new');
    controller.dispose();
  });
});

it('keeps platform-specific opaque bounds separate from canonical numeric IDs', () => {
  expect(validCreatorLookupId('ks', 'a'.repeat(128))).toBe(true);
  expect(validCreatorLookupId('ks', 'a'.repeat(129))).toBe(false);
  expect(validCreatorLookupId('ks', 'user.name')).toBe(false);
  expect(validCreatorLookupId('zhihu', 'user.name')).toBe(true);
  expect(validCreatorLookupId('zhihu', 'a'.repeat(255))).toBe(true);
  expect(validCreatorLookupId('bili', '3xSynthetic')).toBe(false);
  expect(validCreatorLookupId('wb', '18446744073709551616')).toBe(false);
});
