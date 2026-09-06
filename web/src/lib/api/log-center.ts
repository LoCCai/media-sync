import { api, ApiError, LatestRequestGate } from './client';

export const LOG_MODULES = [
  'api',
  'cli',
  'login',
  'cookie_login',
  'creator_profile',
  'crawler',
  'download',
  'archive',
  'scheduler',
  'pipeline',
  'exporter',
  'library',
  'media_server',
  'supervisor',
  'output_directories',
  'application',
  'log_store'
];
export const LOG_LEVELS = ['debug', 'info', 'warning', 'error', 'critical'];
export const LOG_PLATFORMS = ['bili', 'xhs', 'dy', 'ks', 'wb', 'tieba', 'zhihu'];
export const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
export interface LogEvent {
  schema_version: number;
  timestamp: string;
  writer_id: string;
  sequence: number;
  event_code: string;
  module: string;
  level: string;
  phase?: string;
  action?: string;
  outcome?: string;
  error_type?: string;
  source_frame?: string;
  duration_ms?: number;
  operation_id?: string;
  asset_id?: string;
  account_id?: string;
  login_session_id?: string;
  job_id?: string;
  run_id?: string;
  subscription_id?: string;
  correlation_id?: string;
  platform?: string;
}
export interface LogCoverage {
  order: string;
  global_time_order: boolean;
  bounded: boolean;
  scan_limited: boolean;
  corrupt_records: number;
  truncated_segments: number;
  unavailable_segments: number;
  omitted_segment_tails: number;
  retention_may_have_removed: boolean;
}
export interface LogPage {
  events: LogEvent[];
  next_cursor: string | null;
  coverage: LogCoverage;
}
export interface LogStatus {
  health: string;
  queued: number;
  accepted: number;
  written: number;
  dropped: number;
  invalid: number;
  segment_max_bytes: number;
  total_max_bytes: number;
  retention_days: number;
  storage_bytes: number | null;
  managed_segments: number | null;
  active_segments: number | null;
  scope: string;
  last_error: string | null;
  writer_running: boolean;
  drained: boolean;
  shutdown_complete: boolean;
}
export interface OperationTrace {
  operation: { id: string; state: string; kind: string; phase: string; runner_status: string | null };
  control_events: Array<{
    sequence: number | null;
    at: string | null;
    event_code: string;
    phase: string;
    to_state: string | null;
  }>;
  control_events_truncated: boolean;
  login_stage_evidence: string;
}
export interface LogFilters {
  operation_id?: string;
  account_id?: string;
  login_session_id?: string;
  job_id?: string;
  run_id?: string;
  subscription_id?: string;
  platform?: string;
  module?: string;
  level?: string;
  since?: string;
  until?: string;
}
const ids = new Set([
  'operation_id',
  'account_id',
  'login_session_id',
  'job_id',
  'run_id',
  'subscription_id'
]);
const keys = new Set([...ids, 'platform', 'module', 'level', 'since', 'until']);
function canonicalLogTime(value: string): string {
  const parts =
    /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,6}))?)?(Z|[+-]\d{2}:\d{2})?$/.exec(value);
  if (!parts) throw new Error('log_query_invalid');
  const [, year, month, day, hour, minute, second = '0', fraction = '', zone] = parts;
  const days = new Date(Date.UTC(Number(year), Number(month), 0)).getUTCDate();
  if (
    Number(year) < 1000 ||
    Number(month) < 1 ||
    Number(month) > 12 ||
    Number(day) < 1 ||
    Number(day) > days ||
    Number(hour) > 23 ||
    Number(minute) > 59 ||
    Number(second) > 59
  )
    throw new Error('log_query_invalid');
  const parsed = new Date(value);
  if (
    !Number.isFinite(parsed.getTime()) ||
    (!zone &&
      (parsed.getFullYear() !== Number(year) ||
        parsed.getMonth() + 1 !== Number(month) ||
        parsed.getDate() !== Number(day) ||
        parsed.getHours() !== Number(hour) ||
        parsed.getMinutes() !== Number(minute)))
  )
    throw new Error('log_query_invalid');
  return parsed.toISOString().slice(0, -1) + fraction.padEnd(6, '0').slice(3) + 'Z';
}
export function logQuery(filters: LogFilters, cursor?: string | null): string {
  const params = new URLSearchParams({ limit: '100' });
  for (const key of keys) {
    const value = filters[key as keyof LogFilters];
    if (value === undefined) continue;
    if (typeof value !== 'string') throw new Error('log_query_invalid');
    if (!value) continue;
    if (ids.has(key) && !UUID_PATTERN.test(value)) throw new Error('log_query_invalid');
    if (
      (key === 'module' && !LOG_MODULES.includes(value)) ||
      (key === 'level' && !LOG_LEVELS.includes(value)) ||
      (key === 'platform' && !LOG_PLATFORMS.includes(value))
    )
      throw new Error('log_query_invalid');
    if (key === 'since' || key === 'until') {
      params.set(key, canonicalLogTime(value));
    } else params.set(key, value);
  }
  if (Object.keys(filters).some((key) => !keys.has(key))) throw new Error('log_query_invalid');
  if (params.has('since') && params.has('until') && params.get('since')! > params.get('until')!)
    throw new Error('log_query_invalid');
  if (cursor) {
    if (typeof cursor !== 'string' || cursor.length > 2048) throw new Error('log_query_invalid');
    params.set('cursor', cursor);
  }
  return `/api/v1/logs?${params}`;
}
export function initialLogFilters(query: URLSearchParams): LogFilters {
  const result: LogFilters = {};
  for (const key of keys) {
    const value = query.get(key);
    if (!value) continue;
    try {
      logQuery({ [key]: value });
      if (key === 'since' || key === 'until') {
        const canonical = canonicalLogTime(value);
        const date = new Date(canonical);
        const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
        result[key] = local.toISOString().slice(0, -1) + canonical.slice(-4, -1);
      } else result[key as keyof LogFilters] = value;
    } catch {
      /* Never reflect unknown URL values into the form. */
    }
  }
  return result;
}
export function logFailure(error: unknown): string {
  const code =
    error instanceof ApiError
      ? error.code
      : error instanceof Error &&
          ['log_query_invalid', 'log_response_invalid', 'log_diagnostic_too_large'].includes(error.message)
        ? error.message
        : '';
  const messages: Record<string, string> = {
    log_query_invalid: '筛选条件无效，请检查 UUID、时间和组件选项。',
    log_cursor_invalid: '日志分页标识无效，请重新查询。',
    log_cursor_stale: '日志片段已轮转或服务已重启，请重新查询；未自动重放。',
    log_store_unavailable: '日志存储不可用，请检查日志目录权限、挂载及磁盘空间。',
    log_store_scan_limited: '本次存储扫描达到上限，请缩小时间范围。',
    log_operation_not_found: '找不到对应操作记录，可清空操作筛选后查看其它日志。',
    log_database_unavailable: '任务数据库暂不可用，无法关联诊断。',
    log_diagnostic_too_large: '诊断包超过大小上限，请缩小日志范围。',
    log_response_invalid: '日志响应未通过安全格式或任务身份校验，请刷新后手动重试。',
    operator_auth_required: '后台会话已失效，请重新登录。'
  };
  return Object.hasOwn(messages, code)
    ? messages[code]
    : '日志请求未完成，请手动重试。服务器原始异常不会在这里显示。';
}
const phases: Record<string, string> = {
  preflight: '登录预检',
  account_lock: '取得账户锁',
  browser_launch: '启动浏览器',
  platform_navigation: '打开平台页面',
  session_probe: '验证已有会话',
  login_dialog: '打开登录入口',
  qr_locate: '定位二维码',
  qr_image_fetch: '获取二维码图像',
  qr_relay: '中转二维码',
  waiting_scan: '等待用户扫码',
  login_confirmation: '确认平台登录',
  profile_finalize: '保存会话',
  cleanup: '清理登录进程',
  upstream_execution: '上游流程（细阶段未知）',
  preparing: '准备执行',
  authenticating: '登录验证',
  downloading: '下载文件',
  exporting: '写入兼容目录',
  syncing: '同步作品',
  discovering: '发现作品',
  ingesting: '保存元数据',
  claiming_jobs: '领取任务',
  jobs_processed: '任务批次完成',
  starting: '启动',
  stopping: '停止',
  completed: '完成',
  running: '执行中',
  probing: '探测服务',
  finalizing: '写入终态',
  reconciling: '核对恢复状态',
  verifying_cookie: '验证 Cookie',
  saving_cookie: '保存 Cookie',
  looking_up_creator: '查询作者',
  fetching_creator_avatar: '获取作者头像',
  baselining: '建立媒体库观察基线',
  dispatching: '发送媒体库刷新',
  accepted: '服务器已接受刷新',
  polling: '等待媒体库观察结果',
  observed: '已观察到目标媒体',
  unknown: '阶段未记录'
};
const actions: Record<string, string> = {
  navigate: '导航',
  click: '点击',
  wait_selector: '等待页面元素',
  wait_load: '等待页面加载',
  fetch: '请求图像',
  relay_write: '写入二维码',
  confirm: '确认登录',
  probe: '探测会话',
  launch: '启动浏览器',
  read_image: '读取图像',
  cleanup: '清理',
  start: '开始',
  finish: '结束',
  execute: '执行',
  finalize: '完成保存',
  phase_change: '阶段变化',
  prepare: '准备',
  acquire: '取得锁',
  'account-cookie-login': 'Cookie 登录',
  'creator-profile': '作者资料查询',
  'account-login': '平台登录',
  'asset-download': '资源下载',
  'scheduler-run': '订阅同步批次',
  'pipeline-run': '下载与导出批次',
  'emby-export': 'Emby 兼容导出',
  'media-server-probe': '媒体服务器探测',
  'media-server-scan': '媒体库定向刷新'
};
export function logPhase(value?: string): string {
  return value ? (Object.hasOwn(phases, value) ? phases[value] : '其它受控阶段') : '未记录细阶段';
}
export function logAction(value?: string): string {
  return value ? (Object.hasOwn(actions, value) ? actions[value] : '其它受控动作') : '—';
}
export function logSummary(event: LogEvent): string {
  if (event.event_code === 'login_terminal')
    return '本次登录结束；下方保留终止动作证据，以账户认证终态为准。';
  if (event.event_code === 'login_stage')
    return event.outcome === 'failed'
      ? '此步骤失败；上游可能继续备用流程，不等于整个登录已失败。'
      : '登录子步骤记录，不单独证明认证成功。';
  if (event.event_code === 'application_log_redacted')
    return '组件日志已记录级别；原始消息/参数未保存，避免凭据泄露。';
  if (event.event_code === 'login_diagnostics_degraded')
    return '本次登录诊断不完整，请同时检查日志健康和任务终态。';
  const summaries: Record<string, string> = {
    operation_started: '后台操作开始',
    operation_phase_changed: '后台操作阶段变化',
    operation_finished: '后台操作结束',
    job_started: '调度任务开始',
    job_finished: '调度任务结束',
    request_finished: 'API 请求完成（不记录请求路径或内容）',
    service_started: '服务启动',
    service_stopped: '服务停止',
    supervisor_started: '调度器启动',
    supervisor_stopped: '调度器停止',
    supervisor_failed: '调度器异常结束',
    command_started: '本地命令开始（不代表已创建数据库操作）',
    command_finished: '本地命令结束（以实际输出及任务状态为准）'
  };
  return Object.hasOwn(summaries, event.event_code) ? summaries[event.event_code] : '受控组件事件';
}

