import { ApiError } from '../api/client';
import type {
  Account,
  CreatorIdentity,
  CreatorLookupResponse,
  CreatorLookupScope,
  CreatorProfile,
  OperationState,
  Subscription
} from '$lib/types/api';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const UID = /^[1-9][0-9]{0,19}$/;
function uuid(value: unknown): value is string {
  return typeof value === 'string' && value.length === 36 && UUID.test(value);
}
function validUid(value: unknown): value is string {
  return (
    typeof value === 'string' &&
    value.trim() === value &&
    UID.test(value) &&
    (value.length < 20 || value <= '18446744073709551615')
  );
}
const ACTIVE = new Set<OperationState>(['queued', 'running']);
const STATES = new Set<OperationState>([
  ...ACTIVE,
  'succeeded',
  'failed_retryable',
  'failed_terminal',
  'cancelled',
  'interrupted'
]);
export const CREATOR_LOOKUP_NOTICE =
  '输入完成后自动查询一次 B 站或微博作者资料；支持已认证的保存会话和 Cookie，只查询昵称与头像，不扫码、不采集内容，无需确认全历史采集。其他五个平台的资料查询尚未接入。资料成功不代表内容已抓取或可播放。';
export const CREATOR_LOOKUP_UNAVAILABLE = '暂时无法确认本次作者资料查询结果；未自动重试。';
export const CREATOR_LOOKUP_LICENSE_REQUIRED = '请先完成首次使用与许可证确认，本次未发起查询。';
export const CREATOR_LOOKUP_WAIT_ENDED =
  '本地等待已结束，不能据此认定服务端已停止或查询失败。请到任务页面核对后再手动查询。';

const ERRORS: Record<string, string> = {
  creator_profile_busy: '该账户正被其他操作使用；本次未查询，请结束后手动重试。',
  creator_profile_failed: '本次作者资料查询未成功，未自动重试。',
  creator_profile_unavailable: '作者资料查询环境暂时不可用，请核对诊断后手动处理。',
  creator_profile_invalid: '本次资料未通过格式校验，未应用到订阅。',
  creator_profile_identity_mismatch: '本次查询身份不匹配，请核对账号、平台和作者 UID。',
  creator_profile_auth_changed: '账户认证已变化，本次资料结果未应用，请核对登录状态。',
  creator_profile_superseded: '此查询已被更新的资料请求替代，不使用旧结果创建订阅。',
  creator_profile_lease_lost: '查询执行权已经变化，请到任务页面核对；未自动重试。',
  creator_profile_runner_failed: '作者资料查询进程未正常完成，请查看诊断后手动处理。',
  creator_profile_operation_invalid: '本次查询操作身份无效，未应用到订阅。',
  creator_profile_account_busy: '该账户正被其他操作使用；本次未查询，请结束后手动重试。',
  account_busy: '该账户正被其他操作使用；本次未查询，请结束后手动重试。',
  creator_profile_auth_required: '平台会话需要重新登录。请到账户页面手动处理；本次不会启动扫码。',
  creator_profile_account_ineligible:
    '该账户当前不满足 B 站或微博已认证 Cookie／保存会话查询条件；未启动扫码。',
  creator_profile_unsupported:
    '当前仅支持 B 站和微博已认证 Cookie／保存会话的作者资料查询，其他五个平台尚未接入。',
  creator_profile_not_found: '本次未取得该作者资料，请核对作者 UID。',
  creator_profile_rate_limited: '平台暂时限制查询；未自动重试，请稍后手动处理。',
  creator_profile_timed_out: '本次作者资料查询超过服务端执行期限；没有自动重试。',
  creator_profile_timeout: '本次作者资料查询超过服务端执行期限；没有自动重试。',
  creator_profile_scope_changed: '账户或查询身份已经变化，本次结果未应用，请重新核对。',
  creator_profile_result_invalid: '本次资料未通过身份与格式校验，未应用到订阅。',
  creator_profile_receipt_invalid: '作者资料凭单已经失效，请重新查询或填写本地备注。',
  creator_profile_receipt_expired: '作者资料凭单已过期，请重新查询或填写本地备注。',
  creator_profile_cancelled: '本次查询已取消，不据此宣称进程已清理。',
  operation_already_running: '相同操作正在执行，请到任务页面核对；没有重复提交。',
  account_not_found: '所选账户已不可用，请刷新账户列表。',
  platform_conflict: '账户与作者平台不一致，本次未查询。',
  operator_auth_required: '后台会话已失效，请重新登录；本次结果不再使用。',
  operator_csrf_forbidden: '后台会话已变化，请重新核验；未自动重放查询。',
  license_acknowledgement_required: '请先完成首次使用与许可证确认。',
  mediacrawler_not_enabled: 'MediaCrawler 尚未启用，未查询平台资料。'
};

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function count(value: unknown, minimum = 1): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= minimum;
}

