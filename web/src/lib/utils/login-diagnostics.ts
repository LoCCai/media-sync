import type { LoginDiagnostic, LoginStatus, Operation, OperationState } from '$lib/types/api';
import {
  LOGIN_RUNNER_STATUSES,
  operationIsActive,
  operationIsTerminal,
  safeOperationResult
} from './operations';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const ERROR_CODES = new Set([
  'operation_login_failed',
  'operation_login_expired',
  'operation_login_browser_launch_failed',
  'operation_interrupted',
  'account_login_busy',
  'account_login_configuration_invalid',
  'account_login_start_failed',
  'account_login_result_invalid',
  'account_login_conflict',
  'account_login_unexpected'
]);

export interface LoginExplanation {
  tone: 'success' | 'warning' | 'danger' | 'info';
  title: string;
  detail: string;
  next: string;
}

export const LOGIN_READINESS_NOTICE = '预检通过只表示可以启动登录，不代表已经登录或通过真人验收。';
export const LOGIN_STATUS_UNAVAILABLE = '暂时无法读取最近登录结果，请刷新确认；不会据此判定认证成功。';

export function isLoginId(value: unknown): value is string {
  return typeof value === 'string' && UUID.test(value);
}

function object(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

export function safeLoginDiagnostic(status: LoginStatus, accountId: string): LoginDiagnostic | null {
  const source = object(status.diagnostic);
  if (
    status.account_id !== accountId ||
    !isLoginId(accountId) ||
    !isLoginId(status.login_session_id) ||
    !['succeeded', 'expired', 'failed', 'cancelled'].includes(status.login_session_status ?? '') ||
    !source ||
    !isLoginId(source.operation_id) ||
    typeof source.operation_state !== 'string' ||
    !operationIsTerminal(source.operation_state as OperationState) ||
    typeof source.runner_status !== 'string' ||
    !LOGIN_RUNNER_STATUSES.has(source.runner_status) ||
    (source.error_code !== null &&
      (typeof source.error_code !== 'string' || !ERROR_CODES.has(source.error_code))) ||
    ['succeeded', 'cancelled'].includes(source.operation_state) !== (source.error_code === null)
  ) {
    return null;
  }
  const authenticated = source.runner_status === 'authenticated';
  const cancelled = source.runner_status === 'cancelled';
  const expired = source.runner_status === 'expired' || source.runner_status === 'timed_out';
  const expectedOperationState = authenticated ? 'succeeded' : cancelled ? 'cancelled' : 'failed_terminal';
  const expectedSessionState = authenticated
    ? 'succeeded'
    : cancelled
      ? 'cancelled'
      : expired
        ? 'expired'
        : 'failed';
  const expectedError =
    authenticated || cancelled
      ? null
      : expired
        ? 'operation_login_expired'
        : source.runner_status === 'browser_launch_failed'
          ? 'operation_login_browser_launch_failed'
          : 'operation_login_failed';
  if (
    source.operation_state !== expectedOperationState ||
    status.login_session_status !== expectedSessionState ||
    source.error_code !== expectedError
  ) {
    return null;
  }
  return {
    operation_id: source.operation_id,
    operation_state: source.operation_state as OperationState,
    runner_status: source.runner_status as LoginDiagnostic['runner_status'],
    error_code: source.error_code as string | null
  };
}

/** The current tracked operation is authority; account-wide latest status is never a QR selector. */
export function trackedLoginOperation(
  value: unknown,
  accountId: string,
  operationId: string
): Operation | null {
  const operation = object(value);
  const target = object(operation?.target);
  if (
    !isLoginId(accountId) ||
    !isLoginId(operationId) ||
    operation?.id !== operationId ||
    operation.kind !== 'account-login' ||
    target?.type !== 'account' ||
    target.id !== accountId ||
    typeof operation.state !== 'string' ||
    (!operationIsActive(operation.state as OperationState) &&
      !operationIsTerminal(operation.state as OperationState))
  ) {
    return null;
  }
  return operation as unknown as Operation;
}

export function operationLoginSession(operation: Operation): string | null {
  if (!Array.isArray(operation.subjects)) return null;
  const subjects = operation.subjects.map(object).filter((item) => item?.role === 'execution');
  return subjects.length === 1 && subjects[0]?.type === 'login_session' && isLoginId(subjects[0].id)
    ? subjects[0].id
    : null;
}

function explanation(
  state: string,
  runner: string | null,
  code: string | null,
  authenticated: boolean
): LoginExplanation {
  if (state === 'succeeded') {
    return authenticated
      ? {
          tone: 'success',
          title: '登录成功',
          detail: '本次操作已确认账户认证成功。',
          next: '可继续配置作者订阅。'
        }
      : {
          tone: 'warning',
          title: '操作已完成，认证结果待确认',
          detail: '未取得完整的认证成功摘要，不据此判定已经登录。',
          next: '刷新账户状态并查看任务记录，勿重复提交登录。'
        };
  }
  if (state === 'cancelled') {
    return {
      tone: 'info',
      title: '登录已取消',
      detail: '本次登录已结束。',
      next: '需要登录时，请重新预检并手动启动。'
    };
  }
  if (state === 'interrupted') {
    return {
      tone: 'warning',
      title: '登录已中断',
      detail: '操作未能完成，当前记录不能确认登录成功。',
      next: '核对服务运行状态和任务记录，再重新预检；不会自动重试登录。'
    };
  }
  if (operationIsActive(state as OperationState)) {
    return {
      tone: 'info',
      title: '登录进行中',
      detail: '正在等待本次登录操作完成。',
      next: '如出现二维码，请使用对应平台 App 扫码。'
    };
  }
  if (runner === 'browser_launch_failed' || code === 'operation_login_browser_launch_failed') {
    return {
      tone: 'danger',
      title: '登录浏览器启动失败',
      detail: '本次浏览器启动或持久化浏览器初始化未能完成。',
      next: '检查当前镜像的浏览器依赖、缓存目录和 Xvfb；重新预检通过后再手动启动。'
    };
  }
  if (
    runner === 'timed_out' ||
    runner === 'expired' ||
    code === 'operation_login_expired' ||
    state === 'expired'
  ) {
    return {
      tone: 'warning',
      title: runner === 'timed_out' ? '登录等待超时' : '登录会话已过期',
      detail: '本次登录未能在会话有效期内完成。',
      next: '确认平台 App 可用后重新预检，再手动生成新二维码。'
    };
  }
  if (runner === 'configuration_invalid' || code === 'account_login_configuration_invalid') {
    return {
      tone: 'danger',
      title: '登录环境配置未就绪',
      detail: '本次登录未满足运行配置要求。',
      next: '查看诊断页面的运行时、锁定源码及目录检查，修复后重新预检。'
    };
  }
  if (runner === 'start_failed' || code === 'account_login_start_failed') {
    return {
      tone: 'danger',
      title: '登录进程未能启动',
      detail: '未能启动本次登录子进程。',
      next: '检查容器运行时和进程权限，查看任务记录后重新预检。'
    };
  }
  if (runner === 'result_invalid' || code === 'account_login_result_invalid') {
    return {
      tone: 'danger',
      title: '登录结果无法确认',
      detail: '本次进程没有返回可验证的登录结果。',
      next: '先检查任务和服务状态；不要把不完整结果当作认证成功。'
    };
  }
  if (runner === 'account_busy' || code === 'account_login_busy' || code === 'account_login_conflict') {
    return {
      tone: 'warning',
      title: '账户登录存在冲突',
      detail: '账户可能仍由另一项操作占用，本次没有确认登录成功。',
      next: '先查看现有任务，等待其结束后重新预检，勿重复启动。'
    };
  }
  return {
    tone: 'danger',
    title: '最近登录失败',
    detail: '未保存更细诊断，不能判断为浏览器、网络或平台凭据问题。',
    next: '查看任务记录及当前运行环境，重新预检后由你手动重试；不会自动发起登录。'
  };
}

export function accountLoginExplanation(
  status: LoginStatus | null,
  accountId: string
): LoginExplanation | null {
  if (!status || status.account_id !== accountId) return null;
  const diagnostic = safeLoginDiagnostic(status, accountId);
  if (diagnostic) {
    return explanation(
      diagnostic.operation_state,
      diagnostic.runner_status,
      diagnostic.error_code,
      status.auth_status === 'authenticated' &&
        status.login_session_status === 'succeeded' &&
        diagnostic.runner_status === 'authenticated'
    );
  }
  if (['pending', 'waiting_user', 'running'].includes(status.login_session_status ?? ''))
    return explanation('running', null, null, false);
  if (status.login_session_status === 'failed' || status.auth_status === 'failed')
    return explanation('failed', null, null, false);
  if (status.login_session_status === 'cancelled') return explanation('cancelled', null, null, false);
  if (status.login_session_status === 'expired' || status.auth_status === 'expired')
    return explanation('expired', null, null, false);
  if (status.auth_status === 'authenticated') return explanation('succeeded', 'authenticated', null, true);
  return null;
}

export function operationLoginExplanation(operation: Operation): LoginExplanation {
  const summary = safeOperationResult(operation);
  const sessionId = operationLoginSession(operation);
  const linked =
    sessionId !== null &&
    summary !== null &&
    summary?.account_id === operation.target?.id &&
    summary.login_session_id === sessionId;
  const runner = linked && typeof summary?.runner_status === 'string' ? summary.runner_status : null;
  const code =
    typeof operation.error_code === 'string' && ERROR_CODES.has(operation.error_code)
      ? operation.error_code
      : null;
  return explanation(
    operation.state,
    runner,
    code,
    linked &&
      runner === 'authenticated' &&
      summary?.auth_status === 'authenticated' &&
      summary.login_session_status === 'succeeded'
  );
}
