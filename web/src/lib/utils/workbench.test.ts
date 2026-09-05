import { describe, expect, it } from 'vitest';

import type {
  Account,
  LoginPreflight,
  LoginStatus,
  PlatformCapability,
  SubscriptionCheckpointSummary,
  SubscriptionPolicySummary,
  SubscriptionPreview
} from '$lib/types/api';

import {
  accountCompositeState,
  AUTHENTICATED_ACCOUNT_NOTICE,
  canStartQrLogin,
  loginPreflightDisposition,
  safeCheckpointSummaryRows,
  safePolicySummaryRows,
  subscriptionWizardGates
} from './workbench';

const biliCapability: PlatformCapability = {
  platform: 'bili',
  display_name: '哔哩哔哩',
  login_methods: ['qr', 'cookie', 'saved_session'],
  qr_login: true,
  creator_input: {
    kind: 'uid',
    label: 'UID',
    placeholder: '纯数字 UID',
    examples: ['123456'],
    allows_secret_reference: false
  },
  requires_full_history_acknowledgement: true,
  offline_shapes: ['video'],
  limitations: ['真人验证未运行'],
  live_qualification: 'NOT_RUN'
};

const account: Account = {
  id: 'account-1',
  platform: 'bili',
  adapter: 'mediacrawler',
  display_name: '主账号',
  login_method: 'qr',
  auth_status: 'unknown',
  created_at: null
};

const passingPreflight: LoginPreflight = {
  ok: true,
  status: 'ready',
  code: 'login_preflight_ready',
  retryable: false,
  account_id: account.id,
  platform: account.platform,
  checks: [{ name: 'browser', status: 'pass', required: true, detail_code: null }],
  live_qualification: 'NOT_RUN'
};

const loginStatus: LoginStatus = {
  account_id: account.id,
  auth_status: 'unknown',
  auth_updated_at: null,
  login_session_id: null,
  login_session_status: null,
  expires_at: null,
  completed_at: null,
  created_at: null,
  updated_at: null
};

const preview: SubscriptionPreview = {
  account_id: account.id,
  platform: account.platform,
  account_display_name: account.display_name,
  creator_remote_id: '123456',
  creator_display_name: '创作者',
  interval_seconds: 21_600,
  max_items: 30,
  policy_summary: {
    adapter: 'mediacrawler',
    schema_version: 1,
    allow_full_history: false,
    request_delay_seconds: 5,
    headless: true,
    creator_reference_configured: false
  },
  exists: false
};

describe('capability-driven account rules', () => {
  it('permits QR login only for an exact passing account preflight', () => {
    expect(canStartQrLogin(account, biliCapability, passingPreflight, loginStatus)).toBe(true);
    expect(
      canStartQrLogin(account, { ...biliCapability, qr_login: false }, passingPreflight, loginStatus)
    ).toBe(false);
    expect(
      canStartQrLogin({ ...account, login_method: 'saved_session' }, biliCapability, passingPreflight, {
        ...loginStatus,
        auth_status: 'expired'
      })
    ).toBe(true);
    expect(
      canStartQrLogin(
        account,
        biliCapability,
        {
          ...passingPreflight,
          ok: false,
          retryable: true,
          checks: [{ name: 'browser', status: 'fail', required: true, detail_code: 'browser_missing' }]
        },
        loginStatus
      )
    ).toBe(false);
    expect(
      canStartQrLogin(account, biliCapability, { ...passingPreflight, account_id: 'other' }, loginStatus)
    ).toBe(false);
  });

  it.each(['unknown', 'required', 'expired', 'failed', 'authenticated', 'authenticating', 'unrecognized'])(
    'requires backend-eligible auth status %s even with a cached passing preflight',
    (auth_status) => {
      const status = { ...loginStatus, auth_status };
      expect(canStartQrLogin(account, biliCapability, passingPreflight, status)).toBe(
        ['unknown', 'required', 'expired', 'failed'].includes(auth_status)
      );
      expect(
        canStartQrLogin(
          { ...account, login_method: 'saved_session' },
          biliCapability,
          passingPreflight,
          status
        )
      ).toBe(auth_status === 'expired');
    }
  );

  it.each(['pending', 'waiting_user', 'running'])(
    'never starts another login for an active %s session',
    (login_session_status) => {
      expect(
        canStartQrLogin(account, biliCapability, passingPreflight, { ...loginStatus, login_session_status })
      ).toBe(false);
    }
  );

  it('keeps unsupported methods/adapters and foreign capabilities ineligible', () => {
    expect(
      canStartQrLogin({ ...account, login_method: 'cookie' }, biliCapability, passingPreflight, loginStatus)
    ).toBe(false);
    expect(
      canStartQrLogin({ ...account, adapter: 'other' }, biliCapability, passingPreflight, loginStatus)
    ).toBe(false);
    expect(
      canStartQrLogin(account, { ...biliCapability, platform: 'dy' }, passingPreflight, loginStatus)
    ).toBe(false);
  });

  it('treats authenticated saved-session preflight as not needed, never as a passed live check', () => {
    const authenticatedAccount = {
      ...account,
      login_method: 'saved_session',
      auth_status: 'authenticated'
    } as Account;
    const status = { ...loginStatus, auth_status: 'authenticated', login_session_status: 'succeeded' };
    const ineligible = { ...passingPreflight, ok: false, code: 'account_login_ineligible' };
    expect(loginPreflightDisposition(authenticatedAccount, status)).toBe('not_needed');
    expect(accountCompositeState(authenticatedAccount, status, biliCapability, ineligible)).toEqual({
      status: 'authenticated',
      label: '已认证',
      detail: '本地保存的认证结果；未实时验证平台会话'
    });
    expect(canStartQrLogin(authenticatedAccount, biliCapability, passingPreflight, status)).toBe(false);
    expect(AUTHENTICATED_ACCOUNT_NOTICE).toContain('只读取已保存结果');
    expect(AUTHENTICATED_ACCOUNT_NOTICE).toContain('未向平台实时验证');
    expect(ineligible.ok).toBe(false);
  });

  it.each([null, { ...loginStatus, account_id: 'other', auth_status: 'authenticated' }])(
    'cannot infer authentication or start permission from absent/foreign status',
    (status) => {
      const authenticatedAccount = { ...account, auth_status: 'authenticated' };
      expect(loginPreflightDisposition(authenticatedAccount, status)).toBe('status_unavailable');
      expect(canStartQrLogin(authenticatedAccount, biliCapability, passingPreflight, status)).toBe(false);
      expect(
        accountCompositeState(authenticatedAccount, status, biliCapability, passingPreflight).label
      ).toBe('本地状态待确认');
    }
  );

  it('preserves genuine expiry and browser-preflight failures', () => {
    const status = { ...loginStatus, auth_status: 'expired' };
    const expiredAccount = { ...account, login_method: 'saved_session' } as Account;
    expect(loginPreflightDisposition(expiredAccount, status)).toBe('required');
    expect(canStartQrLogin(expiredAccount, biliCapability, null, status)).toBe(false);
    expect(canStartQrLogin(expiredAccount, biliCapability, passingPreflight, status)).toBe(true);
    const failed = { ...passingPreflight, ok: false, retryable: true, code: 'browser_launch_failed' };
    expect(accountCompositeState(account, loginStatus, biliCapability, failed).label).toBe('预检可重试');
    expect(canStartQrLogin(account, biliCapability, failed, loginStatus)).toBe(false);
    expect(loginPreflightDisposition({ ...account, login_method: 'cookie' }, loginStatus)).toBe('required');
  });
});

