import type { Asset, AssetAction, AssetKind, AssetStatus, ContentKind, Platform } from '$lib/types/api';

export const EXPLORER_RESULT_LIMIT = 200;
export const EXPLORER_QUERY_LIMIT = 200;

export type ExplorerFilterValue = string | number | boolean | null | undefined;
export type AssetPreviewKind = 'image' | 'video' | 'audio' | 'new-tab' | 'none';

export interface ExplorerQuery {
  q?: string;
  platform?: Platform | 'all';
  kind?: string | 'all';
  status?: string | 'all';
  author_id?: string;
  content_id?: string;
  archived?: boolean | 'all';
  exported?: boolean | 'all';
  limit?: number;
}

export interface DerivedAssetActions {
  canPreview: boolean;
  canDownload: boolean;
  canExportAuthor: boolean;
  previewKind: AssetPreviewKind;
}

export interface ContentExplorerQueryState {
  q: string;
  platform: Platform | 'all';
  kind: ContentKind | 'all';
  author_id: string;
  archived: boolean | 'all';
  exported: boolean | 'all';
}

export interface AssetExplorerQueryState {
  q: string;
  platform: Platform | 'all';
  kind: AssetKind | 'all';
  status: AssetStatus | 'all';
  author_id: string;
  content_id: string;
  archived: boolean | 'all';
}

const PLATFORMS = ['bili', 'xhs', 'dy', 'ks', 'wb', 'tieba', 'zhihu'] as const satisfies readonly Platform[];
const CONTENT_KINDS = [
  'video',
  'image',
  'gallery',
  'text',
  'article',
  'audio',
  'dynamic',
  'mixed'
] as const satisfies readonly ContentKind[];
const ASSET_KINDS = [
  'image',
  'video',
  'audio',
  'subtitle',
  'cover',
  'avatar',
  'attachment'
] as const satisfies readonly AssetKind[];
const ASSET_STATUSES = [
  'discovered',
  'queued',
  'downloading',
  'downloaded',
  'verified',
  'exported',
  'failed_retryable',
  'failed_terminal'
] as const satisfies readonly AssetStatus[];

const INLINE_MIME_TYPES = new Map<string, Exclude<AssetPreviewKind, 'new-tab' | 'none'>>([
  ['image/jpeg', 'image'],
  ['image/png', 'image'],
  ['image/gif', 'image'],
  ['image/webp', 'image'],
  ['image/avif', 'image'],
  ['video/mp4', 'video'],
  ['audio/mp4', 'audio'],
  ['audio/webm', 'audio'],
  ['audio/flac', 'audio'],
  ['audio/mpeg', 'audio'],
  ['audio/ogg', 'audio'],
  ['audio/wav', 'audio']
]);

function boundedText(value: string, limit: number): string {
  return [...value.trim()].slice(0, limit).join('');
}

function enumFilter<T extends string>(value: string | null, allowed: readonly T[]): T | 'all' {
  return value !== null && allowed.includes(value as T) ? (value as T) : 'all';
}

function booleanFilter(value: string | null): boolean | 'all' {
  if (value === 'true') return true;
  if (value === 'false') return false;
  return 'all';
}

/** Read every supported content filter, resetting omitted or invalid values. */
export function contentExplorerQueryState(parameters: URLSearchParams): ContentExplorerQueryState {
  return {
    q: boundedText(parameters.get('q') ?? '', EXPLORER_QUERY_LIMIT),
    platform: enumFilter(parameters.get('platform'), PLATFORMS),
    kind: enumFilter(parameters.get('kind'), CONTENT_KINDS),
    author_id: boundedText(parameters.get('author_id') ?? '', 64),
    archived: booleanFilter(parameters.get('archived')),
    exported: booleanFilter(parameters.get('exported'))
  };
}

/** Read every supported asset filter, resetting omitted or invalid values. */
export function assetExplorerQueryState(parameters: URLSearchParams): AssetExplorerQueryState {
  return {
    q: boundedText(parameters.get('q') ?? '', EXPLORER_QUERY_LIMIT),
    platform: enumFilter(parameters.get('platform'), PLATFORMS),
    kind: enumFilter(parameters.get('kind'), ASSET_KINDS),
    status: enumFilter(parameters.get('status'), ASSET_STATUSES),
    author_id: boundedText(parameters.get('author_id') ?? '', 64),
    content_id: boundedText(parameters.get('content_id') ?? '', 64),
    archived: booleanFilter(parameters.get('archived'))
  };
}

function normalizedFilterValue(key: string, value: ExplorerFilterValue): string | null {
  if (value === null || value === undefined || value === 'all') return null;
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return null;
    if (key === 'limit') {
      return String(Math.max(1, Math.min(EXPLORER_RESULT_LIMIT, Math.trunc(value))));
    }
    return String(value);
  }
  const normalized = key === 'q' ? boundedText(value, EXPLORER_QUERY_LIMIT) : value.trim();
  return normalized || null;
}

/** Build a deterministic same-origin explorer URL from bounded literal filters. */
export function buildExplorerQuery(path: string, query: ExplorerQuery): string {
  const parameters = new URLSearchParams();
  for (const [key, value] of Object.entries(query).sort(([left], [right]) => left.localeCompare(right))) {
    const normalized = normalizedFilterValue(key, value);
    if (normalized !== null) parameters.set(key, normalized);
  }
  const encoded = parameters.toString();
  return encoded ? `${path}?${encoded}` : path;
}

export function assetArchiveUrl(assetId: string): string {
  return `/api/v1/assets/${encodeURIComponent(assetId)}/archive`;
}

export function assetRecoveryUrl(assetId: string): string {
  return `/api/v1/assets/${encodeURIComponent(assetId)}/download`;
}

export function previewKind(mimeType: string | null): AssetPreviewKind {
  if (!mimeType) return 'new-tab';
  return INLINE_MIME_TYPES.get(mimeType) ?? 'new-tab';
}

export function hasAssetAction(asset: Pick<Asset, 'allowed_actions'>, action: AssetAction): boolean {
  return asset.allowed_actions.includes(action);
}

/** Derive controls only from the server's explicit action set and safe archive facts. */
export function assetActions(
  asset: Pick<Asset, 'allowed_actions' | 'archive' | 'mime_type'>
): DerivedAssetActions {
  const canPreview =
    hasAssetAction(asset, 'preview') && asset.archive.eligible && Boolean(asset.archive.preview_url);
  const canDownload = hasAssetAction(asset, 'download') && Boolean(asset.archive.recovery_url);
  return {
    canPreview,
    canDownload,
    canExportAuthor: hasAssetAction(asset, 'export_author'),
    previewKind: canPreview ? previewKind(asset.mime_type) : 'none'
  };
}

/** Keep recovery controls subordinate to the server-provided action set. */
export function assetRecoveryAvailable(actions: Pick<DerivedAssetActions, 'canDownload'>): boolean {
  return actions.canDownload;
}
