import type { Job } from '$lib/types/api';
import { LatestRequestGate } from '../api/client';
import { isSchedulerJobId, schedulerJobDiagnostic, schedulerJobErrorCode } from './scheduler-job-diagnostics';

export const JOB_REPORT_UNAVAILABLE = '暂时无法取得本任务的安全诊断报告，请重新打开任务详情后再试。';
const MAX_REPORT_BYTES = 16_384;
const STATES = [
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
];
const RUN_STATES = [
  'queued',
  'claimed',
  'awaiting_auth',
  'running',
  'ingesting',
  'succeeded',
  'failed_retryable',
  'failed_terminal',
  'cancelled'
];
const OPERATION_STATES = [
  'queued',
  'running',
  'succeeded',
  'failed_retryable',
  'failed_terminal',
  'cancelled',
  'interrupted'
];
const ERROR_STATES = [
  'failed_terminal',
  'failed_retryable',
  'retry_wait',
  'waiting_auth',
  'waiting_user',
  'awaiting_auth',
  'interrupted',
  'cancelled'
];
const CONTROL_ERRORS = [
  'scheduler_lease_lost',
  'scheduler_cancelled',
  'operation_interrupted',
  'scheduler_operation_rejected',
  'operation_execution_failed',
  'scheduler_run_failed'
];
const KINDS = [
  'account-login',
  'account-cookie-login',
  'creator-profile',
  'asset-download',
  'emby-export',
  'media-server-probe',
  'media-server-scan',
  'pipeline-run',
  'scheduler-run'
];
const PHASES = [
  'preparing',
  'running',
  'syncing',
  'ingesting',
  'finalizing',
  'reconciling',
  'completed',
  'claiming_jobs',
  'jobs_processed'
];
const REVISIONS = [
  '0001_core',
  '0002_checkpoint',
  '0003_media_download_emby',
  '0004_scheduler_control_plane',
  '0005_asset_refresh_sources',
  '0006_operations_observability',
  '0007_media_server_operations',
  '0008_playback_evidence',
  '0009_subscription_removal',
  '0010_creator_profiles',
  '0011_cookie_login'
];
const OBSERVATIONS: Record<string, string> = {
  no_attached_run: '任务尚未关联采集运行；不能据此判断已产生内容。',
  attached_run_missing: '任务指向的采集运行记录缺失，需要核对持久记录。',
  attached_run_scope_mismatch: '关联运行不属于本订阅，未展示其数据。',
  job_terminal_run_nonterminal: '任务已结束，但采集运行仍未结束；这是状态不一致，不代表仍有进程运行。',
  worker_completed_job_failed: 'Worker 操作已完成，但本采集任务失败；两者含义不同。',
  run_succeeded_job_unreconciled: '采集运行已成功，但任务尚未协调为成功；先核对已有内容，避免重复处理。'
};
const TIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/;

function object(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}
function choice(value: unknown, allowed: readonly string[]): string | null {
  return typeof value === 'string' && allowed.includes(value) ? value : null;
}
function id(value: unknown): string | null {
  return isSchedulerJobId(value) ? value : null;
}
function count(value: unknown): number | null {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 ? value : null;
}
function time(value: unknown): string | null {
  return typeof value === 'string' &&
    value.length <= 32 &&
    TIME.test(value) &&
    Number.isFinite(Date.parse(value))
    ? value
    : null;
}
function error(value: unknown, state: string | null): { code: string | null; availability: string } {
  const raw = object(value);
  const availability =
    choice(raw?.availability, ['not_recorded', 'ineligible_state', 'recognized', 'unrecognized']) ??
    'unrecognized';
  if (availability !== 'recognized') return { code: null, availability };
  if (!state || !ERROR_STATES.includes(state)) return { code: null, availability: 'ineligible_state' };
  const fixed =
    schedulerJobErrorCode({ status: 'failed_terminal', last_error_code: raw?.code } as Job) ??
    choice(raw?.code, CONTROL_ERRORS);
  return { code: fixed, availability: fixed ? 'recognized' : 'unrecognized' };
}

