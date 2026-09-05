import { describe, expect, it } from 'vitest';

import type { LibraryInspection, MediaServerStatus } from '$lib/types/api';
import { authorAllowsRefreshAndVerify, libraryAllows, mediaServerAllows } from './library';

const inspection: LibraryInspection = {
  schema_version: 2,
  author_id: 'local-author',
  publication: null,
  freshness: 'not_published',
  freshness_reason_code: null,
  integrity: 'not_available',
  integrity_reason_code: null,
  user_changes_protected: true,
  files: [],
  page: {
    start_index: 0,
    next_index: 0,
    limit: 64,
    returned_count: 0,
    bytes_read: 0,
    complete: false,
    budget_exhausted: false,
    next_cursor: null
  },
  allowed_actions: ['export_author']
};

const unconfigured: MediaServerStatus = {
  schema_version: 1,
  configuration: {
    configured: false,
    provider: null,
    origin: null,
    library_id_digest: null,
    profile_fingerprint: null,
    verify_tls: true,
    timeout_seconds: 10,
    operations_enabled: false,
    allowed_network_count: 0,
    library_path_configured: false,
    api_key_configured: false
  },
  latest_probe: null,
  latest_scan: null,
  allowed_actions: []
};

describe('local export without optional server linkage', () => {
  it.each([null, unconfigured])(
    'keeps local export available while remote actions are unavailable',
    (server) => {
      expect(libraryAllows(inspection, 'export_author')).toBe(true);
      expect(mediaServerAllows(server, 'probe')).toBe(false);
      expect(mediaServerAllows(server, 'scan')).toBe(false);
      expect(authorAllowsRefreshAndVerify(inspection, server)).toBe(false);
    }
  );

  it('does not grant local export when the backend withholds archive or integrity authority', () => {
    expect(libraryAllows({ ...inspection, freshness: 'blocked', allowed_actions: [] }, 'export_author')).toBe(
      false
    );
  });
});
