import { ApiError, LatestRequestGate } from '../api/client';
import type {
  SubscriptionDetail,
  SubscriptionPolicySummary,
  SubscriptionPolicyUpdateResult
} from '../types/api';

export const MAX_SUBSCRIPTION_INTERVAL_SECONDS = 2_147_483_647;
export const MAX_SUBSCRIPTION_REQUEST_DELAY_SECONDS = 300;

export type BiliSubscriptionScope = 'uploads' | 'dynamics' | 'both';

export interface SubscriptionPolicyDraft {
  interval_seconds: number;
  max_items: number;
  request_delay_seconds: number;
  headless: boolean;
  bili_scope: BiliSubscriptionScope | null;
}

export interface SubscriptionPolicyRequest extends SubscriptionPolicyDraft {
  expected_schedule_revision: number;
}

export type SubscriptionPolicyFailure = {
  message: string;
  destination: 'jobs' | 'detail' | 'deleted' | null;
};

export type SubscriptionPolicyRequestResult =
  | { kind: 'fulfilled'; value: SubscriptionPolicyUpdateResult }
  | { kind: 'failed'; failure: SubscriptionPolicyFailure }
  | { kind: 'superseded' };

type ValidSubscriptionPolicySummary = SubscriptionPolicySummary & {
  schema_version: 1 | 2;
  allow_full_history: boolean;
  request_delay_seconds: number;
  headless: boolean;
  creator_reference_configured: boolean;
};

const FAILURE_MESSAGES: Record<
  string,
  { message: string; destination: SubscriptionPolicyFailure['destination'] }
> = {
  subscription_policy_busy: {
    message: '仍有此订阅的待处理任务，本次未修改。请先在任务页面确认任务结束。',
    destination: 'jobs'
  },
  subscription_policy_invalid: {
    message: '当前持久策略无法安全读取，本次未修改；请查看诊断后再处理。',
    destination: 'detail'
  },
  subscription_policy_not_found: {
    message: '订阅不存在或已失效，本次未修改。',
    destination: 'detail'
  },
  subscription_policy_options_invalid: {
    message: '策略字段或平台范围不符合安全边界，本次未修改。',
    destination: null
  },
  subscription_policy_removed: {
    message: '订阅已删除，本次未修改；需要时请先恢复为暂停状态。',
    destination: 'deleted'
  },
  subscription_policy_requires_paused: {
    message: '订阅仍处于启用状态，本次未修改。请先暂停并重新打开详情。',
    destination: 'detail'
  },
  subscription_policy_revision_conflict: {
    message: '订阅策略已被更新，本次未覆盖。请重新打开详情并核对当前值。',
    destination: 'detail'
  },
  subscription_policy_revision_exhausted: {
    message: '调度修订已达安全上限，本次未修改；请查看诊断。',
    destination: 'detail'
  },
  subscription_policy_unsupported_adapter: {
    message: '当前订阅不支持此策略编辑器，本次未修改。',
    destination: null
  }
};

const UNAVAILABLE: SubscriptionPolicyFailure = {
  message: '无法确认策略是否已保存，请重新打开订阅详情核对；不要直接重复提交。',
  destination: 'detail'
};

