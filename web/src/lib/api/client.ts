const ERROR_MESSAGES: Record<string, string> = {
  account_not_found: '所选账户不存在或已失效。',
  account_exists_with_different_configuration: '同名账户已存在，但登录配置不同。',
  account_login_configuration_invalid: '登录运行环境未就绪，请先查看诊断。',
  account_login_unexpected: '登录进程异常结束，请查看诊断后重试。',
  browser_launch_failed: 'Chromium 无法启动，请检查容器浏览器环境。',
  checkout_invalid: 'MediaCrawler checkout 未通过资格检查。',
  creator_display_name_invalid: '作者显示名称无效。',
  creator_remote_id_must_be_stable_id: '作者标识必须是不含 URL 参数或秘密信息的稳定 ID。',
  creator_secret_ref_not_supported: '所选平台不接受作者权限引用。',
  creator_secret_ref_only_for_mediacrawler: '作者权限引用仅适用于 MediaCrawler 账户。',
  database_operation_failed: '数据库操作失败，请稍后重试。',
  export_failed: '媒体库导出失败。',
  full_history_acknowledgement_required: '所选平台需要明确确认首次全历史采集。',
  invalid_creator_secret_reference: '作者权限引用格式无效，请使用受支持的不透明引用。',
  license_acknowledgement_required: '需要先完成首次使用确认。',
  license_digest_mismatch: 'MediaCrawler 许可证摘要与锁定版本不一致。',
  license_requires_enable_mediacrawler: '许可证确认与 MediaCrawler 启用状态不一致。',
  library_author_not_found: '作者不存在或已失效。',
  library_cursor_invalid: '媒体树分页游标无效，请重新开始检查。',
  library_cursor_stale: '发布版本已经变化，请重新开始检查。',
  library_inspection_busy: '另一项媒体树检查正在进行，请稍后重试。',
  library_inspection_failed: '媒体树检查暂时不可用。',
  library_inspection_invalid: '媒体树检查请求无效。',
  library_publication_inconsistent: '数据库发布记录与受管媒体树不一致。',
  login_qr_not_available: '二维码尚未生成。',
  mediacrawler_not_enabled: 'MediaCrawler 尚未启用。',
  media_server_address_forbidden: '媒体服务器地址不在已配置的允许网络中。',
  media_server_authentication_failed: '媒体服务器拒绝了已配置凭据。',
  media_server_library_ambiguous: '媒体服务器返回了重复的 Library 身份。',
  media_server_library_not_found: '媒体服务器中找不到已配置的 Library。',
  media_server_library_path_mismatch: '媒体服务器 Library 路径与固定映射不一致。',
  media_server_not_configured: '尚未配置媒体服务器。',
  media_server_operations_disabled: '媒体服务器操作门尚未开启。',
  media_server_scan_acceptance_unknown: '刷新请求是否被服务器接受无法确认；请人工核对，勿自动重试。',
  media_server_scan_rejected: '媒体服务器拒绝了定向刷新请求。',
  media_server_targeted_scan_unsupported: '服务器不支持定向 Library 刷新，且不会回退到全库刷新。',
  media_server_timeout: '媒体服务器请求超时。',
  media_server_transport: '无法安全连接媒体服务器。',
  operation_already_running: '相同操作正在运行，请等待完成。',
  platform_conflict: '账户平台与作者平台不一致。',
  request_validation_failed: '请求字段格式无效，请检查后重试。',
  scheduler_operation_rejected: '调度操作被拒绝，请刷新状态后重试。',
  subscription_exists_with_different_options: '该账户与作者的订阅已存在，但同步策略不同。',
  subscription_options_invalid: '订阅频率、上限或运行策略无效。',
  tracked_blob_mismatch: 'MediaCrawler 必需文件与锁定提交不一致。',
  worktree_dirty: 'MediaCrawler 工作树存在修改或未跟踪文件。'
};

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly payload: unknown;

  constructor(status: number, code: string, payload: unknown) {
    super(ERROR_MESSAGES[code] ?? code.replaceAll('_', ' '));
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.payload = payload;
  }
}

export type LatestRequestResult<T> =
  | { status: 'fulfilled'; value: T }
  | { status: 'rejected'; reason: unknown }
  | { status: 'superseded' };

export type IdleRequestResult<T> = LatestRequestResult<T> | { status: 'busy' };

export class LatestRequestGate {
  private generation = 0;
  private controller: AbortController | null = null;

  async run<T>(request: (signal: AbortSignal) => Promise<T>): Promise<LatestRequestResult<T>> {
    this.controller?.abort();
    const generation = ++this.generation;
    const controller = new AbortController();
    this.controller = controller;

    try {
      const value = await request(controller.signal);
      return generation === this.generation ? { status: 'fulfilled', value } : { status: 'superseded' };
    } catch (reason) {
      return generation === this.generation ? { status: 'rejected', reason } : { status: 'superseded' };
    } finally {
      if (generation === this.generation && this.controller === controller) this.controller = null;
    }
  }

  runIfIdle<T>(request: (signal: AbortSignal) => Promise<T>): Promise<IdleRequestResult<T>> {
    if (this.controller !== null) return Promise.resolve({ status: 'busy' });
    return this.run(request);
  }

  cancel(): void {
    this.generation += 1;
    this.controller?.abort();
    this.controller = null;
  }
}

function errorCode(payload: unknown, status: number): string {
  if (payload && typeof payload === 'object') {
    const body = payload as Record<string, unknown>;
    if (typeof body.detail === 'string') return body.detail;
    if (body.error && typeof body.error === 'object') {
      const code = (body.error as Record<string, unknown>).code;
      if (typeof code === 'string') return code;
    }
  }
  return `http_${status}`;
}

export async function api<T>(path: string, init: RequestInit = {}, timeoutMs = 20_000): Promise<T> {
  const controller = new AbortController();
  const callerSignal = init.signal;
  const abortFromCaller = (): void => controller.abort();
  if (callerSignal?.aborted) abortFromCaller();
  else callerSignal?.addEventListener('abort', abortFromCaller, { once: true });
  let timedOut = false;
  const timeout = window.setTimeout(() => {
    if (controller.signal.aborted) return;
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  try {
    const response = await fetch(path, {
      ...init,
      cache: 'no-store',
      credentials: 'same-origin',
      headers: {
        Accept: 'application/json',
        ...(init.body ? { 'Content-Type': 'application/json' } : {}),
        ...init.headers
      },
      signal: controller.signal
    });
    const contentType = response.headers.get('content-type') ?? '';
    const payload: unknown = contentType.includes('application/json')
      ? await response.json()
      : await response.text();
    if (!response.ok) throw new ApiError(response.status, errorCode(payload, response.status), payload);
    return payload as T;
  } catch (error) {
    if (timedOut && error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError(408, 'request_timeout', null);
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
    callerSignal?.removeEventListener('abort', abortFromCaller);
  }
}

export function apiMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return '操作失败，请稍后重试。';
}
