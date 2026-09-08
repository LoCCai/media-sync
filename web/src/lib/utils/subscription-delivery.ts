import { ApiError } from '../api/client';
import type {
  BiliDeliveryProgress,
  OperationState,
  Platform,
  SubscriptionDeliveryResult,
  SubscriptionDeliveryStart,
  SubscriptionDetail,
  XhsDeliveryProgress
} from '$lib/types/api';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const OPERATION_STATES = new Set<OperationState>([
  'queued',
  'running',
  'succeeded',
  'failed_retryable',
  'failed_terminal',
  'cancelled',
  'interrupted'
]);
const ACTIVE_STATES = new Set<OperationState>(['queued', 'running']);
const PLATFORMS = new Set<Platform>(['bili', 'xhs', 'dy', 'ks', 'wb', 'tieba', 'zhihu']);
const PHASES: Record<string, string> = {
  preparing: '准备精确执行',
  materializing_sync: '创建此订阅的采集任务',
  discovering_content: '查询并采集作者内容',
  content_discovered: '作者内容采集完成',
  resolving_pipeline: '定位此轮下载任务',
  delivering_assets: '下载并归档资产，生成兼容目录',
  assets_delivered: '资产下载、归档与目录生成完成',
  verifying_directory: '验证本地媒体目录',
  directory_verified: '本地媒体目录已验证'
};
const DELIVERY_ERRORS: Record<string, string> = {
  operation_already_running: '此订阅已有交付操作在运行；没有重复提交，请到任务或日志中心核对。',
  subscription_delivery_busy: '此订阅或全局执行容量正被占用；操作已保留为可重试失败，请先核对任务。',
  subscription_delivery_mediacrawler_not_enabled:
    'MediaCrawler 尚未为本次交付启用；本次没有创建采集或下载任务。',
  subscription_delivery_license_required:
    '本次交付缺少 MediaCrawler 许可证确认；本次没有创建采集或下载任务。',
  subscription_delivery_cancel_unsupported:
    '该交付链已获得持久任务所有权，当前版本不会虚假声称取消；请让已开始的阶段收尾并在任务/日志中核对。',
  subscription_delivery_paused: '订阅当前已暂停；本次没有开始采集，请先启用并重新读取最新状态。',
  subscription_delivery_stale: '订阅配置、调度修订或任务身份已经变化；旧结果不会用于宣称交付成功。',
  subscription_delivery_discovery_failed: '作者内容采集未成功；不会继续宣称下载或目录交付成功。',
  subscription_delivery_pipeline_missing: '采集成功后没有找到与本轮严格绑定的下载任务；请查看任务与日志。',
  subscription_delivery_pipeline_failed: '下载、归档或目录写入未成功；请查看任务与日志中的具体阶段。',
  subscription_delivery_storage_unavailable: '数据库或媒体存储暂时不可用；请核对日志后再决定是否重试。',
  subscription_delivery_evidence_invalid: '交付结果缺少可验证的精确任务或目录证据；不会显示为成功。',
  subscription_delivery_scope_changed: '执行期间作者资产范围发生变化；不会用过期范围宣称交付成功。',
  subscription_delivery_unexpected: '交付流程意外结束；请使用操作 ID 在日志中心核对。',
  subscription_delivery_cancelled: '交付操作已取消；未完成的阶段不会显示为目录交付成功。',
  subscription_delivery_interrupted: '服务重启或执行权变化中断了交付；请用操作 ID 核对任务和日志。',
  license_acknowledgement_required: '请先完成首次使用与许可证确认，本次没有发起采集。',
  license_requires_enable_mediacrawler: 'MediaCrawler 启用状态与许可证确认不一致，本次没有发起采集。',
  mediacrawler_not_enabled: 'MediaCrawler 尚未启用，本次没有发起采集。',
  operator_auth_required: '后台会话已失效；本地停止观察，但服务端操作不一定已经停止。',
  operator_csrf_forbidden: '后台会话已经变化；请求未自动重放，请使用任务页面核对。',
  request_validation_failed: '交付请求格式无效；没有自动重试。',
  request_timeout: '本地等待请求结果超时，无法判断服务端是否接受；不要直接重复提交，请先核对任务。',
  xhs_access_restricted: 'XHS 返回访问受限；已保留当前游标和已完成笔记，请降低频率并稍后从同一页继续。',
  xhs_empty_page_stalled: 'XHS 返回空页面但仍声称有下一页，游标没有推进；不会把它误判为历史末尾。',
  xhs_note_detail_partial:
    '本轮有 XHS 笔记详情未取得；其他完整笔记已保留，失败笔记会在同一页用新 token 重试。'
};
const FEEDS: Record<string, string> = {
  uploads: '普通投稿',
  dynamics: '动态',
  notes: '笔记',
  posts: '作品',
  threads: '主题帖',
  answers: '回答'
};
const SCAN_STATES: Record<string, string> = {
  unproven: '未证明；没有可信的历史覆盖结论',
  scanning: '历史扫描已推进；仍不代表历史完整',
  source_end_observed: '曾观察到当前来源末尾；不等于历史完整'
};
const LANES: Record<string, string> = { head: '头部更新', history: '历史回填' };
const STOP_REASONS: Record<string, string> = {
  item_limit: '达到单元条目上限',
  list_limit: '达到列表请求预算',
  head_boundary: '观察到既有头部边界',
  source_end: '本轮观察到来源末尾',
  restarted: '分页证据变化并保守重启',
  snapshot_saved: '已保存待处理快照',
  page_end: '本轮页面结束'
};
const SHA1 = /^[0-9a-f]{40}$/;
const CODE = /^[a-z][a-z0-9_]{0,127}$/;
const BILI_DELIVERY_PHASES = new Set(['backfill', 'reconciling', 'incremental', 'blocked']);
const BILI_DELIVERY_PHASE_LABELS: Record<BiliDeliveryProgress['phase'], string> = {
  backfill: '历史回填',
  reconciling: '头部对账',
  incremental: '增量检查',
  blocked: '需要处理'
};
const XHS_DELIVERY_PHASES = new Set(['backfill', 'reconciling', 'incremental', 'blocked']);
const XHS_DELIVERY_PHASE_LABELS: Record<XhsDeliveryProgress['phase'], string> = {
  backfill: '历史笔记回填',
  reconciling: '头部笔记对账',
  incremental: '增量笔记检查',
  blocked: '需要处理'
};
const XHS_STOP_REASONS: Record<Exclude<XhsDeliveryProgress['last_stop_reason'], null>, string> = {
  has_more_false: '列表明确返回没有下一页',
  empty_page_stalled: '空页面且游标没有推进',
  access_restricted: '平台访问受限',
  unit_cap_reached: '本轮达到页面或条目边界'
};

