import type { Job } from '$lib/types/api';

const ERROR_STATES = new Set([
  'failed_retryable',
  'failed_terminal',
  'retry_wait',
  'waiting_auth',
  'waiting_user',
  'fenced'
]);
const JOB_STATES = new Set([
  'queued',
  'claimed',
  'running',
  'retry_wait',
  'waiting_auth',
  'waiting_user',
  'succeeded',
  'failed_retryable',
  'failed_terminal',
  'cancelled',
  'fenced'
]);
const PLATFORMS = new Set(['bili', 'xhs', 'dy', 'ks', 'wb', 'tieba', 'zhihu']);
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const TIMESTAMP = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/;

interface Explanation {
  title: string;
  detail: string;
  next: string;
}

// Exact classify_failure vocabulary, not arbitrary stable-looking error strings.
const EXPLANATIONS: Record<string, Explanation> = {
  bili_dynamic_unsupported: {
    title: '动态包含暂不支持的内容',
    detail: '正文或媒体包含尚未实现的组件；未把不完整内容当成功，待处理断点保留。',
    next: '暂停此订阅并导出安全诊断给开发者；可在任务空闲后改为仅投稿，不要连续重试。'
  },
  bili_dynamic_identity_mismatch: {
    title: '动态身份或内容版本发生变化',
    detail: '详情与待处理快照的作者、动态编号、类型或时间不一致；未推进该断点。',
    next: '保留诊断与私密快照供本地排查，不要删除数据库或把原始 Cookie 发给开发者。'
  },
  bili_dynamic_schema_invalid: {
    title: '动态详情格式未通过校验',
    detail: '返回结构或媒体身份不满足当前支持合同；不代表登录成功或采集成功。',
    next: '提供安全诊断和版本号给开发者；原始正文、图片地址和凭据不包含在诊断中。'
  },
  scheduler_heartbeat_failed: {
    title: '调度心跳维护失败',
    detail: '任务执行期间的调度心跳维护未能完成；这不说明平台凭据失效或网络故障。',
    next: '核对当前服务诊断与本 Job 的持久状态，再决定是否人工重试；不要仅凭 Worker 完成判断采集成功。'
  },
  scheduler_heartbeat_storage_busy: {
    title: '调度心跳写入遇到存储忙',
    detail: '心跳写入遇到已识别的 SQLite 忙或锁定状态；这不等于数据库损坏，也不证明平台凭据无效。',
    next: '检查数据库并发占用及服务状态，先核对已保存的任务结果；不要删除数据库或盲目重复采集。'
  },
  scheduler_finalize_failed: {
    title: '任务结果收尾失败',
    detail: '调度任务的结果收尾阶段未能完成；不能据此推断此前抓取阶段是否成功。',
    next: '核对本 Job、关联运行及已有内容的持久记录，再决定后续操作，避免重复处理。'
  },
  schema_invalid: {
    title: '任务失败阶段未明确',
    detail:
      '该通用码可能来自内部检查，也可能来自旧版心跳或收尾兜底；仅凭此记录不能确定失败阶段或 Cookie／网络问题。',
    next: '保留现有记录，核对服务版本和安全诊断；不要按这个历史错误码替换凭据或直接重试。'
  },
  content_ownership_conflict: {
    title: '内容归属冲突',
    detail:
      '本次来源与已保存内容的作者归属冲突；原内容仍归原作者，冲突写入已拒绝。本任务不会自动重试，也不会因此触发账户熔断。',
    next: '保留现有记录，检查订阅与内容来源是否匹配；该错误不表示凭据失效。'
  },
  configuration_invalid: {
    title: '任务配置检查未通过',
    detail: '任务记录表明运行配置未满足要求，尚无更具体的阶段证据。',
    next: '检查订阅配置、平台能力及当前服务诊断，修复后再决定是否重试。'
  },
  handler_unsupported: {
    title: '当前处理器不支持此任务',
    detail: '任务处理器未提供本次请求所需的能力。',
    next: '核对平台能力与任务类型，不要通过重复提交绕过能力限制。'
  },
  output_security_failed: {
    title: '任务输出安全检查未通过',
    detail: '本次输出未通过受管安全校验，不能视为已完成采集。',
    next: '检查服务版本与受管目录，不要绕过安全检查或直接发布未验证输出。'
  },
  unexpected_handler_failure: {
    title: '任务处理异常',
    detail: '已保存的固定码未提供更细的阶段诊断，不能据此推断平台凭据或网络问题。',
    next: '查看本 Job 的状态和当前服务诊断，先核对已有结果，再决定后续操作。'
  },
  rate_limited: {
    title: '任务记录为限流状态',
    detail: '本次任务报告限流，尚未完成采集。',
    next: '查看任务可运行时间及订阅频率，避免连续手动触发。'
  },
  risk_controlled: {
    title: '任务记录为平台风控状态',
    detail: '本次任务报告平台风控限制，不能视为采集成功。',
    next: '查看平台提示与任务状态，不要通过连续重试绕过限制。'
  },
  temporary_upstream: {
    title: '任务报告上游暂时异常',
    detail: '本次任务报告暂时性上游异常，未保存更细的原因。',
    next: '查看任务重试安排和当前服务状态，避免重复启动。'
  },
  upstream_timeout: {
    title: '任务报告上游等待超时',
    detail: '任务记录为上游等待超时；这不证明凭据无效。',
    next: '检查任务状态与运行环境，再决定是否等待既有重试安排。'
  },
  upstream_unavailable: {
    title: '任务报告上游暂不可用',
    detail: '本次任务未能取得可用的上游响应。',
    next: '查看服务诊断及任务重试安排，不要连续重复提交。'
  },
  account_busy: {
    title: '任务等待账户使用权',
    detail: '该任务报告账户正在被其他执行使用。',
    next: '查看现有账户任务并等待其结束，勿重复启动登录或采集。'
  },
  auth_expired: {
    title: '任务需要重新确认认证',
    detail: '该任务报告认证已过期；本条错误码不是对当前 Cookie 的实时验证。',
    next: '前往账户页核对已保存状态，并由你决定是否重新认证。'
  },
  credentials_unavailable: {
    title: '任务无法取得所需凭据',
    detail: '任务未取得可用的凭据配置；这不等于已经证明 Cookie 无效。',
    next: '核对账户配置与服务的凭据读取条件，不要把秘密内容贴入任务记录。'
  },
  captcha_required: {
    title: '任务等待平台验证',
    detail: '任务报告需要人工完成平台验证。',
    next: '查看对应平台的人工验证要求；页面不会自动代做验证或重试。'
  },
  interactive_required: {
    title: '任务等待人工交互',
    detail: '当前任务需要人工处理平台交互。',
    next: '检查账户及平台提示后再决定下一步，不要连续重试。'
  },
  license_acknowledgement_required: {
    title: '任务等待许可证确认',
    detail: '本次任务未满足明确的许可证确认条件。',
    next: '先阅读并自行决定是否接受对应许可证；错误展示不会替你接受。'
  },
  qr_required: {
    title: '任务需要人工扫码',
    detail: '任务报告需要人工扫码认证，尚未完成采集。',
    next: '前往账户页核对登录条件，再由你手动决定是否启动扫码。'
  }
};