/** Rebuild every report field; never retain unknown properties or arbitrary text. */
export function parseJobReport(value: unknown, expectedId: string) {
  const root = object(value);
  const job = object(root?.job);
  const database = object(root?.database);
  if (
    !isSchedulerJobId(expectedId) ||
    root?.schema_version !== 1 ||
    !job ||
    job.id !== expectedId ||
    !database ||
    typeof database.revision_matches !== 'boolean' ||
    typeof root.run_found !== 'boolean' ||
    typeof root.run_matches_subscription !== 'boolean' ||
    typeof root.operations_truncated !== 'boolean' ||
    !Array.isArray(root.operations) ||
    root.operations.length > 5 ||
    !Array.isArray(root.observations) ||
    root.observations.length > 6 ||
    !time(root.generated_at)
  )
    return null;
  const rawRun = object(root.run);
  if (
    root.run !== null &&
    (!rawRun ||
      !root.run_found ||
      !root.run_matches_subscription ||
      !id(job.run_id) ||
      rawRun.id !== job.run_id)
  )
    return null;
  if (root.run_matches_subscription && (!root.run_found || !rawRun)) return null;
  const jobState = choice(job.status, STATES);
  const runState = choice(rawRun?.status, RUN_STATES);
  const operations = [];
  const operationIds = new Set<string>();
  for (const item of root.operations) {
    const row = object(item);
    const operationId = id(row?.id);
    if (!row || !operationId || operationIds.has(operationId)) return null;
    operationIds.add(operationId);
    const state = choice(row.state, OPERATION_STATES);
    operations.push({
      id: operationId,
      kind: choice(row.kind, KINDS),
      state,
      phase: choice(row.phase, PHASES),
      correlation_id: id(row.correlation_id),
      error: error(row.error, state),
      requested_at: time(row.requested_at),
      started_at: time(row.started_at),
      finished_at: time(row.finished_at)
    });
  }
  const expectedRevision = choice(database.expected_revision, REVISIONS);
  const observedRevision = choice(database.observed_revision, REVISIONS);
  return {
    schema_version: 1 as const,
    application_version:
      typeof root.application_version === 'string' &&
      /^\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(root.application_version)
        ? root.application_version
        : null,
    generated_at: time(root.generated_at),
    database: {
      expected_revision: expectedRevision,
      observed_revision: observedRevision,
      revision_matches:
        database.revision_matches &&
        expectedRevision !== null &&
        observedRevision !== null &&
        expectedRevision === observedRevision
    },
    job: {
      id: expectedId,
      subscription_id: id(job.subscription_id),
      run_id: id(job.run_id),
      platform: choice(job.platform, ['bili', 'xhs', 'dy', 'ks', 'wb', 'tieba', 'zhihu']),
      status: jobState,
      attempt: count(job.attempt),
      max_attempts: count(job.max_attempts),
      error: error(job.error, jobState),
      available_at: time(job.available_at),
      created_at: time(job.created_at),
      started_at: time(job.started_at),
      finished_at: time(job.finished_at),
      updated_at: time(job.updated_at)
    },
    run_found: root.run_found,
    run_matches_subscription: root.run_matches_subscription,
    run: rawRun
      ? {
          id: id(rawRun.id),
          status: runState,
          error: error(rawRun.error, runState),
          attempt: count(rawRun.attempt),
          discovered_count: count(rawRun.discovered_count),
          updated_count: count(rawRun.updated_count),
          asset_count: count(rawRun.asset_count),
          started_at: time(rawRun.started_at),
          finished_at: time(rawRun.finished_at)
        }
      : null,
    operations,
    operations_truncated: root.operations_truncated,
    observations: root.observations.filter(
      (item): item is string => typeof item === 'string' && Object.hasOwn(OBSERVATIONS, item)
    )
  };
}
export type JobReport = NonNullable<ReturnType<typeof parseJobReport>>;