export const EXACT_DELIVERY_NOTICE =
  '只为当前选中的订阅创建并领取精确任务，依次执行采集→下载→归档→生成兼容目录。B站投稿和带创作者凭据的 XHS 笔记按本次 Run 内容与该订阅未完成积压（source_run_plus_retry_backlog）处理；其他兼容流程仍可能使用作者有效资产快照（author_active_snapshot），不是“仅本轮新增”。生成兼容目录不要求连接 Emby 或 Jellyfin；媒体服务器连接只是可选联动。';
export const UPSTREAM_HISTORY_NOTICE =
  '平台作者接口可能扫描完整历史或进行多轮分页；订阅的单次入库上限不一定限制上游扫描量。执行会使用已保存的平台会话并可能触发平台风控，不会自动规避验证码或绕过限制。';
export const SCAN_PROGRESS_NOTICE =
  '这里只展示已提交且与检查点绑定的扫描证据；未证明、扫描中或曾观察到来源末尾，都不声明全历史完成。';
export const BILI_DELIVERY_PROGRESS_NOTICE =
  '“增量检查”表示最近一个有界快照已完成源末尾与头部对账，不表示平台历史永久完整；认证、作者、策略或锁定上游变化会使该证明失效。';
export const XHS_DELIVERY_PROGRESS_NOTICE =
  '“增量笔记检查”只表示不透明游标历史到达明确末页，并以新 token 稳定重列过头部；不会显示游标或 token，也不表示平台历史永久不变。';
export const DELIVERY_UNAVAILABLE =
  '暂时无法安全确认本次交付结果；没有自动重试，也不会据此宣称媒体已经写入目录。';
export const DELIVERY_OBSERVATION_ENDED =
  '本地状态观察已结束，但这不代表服务端操作已停止。请使用操作 ID 到任务或日志中心核对终态。';
export const DELIVERY_LICENSE_REQUIRED = '请先完成首次使用与许可证确认，本次没有发起采集。';

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function uuid(value: unknown): value is string {
  return typeof value === 'string' && UUID.test(value);
}

function count(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;
}

function exactKeys(value: Record<string, unknown>, expected: string[]): boolean {
  return Object.keys(value).sort().join(',') === [...expected].sort().join(',');
}

export interface SubscriptionDeliveryScope {
  subscription_id: string;
  platform: Platform;
  expected_schedule_revision: number;
  session_epoch: number;
}

export interface SubscriptionDeliverySnapshot {
  id: string;
  state: OperationState;
  phase: string | null;
  progress: { current: number | null; total: number | null; unit: 'steps' | null } | null;
  error_code: string | null;
  result: SubscriptionDeliveryResult | null;
}

export interface SubscriptionDeliveryView {
  scope: SubscriptionDeliveryScope | null;
  phase: 'idle' | 'not_started' | 'submitting' | 'waiting' | 'succeeded' | 'failed' | 'wait_ended';
  operation_id: string | null;
  operation: SubscriptionDeliverySnapshot | null;
  message: string;
}

export function initialSubscriptionDeliveryView(): SubscriptionDeliveryView {
  return { scope: null, phase: 'idle', operation_id: null, operation: null, message: '' };
}

export function validSubscriptionDeliveryScope(value: unknown): value is SubscriptionDeliveryScope {
  const source = record(value);
  return Boolean(
    source &&
      uuid(source.subscription_id) &&
      PLATFORMS.has(source.platform as Platform) &&
      count(source.expected_schedule_revision) &&
      count(source.session_epoch)
  );
}

export function subscriptionDeliveryRequest(
  scope: SubscriptionDeliveryScope,
  gate: { enable_mediacrawler: true; accept_mediacrawler_license: true }
): SubscriptionDeliveryStart {
  if (!validSubscriptionDeliveryScope(scope)) throw new Error('subscription_delivery_scope_invalid');
  return {
    expected_schedule_revision: scope.expected_schedule_revision,
    global_capacity: 1,
    lease_seconds: 3_600,
    retry_delay_seconds: 30,
    ...gate
  };
}

