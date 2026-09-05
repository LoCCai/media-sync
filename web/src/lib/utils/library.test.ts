import { describe, expect, it } from 'vitest';

import type { LibraryInspection, MediaServerAuthorLookup, MediaServerStatus } from '$lib/types/api';

import {
  authorAllowsRefreshAndVerify,
  authorObservationOperationRequest,
  emptyMediaServerOperationRequest,
  libraryAllows,
  libraryFreshnessLabel,
  libraryIntegrityLabel,
  libraryStateTone,
  mediaServerAllows,
  mediaServerLookupPresentation,
  mediaServerPosture,
  mergeLibraryInspectionPage
} from './library';

function inspection(overrides: Partial<LibraryInspection> = {}): LibraryInspection {
  return {
    schema_version: 2,
    author_id: 'author-1',
    publication: {
      layout_version: '1',
      publication_scope: '1'.repeat(64),
      job_id: 'job-1',
      source_fingerprint: '2'.repeat(64),
      tree_sha256: '3'.repeat(64),
      manifest_sha256: '4'.repeat(64),
      managed_file_count: 2
    },
    freshness: 'current',
    freshness_reason_code: null,
    integrity: 'page_verified',
    integrity_reason_code: null,
    user_changes_protected: true,
    files: [{ relative_path: 'one.mp4', sha256: '5'.repeat(64), size_bytes: 10 }],
    page: {
      start_index: 0,
      next_index: 1,
      limit: 1,
      returned_count: 1,
      bytes_read: 10,
      complete: false,
      budget_exhausted: false,
      next_cursor: 'cursor-1'
    },
    allowed_actions: [],
    ...overrides
  };
}

function mediaServer(overrides: Partial<MediaServerStatus> = {}): MediaServerStatus {
  return {
    schema_version: 1,
    configuration: {
      configured: true,
      provider: 'emby',
      origin: 'http://media.invalid',
      library_id_digest: '1'.repeat(64),
      profile_fingerprint: '2'.repeat(64),
      verify_tls: true,
      timeout_seconds: 10,
      operations_enabled: true,
      allowed_network_count: 1,
      library_path_configured: true,
      api_key_configured: true
    },
    latest_probe: null,
    latest_scan: null,
    allowed_actions: ['probe', 'scan'],
    ...overrides
  };
}

describe('library console derivations', () => {
  it('keeps freshness, integrity, and action authority independent', () => {
    expect(libraryFreshnessLabel('outdated')).toBe('需要重新发布');
    expect(libraryIntegrityLabel('page_verified')).toBe('本页已校验');
    expect(libraryStateTone('current', 'complete')).toBe('success');
    expect(libraryStateTone('current', 'drifted')).toBe('danger');
    expect(libraryAllows(inspection({ allowed_actions: ['export_author'] }), 'export_author')).toBe(true);
    expect(libraryAllows(inspection(), 'export_author')).toBe(false);
  });

  it('appends only a contiguous page from the same publication identity', () => {
    const first = mergeLibraryInspectionPage(null, inspection());
    const secondPage = inspection({
      files: [{ relative_path: 'two.nfo', sha256: '6'.repeat(64), size_bytes: 20 }],
      page: {
        start_index: 1,
        next_index: 2,
        limit: 1,
        returned_count: 1,
        bytes_read: 20,
        complete: false,
        budget_exhausted: false,
        next_cursor: null
      }
    });
    const appended = mergeLibraryInspectionPage(first, secondPage);
    expect(appended.files.map((item) => item.relative_path)).toEqual(['one.mp4', 'two.nfo']);
    expect(appended.inspection.page).toMatchObject({
      start_index: 1,
      next_index: 2,
      complete: false,
      next_cursor: null
    });

    const changed = inspection({
      publication: { ...secondPage.publication!, manifest_sha256: '7'.repeat(64) },
      files: [{ relative_path: 'replacement.mp4', sha256: '8'.repeat(64), size_bytes: 30 }]
    });
    expect(mergeLibraryInspectionPage(appended, changed).files).toEqual(changed.files);
  });

  it('derives media-server posture and actions only from server payloads', () => {
    const status = mediaServer();
    expect(mediaServerAllows(status, 'scan')).toBe(true);
    expect(mediaServerPosture(status)).toEqual({ label: '已配置，尚未探测', tone: 'info' });
    expect(
      mediaServerPosture(
        mediaServer({ latest_probe: { state: 'succeeded' } as MediaServerStatus['latest_probe'] })
      )
    ).toEqual({ label: '连接已验证', tone: 'success' });
    expect(mediaServerAllows(mediaServer({ allowed_actions: [] }), 'probe')).toBe(false);
  });

  it('requires both server-provided action grants for refresh and verify', () => {
    const complete = inspection({
      freshness: 'current',
      integrity: 'complete',
      allowed_actions: ['refresh_and_verify']
    });
    expect(authorAllowsRefreshAndVerify(complete, mediaServer())).toBe(true);
    expect(authorAllowsRefreshAndVerify({ ...complete, allowed_actions: [] }, mediaServer())).toBe(false);
    expect(authorAllowsRefreshAndVerify(complete, mediaServer({ allowed_actions: ['probe'] }))).toBe(false);
    expect(
      authorAllowsRefreshAndVerify(
        inspection({ freshness: 'current', integrity: 'complete', allowed_actions: [] }),
        mediaServer()
      )
    ).toBe(false);
  });

  it('keeps legacy and author observation scan bodies as two exact shapes', () => {
    const authorId = '11111111-1111-4111-8111-111111111111';
    expect(emptyMediaServerOperationRequest()).toEqual({ method: 'POST', body: '{}' });
    expect(authorObservationOperationRequest(authorId)).toEqual({
      method: 'POST',
      body: JSON.stringify({ author_id: authorId })
    });
  });

  it('describes a direct lookup as an observation rather than completion or playback evidence', () => {
    const base = {
      schema_version: 1 as const,
      author_id: '11111111-1111-4111-8111-111111111111',
      provider: 'emby' as const,
      library_id_digest: '1'.repeat(64),
      publication_fingerprint: '2'.repeat(64),
      selector_fingerprint: '3'.repeat(64),
      observed_at: '2026-09-05T08:00:00+00:00',
      complete: true as const
    };
    const missing: MediaServerAuthorLookup = { ...base, lookup_state: 'not_found', match_count: 0 };
    const matched: MediaServerAuthorLookup = {
      ...base,
      lookup_state: 'matched',
      match_count: 1,
      item_fingerprint: '4'.repeat(64),
      observation_fingerprint: '5'.repeat(64)
    };

    expect(mediaServerLookupPresentation(missing)).toMatchObject({
      label: '未观察到项目',
      tone: 'info'
    });
    expect(mediaServerLookupPresentation(matched)).toMatchObject({
      label: '已观察到唯一项目',
      tone: 'success'
    });
    expect(mediaServerLookupPresentation(matched).detail).toContain('不代表 provider 任务完成');
    expect(mediaServerLookupPresentation(matched).detail).toContain('媒体可播放');
  });
});