export interface SchedulerJobDiagnostic extends Explanation {
  code: string | null;
  tone: 'danger' | 'warning';
}

export function isSchedulerJobId(value: unknown): value is string {
  return typeof value === 'string' && UUID.test(value);
}

export function schedulerJobErrorCode(job: Job): string | null {
  return ERROR_STATES.has(job.status) &&
    typeof job.last_error_code === 'string' &&
    Object.hasOwn(EXPLANATIONS, job.last_error_code)
    ? job.last_error_code
    : null;
}

export function schedulerJobDiagnostic(
  job: Job,
  expectedJobId: string = job.job_id
): SchedulerJobDiagnostic | null {
  if (!isSchedulerJobId(expectedJobId) || job.job_id !== expectedJobId || !ERROR_STATES.has(job.status))
    return null;
  const code = schedulerJobErrorCode(job);
  const explanation = code
    ? EXPLANATIONS[code]
    : {
        title: '未保存更细诊断',
        detail: '本 Job 的安全错误码不可用，或旧接口未提供该字段；不能据此判断失败阶段或平台凭据状态。',
        next: '刷新本 Job 的详情并核对当前服务诊断；不要把 Worker 完成视为采集成功。'
      };
  return { ...explanation, code, tone: job.status.startsWith('failed_') ? 'danger' : 'warning' };
}

/** Preserve only the pre-existing Job fields and the sanitized additive code. */
export function schedulerJobDetailRows(job: Job): Array<{ key: string; value: string | number | null }> {
  const keys = [
    'job_id',
    'subscription_id',
    'account_id',
    'platform',
    'status',
    'attempt',
    'max_attempts',
    'available_at',
    'scheduled_for',
    'run_id',
    'created_at',
    'updated_at',
    'started_at',
    'finished_at'
  ] as const;
  const rows = keys.map((key) => {
    const raw: unknown = job[key];
    let value: string | number | null = null;
    if (key.endsWith('_id')) value = isSchedulerJobId(raw) ? raw : null;
    else if (key === 'status') value = typeof raw === 'string' && JOB_STATES.has(raw) ? raw : null;
    else if (key === 'platform') value = typeof raw === 'string' && PLATFORMS.has(raw) ? raw : null;
    else if (key === 'attempt' || key === 'max_attempts')
      value = typeof raw === 'number' && Number.isSafeInteger(raw) && raw >= 0 ? raw : null;
    else
      value = typeof raw === 'string' && TIMESTAMP.test(raw) && Number.isFinite(Date.parse(raw)) ? raw : null;
    return { key: key as string, value };
  });
  return [...rows, { key: 'last_error_code', value: schedulerJobErrorCode(job) }];
}