function parseResult(value: unknown, scope: SubscriptionDeliveryScope): SubscriptionDeliveryResult | null {
  const source = record(value);
  const baseFields = [
    'subscription_id',
    'account_id',
    'author_id',
    'platform',
    'sync_job_id',
    'run_id',
    'pipeline_job_id',
    'export_job_id',
    'discovery_count',
    'asset_identity_count',
    'updated_count',
    'discovery_count_semantics',
    'selection_scope',
    'selected_asset_count',
    'verified_asset_count',
    'downloaded_count',
    'already_verified_count',
    'publication_disposition',
    'managed_file_count',
    'directory_verified'
  ];
  const contentFields = [
    'observed_content_count',
    'delivered_content_count',
    'failed_content_count',
    'retry_backlog_content_count',
    'delivered_retry_backlog_content_count',
    'failed_retry_backlog_content_count',
    'retryable_failed_content_count',
    'terminal_failed_content_count',
    'failure_codes',
    'partial'
  ];
  const contentScoped = Boolean(source && exactKeys(source, [...baseFields, ...contentFields]));
  if (
    !source ||
    (!exactKeys(source, baseFields) && !contentScoped) ||
    source.subscription_id !== scope.subscription_id ||
    source.platform !== scope.platform ||
    !uuid(source.account_id) ||
    !uuid(source.author_id) ||
    !uuid(source.sync_job_id) ||
    !uuid(source.run_id) ||
    !uuid(source.pipeline_job_id) ||
    !uuid(source.export_job_id) ||
    !count(source.discovery_count) ||
    !count(source.asset_identity_count) ||
    !(source.updated_count === null || count(source.updated_count)) ||
    !['created_rows', 'processed_items'].includes(String(source.discovery_count_semantics)) ||
    source.selection_scope !== (contentScoped ? 'source_run_plus_retry_backlog' : 'author_active_snapshot') ||
    !count(source.selected_asset_count) ||
    !count(source.verified_asset_count) ||
    !count(source.downloaded_count) ||
    !count(source.already_verified_count) ||
    source.selected_asset_count !== source.verified_asset_count ||
    source.downloaded_count + source.already_verified_count !== source.verified_asset_count ||
    !['published', 'already_exported'].includes(String(source.publication_disposition)) ||
    !count(source.managed_file_count) ||
    source.directory_verified !== true
  )
    return null;
  const result: SubscriptionDeliveryResult = {
    subscription_id: scope.subscription_id,
    account_id: source.account_id,
    author_id: source.author_id,
    platform: scope.platform,
    sync_job_id: source.sync_job_id,
    run_id: source.run_id,
    pipeline_job_id: source.pipeline_job_id,
    export_job_id: source.export_job_id,
    discovery_count: source.discovery_count,
    asset_identity_count: source.asset_identity_count,
    updated_count: source.updated_count,
    discovery_count_semantics:
      source.discovery_count_semantics as SubscriptionDeliveryResult['discovery_count_semantics'],
    selection_scope: contentScoped ? 'source_run_plus_retry_backlog' : 'author_active_snapshot',
    selected_asset_count: source.selected_asset_count,
    verified_asset_count: source.verified_asset_count,
    downloaded_count: source.downloaded_count,
    already_verified_count: source.already_verified_count,
    publication_disposition:
      source.publication_disposition as SubscriptionDeliveryResult['publication_disposition'],
    managed_file_count: source.managed_file_count,
    directory_verified: true
  };
  if (!contentScoped) return result;
  const failureCodes = source.failure_codes;
  if (
    !count(source.observed_content_count) ||
    !count(source.delivered_content_count) ||
    !count(source.failed_content_count) ||
    !count(source.retry_backlog_content_count) ||
    !count(source.delivered_retry_backlog_content_count) ||
    !count(source.failed_retry_backlog_content_count) ||
    !count(source.retryable_failed_content_count) ||
    !count(source.terminal_failed_content_count) ||
    !Array.isArray(failureCodes) ||
    failureCodes.length > 16 ||
    failureCodes.some((code) => typeof code !== 'string' || !CODE.test(code)) ||
    failureCodes.join(',') !== [...new Set(failureCodes)].sort().join(',') ||
    typeof source.partial !== 'boolean' ||
    source.delivered_content_count + source.failed_content_count !== source.observed_content_count ||
    source.delivered_retry_backlog_content_count + source.failed_retry_backlog_content_count !==
      source.retry_backlog_content_count ||
    source.retryable_failed_content_count + source.terminal_failed_content_count !==
      source.failed_content_count + source.failed_retry_backlog_content_count ||
    source.partial !== source.failed_content_count + source.failed_retry_backlog_content_count > 0 ||
    failureCodes.length > 0 !== source.failed_content_count + source.failed_retry_backlog_content_count > 0
  )
    return null;
  return {
    ...result,
    observed_content_count: source.observed_content_count,
    delivered_content_count: source.delivered_content_count,
    failed_content_count: source.failed_content_count,
    retry_backlog_content_count: source.retry_backlog_content_count,
    delivered_retry_backlog_content_count: source.delivered_retry_backlog_content_count,
    failed_retry_backlog_content_count: source.failed_retry_backlog_content_count,
    retryable_failed_content_count: source.retryable_failed_content_count,
    terminal_failed_content_count: source.terminal_failed_content_count,
    failure_codes: [...failureCodes],
    partial: source.partial
  };
}

function parseProgress(value: unknown): SubscriptionDeliverySnapshot['progress'] | undefined {
  if (value === null) return null;
  const source = record(value);
  if (
    !source ||
    !(source.current === null || count(source.current)) ||
    !(source.total === null || count(source.total)) ||
    !(source.unit === null || source.unit === 'steps')
  )
    return undefined;
  return {
    current: source.current as number | null,
    total: source.total as number | null,
    unit: source.unit as 'steps' | null
  };
}

