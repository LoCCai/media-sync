import { describe, expect, it } from 'vitest';

import type { Asset } from '$lib/types/api';

import {
  assetActions,
  assetArchiveUrl,
  assetExplorerQueryState,
  assetRecoveryAvailable,
  assetRecoveryUrl,
  buildExplorerQuery,
  contentExplorerQueryState,
  previewKind
} from './explorer';

const asset: Asset = {
  id: '11111111-1111-4111-8111-111111111111',
  author_id: '22222222-2222-4222-8222-222222222222',
  author_display_name: '示例作者',
  content_id: '33333333-3333-4333-8333-333333333333',
  content_title: '示例内容',
  platform: 'bili',
  kind: 'video',
  position: 0,
  generation: 1,
  status: 'verified',
  mime_type: 'video/mp4',
  size_bytes: 128,
  verified_at: '2026-09-05T08:00:00+00:00',
  archive: {
    state: 'eligible',
    eligible: true,
    preview_url: '/api/v1/assets/11111111-1111-4111-8111-111111111111/archive',
    recovery_url: '/api/v1/assets/11111111-1111-4111-8111-111111111111/download'
  },
  allowed_actions: ['preview', 'export_author']
};

describe('explorer query builder', () => {
  it('trims, encodes, omits all filters, and keeps false as an explicit value', () => {
    expect(
      buildExplorerQuery('/api/v1/contents', {
        q: '  100% 图集_一  ',
        platform: 'all',
        archived: false,
        exported: 'all',
        limit: 100
      })
    ).toBe('/api/v1/contents?archived=false&limit=100&q=100%25+%E5%9B%BE%E9%9B%86_%E4%B8%80');
  });

  it('bounds result counts and literal query text on the client', () => {
    const url = new URL(
      buildExplorerQuery('/api/v1/assets', { q: '查'.repeat(250), limit: 10_000 }),
      'http://localhost'
    );
    expect(url.searchParams.get('limit')).toBe('200');
    expect([...(url.searchParams.get('q') ?? '')]).toHaveLength(200);
  });

  it('reads content deep links and resets omitted or invalid filters', () => {
    expect(
      contentExplorerQueryState(
        new URLSearchParams(
          'q=%20Catalogue%20&platform=bili&kind=video&author_id=author-1&archived=false&exported=true'
        )
      )
    ).toEqual({
      q: 'Catalogue',
      platform: 'bili',
      kind: 'video',
      author_id: 'author-1',
      archived: false,
      exported: true
    });
    expect(contentExplorerQueryState(new URLSearchParams())).toEqual({
      q: '',
      platform: 'all',
      kind: 'all',
      author_id: '',
      archived: 'all',
      exported: 'all'
    });
  });

  it('reads asset deep links while rejecting invalid enum and boolean filters', () => {
    expect(
      assetExplorerQueryState(
        new URLSearchParams(
          'q=asset-1&platform=xhs&kind=image&status=verified&author_id=author-1&content_id=content-1&archived=true'
        )
      )
    ).toEqual({
      q: 'asset-1',
      platform: 'xhs',
      kind: 'image',
      status: 'verified',
      author_id: 'author-1',
      content_id: 'content-1',
      archived: true
    });
    expect(
      assetExplorerQueryState(new URLSearchParams('platform=unknown&status=unknown&archived=1'))
    ).toMatchObject({
      platform: 'all',
      status: 'all',
      archived: 'all'
    });
  });
});

describe('asset preview and actions', () => {
  it.each([
    ['image/jpeg', 'image'],
    ['image/png', 'image'],
    ['image/gif', 'image'],
    ['image/webp', 'image'],
    ['image/avif', 'image'],
    ['video/mp4', 'video'],
    ['audio/flac', 'audio'],
    ['audio/mp4', 'audio'],
    ['audio/mpeg', 'audio'],
    ['audio/ogg', 'audio'],
    ['audio/wav', 'audio'],
    ['audio/webm', 'audio']
  ] as const)('renders archive MIME %s inline as %s', (mimeType, expected) => {
    expect(previewKind(mimeType)).toBe(expected);
  });

  it.each([
    'application/pdf',
    'application/x-subrip',
    'text/vtt',
    'application/octet-stream',
    'video/webm',
    'video/x-flv',
    'video/x-matroska',
    'audio/aac',
    'image/svg+xml',
    'VIDEO/MP4',
    ' video/mp4 '
  ])('opens non-inline MIME %s in a new tab', (mimeType) => {
    expect(previewKind(mimeType)).toBe('new-tab');
  });

  it('opens an archive with no declared MIME in a new tab', () => {
    expect(previewKind(null)).toBe('new-tab');
  });

  it('honors server-derived actions and archive eligibility', () => {
    expect(assetActions(asset)).toEqual({
      canPreview: true,
      canDownload: false,
      canExportAuthor: true,
      previewKind: 'video'
    });
    expect(
      assetActions({
        ...asset,
        archive: { ...asset.archive, eligible: false, preview_url: null },
        allowed_actions: ['download']
      })
    ).toEqual({
      canPreview: false,
      canDownload: true,
      canExportAuthor: false,
      previewKind: 'none'
    });
    expect(assetRecoveryAvailable(assetActions(asset))).toBe(false);
    expect(
      assetRecoveryAvailable(
        assetActions({
          ...asset,
          archive: { ...asset.archive, eligible: false, preview_url: null },
          allowed_actions: ['download']
        })
      )
    ).toBe(true);
  });

  it('constructs encoded same-origin action URLs from the public asset id', () => {
    expect(assetArchiveUrl('asset/id')).toBe('/api/v1/assets/asset%2Fid/archive');
    expect(assetRecoveryUrl('asset/id')).toBe('/api/v1/assets/asset%2Fid/download');
  });
});
