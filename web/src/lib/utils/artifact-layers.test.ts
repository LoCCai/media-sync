import { describe, expect, it } from 'vitest';

import { artifactLayers } from './artifact-layers';
import type { Settings } from '$lib/types/api';

function settings(patch: Partial<Settings> = {}): Settings {
  return {
    version: '0.1.0',
    state_dir: '/data/state',
    archive_dir: '/data/archive',
    export_dir: '/data/library',
    job_dir: '/data/jobs',
    api_bind: '0.0.0.0:8632',
    mediacrawler_python_executable: null,
    ...patch
  } as Settings;
}

describe('artifactLayers', () => {
  it('projects the three layers with configured roots', () => {
    const layers = artifactLayers(settings({ mediacrawler_runtime_dir: '/data/mediacrawler/' }));
    expect(layers.map((layer) => layer.key)).toEqual(['raw', 'archive', 'library']);
    expect(layers[0].path).toBe('/data/mediacrawler/webui-output');
    expect(layers[1].path).toBe('/data/archive');
    expect(layers[2].path).toBe('/data/library');
  });

  it('degrades to honest placeholders for missing roots', () => {
    const layers = artifactLayers(settings({ mediacrawler_runtime_dir: undefined }));
    expect(layers[0].path).toContain('未读取到');
  });

  it('returns placeholders for absent settings without guessing', () => {
    const layers = artifactLayers(null);
    expect(layers.every((layer) => layer.path.startsWith('（未读取到'))).toBe(true);
  });
});
