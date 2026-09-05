import type {
  Account,
  LoginPreflight,
  LoginStatus,
  Platform,
  PlatformCapability,
  SubscriptionCheckpointSummary,
  SubscriptionPolicySummary,
  SubscriptionPreview
} from '$lib/types/api';
import {
  accountLoginExplanation,
  LOGIN_READINESS_NOTICE,
  LOGIN_STATUS_UNAVAILABLE
} from './login-diagnostics';

export const AUTHENTICATED_ACCOUNT_NOTICE =
  '本地记录为已认证。当前页面只读取已保存结果，未向平台实时验证会话；无需再次启动扫码登录，可继续配置作者订阅。';

export function loginPreflightDisposition(
  account: Account | null,
  status: LoginStatus | null
): 'not_needed' | 'status_unavailable' | 'required' {
  if (!account || !status || status.account_id !== account.id) return 'status_unavailable';
  return status.auth_status === 'authenticated' ? 'not_needed' : 'required';
}

export interface SubscriptionWizardState {
  accountId: string;
  capability: PlatformCapability | null;
  creatorId: string;
  creatorName: string;
  profileLookupId?: string | null;
  preview: SubscriptionPreview | null;
  fullHistoryAcknowledged: boolean;
}

export interface SubscriptionWizardGates {
  canContinueFromAccount: boolean;
  canRequestPreview: boolean;
  canCreate: boolean;
  confirmationRequired: boolean;
}

export interface SafeSummaryRow {
  label: string;
  value: string;
}

export function capabilityByPlatform(
  capabilities: PlatformCapability[],
  platform: Platform | null | undefined
): PlatformCapability | null {
  if (!platform) return null;
  return capabilities.find((item) => item.platform === platform) ?? null;
}

export function loginMethodLabel(method: string | null | undefined): string {
  return (
    {
      qr: '扫码',
      cookie: 'Cookie 引用',
      saved_session: '已保存会话',
      phone: '手机号'
    }[method ?? ''] ??
    method ??
    '未配置'
  );
}

export function canStartQrLogin(
  account: Account | null,
  capability: PlatformCapability | null,
  preflight: LoginPreflight | null,
  status: LoginStatus | null
): boolean {
  if (!account || !capability || !preflight || !status || status.account_id !== account.id) return false;
  if (account.id !== preflight.account_id || account.platform !== preflight.platform) return false;
  const eligible =
    (account.login_method === 'qr' &&
      ['unknown', 'required', 'expired', 'failed'].includes(status.auth_status)) ||
    (account.login_method === 'saved_session' && status.auth_status === 'expired');
  if (
    account.adapter !== 'mediacrawler' ||
    account.platform !== capability.platform ||
    !eligible ||
    ['pending', 'waiting_user', 'running'].includes(status.login_session_status ?? '') ||
    !capability.qr_login ||
    !capability.login_methods.includes('qr')
  ) {
    return false;
  }
  return preflight.ok && !preflight.checks.some((check) => check.required && check.status !== 'pass');
}

export function accountCompositeState(
  account: Account,
  status: LoginStatus | null,
  capability: PlatformCapability | null,
  preflight: LoginPreflight | null
): { status: string; label: string; detail: string } {
  if (status?.account_id !== account.id) status = null;
  if (!capability) {
    return { status: 'failed_terminal', label: '能力未知', detail: '尚未取得平台能力契约' };
  }
  if (!account.login_method || !capability.login_methods.some((method) => method === account.login_method)) {
    return { status: 'failed_terminal', label: '组合不支持', detail: '账户登录方式不在平台能力范围内' };
  }
  if (status?.auth_status === 'authenticated') {
    return { status: 'authenticated', label: '已认证', detail: '本地保存的认证结果；未实时验证平台会话' };
  }
  if (!status) {
    return { status: 'pending', label: '本地状态待确认', detail: LOGIN_STATUS_UNAVAILABLE };
  }
  if (
    status?.login_session_status &&
    ['pending', 'waiting_user', 'running'].includes(status.login_session_status)
  ) {
    return { status: 'running', label: '登录进行中', detail: '存在正在推进的登录会话' };
  }
  if (status?.login_session_status === 'failed' || status?.auth_status === 'failed') {
    const result = accountLoginExplanation(status, account.id);
    return {
      status: 'failed',
      label: result?.title ?? '最近登录失败',
      detail: result?.detail ?? '未保存更细诊断'
    };
  }
  if (status?.login_session_status === 'expired' || status?.auth_status === 'expired') {
    return { status: 'expired', label: '登录已过期', detail: '需要重新预检并手动登录，不代表已认证' };
  }
  if (status?.login_session_status === 'cancelled') {
    return { status: 'cancelled', label: '最近登录已取消', detail: '重新预检后可手动发起新的登录' };
  }
  if (!preflight) {
    return { status: 'pending', label: '等待预检', detail: '通过启动前检查后才可扫码' };
  }
  if (!preflight.ok) {
    return {
      status: preflight.retryable ? 'failed_retryable' : 'failed_terminal',
      label: preflight.retryable ? '预检可重试' : '预检阻塞',
      detail: preflight.code
    };
  }
  return { status: 'required', label: '允许启动登录', detail: LOGIN_READINESS_NOTICE };
}