describe('subscription wizard gates', () => {
  it('opens each step only after account, creator preview, and required acknowledgement', () => {
    const base = {
      accountId: account.id,
      capability: biliCapability,
      creatorId: '123456',
      creatorName: '创作者',
      preview,
      fullHistoryAcknowledged: false
    };

    expect(subscriptionWizardGates({ ...base, accountId: '', capability: null })).toEqual({
      canContinueFromAccount: false,
      canRequestPreview: false,
      canCreate: false,
      confirmationRequired: false
    });
    expect(subscriptionWizardGates({ ...base, creatorId: '' }).canRequestPreview).toBe(false);
    expect(subscriptionWizardGates(base).canRequestPreview).toBe(false);
    expect(subscriptionWizardGates({ ...base, fullHistoryAcknowledged: true }).canRequestPreview).toBe(true);
    expect(subscriptionWizardGates(base).canCreate).toBe(false);
    expect(subscriptionWizardGates({ ...base, fullHistoryAcknowledged: true }).canCreate).toBe(true);
  });

  it('invalidates a stale server preview after creator or account changes', () => {
    const state = {
      accountId: account.id,
      capability: { ...biliCapability, requires_full_history_acknowledgement: false },
      creatorId: 'different',
      creatorName: '创作者',
      preview,
      fullHistoryAcknowledged: false
    };
    expect(subscriptionWizardGates(state).canCreate).toBe(false);
  });

  it('uses the capability flag instead of a hard-coded platform list', () => {
    const boundedCapability: PlatformCapability = {
      ...biliCapability,
      requires_full_history_acknowledgement: false
    };
    const gates = subscriptionWizardGates({
      accountId: account.id,
      capability: boundedCapability,
      creatorId: preview.creator_remote_id,
      creatorName: preview.creator_display_name,
      preview,
      fullHistoryAcknowledged: false
    });

    expect(gates.confirmationRequired).toBe(false);
    expect(gates.canRequestPreview).toBe(true);
    expect(gates.canCreate).toBe(true);
  });
});

describe('redaction-safe summaries', () => {
  it('renders only the policy and checkpoint allowlists', () => {
    const policy = {
      adapter: 'mediacrawler',
      allow_full_history: false,
      request_delay_seconds: 5,
      headless: true,
      creator_reference_configured: true,
      secret_ref: 'env:DO_NOT_RENDER'
    } as SubscriptionPolicySummary;
    const checkpoint = {
      has_checkpoint: true,
      has_forward_cursor: true,
      has_backfill_cursor: false,
      revision: 2,
      cursor_version: 1,
      watermarked_at: null,
      watermark_count: 30,
      last_success_at: null,
      raw_cursor: 'DO_NOT_RENDER'
    } as SubscriptionCheckpointSummary;

    expect(JSON.stringify(safePolicySummaryRows(policy))).not.toContain('DO_NOT_RENDER');
    expect(JSON.stringify(safeCheckpointSummaryRows(checkpoint))).not.toContain('DO_NOT_RENDER');
  });
});
