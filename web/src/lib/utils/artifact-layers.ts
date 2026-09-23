import type { Settings } from '$lib/types/api';

export interface ArtifactLayer {
  key: 'raw' | 'archive' | 'library';
  title: string;
  path: string;
  description: string;
}

/**
 * Project the three artifact layers an operator needs to tell apart:
 * raw crawler output, the verified SHA-256 store, and the Emby/Jellyfin tree.
 * Paths come straight from the settings API; missing optional roots degrade
 * to an honest placeholder instead of a guessed path.
 */
export function artifactLayers(settings: Settings | null | undefined): ArtifactLayer[] {
  const rawRoot = settings?.mediacrawler_runtime_dir?.trim();
  const archive = settings?.archive_dir?.trim();
  const library = settings?.export_dir?.trim();
  return [
    {
      key: 'raw',
      title: '爬虫原始输出',
      path: rawRoot ? `${rawRoot.replace(/\/+$/, '')}/webui-output` : '（未读取到 MediaCrawler 运行时根）',
      description: '原生爬虫直接转储的 JSONL 与上游自存媒体，仅供导入与排查，不是发布产物。'
    },
    {
      key: 'archive',
      title: '校验正本库（SHA-256）',
      path: archive || '（未读取到归档根）',
      description: 'media-sync 下载并通过校验的不可变正本；Emby 目录只从这一层派生。'
    },
    {
      key: 'library',
      title: 'Emby/Jellyfin 媒体树',
      path: library || '（未读取到导出根）',
      description: '确定性生成的剧集目录、NFO 与海报；可只读挂载给媒体服务器。'
    }
  ];
}