export function subscriptionWizardGates(state: SubscriptionWizardState): SubscriptionWizardGates {
  const accountReady = Boolean(state.accountId && state.capability);
  const creatorReady =
    accountReady && Boolean(state.creatorId.trim() && (state.creatorName.trim() || state.profileLookupId));
  const confirmationRequired = Boolean(state.capability?.requires_full_history_acknowledgement);
  const previewMatches = Boolean(
    state.preview &&
      state.preview.account_id === state.accountId &&
      state.preview.platform === state.capability?.platform &&
      state.preview.creator_remote_id === state.creatorId.trim() &&
      (state.profileLookupId
        ? state.preview.profile_lookup_id === state.profileLookupId &&
          (state.preview.local_alias ?? '') === state.creatorName.trim()
        : (state.preview.local_alias ?? state.preview.creator_display_name) === state.creatorName.trim())
  );
  return {
    canContinueFromAccount: accountReady,
    canRequestPreview: creatorReady && (!confirmationRequired || state.fullHistoryAcknowledged),
    canCreate: previewMatches && (!confirmationRequired || state.fullHistoryAcknowledged),
    confirmationRequired
  };
}

function booleanLabel(value: boolean): string {
  return value ? '是' : '否';
}

export function safePolicySummaryRows(summary: SubscriptionPolicySummary): SafeSummaryRow[] {
  const rows: SafeSummaryRow[] = [{ label: '适配器', value: summary.adapter }];
  if (summary.schema_version !== undefined) {
    rows.push({
      label: '策略版本',
      value: summary.schema_version === null ? '不可用' : String(summary.schema_version)
    });
  }
  if (summary.allow_full_history !== undefined) {
    rows.push({
      label: '全历史确认',
      value: summary.allow_full_history === null ? '不可用' : booleanLabel(summary.allow_full_history)
    });
  }
  if (summary.request_delay_seconds !== undefined) {
    rows.push({
      label: '请求间隔',
      value: summary.request_delay_seconds === null ? '不可用' : `${summary.request_delay_seconds} 秒`
    });
  }
  if (summary.headless !== undefined) {
    rows.push({
      label: '浏览器模式',
      value: summary.headless === null ? '不可用' : summary.headless ? '后台运行' : '可见浏览器'
    });
  }
  if (summary.creator_reference_configured !== undefined) {
    rows.push({
      label: '作者权限引用',
      value: summary.creator_reference_configured ? '已配置' : '未配置'
    });
  }
  return rows;
}

export function safeCheckpointSummaryRows(summary: SubscriptionCheckpointSummary): SafeSummaryRow[] {
  return [
    { label: '已有检查点', value: booleanLabel(summary.has_checkpoint) },
    { label: '前向游标', value: summary.has_forward_cursor ? '已建立' : '未建立' },
    { label: '回填游标', value: summary.has_backfill_cursor ? '已建立' : '未建立' },
    { label: '检查点修订', value: String(summary.revision) },
    { label: '游标版本', value: String(summary.cursor_version) },
    { label: '水位时间', value: summary.watermarked_at ?? '尚无' },
    { label: '水位计数', value: String(summary.watermark_count) },
    { label: '最近成功', value: summary.last_success_at ?? '尚无' }
  ];
}