export function parseSubscriptionDeliveryOperation(
  value: unknown,
  scope: SubscriptionDeliveryScope,
  operationId: string
): SubscriptionDeliverySnapshot | null {
  const source = record(value);
  const target = record(source?.target);
  const progress = parseProgress(source?.progress);
  if (
    !source ||
    !validSubscriptionDeliveryScope(scope) ||
    !uuid(operationId) ||
    source.id !== operationId ||
    source.kind !== 'subscription-delivery' ||
    !OPERATION_STATES.has(source.state as OperationState) ||
    !target ||
    target.type !== 'subscription' ||
    target.id !== scope.subscription_id ||
    progress === undefined ||
    !(source.phase === null || typeof source.phase === 'string') ||
    !(source.error_code === null || typeof source.error_code === 'string')
  )
    return null;
  const state = source.state as OperationState;
  const result = state === 'succeeded' ? parseResult(source.result, scope) : null;
  if (state === 'succeeded' && !result) return null;
  return {
    id: operationId,
    state,
    phase: typeof source.phase === 'string' && Object.hasOwn(PHASES, source.phase) ? source.phase : null,
    progress,
    error_code:
      typeof source.error_code === 'string' && Object.hasOwn(DELIVERY_ERRORS, source.error_code)
        ? source.error_code
        : null,
    result
  };
}

function startedOperation(value: unknown): { operation_id: string; state: OperationState } | null {
  const source = record(value);
  if (!source || !uuid(source.operation_id) || !OPERATION_STATES.has(source.state as OperationState))
    return null;
  return { operation_id: source.operation_id, state: source.state as OperationState };
}

export function subscriptionDeliveryFailure(error: unknown): string {
  const code = error instanceof ApiError ? error.code : typeof error === 'string' ? error : null;
  return code && Object.hasOwn(DELIVERY_ERRORS, code) ? DELIVERY_ERRORS[code] : DELIVERY_UNAVAILABLE;
}

export function subscriptionDeliveryPhaseLabel(view: SubscriptionDeliveryView): string {
  if (view.phase === 'submitting') return '正在提交精确执行';
  if (view.phase === 'not_started') return '尚未启动';
  if (view.phase === 'wait_ended') return '本地观察已结束';
  if (view.phase === 'failed' && !view.operation) return '请求结果未确认';
  const operationPhase = view.operation?.phase;
  if (operationPhase && Object.hasOwn(PHASES, operationPhase)) return PHASES[operationPhase];
  if (view.phase === 'succeeded') return '本地媒体目录已验证';
  if (view.phase === 'failed') return '交付未成功';
  return view.operation_id ? '等待服务端阶段更新' : '等待确认';
}

export function subscriptionDeliveryResultRows(result: SubscriptionDeliveryResult): Array<{
  label: string;
  value: string;
}> {
  const rows = [
    {
      label: result.discovery_count_semantics === 'created_rows' ? '本轮新建内容' : '本轮处理条目',
      value: `${result.discovery_count} 条`
    },
    { label: '识别到的资产身份', value: `${result.asset_identity_count} 个` },
    {
      label:
        result.selection_scope === 'source_run_plus_retry_backlog'
          ? '本轮与重试积压资产'
          : '作者当前有效资产快照',
      value: `${result.selected_asset_count} 个，${
        result.selection_scope === 'author_active_snapshot' ? '已全部验证' : '已验证'
      }`
    },
    { label: '本轮下载', value: `${result.downloaded_count} 个` },
    { label: '复用已有已验证文件', value: `${result.already_verified_count} 个` },
    {
      label: '兼容目录生成',
      value: result.publication_disposition === 'already_exported' ? '已有相同发布版本' : '已发布新目录版本'
    },
    { label: '受管目录文件', value: `${result.managed_file_count} 个` },
    { label: '目录证据', value: '已由后端重新验证；不依赖媒体服务器连接' }
  ];
  if (result.selection_scope === 'source_run_plus_retry_backlog') {
    rows.splice(
      2,
      0,
      { label: '本轮观察内容', value: `${result.observed_content_count ?? 0} 条` },
      { label: '本轮完整交付内容', value: `${result.delivered_content_count ?? 0} 条` },
      {
        label: '本轮未完成内容',
        value: `${result.failed_content_count ?? 0} 条`
      },
      {
        label: '重试积压内容',
        value: `${result.retry_backlog_content_count ?? 0} 条（交付 ${result.delivered_retry_backlog_content_count ?? 0} / 未完成 ${result.failed_retry_backlog_content_count ?? 0}）`
      },
      {
        label: '全部失败内容',
        value: `${(result.failed_content_count ?? 0) + (result.failed_retry_backlog_content_count ?? 0)} 条（可重试 ${result.retryable_failed_content_count ?? 0} / 终态 ${result.terminal_failed_content_count ?? 0}）`
      }
    );
  }
  return rows;
}

export function subscriptionDeliveryUpstreamNotice(detail: SubscriptionDetail): string {
  if (detail.platform !== 'bili') return UPSTREAM_HISTORY_NOTICE;
  const scope = detail.policy_summary?.bili_scope ?? 'uploads';
  return `B站本次只推进当前配置的${scope === 'both' ? '投稿或动态其中一个来源' : scope === 'dynamics' ? '动态来源' : '投稿来源'}有界采集单元；投稿交付只选择本轮精确内容与该订阅未完成积压。一次推进或观察到来源末尾，都不代表全历史完成。`;
}

export interface ScanProgressCard {
  feed: string;
  state: string;
  rows: Array<{ label: string; value: string }>;
}

