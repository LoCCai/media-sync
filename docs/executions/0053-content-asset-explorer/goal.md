**English** | [中文](goal.zh.md)

# Execution 0053 goal

- Status: Planned; implementation not started
- Date: 2026-09-05
- Predecessor: be26cc7 (Execution 0052 closeout)
- Scope: content and asset exploration, safe local archive preview, and web catalogue upgrades
- Database migration: none planned
- Plan commit: the commit containing this record (self SHA not embedded)

## Outcome goals

1. Extend the existing bounded content and asset list APIs with backward-compatible server-side filters while preserving their array response shape and safe legacy fields.
2. Add exact content and asset detail endpoints that expose useful catalogue, lifecycle, integrity and relationship facts without exposing raw upstream records, locators, source URLs, host paths, exception text, credentials or signed query values.
3. Add UUID-addressed GET and HEAD access to a verified local archive blob. Resolve the path only from the authoritative Asset row, require the exact content-addressed location, and verify and stream through the same opened file descriptor.
4. Support one HTTP byte range with correct 200, 206 and 416 behavior, bounded parsing, exact Content-Length and Content-Range headers, a safe media-type allowlist, no-store caching and browser-hardening headers.
5. Keep recovery inside the existing durable asset-download Operation. A missing, corrupt or unsafe archive preview returns a fixed safe recovery-required result; the UI may submit the existing download/verify endpoint but no new reset shortcut or operation kind is introduced.
6. Upgrade the Contents, Assets and Library routes into a usable catalogue: server-side filters, safe detail views, ordered related assets, inline image/audio/video preview where eligible, recovery actions and author drill-downs.

## Acceptance boundary

- Existing clients of GET /api/v1/contents and GET /api/v1/assets continue receiving arrays and may keep using the existing parameters. New filters are optional, bounded and deterministic.
- GET /api/v1/contents/{content_id} returns complete plain-text content plus ordered safe asset summaries and export facts; GET /api/v1/assets/{asset_id} returns safe lifecycle and preview eligibility facts.
- Detail and list JSON never contains Content.raw, Asset.raw, Asset.locator, Asset.source_url, Asset.local_path, download validators, error messages, export output paths or settings paths.
- The preview endpoint never accepts a path or URL. It serves only an Asset in verified/exported state with complete size and SHA-256 metadata at archive/sha256/<prefix>/<digest>.<extension>.
- Preview opens a regular, non-link, single-link, read-only file below the configured archive root; the same descriptor is used for SHA-256/size/identity checks and response streaming. Replacement, mutation, symlink, hardlink, outside-root, missing and corrupt cases fail closed.
- Only a single bytes range is accepted. Prefix, open-ended and suffix ranges are supported; multiple, malformed and unsatisfiable ranges return 416 with the authoritative total size.
- No database revision, thumbnail cache, archive deletion, orphan cleanup, new Operation kind or implicit mutation from GET/HEAD is introduced.
- Focused Python and Web tests plus repository gates pass. Live platform, CDN and real Emby/Jellyfin qualification remains NOT_RUN under Execution 0047.

## Explicit limits

Execution 0053 does not add a media-server connection, scan trigger, playback qualification, filesystem tree browser, generated thumbnails, archive inventory cleanup, operator authentication, destructive deletion or retention policy. Media-library tree and real Emby/Jellyfin control remain 0054; authentication, retention and destructive actions remain 0055; final migration and release remain 0056.