export function jobReportObservations(report: JobReport): string[] {
  return report.observations
    .filter((code) => Object.hasOwn(OBSERVATIONS, code))
    .map((code) => OBSERVATIONS[code]);
}

export function jobReportArtifact(
  report: JobReport,
  expectedId: string
): { filename: string; text: string } | null {
  const clean = parseJobReport(report, expectedId);
  if (!clean) return null;
  const text = JSON.stringify(clean, null, 2);
  if (new TextEncoder().encode(text).byteLength > MAX_REPORT_BYTES) return null;
  return { filename: `media-sync-job-${expectedId}.json`, text };
}

export class JobReportReader {
  private readonly gate = new LatestRequestGate();
  constructor(
    private readonly fetchReport: (id: string, signal: AbortSignal) => Promise<unknown>,
    private readonly auth: () => { authenticated: boolean; epoch: number }
  ) {}
  async read(
    jobId: string
  ): Promise<{ kind: 'fulfilled'; report: JobReport } | { kind: 'failed' | 'superseded' }> {
    const session = this.auth();
    if (!isSchedulerJobId(jobId) || !session.authenticated) {
      this.invalidate();
      return { kind: 'failed' };
    }
    const result = await this.gate.run((signal) => this.fetchReport(jobId, signal));
    const current = this.auth();
    if (result.status === 'superseded' || !current.authenticated || session.epoch !== current.epoch)
      return { kind: 'superseded' };
    const report = result.status === 'fulfilled' ? parseJobReport(result.value, jobId) : null;
    return report && jobReportArtifact(report, jobId) ? { kind: 'fulfilled', report } : { kind: 'failed' };
  }
  invalidate(): void {
    this.gate.cancel();
  }
}

export function jobBusinessSummary(job: Job): { title: string; detail: string; next: string } {
  const diagnostic = schedulerJobDiagnostic(job);
  if (diagnostic) return diagnostic;
  const states: Record<string, { title: string; detail: string; next: string }> = {
    queued: {
      title: '等待采集',
      detail: '任务已进入队列，尚未开始采集。',
      next: '查看可运行时间，等待现有 Worker 处理，不必重复提交。'
    },
    claimed: {
      title: '准备采集',
      detail: '任务已被 Worker 领取，尚不能证明已取得内容。',
      next: '等待状态更新；长时间停留时可获取本任务诊断报告。'
    },
    running: {
      title: '采集中',
      detail: '任务记录仍在运行，不表示视频已下载或导出。',
      next: '等待任务结果；异常停滞时先查看诊断报告与已有内容。'
    },
    succeeded: {
      title: '采集任务报告完成',
      detail: '任务报告成功，不等于产生了新增内容，也不证明下载、导出或播放完成。',
      next: '到内容与资产页核对采集条数、下载和本地导出结果。'
    },
    cancelled: {
      title: '任务已取消',
      detail: '任务记录已标记取消；不能据此证明进程清理完成。',
      next: '查看关联订阅状态；不要把取消理解为已删除内容。'
    }
  };
  return Object.hasOwn(states, job.status)
    ? states[job.status]
    : {
        title: '任务状态待确认',
        detail: '没有可安全解释的任务状态。',
        next: '刷新任务详情，或获取本任务的安全诊断报告。'
      };
}

export function jobOperationPhase(value: unknown): string {
  const labels: Record<string, string> = {
    preparing: '准备中',
    running: '执行中',
    syncing: '采集中',
    ingesting: '正在入库',
    finalizing: '收尾中',
    reconciling: '核对持久状态',
    completed: '已完成',
    claiming_jobs: '领取任务',
    jobs_processed: '任务批次已处理'
  };
  return typeof value === 'string' && Object.hasOwn(labels, value) ? labels[value] : '阶段待确认';
}