export function safeScanProgressCards(value: unknown): ScanProgressCard[] {
  const unavailable: ScanProgressCard[] = [
    {
      feed: '扫描证据',
      state: '不可用；不声明全历史完成',
      rows: [{ label: '处理建议', value: '刷新订阅详情并查看本轮任务与日志' }]
    }
  ];
  const source = record(value);
  if (
    !source ||
    source.schema_version !== 1 ||
    source.history_complete !== false ||
    !Array.isArray(source.feeds) ||
    source.feeds.length < 1 ||
    source.feeds.length > 2
  )
    return unavailable;
  const cards: ScanProgressCard[] = [];
  const seen = new Set<string>();
  for (const entryValue of source.feeds) {
    const entry = record(entryValue);
    if (!entry) return unavailable;
    const hasRecordedEvidence = count(entry.unit_count) && entry.unit_count > 0;
    if (
      typeof entry.feed !== 'string' ||
      !Object.hasOwn(FEEDS, entry.feed) ||
      seen.has(entry.feed) ||
      typeof entry.state !== 'string' ||
      !Object.hasOwn(SCAN_STATES, entry.state) ||
      !count(entry.unit_count) ||
      !count(entry.item_count) ||
      !count(entry.history_unit_count) ||
      !count(entry.history_item_count) ||
      entry.history_unit_count > entry.unit_count ||
      entry.history_item_count > entry.item_count ||
      !(
        entry.last_lane === null ||
        (typeof entry.last_lane === 'string' && Object.hasOwn(LANES, entry.last_lane))
      ) ||
      !(
        entry.last_stop_reason === null ||
        (typeof entry.last_stop_reason === 'string' && Object.hasOwn(STOP_REASONS, entry.last_stop_reason))
      ) ||
      (hasRecordedEvidence &&
        (!count(entry.contract_version) ||
          entry.contract_version < 1 ||
          typeof entry.upstream_sha !== 'string' ||
          !SHA1.test(entry.upstream_sha) ||
          !uuid(entry.generation_id) ||
          !count(entry.checkpoint_revision) ||
          entry.checkpoint_revision < 1 ||
          entry.last_lane === null ||
          entry.last_stop_reason === null)) ||
      (!hasRecordedEvidence &&
        (entry.state !== 'unproven' ||
          entry.item_count !== 0 ||
          entry.history_unit_count !== 0 ||
          entry.history_item_count !== 0)) ||
      (entry.state === 'scanning' && entry.history_unit_count < 1) ||
      (entry.state === 'source_end_observed' &&
        (entry.history_unit_count < 1 || !uuid(entry.source_end_run_id)))
    )
      return unavailable;
    seen.add(entry.feed);
    const rows = [
      { label: '已记录采集单元', value: `${entry.unit_count} 轮 / ${entry.item_count} 条` },
      { label: '其中历史回填', value: `${entry.history_unit_count} 轮 / ${entry.history_item_count} 条` }
    ];
    if (typeof entry.last_lane === 'string') rows.push({ label: '最近通道', value: LANES[entry.last_lane] });
    if (typeof entry.last_stop_reason === 'string')
      rows.push({ label: '最近停止原因', value: STOP_REASONS[entry.last_stop_reason] });
    cards.push({ feed: FEEDS[entry.feed], state: SCAN_STATES[entry.state], rows });
  }
  return cards;
}

function optionalIso(value: unknown): value is string | null {
  return (
    value === null ||
    (typeof value === 'string' &&
      value.length <= 40 &&
      /(?:Z|[+-][0-9]{2}:[0-9]{2})$/.test(value) &&
      Number.isFinite(Date.parse(value)))
  );
}

