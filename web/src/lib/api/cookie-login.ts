import { ApiError } from './client';
import type { Account, OperationState, Platform, PlatformCapability } from '$lib/types/api';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const SUPPORTED = new Set<Platform>(['bili', 'xhs', 'wb', 'zhihu', 'tieba']);
const ACTIVE = new Set<OperationState>(['queued', 'running']);
const STATES = new Set<OperationState>([
  ...ACTIVE,
  'succeeded',
  'failed_retryable',
  'failed_terminal',
  'cancelled',
  'interrupted'
]);
export const COOKIE_LOGIN_UNKNOWN =
  '本次保存结果未能确认；请关闭弹窗并刷新本地状态、核对任务记录后再操作。未自动重试，不能据此认定原认证未改变。';
export const COOKIE_LOGIN_LICENSE_REQUIRED = '请先完成首次使用与许可证确认，本次未发起 Cookie 校验或保存。';
export const COOKIE_LOGIN_SUCCESS =
  'Cookie 已通过平台认证校验并保存。本结果不代表作者资料查询、内容采集、下载、导出或播放已经成功。';
export const COOKIE_LOGIN_FOLLOW_UP =
  '支持 B 站、小红书、微博、知乎、贴吧；抖音、快手的粘贴 Cookie 校验尚未接入。作者资料查询在订阅页面独立执行；贴吧昵称与可选头像已接入，小红书资料仍待实现。真实平台端到端验收尚未运行。';
const ERRORS: Record<string, string> = {
  cookie_login_request_invalid: '输入或请求格式不符合要求；请使用请求 Cookie 头的值。',
  cookie_login_body_too_large: '输入超出限制；Cookie 最多 16 KiB。',
  cookie_login_content_type_invalid: '请求格式不受支持，请刷新页面。',
  cookie_login_account_not_found: '账户已不存在，请刷新账户列表。',
  cookie_login_conflict: '账户认证修订或平台已变化，请关闭并刷新本地状态。',
  cookie_login_busy: '账户正在执行其他登录或采集操作，请稍后手动处理。',
  cookie_login_unavailable: '此平台的 Cookie 校验或运行环境暂不可用。',
  cookie_login_rejected: '平台未确认此 Cookie 已认证，请在平台重新登录后手动提供有效 Cookie。',
  cookie_login_verification_unavailable: '本次无法取得平台的明确认证证据，请检查运行环境后手动处理。',
  cookie_login_timed_out: '本次服务端校验超时，未自动重试。',
  cookie_login_cancelled: '本次校验已取消；不据此宣称进程清理完成。',
  cookie_login_result_invalid: '校验结果未通过格式或身份检查。',
  cookie_login_cleanup_failed: '验证进程清理未获确认，请检查运行环境。',
  cookie_login_save_failed: '服务端未能确认凭据保存，请核对任务和账户记录。'
};

function object(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}
function uuid(value: unknown): value is string {
  return typeof value === 'string' && value.length === 36 && UUID.test(value);
}
function revision(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;
}
export function safeCookieLoginErrorCode(value: unknown): string | null {
  return typeof value === 'string' && Object.hasOwn(ERRORS, value) ? value : null;
}
export function cookieLoginFailure(value: unknown): string {
  const code = safeCookieLoginErrorCode(value instanceof ApiError ? value.code : value);
  // A save/commit failure can be ambiguous; do not promise rollback.
  return code && code !== 'cookie_login_save_failed'
    ? `${ERRORS[code]} 本次未替换原认证；其他并发操作的结果请刷新核对。`
    : COOKIE_LOGIN_UNKNOWN;
}
export function cookieLoginEligibility(
  account: Account | null,
  capability: PlatformCapability | null
): string {
  if (!account || !uuid(account.id)) return '请先添加或选择一个平台账户。';
  if (!capability || capability.platform !== account.platform || capability.pasted_cookie_login !== true)
    return '此平台尚未开放粘贴 Cookie 校验，或能力信息尚未取得。';
  if (account.adapter !== 'mediacrawler' || !SUPPORTED.has(account.platform))
    return '当前账户或平台尚不支持粘贴 Cookie 校验。';
  if (!revision(account.auth_revision) || account.auth_revision >= Number.MAX_SAFE_INTEGER)
    return '账户认证修订不可用，请刷新本地状态或更新服务端。';
  if (account.auth_status === 'authenticating') return '账户正在登录，请等待结束后再操作。';
  return '';
}
export function cookieInputIssue(value: string): string {
  if (!value.trim()) return '请粘贴请求 Cookie 头的值；本次未发起请求。';
  if (value.length > 16_384) return 'Cookie 最多 16 KiB；本次未发起请求。';
  if (/[^\x20-\x7e]/.test(value))
    return 'Cookie 仅接受单行 ASCII 请求头值，不接受换行或控制字符；本次未发起请求。';
  return '';
}