function timestamp(value: unknown): value is string {
  return (
    typeof value === 'string' &&
    value.trim() === value &&
    value.length <= 40 &&
    /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/.test(value) &&
    Number.isFinite(Date.parse(value))
  );
}

export function creatorIdentityMatches(value: CreatorIdentity, identity: CreatorIdentity): boolean {
  return (
    value.account_id === identity.account_id &&
    value.platform === identity.platform &&
    value.creator_remote_id === identity.creator_remote_id
  );
}

export function isCreatorLookupPlatform(value: unknown): value is 'bili' | 'wb' {
  return value === 'bili' || value === 'wb';
}

export function creatorLookupIdentity(account: Account | null, creatorId: string): CreatorIdentity | null {
  const uid = creatorId.trim();
  if (
    !account ||
    !uuid(account.id) ||
    !isCreatorLookupPlatform(account.platform) ||
    account.adapter !== 'mediacrawler' ||
    !['saved_session', 'cookie'].includes(account.login_method ?? '') ||
    account.auth_status !== 'authenticated' ||
    !validUid(uid)
  )
    return null;
  return { account_id: account.id, platform: account.platform, creator_remote_id: uid };
}

export function creatorLookupEligibility(account: Account | null): string {
  if (!account) return '请先选择平台账户。';
  if (!isCreatorLookupPlatform(account.platform))
    return '此平台的远端作者资料查询尚未接入；当前仅支持 B 站和微博，仍可填写本地备注并校验订阅。';
  if (account.adapter !== 'mediacrawler' || !['saved_session', 'cookie'].includes(account.login_method ?? ''))
    return '当前只支持 B 站或微博 MediaCrawler Cookie 凭据或已保存会话；此处不会启动扫码或其他登录方式。';
  if (account.auth_status !== 'authenticated')
    return '账户没有已认证的 Cookie 凭据或保存会话；请到账户页面手动处理登录，此处不会自动扫码。';
  return '';
}

export function creatorLookupFailure(value: unknown): string {
  const code = value instanceof ApiError ? value.code : typeof value === 'string' ? value : null;
  return code && Object.hasOwn(ERRORS, code) ? ERRORS[code] : CREATOR_LOOKUP_UNAVAILABLE;
}

export function safeCreatorAvatarUrl(profile: CreatorProfile): string | null {
  if (profile.avatar_state === 'absent' || !uuid(profile.id) || !count(profile.avatar_revision)) return null;
  const path = `/api/v1/creator-profiles/${profile.id}/avatar/${profile.avatar_revision}`;
  return profile.avatar_url === path ? path : null;
}

export function parseCreatorProfile(value: unknown, identity: CreatorIdentity): CreatorProfile | null {
  const source = record(value);
  if (
    !source ||
    typeof source.id !== 'string' ||
    !uuid(source.id) ||
    !uuid(identity.account_id) ||
    !isCreatorLookupPlatform(identity.platform) ||
    !validUid(identity.creator_remote_id) ||
    !creatorIdentityMatches(source as unknown as CreatorIdentity, identity) ||
    typeof source.nickname !== 'string' ||
    !source.nickname.trim() ||
    Array.from(source.nickname).length > 512 ||
    source.nickname.trim() !== source.nickname ||
    /[\u0000-\u001f\u007f-\u009f]/u.test(source.nickname) ||
    source.profile_url !==
      (identity.platform === 'wb'
        ? `https://weibo.com/u/${identity.creator_remote_id}`
        : `https://space.bilibili.com/${identity.creator_remote_id}`) ||
    !count(source.revision) ||
    !timestamp(source.observed_at) ||
    !count(source.avatar_revision, 0) ||
    !['current', 'retained', 'absent'].includes(String(source.avatar_state))
  )
    return null;
  const profile: CreatorProfile = {
    id: source.id,
    account_id: identity.account_id,
    platform: identity.platform,
    creator_remote_id: identity.creator_remote_id,
    nickname: source.nickname,
    profile_url: source.profile_url as string,
    revision: source.revision,
    observed_at: source.observed_at,
    avatar_revision: source.avatar_revision,
    avatar_observed_at: source.avatar_observed_at as string | null,
    avatar_state: source.avatar_state as CreatorProfile['avatar_state'],
    avatar_url: source.avatar_url as string | null
  };
  if (profile.avatar_state === 'absent') {
    if (profile.avatar_url !== null || profile.avatar_observed_at !== null || profile.avatar_revision !== 0)
      return null;
  } else if (!safeCreatorAvatarUrl(profile) || !timestamp(profile.avatar_observed_at)) return null;
  return profile;
}

