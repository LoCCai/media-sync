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
  login_qr_not_available: '二维码尚未生成。',
  mediacrawler_not_enabled: 'MediaCrawler 尚未启用。',
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
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
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
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError(408, 'request_timeout', null);
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}

export function apiMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return '操作失败，请稍后重试。';
}