export interface CookieLoginIdentity {
  account_id: string;
  platform: Platform;
  expected_auth_revision: number;
}
export interface CookieLoginScope extends CookieLoginIdentity {
  frontend_generation: string;
}
export interface CookieLoginResult {
  account_id: string;
  auth_status: 'authenticated';
  login_method: 'cookie';
  auth_revision: number;
}
export interface CookieLoginView {
  scope: CookieLoginScope | null;
  operation_id: string | null;
  phase: 'idle' | 'not_started' | 'submitting' | 'checking' | 'saved' | 'not_saved' | 'unknown';
  result: CookieLoginResult | null;
  message: string;
}
export function initialCookieLoginView(): CookieLoginView {
  return { scope: null, operation_id: null, phase: 'idle', result: null, message: '' };
}

/** Accept only the exact Operation and the atomic expected revision + 1 result. */
export function parseCookieLoginOperation(value: unknown, scope: CookieLoginScope, operationId: string) {
  const source = object(value);
  const target = object(source?.target);
  if (
    !source ||
    !uuid(operationId) ||
    source.id !== operationId ||
    source.kind !== 'account-cookie-login' ||
    !target ||
    target.type !== 'account' ||
    target.id !== scope.account_id ||
    !STATES.has(source.state as OperationState)
  )
    return null;
  const state = source.state as OperationState;
  let result: CookieLoginResult | null = null;
  if (state === 'succeeded') {
    const raw = object(source.result);
    if (
      !raw ||
      Object.keys(raw).sort().join(',') !== 'account_id,auth_revision,auth_status,login_method' ||
      raw.account_id !== scope.account_id ||
      raw.auth_status !== 'authenticated' ||
      raw.login_method !== 'cookie' ||
      !revision(raw.auth_revision) ||
      raw.auth_revision !== scope.expected_auth_revision + 1 ||
      source.error_code !== null
    )
      return null;
    result = {
      account_id: scope.account_id,
      auth_status: 'authenticated',
      login_method: 'cookie',
      auth_revision: raw.auth_revision
    };
  } else if (source.result !== null || (ACTIVE.has(state) && source.error_code !== null)) return null;
  return { state, result, error_code: safeCookieLoginErrorCode(source.error_code) };
}

export interface CookieLoginTransport {
  licenseConfirmed(): boolean;
  session(): { epoch: number; authenticated: boolean };
  start(scope: CookieLoginScope, candidate: string, signal: AbortSignal): Promise<unknown>;
  read(operationId: string, signal: AbortSignal): Promise<unknown>;
}
function newGeneration(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
function pause(signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal.aborted) return resolve();
    const done = (): void => {
      clearTimeout(timer);
      signal.removeEventListener('abort', done);
      resolve();
    };
    const timer = setTimeout(done, 1_500);
    signal.addEventListener('abort', done, { once: true });
  });
}