export function subscriptionCreatorProfile(subscription: Subscription): CreatorProfile | null {
  return parseCreatorProfile(subscription.creator_profile, subscription);
}

export function creatorAvatarKey(profile: CreatorProfile, contextKey: string): string {
  return JSON.stringify([
    contextKey,
    profile.account_id,
    profile.platform,
    profile.creator_remote_id,
    profile.id,
    profile.avatar_revision,
    safeCreatorAvatarUrl(profile)
  ]);
}

export function creatorAvatarEventMatches(key: string, profile: CreatorProfile, contextKey: string): boolean {
  return key === creatorAvatarKey(profile, contextKey);
}

export function subscriptionCreatorLabel(subscription: Subscription): string {
  return (
    (typeof subscription.local_alias === 'string' ? subscription.local_alias.trim() : '') ||
    subscriptionCreatorProfile(subscription)?.nickname ||
    subscription.creator_display_name ||
    subscription.creator_remote_id
  );
}

export function parseCreatorLookup(
  value: unknown,
  scope: CreatorLookupScope,
  operationId: string,
  generation: number | null
): CreatorLookupResponse | null {
  const source = record(value);
  if (
    !source ||
    !uuid(operationId) ||
    source.operation_id !== operationId ||
    !STATES.has(source.state as OperationState) ||
    (source.error_code !== null && typeof source.error_code !== 'string')
  )
    return null;
  let lookup: CreatorLookupResponse['lookup'] = null;
  if (source.lookup !== null) {
    const entry = record(source.lookup);
    if (
      !entry ||
      !creatorIdentityMatches(entry as unknown as CreatorIdentity, scope) ||
      entry.frontend_generation !== scope.frontend_generation ||
      entry.operation_id !== operationId ||
      !count(entry.generation) ||
      (generation !== null && entry.generation !== generation) ||
      (entry.result_profile_revision !== null && !count(entry.result_profile_revision))
    )
      return null;
    lookup = {
      ...scope,
      operation_id: operationId,
      generation: entry.generation,
      result_profile_revision: entry.result_profile_revision as number | null
    };
  } else if (generation !== null || source.state === 'succeeded') return null;
  let profile: CreatorProfile | null = null;
  if (source.profile !== null) {
    profile = parseCreatorProfile(source.profile, scope);
    if (!lookup || !profile || !['lookup_result', 'previous_success'].includes(String(source.profile_source)))
      return null;
    if (
      source.profile_source === 'lookup_result' &&
      (source.state !== 'succeeded' || lookup.result_profile_revision !== profile.revision)
    )
      return null;
  } else if (source.profile_source !== null) return null;
  if (source.state === 'succeeded' && source.error_code !== null) return null;
  return {
    operation_id: operationId,
    state: source.state as OperationState,
    error_code: source.error_code === null ? null : String(source.error_code),
    lookup,
    profile,
    profile_source: source.profile_source as CreatorLookupResponse['profile_source']
  };
}

export interface CreatorLookupView {
  scope: CreatorLookupScope | null;
  operation_id: string | null;
  generation: number | null;
  phase: 'idle' | 'not_started' | 'submitting' | 'waiting' | 'succeeded' | 'failed' | 'wait_ended';
  profile: CreatorProfile | null;
  profile_source: CreatorLookupResponse['profile_source'];
  receipt: string | null;
  message: string;
}

export function initialCreatorLookupView(): CreatorLookupView {
  return {
    scope: null,
    operation_id: null,
    generation: null,
    phase: 'idle',
    profile: null,
    profile_source: null,
    receipt: null,
    message: ''
  };
}

export interface CreatorLookupTransport {
  licenseConfirmed?(): boolean;
  start(scope: CreatorLookupScope, signal: AbortSignal): Promise<unknown>;
  read(operationId: string, signal: AbortSignal): Promise<unknown>;
}

export function creatorLookupButtonLabel(phase: CreatorLookupView['phase']): string {
  return phase === 'idle' || phase === 'not_started' ? '查询作者资料' : '重新查询';
}

