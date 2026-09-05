import { ApiError, LatestRequestGate } from '../api/client';
import type { Subscription, SubscriptionLifecycleResult } from '$lib/types/api';

export const LOCAL_CREATOR_PREVIEW_NOTICE =
  '本地格式与订阅策略校验不会访问平台。远端昵称与头像来自独立的资料查询，本地备注仍由你填写；资料查询成功不代表内容已采集。';
export const SUBSCRIPTION_REMOVAL_NOTICE =
  '删除后停止此订阅的后续调度，并取消符合条件的未开始采集和流水线任务。作者、内容、媒体文件、导出目录、任务历史和检查点全部保留，不会清理磁盘文件。';
export const SUBSCRIPTION_RESTORE_NOTICE =
  '恢复原订阅 ID、配置和检查点，恢复后先暂停；不会恢复已取消任务或自动开始采集。需要继续时，请另行启用订阅。';
export const SUBSCRIPTION_REQUEST_UNAVAILABLE =
  '暂时无法确认本次订阅请求的结果，请刷新列表核对后再操作；未自动重试。';

const ERRORS: Record<string, string> = {
  subscription_busy:
    '订阅有正在领取、执行的任务或相关活动操作，本次未删除。请到任务页面核对，结束后再手动删除。',
  subscription_removed: '该订阅已删除。请切换到“已删除”视图恢复原订阅，不会重新创建或自动运行。',
  subscription_exists_with_different_options:
    '该账户与作者的订阅已存在，但策略不同。请查看原订阅，不会覆盖配置。',
  account_not_found: '所选账户不存在，请刷新账户列表后重新选择。',
  platform_conflict: '账户与作者平台不一致，请重新选择。',
  creator_display_name_invalid: '请填写有效的本地备注名称。',
  creator_profile_receipt_invalid: '作者资料凭单已失效，请重新查询或填写本地备注后再校验。',
  creator_profile_receipt_expired: '作者资料凭单已过期，请重新查询或填写本地备注后再校验。',
  creator_remote_id_must_be_stable_id: '作者标识必须是稳定 ID，不能包含链接、参数或秘密信息。',
  creator_secret_ref_not_supported: '所选平台不支持作者权限引用。',
  invalid_creator_secret_reference: '作者权限引用格式无效，请使用受支持的不透明引用。',
  subscription_options_invalid: '采集间隔、数量上限或运行策略无效，请检查后再试。',
  full_history_acknowledgement_required: '该平台需要明确确认全历史边界；本地校验本身不会采集。',
  request_validation_failed: '请求格式无效，请检查输入并刷新状态后再试。',
  scheduler_operation_rejected: '调度操作未被接受，请刷新状态并查看任务页面。',
  operator_auth_required: '后台会话已失效，请重新登录并核对状态。',
  operator_csrf_forbidden: '后台会话已变化，请重新核验并检查状态；未自动重试。'
};

export interface SubscriptionFailure {
  message: string;
  destination: 'jobs' | 'deleted' | null;
}

export function subscriptionFailure(error: unknown): SubscriptionFailure {
  if (error instanceof ApiError && Object.hasOwn(ERRORS, error.code)) {
    return {
      message: ERRORS[error.code],
      destination:
        error.code === 'subscription_busy' ? 'jobs' : error.code === 'subscription_removed' ? 'deleted' : null
    };
  }
  if (error instanceof ApiError && error.status === 404) {
    return { message: '该订阅当前不可用，请刷新列表或查看“已删除”视图核对。', destination: 'deleted' };
  }
  return { message: SUBSCRIPTION_REQUEST_UNAVAILABLE, destination: null };
}

export function isSubscriptionId(value: unknown): value is string {
  return (
    typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(value)
  );
}

export function isRemovedSubscription(subscription: Pick<Subscription, 'deleted_at'>): boolean {
  return typeof subscription.deleted_at === 'string' && subscription.deleted_at.length > 0;
}

export function subscriptionMatchesView(value: unknown, deleted: boolean): value is Subscription {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const row = value as Subscription;
  return (
    isSubscriptionId(row.id) &&
    typeof row.enabled === 'boolean' &&
    (row.deleted_at === null ||
      (typeof row.deleted_at === 'string' && Number.isFinite(Date.parse(row.deleted_at)))) &&
    isRemovedSubscription(row) === deleted &&
    (!deleted || row.enabled === false)
  );
}

export type SubscriptionRequestResult<T> =
  | { kind: 'fulfilled'; value: T }
  | { kind: 'failed'; failure: SubscriptionFailure }
  | { kind: 'superseded' };

/** Read or mutation response lifetime only: cancellation never claims server rollback. */
export class SubscriptionRequestGate {
  private readonly gate = new LatestRequestGate();

  async run<T>(
    request: (signal: AbortSignal) => Promise<T>,
    accept: (value: T) => boolean = () => true
  ): Promise<SubscriptionRequestResult<T>> {
    const result = await this.gate.run(request);
    if (result.status === 'superseded') return { kind: 'superseded' };
    if (result.status === 'rejected') return { kind: 'failed', failure: subscriptionFailure(result.reason) };
    try {
      if (accept(result.value)) return { kind: 'fulfilled', value: result.value };
    } catch {
      /* A malformed response never becomes an error message. */
    }
    return { kind: 'failed', failure: subscriptionFailure(null) };
  }

  cancel(): void {
    this.gate.cancel();
  }
}

export type SubscriptionLifecycleAction = 'delete' | 'restore';

export function subscriptionLifecyclePath(id: string, action: SubscriptionLifecycleAction): string | null {
  if (!isSubscriptionId(id) || (action !== 'delete' && action !== 'restore')) return null;
  return `/api/v1/subscriptions/${id}${action === 'restore' ? '/restore' : ''}`;
}

export function validSubscriptionLifecycleResult(
  value: unknown,
  id: string,
  action: SubscriptionLifecycleAction
): value is SubscriptionLifecycleResult {
  if (!value || typeof value !== 'object' || Array.isArray(value) || !isSubscriptionId(id)) return false;
  const result = value as SubscriptionLifecycleResult;
  return (
    Object.keys(value).sort().join(',') === 'cancelled_jobs,changed,id,media_preserved,status' &&
    result.id === id &&
    result.status === (action === 'delete' ? 'deleted' : 'paused') &&
    typeof result.changed === 'boolean' &&
    Number.isSafeInteger(result.cancelled_jobs) &&
    result.cancelled_jobs >= 0 &&
    (action !== 'restore' || result.cancelled_jobs === 0) &&
    result.media_preserved === true
  );
}
