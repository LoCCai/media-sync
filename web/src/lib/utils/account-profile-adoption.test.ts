import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import type { CrawlerProfileAdoption } from '$lib/types/api';

const source = readFileSync(new URL('../../routes/accounts/+page.svelte', import.meta.url), 'utf8');

describe('upstream crawler profile adoption page', () => {
  it('presents one three-step upstream login path and the subscription continuation', () => {
    expect(source).toContain('href="/crawler/"');
    expect(source).toContain('在原生界面完成登录');
    expect(source).toContain('二维码或 Cookie 登录');
    expect(source).toContain('认领已登录会话');
    expect(source).toContain('href="/subscriptions"');
  });

  it('submits the current account revision through one bounded adoption request', () => {
    expect(source).toContain('`/api/v1/accounts/${account.id}/crawler-profile`');
    expect(source).toContain('JSON.stringify({ expected_auth_revision: account.auth_revision })');
    expect(source).toContain('120_000');
    expect(source).toContain('adoptingAccountId === account.id');
  });

  it('keeps only local account creation and removes the duplicate login workbench', () => {
    expect(source).toContain("api<Account>('/api/v1/accounts'");
    expect(source).toContain('JSON.stringify({ platform: formPlatform, display_name: displayName })');
    expect(source).not.toContain('CookieLoginDialog');
    expect(source).not.toContain('LoginAttemptMonitor');
    expect(source).not.toContain('AccountPreflightReader');
    expect(source).not.toContain('apiBlob');
    expect(source).not.toContain('<Modal');
    expect(source).not.toContain('/login-preflight');
    expect(source).not.toContain('/cookie-login');
  });

  it('exposes the closed adoption response contract', () => {
    const adoption: CrawlerProfileAdoption = {
      account_id: '11111111-1111-4111-8111-111111111111',
      platform: 'bili',
      login_method: 'saved_session',
      auth_status: 'authenticated',
      auth_revision: 2
    };

    expect(adoption).toEqual({
      account_id: '11111111-1111-4111-8111-111111111111',
      platform: 'bili',
      login_method: 'saved_session',
      auth_status: 'authenticated',
      auth_revision: 2
    });
  });
});