export function parseBiliDeliveryProgress(value: unknown): BiliDeliveryProgress | null {
  const source = record(value);
  const fields = [
    'schema_version',
    'initialized',
    'phase',
    'baseline_snapshot_complete',
    'generation_id',
    'batch_count',
    'content_observation_count',
    'backfill_batch_count',
    'reconciliation_batch_count',
    'incremental_batch_count',
    'partial_batch_count',
    'failed_content_count',
    'last_lane',
    'last_stop_reason',
    'last_delivery_at',
    'source_end_observed_at',
    'source_end_run_id',
    'reconciled_at',
    'reconciliation_run_id',
    'baseline_snapshot_at',
    'next_eligible_at',
    'blocked_code'
  ];
  if (
    !source ||
    !exactKeys(source, fields) ||
    source.schema_version !== 1 ||
    typeof source.initialized !== 'boolean' ||
    typeof source.phase !== 'string' ||
    !BILI_DELIVERY_PHASES.has(source.phase) ||
    typeof source.baseline_snapshot_complete !== 'boolean' ||
    !(source.generation_id === null || uuid(source.generation_id)) ||
    !count(source.batch_count) ||
    !count(source.content_observation_count) ||
    !count(source.backfill_batch_count) ||
    !count(source.reconciliation_batch_count) ||
    !count(source.incremental_batch_count) ||
    !count(source.partial_batch_count) ||
    !count(source.failed_content_count) ||
    !(
      source.last_lane === null ||
      (typeof source.last_lane === 'string' && Object.hasOwn(LANES, source.last_lane))
    ) ||
    !(
      source.last_stop_reason === null ||
      (typeof source.last_stop_reason === 'string' && Object.hasOwn(STOP_REASONS, source.last_stop_reason))
    ) ||
    !optionalIso(source.last_delivery_at) ||
    !optionalIso(source.source_end_observed_at) ||
    !(source.source_end_run_id === null || uuid(source.source_end_run_id)) ||
    !optionalIso(source.reconciled_at) ||
    !(source.reconciliation_run_id === null || uuid(source.reconciliation_run_id)) ||
    !optionalIso(source.baseline_snapshot_at) ||
    !optionalIso(source.next_eligible_at) ||
    !(
      source.blocked_code === null ||
      (typeof source.blocked_code === 'string' && CODE.test(source.blocked_code))
    )
  )
    return null;
  const phase = source.phase as BiliDeliveryProgress['phase'];
  const counters =
    source.backfill_batch_count + source.reconciliation_batch_count + source.incremental_batch_count;
  if (
    counters !== source.batch_count ||
    source.partial_batch_count > source.batch_count ||
    source.baseline_snapshot_complete !== (phase === 'incremental') ||
    (source.generation_id !== null) !== source.initialized ||
    (source.source_end_observed_at !== null) !== (source.source_end_run_id !== null) ||
    (source.reconciled_at !== null) !== (source.reconciliation_run_id !== null) ||
    (source.reconciled_at !== null) !== (source.baseline_snapshot_at !== null) ||
    (phase === 'incremental' && source.baseline_snapshot_at === null) ||
    (phase === 'blocked') !== (source.blocked_code !== null) ||
    (!source.initialized &&
      (phase !== 'backfill' ||
        source.baseline_snapshot_complete ||
        source.batch_count !== 0 ||
        source.content_observation_count !== 0 ||
        source.partial_batch_count !== 0 ||
        source.failed_content_count !== 0 ||
        source.last_lane !== null ||
        source.last_stop_reason !== null ||
        source.last_delivery_at !== null ||
        source.source_end_observed_at !== null ||
        source.reconciled_at !== null ||
        source.baseline_snapshot_at !== null ||
        source.blocked_code !== null))
  )
    return null;
  return {
    schema_version: 1,
    initialized: source.initialized,
    phase,
    baseline_snapshot_complete: source.baseline_snapshot_complete,
    generation_id: source.generation_id,
    batch_count: source.batch_count,
    content_observation_count: source.content_observation_count,
    backfill_batch_count: source.backfill_batch_count,
    reconciliation_batch_count: source.reconciliation_batch_count,
    incremental_batch_count: source.incremental_batch_count,
    partial_batch_count: source.partial_batch_count,
    failed_content_count: source.failed_content_count,
    last_lane: source.last_lane as BiliDeliveryProgress['last_lane'],
    last_stop_reason: source.last_stop_reason,
    last_delivery_at: source.last_delivery_at,
    source_end_observed_at: source.source_end_observed_at,
    source_end_run_id: source.source_end_run_id,
    reconciled_at: source.reconciled_at,
    reconciliation_run_id: source.reconciliation_run_id,
    baseline_snapshot_at: source.baseline_snapshot_at,
    next_eligible_at: source.next_eligible_at,
    blocked_code: source.blocked_code
  };
}

export interface BiliDeliveryProgressCard {
  phase: string;
  status: string;
  notice: string;
  rows: Array<{ label: string; value: string }>;
}

function displayTime(value: string | null): string {
  return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—';
}

export function safeBiliDeliveryProgressCard(value: unknown): BiliDeliveryProgressCard {
  const progress = parseBiliDeliveryProgress(value);
  if (!progress) {
    return {
      phase: '证据不可用',
      status: 'unknown',
      notice: '服务端投影未通过封闭格式校验；请刷新详情并核对任务日志。',
      rows: [{ label: '基线快照', value: '未声明完成' }]
    };
  }
  const rows = progress.initialized
    ? [
        {
          label: '已交付批次',
          value: `${progress.batch_count} 轮（回填 ${progress.backfill_batch_count} / 对账 ${progress.reconciliation_batch_count} / 增量 ${progress.incremental_batch_count}）`
        },
        { label: '本地交付内容观察', value: `${progress.content_observation_count} 条` },
        {
          label: '部分批次 / 当前失败内容',
          value: `${progress.partial_batch_count} 轮 / ${progress.failed_content_count} 条`
        },
        {
          label: '最近交付',
          value:
            progress.last_lane && progress.last_stop_reason
              ? `${LANES[progress.last_lane]} · ${STOP_REASONS[progress.last_stop_reason]} · ${displayTime(progress.last_delivery_at)}`
              : displayTime(progress.last_delivery_at)
        },
        { label: '最近源末尾证据', value: displayTime(progress.source_end_observed_at) },
        { label: '最近稳定对账', value: displayTime(progress.reconciled_at) },
        { label: '下次可运行', value: displayTime(progress.next_eligible_at) }
      ]
    : [
        { label: '交付合格批次', value: '尚未产生' },
        { label: '基线快照', value: '未声明完成' },
        { label: '下次可运行', value: displayTime(progress.next_eligible_at) }
      ];
  if (progress.blocked_code) rows.push({ label: '阻塞代码', value: progress.blocked_code });
  return {
    phase: BILI_DELIVERY_PHASE_LABELS[progress.phase],
    status:
      progress.phase === 'incremental'
        ? 'succeeded'
        : progress.phase === 'blocked'
          ? 'failed_terminal'
          : progress.phase === 'reconciling'
            ? 'running'
            : 'queued',
    notice: BILI_DELIVERY_PROGRESS_NOTICE,
    rows
  };
}

