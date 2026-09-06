import { api, ApiError, LatestRequestGate } from './client';
import type { Platform } from '../types/api';

export const OUTPUT_PLATFORMS: Platform[] = ['bili', 'xhs', 'dy', 'ks', 'wb', 'tieba', 'zhihu'];
export interface OutputDraft {
  shared_root: string;
  layout: 'platform_subdirectories' | 'legacy_flat';
  platform_overrides: Record<Platform, string | null>;
}
export interface OutputPolicy extends OutputDraft {
  revision: number;
  initialized: boolean;
  effective_roots: Record<Platform, string>;
  protected_platforms: Platform[];
}
export interface OutputView {
  policy: OutputPolicy | null;
  draft: OutputDraft | null;
  preview: OutputPolicy | null;
  busy: boolean;
  error: string;
  notice: string;
}

const failures: Record<string, string> = {
  output_directory_invalid: '请输入容器内的绝对目录路径，不可使用根目录、相对路径或网址。',
  output_directory_unsafe: '目录包含链接、非目录节点或与程序私有目录冲突，请选择独立媒体目录。',
  output_directory_overlap: '平台生效目录不能互相包含或重叠；请调整覆盖路径。',
  output_directory_conflict: '设置已被其他操作修改。草稿已保留；请重新加载最新设置后核对，不会自动覆盖。',
  output_directory_migration_required:
    '受保护平台已有输出或写入绑定，不能直接改目录。请保留原路径；文件迁移尚未提供。',
  output_directory_unavailable: '目录配置暂时无法读取或验证，请检查存储及数据库后手动重试。',
  operator_auth_required: '后台会话已失效，请重新登录后手动重试。',
  operator_csrf_forbidden: '会话已变化，请重新核验后手动重试；未自动重放保存。'
};

export function outputFailure(error: unknown): string {
  const code = error instanceof ApiError ? error.code : '';
  const payload = error instanceof ApiError ? error.payload : null;
  const affected =
    payload && typeof payload === 'object' && 'platforms' in payload
      ? (payload as { platforms: unknown }).platforms
      : null;
  const platforms = Array.isArray(affected)
    ? OUTPUT_PLATFORMS.filter((platform) => affected.includes(platform))
    : [];
  return (
    (failures[code] ?? '目录操作未确认成功，请重新加载核对；不会自动重试或显示服务器原始异常。') +
    (platforms.length ? ` 受影响平台：${platforms.join('、')}。` : '')
  );
}

function copyDraft(policy: OutputDraft): OutputDraft {
  return {
    shared_root: policy.shared_root,
    layout: policy.layout,
    platform_overrides: { ...policy.platform_overrides }
  };
}

/** Server authority only. Explicit preview/save, no replay after stale or failed requests. */
export class OutputDirectoryController {
  view: OutputView = { policy: null, draft: null, preview: null, busy: false, error: '', notice: '' };
  private gate = new LatestRequestGate();

  constructor(
    private publish: (view: OutputView) => void,
    private request: typeof api = api
  ) {}

  private emit(changes: Partial<OutputView>): void {
    this.view = { ...this.view, ...changes };
    this.publish(this.view);
  }

  edit(draft: OutputDraft): void {
    if (this.view.busy) return;
    this.emit({ draft: copyDraft(draft), preview: null, error: '', notice: '' });
  }

  async load(): Promise<void> {
    if (this.view.busy) return;
    this.emit({ busy: true, error: '', notice: '', preview: null });
    const result = await this.gate.run((signal) =>
      this.request<OutputPolicy>('/api/v1/settings/output', { signal })
    );
    if (result.status === 'superseded') return;
    if (result.status === 'fulfilled') {
      this.emit({ busy: false, policy: result.value, draft: copyDraft(result.value) });
    } else this.emit({ busy: false, error: outputFailure(result.reason) });
  }

  async preview(): Promise<void> {
    if (this.view.busy || !this.view.draft || !this.view.policy) return;
    const revision = this.view.policy.revision;
    const body = copyDraft(this.view.draft);
    this.emit({ busy: true, preview: null, error: '', notice: '' });
    const result = await this.gate.run((signal) =>
      this.request<OutputPolicy>('/api/v1/settings/output/preview', {
        method: 'POST',
        body: JSON.stringify(body),
        signal
      })
    );
    if (result.status === 'superseded') return;
    if (result.status === 'fulfilled' && result.value.revision === revision) {
      this.emit({ busy: false, preview: result.value, notice: '预览通过，尚未保存；未创建或搬动文件。' });
    } else
      this.emit({
        busy: false,
        error: outputFailure(
          result.status === 'rejected' ? result.reason : new ApiError(409, 'output_directory_conflict', null)
        )
      });
  }

  async save(): Promise<void> {
    if (this.view.busy || !this.view.preview || !this.view.draft || !this.view.policy) return;
    const body = { ...copyDraft(this.view.draft), expected_revision: this.view.policy.revision };
    this.emit({ busy: true, preview: null, error: '', notice: '' });
    const result = await this.gate.run((signal) =>
      this.request<OutputPolicy>('/api/v1/settings/output', {
        method: 'PUT',
        body: JSON.stringify(body),
        signal
      })
    );
    if (result.status === 'superseded') return;
    if (result.status === 'fulfilled') {
      this.emit({
        busy: false,
        policy: result.value,
        draft: copyDraft(result.value),
        notice: '目录设置已保存。新任务使用此配置；未创建、迁移或删除任何文件。'
      });
    } else this.emit({ busy: false, error: outputFailure(result.reason) });
  }

  dispose(): void {
    this.gate.cancel();
  }
}