/** Observable state contains no Cookie, raw errors, or request bodies. No automatic resubmission. */
export class CookieLoginController {
  private view = initialCookieLoginView();
  private key = '';
  private epoch = -1;
  private generation = 0;
  private controller: AbortController | null = null;
  private disposed = false;
  constructor(
    private transport: CookieLoginTransport,
    private publish: (view: CookieLoginView) => void,
    private makeUuid: () => string = newGeneration
  ) {}
  get snapshot(): CookieLoginView {
    return this.view;
  }
  setContext(account: Account | null, capability: PlatformCapability | null, sessionEpoch: number): void {
    if (this.disposed) return;
    const eligible = cookieLoginEligibility(account, capability) === '';
    const key =
      eligible && account
        ? JSON.stringify([account.id, account.platform, account.auth_revision, sessionEpoch])
        : '';
    if (key === this.key) return;
    this.stop();
    this.key = key;
    this.epoch = sessionEpoch;
    this.view = {
      ...initialCookieLoginView(),
      scope:
        eligible && account
          ? {
              account_id: account.id,
              platform: account.platform,
              expected_auth_revision: account.auth_revision,
              frontend_generation: this.makeUuid()
            }
          : null
    };
    this.publish(this.view);
  }
  private stop(): void {
    this.generation += 1;
    this.controller?.abort();
    this.controller = null;
  }
  dispose(): void {
    this.stop();
    this.disposed = true;
    this.key = '';
    this.view = initialCookieLoginView();
  }
  async submit(candidate: string): Promise<void> {
    const session = this.transport.session();
    if (
      this.disposed ||
      !this.view.scope ||
      this.controller ||
      !session.authenticated ||
      session.epoch !== this.epoch ||
      ['saved', 'unknown'].includes(this.view.phase)
    ) {
      candidate = '';
      return;
    }
    const issue = !this.transport.licenseConfirmed()
      ? COOKIE_LOGIN_LICENSE_REQUIRED
      : cookieInputIssue(candidate);
    if (issue) {
      candidate = '';
      this.view = { ...this.view, phase: 'not_started', message: issue };
      this.publish(this.view);
      return;
    }
    const scope = { ...this.view.scope, frontend_generation: this.makeUuid() };
    if (!uuid(scope.frontend_generation)) {
      candidate = '';
      return;
    }
    const generation = ++this.generation;
    const controller = new AbortController();
    this.controller = controller;
    const current = (): boolean => {
      const now = this.transport.session();
      return (
        !this.disposed &&
        generation === this.generation &&
        !controller.signal.aborted &&
        now.authenticated &&
        now.epoch === this.epoch
      );
    };
    const update = (fields: Partial<CookieLoginView>): void => {
      if (current()) {
        this.view = { ...this.view, ...fields };
        this.publish(this.view);
      }
    };
    update({ scope, phase: 'submitting', operation_id: null, result: null, message: '' });
    const expire = (): void => {
      update({ phase: 'unknown', message: COOKIE_LOGIN_UNKNOWN });
      this.stop();
    };
    const deadline = setTimeout(expire, 90_000);
    const clearDeadline = (): void => clearTimeout(deadline);
    controller.signal.addEventListener('abort', clearDeadline, { once: true });
    let accepted = false;
    try {
      let pending: Promise<unknown>;
      try {
        pending = this.transport.start(scope, candidate, controller.signal);
      } finally {
        candidate = '';
      }
      const started = object(await pending);
      if (!current()) return;
      if (!started || !uuid(started.operation_id) || !STATES.has(started.state as OperationState))
        throw new Error('cookie_login_unconfirmed');
      accepted = true;
      const operationId = started.operation_id;
      update({ operation_id: operationId, phase: 'checking' });
      for (let reads = 0; reads < 60; reads += 1) {
        const raw = await this.transport.read(operationId, controller.signal);
        if (!current()) return;
        const response = parseCookieLoginOperation(raw, scope, operationId);
        if (!response) throw new Error('cookie_login_unconfirmed');
        if (response.state === 'succeeded' && response.result) {
          update({ phase: 'saved', result: response.result, message: COOKIE_LOGIN_SUCCESS });
          return;
        }
        if (!ACTIVE.has(response.state)) {
          const message =
            response.state === 'interrupted' ? COOKIE_LOGIN_UNKNOWN : cookieLoginFailure(response.error_code);
          update({ phase: message === COOKIE_LOGIN_UNKNOWN ? 'unknown' : 'not_saved', message });
          return;
        }
        await pause(controller.signal);
        if (!current()) return;
      }
      expire();
    } catch (error) {
      // Losing a read after acceptance never implies that the candidate was rejected.
      const message =
        !accepted && error instanceof ApiError ? cookieLoginFailure(error) : COOKIE_LOGIN_UNKNOWN;
      update({ phase: message === COOKIE_LOGIN_UNKNOWN ? 'unknown' : 'not_saved', message });
    } finally {
      candidate = '';
      clearDeadline();
      controller.signal.removeEventListener('abort', clearDeadline);
      if (this.controller === controller) this.controller = null;
    }
  }
}