export function parseXhsDeliveryProgress(value: unknown): XhsDeliveryProgress | null {
  const source = record(value);
  const fields = [
    'schema_version',
    'initialized',
    'phase',
    'baseline_snapshot_complete',
    'generation_id',
    'batch_count',
    'note_observation_count',
    'cursor_step_count',
    'backfill_batch_count',
    'reconciliation_batch_count',
    'incremental_batch_count',
    'partial_batch_count',
    'failed_note_count',
    'last_stop_reason',
    'last_delivery_at',
    'source_end_observed_at',
    'source_end_run_id',
    'reconciled_at',
    'reconciliation_run_id',
    'baseline_snapshot_at',
    'next_eligible_at',
    'blocked_code'
  ];
  if (
    !source ||
    !exactKeys(source, fields) ||
    source.schema_version !== 1 ||
    typeof source.initialized !== 'boolean' ||
    typeof source.phase !== 'string' ||
    !XHS_DELIVERY_PHASES.has(source.phase) ||
    typeof source.baseline_snapshot_complete !== 'boolean' ||
    !(source.generation_id === null || uuid(source.generation_id)) ||
    !count(source.batch_count) ||
    !count(source.note_observation_count) ||
    !count(source.cursor_step_count) ||
    !count(source.backfill_batch_count) ||
    !count(source.reconciliation_batch_count) ||
    !count(source.incremental_batch_count) ||
    !count(source.partial_batch_count) ||
    !count(source.failed_note_count) ||
    !(
      source.last_stop_reason === null ||
      (typeof source.last_stop_reason === 'string' &&
        Object.hasOwn(XHS_STOP_REASONS, source.last_stop_reason))
    ) ||
    !optionalIso(source.last_delivery_at) ||
    !optionalIso(source.source_end_observed_at) ||
    !(source.source_end_run_id === null || uuid(source.source_end_run_id)) ||
    !optionalIso(source.reconciled_at) ||
    !(source.reconciliation_run_id === null || uuid(source.reconciliation_run_id)) ||
    !optionalIso(source.baseline_snapshot_at) ||
    !optionalIso(source.next_eligible_at) ||
    !(
      source.blocked_code === null ||
      (typeof source.blocked_code === 'string' && CODE.test(source.blocked_code))
    )
  )
    return null;
  const phase = source.phase as XhsDeliveryProgress['phase'];
  const batchTotal =
    source.backfill_batch_count + source.reconciliation_batch_count + source.incremental_batch_count;
  if (
    batchTotal !== source.batch_count ||
    source.partial_batch_count > source.batch_count ||
    source.cursor_step_count > source.batch_count ||
    source.baseline_snapshot_complete !== (phase === 'incremental') ||
    (source.generation_id !== null) !== source.initialized ||
    (source.source_end_observed_at !== null) !== (source.source_end_run_id !== null) ||
    (source.reconciled_at !== null) !== (source.reconciliation_run_id !== null) ||
    (source.reconciled_at !== null) !== (source.baseline_snapshot_at !== null) ||
    (phase === 'incremental' && source.baseline_snapshot_at === null) ||
    (source.baseline_snapshot_at !== null && !['incremental', 'blocked'].includes(phase)) ||
    (phase === 'blocked') !== (source.blocked_code !== null) ||
    (!source.initialized &&
      (phase !== 'backfill' ||
        source.batch_count !== 0 ||
        source.note_observation_count !== 0 ||
        source.cursor_step_count !== 0 ||
        source.partial_batch_count !== 0 ||
        source.failed_note_count !== 0 ||
        source.last_stop_reason !== null ||
        source.last_delivery_at !== null ||
        source.source_end_observed_at !== null ||
        source.reconciled_at !== null ||
        source.baseline_snapshot_at !== null ||
        source.blocked_code !== null))
  )
    return null;
  return {
    schema_version: 1,
    initialized: source.initialized,
    phase,
    baseline_snapshot_complete: source.baseline_snapshot_complete,
    generation_id: source.generation_id,
    batch_count: source.batch_count,
    note_observation_count: source.note_observation_count,
    cursor_step_count: source.cursor_step_count,
    backfill_batch_count: source.backfill_batch_count,
    reconciliation_batch_count: source.reconciliation_batch_count,
    incremental_batch_count: source.incremental_batch_count,
    partial_batch_count: source.partial_batch_count,
    failed_note_count: source.failed_note_count,
    last_stop_reason: source.last_stop_reason as XhsDeliveryProgress['last_stop_reason'],
    last_delivery_at: source.last_delivery_at,
    source_end_observed_at: source.source_end_observed_at,
    source_end_run_id: source.source_end_run_id,
    reconciled_at: source.reconciled_at,
    reconciliation_run_id: source.reconciliation_run_id,
    baseline_snapshot_at: source.baseline_snapshot_at,
    next_eligible_at: source.next_eligible_at,
    blocked_code: source.blocked_code
  };
}

