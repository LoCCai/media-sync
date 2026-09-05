import type { Operation } from '$lib/types/api';
import type { OperationTruthNotice } from './operations';

// Exact vocabulary and cardinality bound of the backend batch-result contract.
const STATUSES = new Set([
  'idle',
  'fenced',
  'queued',
  'claimed',
  'running',
  'retry_wait',
  'waiting_auth',
  'waiting_user',
  'succeeded',
  'failed_retryable',
  'failed_terminal',
  'cancelled'
]);
const MAX_RESULTS = 1_000;

export interface SchedulerWorkerSummary {
  processed_count: number;
  status_counts: Record<string, number>;
}

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function count(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 && value <= MAX_RESULTS;
}

/** Unlike a partial field projection, any malformed summary is wholly unavailable. */
export function schedulerWorkerSummary(operation: Operation): SchedulerWorkerSummary | null {
  if (operation.kind !== 'scheduler-run') return null;
  const source = record(operation.result);
  if (
    !source ||
    Object.keys(source).length !== 2 ||
    !Object.hasOwn(source, 'processed_count') ||
    !Object.hasOwn(source, 'status_counts') ||
    !count(source.processed_count)
  )
    return null;
  const counts = record(source.status_counts);
  if (!counts || Object.keys(counts).length > STATUSES.size) return null;
  let total = 0;
  const safe: Record<string, number> = {};
  for (const [status, value] of Object.entries(counts)) {
    if (!STATUSES.has(status) || !count(value)) return null;
    total += value;
    if (!Number.isSafeInteger(total) || total > source.processed_count) return null;
    safe[status] = value;
  }
  return total === source.processed_count ? { processed_count: total, status_counts: safe } : null;
}

export function schedulerWorkerStateLabel(
  kind: Operation['kind'],
  state: string | null | undefined
): string | null {
  return kind === 'scheduler-run' && state === 'succeeded' ? 'Worker 已完成' : null;
}

/** Worker control completion is separate from its bounded Job outcome summary. */
export function schedulerWorkerNotice(operation: Operation): OperationTruthNotice | null {
  if (!schedulerWorkerStateLabel(operation.kind, operation.state)) return null;
  const summary = schedulerWorkerSummary(operation);
  if (!summary)
    return {
      tone: 'warning',
      title: '采集结果无法确认',
      detail: 'Worker 已完成，但结果摘要不可用或不一致；不能据此判断采集成功，请查看关联 Job。'
    };
  const counts = summary.status_counts;
  const succeeded = counts.succeeded ?? 0;
  if ((counts.failed_terminal ?? 0) + (counts.failed_retryable ?? 0) > 0)
    return {
      tone: 'danger',
      title: succeeded > 0 ? '部分采集任务失败' : '采集任务失败',
      detail: 'Worker 执行结束，但摘要中存在失败的 Job；Worker 完成不等于采集成功，请查看关联 Job。'
    };
  if (
    ['queued', 'claimed', 'running', 'retry_wait', 'waiting_auth', 'waiting_user', 'fenced'].some(
      (status) => (counts[status] ?? 0) > 0
    )
  )
    return {
      tone: 'warning',
      title: '采集任务尚未完成',
      detail: '摘要中存在等待、重试或执行权受限的结果；不能视为采集成功，请查看关联 Job。'
    };
  if ((counts.cancelled ?? 0) > 0)
    return {
      tone: 'warning',
      title: '存在已取消的采集任务',
      detail: 'Worker 执行结束，但摘要中有已取消的 Job；不能据此判断采集成功。'
    };
  if (summary.processed_count === 0 || succeeded === 0)
    return {
      tone: 'info',
      title: '本次没有 Job 完成记录',
      detail: 'Worker 返回空结果或空闲结果；这不表示已抓取内容，请查看任务和订阅状态。'
    };
  if (succeeded !== summary.processed_count)
    return {
      tone: 'warning',
      title: '仅部分处理结果报告 Job 完成',
      detail: '摘要同时包含完成与空闲结果；不能将整次 Worker 视为采集成功。'
    };
  return {
    tone: 'success',
    title: 'Job 均报告完成',
    detail: '摘要中的 Job 均报告完成；这不证明新增内容、下载、导出或可播放，请查看内容与关联 Job。'
  };
}