// Independently rebuild display/download projections. TypeScript annotations
// alone do not prevent an unexpected API response from exporting raw secrets.
const operationKinds = [
  'account-cookie-login',
  'creator-profile',
  'account-login',
  'asset-download',
  'scheduler-run',
  'pipeline-run',
  'emby-export',
  'media-server-probe',
  'media-server-scan'
];
const operationStates = [
  'queued',
  'running',
  'succeeded',
  'failed_retryable',
  'failed_terminal',
  'cancelled',
  'interrupted'
];
const eventCodes = [
  'application_log_redacted',
  'request_finished',
  'service_started',
  'service_stopped',
  'operation_started',
  'operation_phase_changed',
  'operation_finished',
  'job_started',
  'job_finished',
  'supervisor_started',
  'supervisor_stopped',
  'supervisor_failed',
  'login_stage',
  'login_terminal',
  'login_diagnostics_degraded',
  'output_policy_saved',
  'log_store_degraded',
  'command_started',
  'command_finished'
];
const eventPhases = [
  ...Object.keys(phases),
  'running',
  'probing',
  'finalizing',
  'reconciling',
  'verifying_cookie',
  'saving_cookie',
  'looking_up_creator',
  'fetching_creator_avatar',
  'baselining',
  'dispatching',
  'accepted',
  'polling',
  'observed'
];
const eventOutcomes = [
  ...operationStates,
  'started',
  'failed',
  'claimed',
  'retry_wait',
  'waiting_auth',
  'waiting_user',
  'awaiting_auth',
  'skipped',
  'rejected',
  'completed',
  'timed_out',
  'expired',
  'fenced',
  'stopped',
  'unknown'
];
const sourceFrames = [
  'parent',
  'runner',
  'client',
  'login',
  'qr_helper',
  'qr_relay',
  'httpx_get',
  'browser_type',
  'browser_context',
  'page',
  'frame',
  'locator',
  'element_handle',
  'cleanup'
];
const runnerStatuses = [
  'authenticated',
  'expired',
  'failed',
  'timed_out',
  'cancelled',
  'account_busy',
  'configuration_invalid',
  'start_failed',
  'result_invalid',
  'upstream_login_exited',
  'upstream_browser_timeout',
  'login_confirmation_failed',
  'browser_launch_failed'
];
const controlCodes = [
  'operation_cancel_observed',
  'operation_cancel_requested',
  'operation_cancelled',
  'operation_entity_linked',
  'operation_failed',
  'operation_interrupted',
  'operation_phase_changed',
  'operation_progressed',
  'operation_reconciled',
  'operation_requested',
  'operation_started',
  'operation_succeeded'
];
const eventIds = [...ids, 'correlation_id', 'author_id', 'asset_id'];
function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('log_response_invalid');
  return value as Record<string, unknown>;
}
function choice(value: unknown, allowed: readonly string[]): string | null {
  return typeof value === 'string' && allowed.includes(value) ? value : null;
}
function uuid(value: unknown): string | null {
  return typeof value === 'string' && UUID_PATTERN.test(value) ? value : null;
}
function count(value: unknown): number | null {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 ? value : null;
}
function timestamp(value: unknown): string | null {
  try {
    return typeof value === 'string' &&
      /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$/.test(value) &&
      canonicalLogTime(value) === value
      ? value
      : null;
  } catch {
    return null;
  }
}
function array(value: unknown, maximum: number): unknown[] {
  if (!Array.isArray(value) || value.length > maximum) throw new Error('log_response_invalid');
  return value;
}
function parseLogEvent(value: unknown): LogEvent {
  const row = object(value);
  const at = timestamp(row.timestamp),
    writer = uuid(row.writer_id),
    sequence = count(row.sequence);
  const code = choice(row.event_code, eventCodes),
    module = choice(row.module, LOG_MODULES),
    level = choice(row.level, LOG_LEVELS);
  if (row.schema_version !== 1 || !at || !writer || !sequence || !code || !module || !level)
    throw new Error('log_response_invalid');
  const result: Record<string, unknown> = {
    schema_version: 1,
    timestamp: at,
    writer_id: writer,
    sequence,
    event_code: code,
    module,
    level
  };
  const enums = {
    phase: eventPhases,
    action: [...Object.keys(actions), ...operationKinds, 'tick', 'stop', 'save', 'drop'],
    outcome: eventOutcomes,
    error_type: [
      'none',
      'playwright_timeout',
      'timeout',
      'os_error',
      'cancelled',
      'system_exit',
      'configuration',
      'confirmation_rejected',
      'browser_launch_failed',
      'unknown'
    ],
    platform: LOG_PLATFORMS,
    source_frame: sourceFrames
  };
  for (const [key, allowed] of Object.entries(enums)) {
    const safe = choice(row[key], allowed);
    if (safe !== null) result[key] = safe;
  }
  for (const key of eventIds) {
    const safe = uuid(row[key]);
    if (safe !== null) result[key] = safe;
  }
  for (const key of ['duration_ms', 'attempt', 'count', 'bytes', 'http_status']) {
    const safe = count(row[key]);
    if (safe !== null) result[key] = safe;
  }
  return result as unknown as LogEvent;
}
function parseLogPage(value: unknown): LogPage {
  const row = object(value),
    coverage = object(row.coverage);
  if (
    row.next_cursor !== null &&
    (typeof row.next_cursor !== 'string' || !row.next_cursor || row.next_cursor.length > 2048)
  )
    throw new Error('log_response_invalid');
  if (
    coverage.order !== 'segment_ascending' ||
    coverage.global_time_order !== false ||
    coverage.bounded !== true
  )
    throw new Error('log_response_invalid');
  return {
    events: array(row.events, 200).map(parseLogEvent),
    next_cursor: row.next_cursor as string | null,
    coverage: {
      order: 'segment_ascending',
      global_time_order: false,
      bounded: true,
      scan_limited: coverage.scan_limited !== false,
      corrupt_records: count(coverage.corrupt_records) ?? 0,
      truncated_segments: count(coverage.truncated_segments) ?? 0,
      unavailable_segments: count(coverage.unavailable_segments) ?? 0,
      omitted_segment_tails: count(coverage.omitted_segment_tails) ?? 0,
      retention_may_have_removed: true
    }
  };
}
function parseLogStatus(value: unknown): LogStatus {
  const row = object(value);
  return {
    health: choice(row.health, ['ok', 'closed', 'degraded', 'unavailable']) ?? 'unavailable',
    queued: count(row.queued) ?? 0,
    accepted: count(row.accepted) ?? 0,
    written: count(row.written) ?? 0,
    dropped: count(row.dropped) ?? 0,
    invalid: count(row.invalid) ?? 0,
    segment_max_bytes: count(row.segment_max_bytes) ?? 0,
    total_max_bytes: count(row.total_max_bytes) ?? 0,
    retention_days: count(row.retention_days) ?? 0,
    storage_bytes: count(row.storage_bytes),
    managed_segments: count(row.managed_segments),
    active_segments: count(row.active_segments),
    scope: 'process_counters_shared_storage',
    last_error: choice(row.last_error, [
      'log_event_invalid',
      'log_store_closed',
      'log_queue_full',
      'log_store_unavailable',
      'log_store_scan_limited',
      'log_flush_timeout'
    ]),
    writer_running: row.writer_running === true,
    drained: row.drained === true,
    shutdown_complete: row.shutdown_complete === true
  };
}
function parseOperationTrace(value: unknown, operationId: string) {
  const row = object(value),
    operation = object(row.operation);
  if (row.schema_version !== 1 || !uuid(operationId) || operation.id !== operationId)
    throw new Error('log_response_invalid');
  const logs = parseLogPage(row.logs);
  if (logs.events.some((event) => event.operation_id !== operationId))
    throw new Error('log_response_invalid');
  return {
    schema_version: 1,
    generated_at: timestamp(row.generated_at),
    operation: {
      id: operationId,
      kind: choice(operation.kind, operationKinds) ?? 'unknown',
      state: choice(operation.state, operationStates) ?? 'unknown',
      revision: count(operation.revision),
      correlation_id: uuid(operation.correlation_id),
      target_type: choice(operation.target_type, ['account', 'asset', 'author']),
      target_id: uuid(operation.target_id),
      phase: choice(operation.phase, eventPhases) ?? 'unknown',
      requested_at: timestamp(operation.requested_at),
      started_at: timestamp(operation.started_at),
      finished_at: timestamp(operation.finished_at),
      runner_status: choice(operation.runner_status, runnerStatuses)
    },
    subjects: array(row.subjects, 64).flatMap((value) => {
      const subject = object(value),
        id = uuid(subject.id),
        type = choice(subject.type, ['login_session', 'job', 'sync_run']),
        role = choice(subject.role, ['execution', 'result', 'related']);
      return id && type && role ? [{ id, type, role }] : [];
    }),
    subjects_truncated: row.subjects_truncated !== false,
    control_events: array(row.control_events, 200).map((value) => {
      const event = object(value);
      return {
        sequence: count(event.sequence),
        at: timestamp(event.at),
        event_code: choice(event.event_code, controlCodes) ?? 'unknown',
        level: choice(event.level, LOG_LEVELS) ?? 'info',
        phase: choice(event.phase, eventPhases) ?? 'unknown',
        from_state: choice(event.from_state, operationStates),
        to_state: choice(event.to_state, operationStates)
      };
    }),
    control_events_truncated: row.control_events_truncated !== false,
    logs,
    login_stage_evidence:
      row.login_stage_evidence === 'available_in_page'
        ? 'available_in_page'
        : 'not_recorded_or_not_in_retained_page',
    consistency: 'bounded_observation_not_atomic',
    authentication_authority: 'durable_account_state_only'
  };
}
export function logDiagnosticArtifact(
  value: unknown,
  operationId: string
): { filename: string; text: string } {
  const row = object(value),
    project = object(row.project),
    upstreams = object(row.upstreams);
  if (row.diagnostic_schema_version !== 1 || project.name !== 'media-sync')
    throw new Error('log_response_invalid');
  const trace = parseOperationTrace(row.trace, operationId);
  const sha = (value: unknown) => (typeof value === 'string' && /^[0-9a-f]{40}$/.test(value) ? value : null);
  const result = {
    diagnostic_schema_version: 1,
    project: {
      name: 'media-sync',
      version:
        typeof project.version === 'string' && /^\d+\.\d+\.\d+$/.test(project.version)
          ? project.version
          : null
    },
    upstreams: { MediaCrawler: sha(upstreams.MediaCrawler), 'bili-sync-up': sha(upstreams['bili-sync-up']) },
    trace: {
      ...trace,
      logs: { ...trace.logs, next_cursor: null, has_more_retained_events: trace.logs.next_cursor !== null }
    },
    logging: parseLogStatus(row.logging),
    limitations: [
      'bounded_retained_page',
      'no_raw_output_or_credentials',
      'not_live_qualification',
      'continuation_cursor_omitted'
    ]
  };
  const text = JSON.stringify(result, null, 2);
  if (new TextEncoder().encode(text).byteLength > 2_097_152) throw new Error('log_diagnostic_too_large');
  return { filename: `media-sync-diagnostic-${operationId}.json`, text };
}
export function logIdentityLink(key: string, value: unknown): string | null {
  return ids.has(key) && uuid(value) ? `/logs?${new URLSearchParams({ [key]: value as string })}` : null;
}
export interface LogView {
  filters: LogFilters;
  events: LogEvent[];
  status: LogStatus | null;
  coverage: LogCoverage | null;
  nextCursor: string | null;
  trace: OperationTrace | null;
  busy: boolean;
  error: string;
}
export class LogCenterController {
  view: LogView = {
    filters: {},
    events: [],
    status: null,
    coverage: null,
    nextCursor: null,
    trace: null,
    busy: false,
    error: ''
  };
  private gate = new LatestRequestGate();
  private disposed = false;
  private activeQuery: string | null = null;
  constructor(
    private publish: (view: LogView) => void,
    private request: typeof api = api
  ) {}
  private emit(changes: Partial<LogView>): void {
    if (this.disposed) return;
    this.view = { ...this.view, ...changes };
    this.publish(this.view);
  }
  async load(filters: LogFilters = this.view.filters, more = false): Promise<void> {
    if (
      this.disposed ||
      (more && (this.view.busy || !this.view.nextCursor || this.view.events.length >= 2000))
    )
      return;
    const selected = { ...filters };
    let url: string;
    try {
      if (more && logQuery(selected) !== logQuery(this.view.filters)) throw new Error('log_query_invalid');
      url = logQuery(selected, more ? this.view.nextCursor : null);
    } catch (error) {
      this.emit({ error: logFailure(error) });
      return;
    }
    if (this.view.busy && this.activeQuery === url) return;
    this.activeQuery = url;
    this.emit({ busy: true, error: '' });
    const result = await this.gate.run(async (signal) => {
      const [page, status, trace] = await Promise.all([
        this.request<LogPage>(url, { signal }),
        this.request<LogStatus>('/api/v1/logs/status', { signal }),
        selected.operation_id
          ? this.request<OperationTrace>(`/api/v1/logs/operations/${selected.operation_id}`, { signal })
          : Promise.resolve(null)
      ]);
      const safePage = parseLogPage(page);
      if (
        safePage.events.some((event) =>
          [...ids, 'module', 'platform', 'level'].some((key) => {
            const filter = selected[key as keyof LogFilters];
            return filter && event[key as keyof LogEvent] !== filter;
          })
        )
      )
        throw new Error('log_response_invalid');
      return [
        safePage,
        parseLogStatus(status),
        selected.operation_id ? parseOperationTrace(trace, selected.operation_id) : null
      ] as const;
    });
    if (result.status === 'superseded') return;
    this.activeQuery = null;
    if (result.status === 'rejected') {
      const cursorInvalid =
        result.reason instanceof ApiError &&
        ['log_cursor_invalid', 'log_cursor_stale'].includes(result.reason.code);
      this.emit({
        busy: false,
        error: logFailure(result.reason),
        ...(cursorInvalid ? { nextCursor: null } : {})
      });
      return;
    }
    const [page, status, trace] = result.value;
    const unique = new Map(
      (more ? this.view.events : []).map((event) => [`${event.writer_id}:${event.sequence}`, event])
    );
    for (const event of page.events) unique.set(`${event.writer_id}:${event.sequence}`, event);
    this.emit({
      busy: false,
      filters: selected,
      events: [...unique.values()].slice(0, 2000),
      status,
      trace,
      coverage:
        more && this.view.coverage
          ? {
              ...page.coverage,
              corrupt_records: this.view.coverage.corrupt_records + page.coverage.corrupt_records,
              truncated_segments: this.view.coverage.truncated_segments + page.coverage.truncated_segments,
              unavailable_segments:
                this.view.coverage.unavailable_segments + page.coverage.unavailable_segments,
              omitted_segment_tails:
                this.view.coverage.omitted_segment_tails + page.coverage.omitted_segment_tails
            }
          : page.coverage,
      nextCursor: page.next_cursor
    });
  }
  dispose(): void {
    this.disposed = true;
    this.activeQuery = null;
    this.gate.cancel();
  }
}