function record(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

function integer(value: unknown, minimum: number, maximum: number): value is number {
  return Number.isSafeInteger(value) && Number(value) >= minimum && Number(value) <= maximum;
}

function delay(value: unknown): value is number {
  return (
    typeof value === 'number' &&
    Number.isFinite(value) &&
    value > 0 &&
    value <= MAX_SUBSCRIPTION_REQUEST_DELAY_SECONDS
  );
}

function scope(value: unknown): value is BiliSubscriptionScope {
  return value === 'uploads' || value === 'dynamics' || value === 'both';
}

function exactKeys(value: Record<string, unknown>, expected: string[]): boolean {
  const keys = Object.keys(value).sort();
  const expectedKeys = [...expected].sort();
  return keys.length === expectedKeys.length && keys.every((key, index) => key === expectedKeys[index]);
}

function validPolicySummary(
  summary: SubscriptionPolicySummary | undefined,
  platform: SubscriptionDetail['platform']
): summary is ValidSubscriptionPolicySummary {
  if (
    !record(summary) ||
    summary.adapter !== 'mediacrawler' ||
    typeof summary.allow_full_history !== 'boolean' ||
    !delay(summary.request_delay_seconds) ||
    typeof summary.headless !== 'boolean' ||
    typeof summary.creator_reference_configured !== 'boolean'
  )
    return false;
  const expectedKeys = [
    'adapter',
    'allow_full_history',
    ...(platform === 'bili' && summary.schema_version === 2 ? ['bili_scope'] : []),
    'creator_reference_configured',
    'headless',
    'request_delay_seconds',
    'schema_version'
  ];
  if (!exactKeys(summary, expectedKeys)) return false;
  if (platform === 'bili') {
    if (summary.schema_version === 1) return summary.bili_scope === undefined;
    return summary.schema_version === 2 && scope(summary.bili_scope);
  }
  return summary.schema_version === 1 && summary.bili_scope === undefined;
}

export function subscriptionPolicyDraft(detail: SubscriptionDetail): SubscriptionPolicyDraft | null {
  if (
    !record(detail) ||
    !integer(detail.interval_seconds, 60, MAX_SUBSCRIPTION_INTERVAL_SECONDS) ||
    !integer(detail.max_items, 1, 1_000) ||
    !record(detail.schedule) ||
    detail.schedule.subscription_id !== detail.id ||
    detail.schedule.interval_seconds !== detail.interval_seconds ||
    !integer(detail.schedule.schedule_revision, 0, MAX_SUBSCRIPTION_INTERVAL_SECONDS) ||
    !validPolicySummary(detail.policy_summary, detail.platform)
  )
    return null;
  const biliScope = detail.platform === 'bili' ? (detail.policy_summary.bili_scope ?? 'uploads') : null;
  return {
    interval_seconds: detail.interval_seconds,
    max_items: detail.max_items,
    request_delay_seconds: detail.policy_summary.request_delay_seconds,
    headless: detail.policy_summary.headless,
    bili_scope: biliScope
  };
}

export function subscriptionPolicyChanged(
  detail: SubscriptionDetail,
  draft: SubscriptionPolicyDraft | null
): boolean {
  const current = subscriptionPolicyDraft(detail);
  return current !== null && draft !== null && JSON.stringify(current) !== JSON.stringify(draft);
}

export function subscriptionPolicyRequest(
  detail: SubscriptionDetail,
  draft: SubscriptionPolicyDraft | null
): SubscriptionPolicyRequest | null {
  const current = subscriptionPolicyDraft(detail);
  if (
    current === null ||
    draft === null ||
    detail.enabled ||
    detail.deleted_at !== null ||
    !integer(draft.interval_seconds, 60, MAX_SUBSCRIPTION_INTERVAL_SECONDS) ||
    !integer(draft.max_items, 1, 1_000) ||
    !delay(draft.request_delay_seconds) ||
    typeof draft.headless !== 'boolean' ||
    (detail.platform === 'bili'
      ? !scope(draft.bili_scope) || (draft.bili_scope !== 'uploads' && draft.max_items < 2)
      : draft.bili_scope !== null) ||
    !subscriptionPolicyChanged(detail, draft)
  )
    return null;
  return {
    ...draft,
    expected_schedule_revision: detail.schedule.schedule_revision
  };
}

function validIsoOrNull(value: unknown): value is string | null {
  return (
    value === null || (typeof value === 'string' && value.length <= 64 && Number.isFinite(Date.parse(value)))
  );
}

export function validSubscriptionPolicyResult(
  value: unknown,
  subscriptionId: string,
  platform: SubscriptionDetail['platform'],
  request: SubscriptionPolicyRequest
): value is SubscriptionPolicyUpdateResult {
  if (!record(value)) return false;
  const expectedKeys = [
    'changed',
    'checkpoint_preserved',
    'checkpoint_revision',
    'enabled',
    'id',
    'interval_seconds',
    'max_items',
    'media_preserved',
    'next_run_at',
    'platform',
    'policy_summary',
    'schedule_revision',
    'status'
  ];
  if (
    !exactKeys(value, expectedKeys) ||
    value.id !== subscriptionId ||
    value.platform !== platform ||
    value.status !== 'paused' ||
    value.enabled !== false ||
    value.changed !== true ||
    value.checkpoint_preserved !== true ||
    value.media_preserved !== true ||
    value.interval_seconds !== request.interval_seconds ||
    value.max_items !== request.max_items ||
    value.schedule_revision !== request.expected_schedule_revision + 1 ||
    !integer(value.checkpoint_revision, 0, Number.MAX_SAFE_INTEGER) ||
    !validIsoOrNull(value.next_run_at) ||
    !record(value.policy_summary)
  )
    return false;
  const summary = value.policy_summary;
  const expectedSummaryKeys = [
    'adapter',
    ...(platform === 'bili' ? ['bili_scope'] : []),
    'allow_full_history',
    'creator_reference_configured',
    'headless',
    'request_delay_seconds',
    'schema_version'
  ];
  return (
    exactKeys(summary, expectedSummaryKeys) &&
    summary.adapter === 'mediacrawler' &&
    summary.schema_version === (platform === 'bili' ? 2 : 1) &&
    typeof summary.allow_full_history === 'boolean' &&
    typeof summary.creator_reference_configured === 'boolean' &&
    summary.request_delay_seconds === request.request_delay_seconds &&
    summary.headless === request.headless &&
    (platform === 'bili' ? summary.bili_scope === request.bili_scope : summary.bili_scope === undefined)
  );
}

export function subscriptionPolicyFailure(error: unknown): SubscriptionPolicyFailure {
  if (error instanceof ApiError && Object.prototype.hasOwnProperty.call(FAILURE_MESSAGES, error.code))
    return FAILURE_MESSAGES[error.code];
  return UNAVAILABLE;
}

export class SubscriptionPolicyRequestGate {
  private readonly requests = new LatestRequestGate();

  async run(
    request: (signal: AbortSignal) => Promise<SubscriptionPolicyUpdateResult>,
    expected: {
      subscriptionId: string;
      platform: SubscriptionDetail['platform'];
      payload: SubscriptionPolicyRequest;
    }
  ): Promise<SubscriptionPolicyRequestResult> {
    const result = await this.requests.run(request);
    if (result.status === 'superseded') return { kind: 'superseded' };
    if (result.status === 'rejected')
      return { kind: 'failed', failure: subscriptionPolicyFailure(result.reason) };
    if (
      !validSubscriptionPolicyResult(
        result.value,
        expected.subscriptionId,
        expected.platform,
        expected.payload
      )
    )
      return { kind: 'failed', failure: subscriptionPolicyFailure(null) };
    return { kind: 'fulfilled', value: result.value };
  }

  cancel(): void {
    this.requests.cancel();
  }
}