export function safeXhsDeliveryProgressCard(value: unknown): BiliDeliveryProgressCard {
  const progress = parseXhsDeliveryProgress(value);
  if (!progress) {
    return {
      phase: '证据不可用',
      status: 'unknown',
      notice: '服务端 XHS 投影未通过封闭格式校验；请刷新详情并核对任务日志。',
      rows: [{ label: '增量基线', value: '未声明完成' }]
    };
  }
  const rows = progress.initialized
    ? [
        {
          label: '已交付批次',
          value: `${progress.batch_count} 轮（回填 ${progress.backfill_batch_count} / 对账 ${progress.reconciliation_batch_count} / 增量 ${progress.incremental_batch_count}）`
        },
        { label: '已推进游标页', value: `${progress.cursor_step_count} 步` },
        { label: '已交付笔记观察', value: `${progress.note_observation_count} 条` },
        {
          label: '部分批次 / 最近失败笔记',
          value: `${progress.partial_batch_count} 轮 / ${progress.failed_note_count} 条`
        },
        {
          label: '最近停止原因',
          value: progress.last_stop_reason ? XHS_STOP_REASONS[progress.last_stop_reason] : '—'
        },
        { label: '最近交付', value: displayTime(progress.last_delivery_at) },
        { label: '明确源末页', value: displayTime(progress.source_end_observed_at) },
        { label: '最近稳定头部对账', value: displayTime(progress.reconciled_at) },
        { label: '下次可运行', value: displayTime(progress.next_eligible_at) }
      ]
    : [
        { label: '交付合格批次', value: '尚未产生' },
        { label: '增量基线', value: '未声明完成' },
        { label: '下次可运行', value: displayTime(progress.next_eligible_at) }
      ];
  if (progress.blocked_code) rows.push({ label: '阻塞代码', value: progress.blocked_code });
  return {
    phase: XHS_DELIVERY_PHASE_LABELS[progress.phase],
    status:
      progress.phase === 'incremental'
        ? 'succeeded'
        : progress.phase === 'blocked'
          ? 'failed_retryable'
          : progress.phase === 'reconciling'
            ? 'running'
            : 'queued',
    notice: XHS_DELIVERY_PROGRESS_NOTICE,
    rows
  };
}

function newUuid(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, (item) => item.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function pause(milliseconds: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal.aborted) return resolve();
    const done = (): void => {
      clearTimeout(timer);
      signal.removeEventListener('abort', done);
      resolve();
    };
    const timer = setTimeout(done, milliseconds);
    signal.addEventListener('abort', done, { once: true });
  });
}

export interface SubscriptionDeliveryTransport {
  licenseConfirmed(): boolean;
  start(scope: SubscriptionDeliveryScope, idempotencyKey: string, signal: AbortSignal): Promise<unknown>;
  read(operationId: string, signal: AbortSignal): Promise<unknown>;
}

/** Observe one explicit exact-delivery intent. Aborting observation never claims server rollback. */
export class SubscriptionDeliveryController {
  private view = initialSubscriptionDeliveryView();
  private controller: AbortController | null = null;
  private revision = 0;
  private key = '';
  private disposed = false;

  constructor(
    private transport: SubscriptionDeliveryTransport,
    private publish: (view: SubscriptionDeliveryView) => void,
    private uuidFactory: () => string = newUuid,
    private wait: (milliseconds: number, signal: AbortSignal) => Promise<void> = pause
  ) {}

  get snapshot(): SubscriptionDeliveryView {
    return this.view;
  }

  setScope(scope: SubscriptionDeliveryScope | null): void {
    if (this.disposed) return;
    if (scope && !validSubscriptionDeliveryScope(scope)) scope = null;
    const key = scope
      ? JSON.stringify([
          scope.subscription_id,
          scope.platform,
          scope.expected_schedule_revision,
          scope.session_epoch
        ])
      : '';
    if (key === this.key) return;
    this.stop();
    this.key = key;
    this.view = { ...initialSubscriptionDeliveryView(), scope };
    this.publish(this.view);
  }

  private stop(): void {
    this.revision += 1;
    this.controller?.abort();
    this.controller = null;
  }

  dispose(): void {
    this.stop();
    this.disposed = true;
  }

  async start(): Promise<void> {
    if (this.disposed || !this.view.scope || this.controller) return;
    if (!this.transport.licenseConfirmed()) {
      this.view = { ...this.view, phase: 'not_started', message: DELIVERY_LICENSE_REQUIRED };
      this.publish(this.view);
      return;
    }
    const scope = this.view.scope;
    const idempotencyKey = this.uuidFactory();
    if (!uuid(idempotencyKey)) return;
    const revision = ++this.revision;
    const controller = new AbortController();
    this.controller = controller;
    const current = (): boolean => !this.disposed && revision === this.revision && !controller.signal.aborted;
    const update = (fields: Partial<SubscriptionDeliveryView>): void => {
      if (!current()) return;
      this.view = { ...this.view, ...fields };
      this.publish(this.view);
    };
    update({ phase: 'submitting', operation_id: null, operation: null, message: '' });
    try {
      const started = startedOperation(await this.transport.start(scope, idempotencyKey, controller.signal));
      if (!current()) return;
      if (!started) throw new Error('subscription_delivery_start_invalid');
      update({ phase: 'waiting', operation_id: started.operation_id });
      while (current()) {
        const operation = parseSubscriptionDeliveryOperation(
          await this.transport.read(started.operation_id, controller.signal),
          scope,
          started.operation_id
        );
        if (!current()) return;
        if (!operation) throw new Error('subscription_delivery_operation_invalid');
        update({ operation });
        if (!ACTIVE_STATES.has(operation.state)) {
          const succeeded = operation.state === 'succeeded' && operation.result !== null;
          update({
            phase: succeeded ? 'succeeded' : 'failed',
            message: succeeded
              ? ''
              : subscriptionDeliveryFailure(
                  operation.error_code ??
                    (operation.state === 'cancelled'
                      ? 'subscription_delivery_cancelled'
                      : operation.state === 'interrupted'
                        ? 'subscription_delivery_interrupted'
                        : null)
                )
          });
          return;
        }
        await this.wait(2_000, controller.signal);
      }
    } catch (error) {
      if (!current()) return;
      update({
        phase: this.view.operation_id ? 'wait_ended' : 'failed',
        message: this.view.operation_id ? DELIVERY_OBSERVATION_ENDED : subscriptionDeliveryFailure(error)
      });
    } finally {
      if (this.controller === controller) this.controller = null;
    }
  }
}
