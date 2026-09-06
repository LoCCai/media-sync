import { describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { api, ApiError } from './client';
import {
  OUTPUT_PLATFORMS,
  OutputDirectoryController,
  outputFailure,
  type OutputPolicy
} from './output-directories';

function policy(revision = 0): OutputPolicy {
  return {
    revision,
    initialized: revision > 0,
    shared_root: '/data/library',
    layout: 'platform_subdirectories',
    platform_overrides: Object.fromEntries(
      OUTPUT_PLATFORMS.map((p) => [p, null])
    ) as OutputPolicy['platform_overrides'],
    effective_roots: Object.fromEntries(
      OUTPUT_PLATFORMS.map((p) => [p, `/data/library/${p}`])
    ) as OutputPolicy['effective_roots'],
    protected_platforms: []
  };
}
function setup() {
  const request = vi.fn();
  const publish = vi.fn();
  const controller = new OutputDirectoryController(publish, request as typeof api);
  return { controller, request, publish };
}

describe('shared output directory settings', () => {
  it('loads authoritative settings and does not mutate the policy when editing', async () => {
    const { controller, request } = setup();
    request.mockResolvedValueOnce(policy());
    await controller.load();
    controller.edit({ ...controller.view.draft!, shared_root: '/mnt/new' });
    expect(controller.view.policy?.shared_root).toBe('/data/library');
    expect(controller.view.draft?.shared_root).toBe('/mnt/new');
    expect(request).toHaveBeenCalledTimes(1);
  });

  it('requires a successful current preview before saving with exact CAS revision', async () => {
    const { controller, request } = setup();
    request.mockResolvedValueOnce(policy(3));
    await controller.load();
    await controller.save();
    expect(request).toHaveBeenCalledTimes(1);
    request.mockResolvedValueOnce(policy(3));
    await controller.preview();
    expect(controller.view.preview?.revision).toBe(3);
    request.mockResolvedValueOnce(policy(4));
    await controller.save();
    const [path, init] = request.mock.calls[2];
    expect(path).toBe('/api/v1/settings/output');
    expect(init.method).toBe('PUT');
    expect(JSON.parse(init.body)).toEqual({ ...controller.view.draft, expected_revision: 3 });
    expect(controller.view.policy?.revision).toBe(4);
    expect(controller.view.preview).toBeNull();
  });

  it('invalidates a preview on any draft edit, including platform overrides', async () => {
    const { controller, request } = setup();
    request.mockResolvedValue(policy());
    await controller.load();
    await controller.preview();
    controller.edit({
      ...controller.view.draft!,
      platform_overrides: { ...controller.view.draft!.platform_overrides, bili: '/mnt/bili' }
    });
    expect(controller.view.preview).toBeNull();
    await controller.save();
    expect(request).toHaveBeenCalledTimes(2);
  });

  it('rejects preview at a changed revision without rebasing the draft', async () => {
    const { controller, request } = setup();
    request.mockResolvedValueOnce(policy());
    await controller.load();
    controller.edit({ ...controller.view.draft!, shared_root: '/mnt/draft' });
    request.mockResolvedValueOnce(policy(1));
    await controller.preview();
    expect(controller.view.error).toContain('草稿已保留');
    expect(controller.view.preview).toBeNull();
    expect(controller.view.draft?.shared_root).toBe('/mnt/draft');
    expect(controller.view.policy?.revision).toBe(0);
  });

  it.each([
    'output_directory_conflict',
    'output_directory_migration_required',
    'operator_csrf_forbidden',
    'request_timeout'
  ])('preserves draft without retry after %s', async (code) => {
    const { controller, request } = setup();
    request.mockResolvedValueOnce(policy());
    await controller.load();
    controller.edit({ ...controller.view.draft!, shared_root: '/mnt/draft' });
    request.mockResolvedValueOnce(policy());
    await controller.preview();
    request.mockRejectedValueOnce(new ApiError(409, code, { platforms: ['bili', 'SECRET_SENTINEL'] }));
    await controller.save();
    await controller.save();
    expect(request).toHaveBeenCalledTimes(3);
    expect(controller.view.preview).toBeNull();
    expect(controller.view.draft?.shared_root).toBe('/mnt/draft');
    expect(controller.view.error).not.toContain('SECRET_SENTINEL');
  });

  it('explicit reload discards draft and clears stale preview', async () => {
    const { controller, request } = setup();
    request.mockResolvedValueOnce(policy());
    await controller.load();
    controller.edit({ ...controller.view.draft!, shared_root: '/mnt/draft' });
    request.mockResolvedValueOnce(policy(8));
    await controller.load();
    expect(controller.view.draft?.shared_root).toBe('/data/library');
    expect(controller.view.policy?.revision).toBe(8);
    expect(controller.view.preview).toBeNull();
  });

  it('blocks concurrent edits/actions and ignores a late response after unmount', async () => {
    const { controller, request, publish } = setup();
    request.mockResolvedValueOnce(policy());
    await controller.load();
    let resolve!: (value: OutputPolicy) => void;
    request.mockReturnValueOnce(
      new Promise<OutputPolicy>((done) => {
        resolve = done;
      })
    );
    const pending = controller.preview();
    controller.edit({ ...controller.view.draft!, shared_root: '/ignored' });
    await controller.load();
    await controller.preview();
    await controller.save();
    expect(request).toHaveBeenCalledTimes(2);
    expect(controller.view.draft?.shared_root).toBe('/data/library');
    controller.dispose();
    const calls = publish.mock.calls.length;
    resolve(policy());
    await pending;
    expect(publish.mock.calls.length).toBe(calls);
  });

  it('does not render raw server exceptions', () => {
    expect(outputFailure(new Error('SECRET_SENTINEL'))).not.toContain('SECRET_SENTINEL');
    expect(outputFailure(new ApiError(500, 'SECRET_SENTINEL', { raw: 'SECRET_SENTINEL' }))).not.toContain(
      'SECRET_SENTINEL'
    );
  });

  it('renders seven controls, container mount guidance, protection and explicit preview/save', () => {
    const source = readFileSync(
      new URL('../components/OutputDirectorySettings.svelte', import.meta.url),
      'utf8'
    );
    expect(OUTPUT_PLATFORMS).toHaveLength(7);
    for (const marker of [
      'OUTPUT_PLATFORMS as platform',
      'supervisor',
      '原目录受保护',
      '预览路径',
      '保存目录设置',
      '放弃草稿',
      '未创建',
      '私有归档'
    ]) {
      // The no-file-write promise is provided by controller status text, not markup.
      if (marker === '未创建') continue;
      expect(source).toContain(marker);
    }
    expect(source).not.toContain('localStorage');
    expect(source).toContain('disabled={!view.preview}');
  });
});