function newGeneration(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('');
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

/** One bounded submit/read lifetime; invalidation only stops local observation, never claims rollback. */
export class CreatorLookupController {
  private view = initialCreatorLookupView();
  private key = '';
  private attempted = false;
  private controller: AbortController | null = null;
  private revision = 0;
  private disposed = false;

  constructor(
    private transport: CreatorLookupTransport,
    private publish: (view: CreatorLookupView) => void,
    private uuid: () => string = newGeneration
  ) {}

  get snapshot(): CreatorLookupView {
    return this.view;
  }

  setIdentity(identity: CreatorIdentity | null, sessionEpoch = 0): void {
    if (this.disposed) return;
    if (
      identity &&
      (!uuid(identity.account_id) ||
        !isCreatorLookupPlatform(identity.platform) ||
        !validUid(identity.creator_remote_id))
    )
      identity = null;
    const key = identity
      ? JSON.stringify([identity.account_id, identity.platform, identity.creator_remote_id, sessionEpoch])
      : '';
    if (key === this.key) return;
    this.stop();
    this.key = key;
    this.attempted = false;
    this.view = {
      ...initialCreatorLookupView(),
      scope: identity
        ? {
            account_id: identity.account_id,
            platform: identity.platform,
            creator_remote_id: identity.creator_remote_id,
            frontend_generation: this.uuid()
          }
        : null
    };
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

  async query(manual = false): Promise<void> {
    if (this.disposed || !this.view.scope || this.controller || (this.attempted && !manual)) return;
    if (this.transport.licenseConfirmed && this.transport.licenseConfirmed() !== true) {
      this.view = {
        ...this.view,
        phase: 'not_started',
        operation_id: null,
        generation: null,
        receipt: null,
        profile_source: this.view.profile ? 'previous_success' : null,
        message: CREATOR_LOOKUP_LICENSE_REQUIRED
      };
      this.publish(this.view);
      return;
    }
    this.attempted = true;
    const scope = manual ? { ...this.view.scope, frontend_generation: this.uuid() } : this.view.scope;
    if (!uuid(scope.frontend_generation)) return;
    const revision = ++this.revision;
    const controller = new AbortController();
    this.controller = controller;
    const current = (): boolean => !this.disposed && this.revision === revision && !controller.signal.aborted;
    const update = (fields: Partial<CreatorLookupView>): void => {
      if (current()) {
        this.view = { ...this.view, ...fields };
        this.publish(this.view);
      }
    };
    update({
      scope,
      operation_id: null,
      generation: null,
      phase: 'submitting',
      receipt: null,
      profile_source: this.view.profile ? 'previous_success' : null,
      message: ''
    });
    const expire = (): void => {
      update({ phase: 'wait_ended', receipt: null, message: CREATOR_LOOKUP_WAIT_ENDED });
      if (current()) this.stop();
    };
    const timer = setTimeout(expire, 75_000);
    const clearDeadline = (): void => clearTimeout(timer);
    controller.signal.addEventListener('abort', clearDeadline, { once: true });
    try {
      const started = record(await this.transport.start(scope, controller.signal));
      if (!current()) return;
      if (
        !started ||
        typeof started.operation_id !== 'string' ||
        !uuid(started.operation_id) ||
        !STATES.has(started.state as OperationState)
      )
        throw new Error('creator_lookup_invalid');
      const operationId = started.operation_id;
      update({ operation_id: operationId, phase: 'waiting' });
      let generation: number | null = null;
      for (let reads = 0; reads < 50; reads += 1) {
        const raw = await this.transport.read(operationId, controller.signal);
        if (!current()) return;
        const result = parseCreatorLookup(raw, scope, operationId, generation);
        if (!result) throw new Error('creator_lookup_invalid');
        generation = result.lookup?.generation ?? null;
        update({ generation });
        if (result.profile) update({ profile: result.profile, profile_source: result.profile_source });
        if (!ACTIVE.has(result.state)) {
          const succeeded =
            result.state === 'succeeded' && result.profile_source === 'lookup_result' && !!result.profile;
          update({
            phase: succeeded ? 'succeeded' : 'failed',
            receipt: succeeded ? operationId : null,
            message: succeeded ? '' : creatorLookupFailure(result.error_code)
          });
          return;
        }
        await pause(1_500, controller.signal);
        if (!current()) return;
      }
      expire();
    } catch (error) {
      update({ phase: 'failed', receipt: null, message: creatorLookupFailure(error) });
    } finally {
      clearTimeout(timer);
      controller.signal.removeEventListener('abort', clearDeadline);
      if (this.controller === controller) this.controller = null;
    }
  }
}
