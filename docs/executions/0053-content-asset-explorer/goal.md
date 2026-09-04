**English** | [中文](goal.zh.md)

# Execution 0053 goal

- Status: Completed
- Date: 2026-09-05
- Predecessor: be26cc7 (Execution 0052 closeout)
- Scope: content and asset exploration, safe local archive preview, and web catalogue upgrades
- Database migration: none
- Plan commit: `66e18ff`

## Delivered outcomes

1. Extended the bounded content and asset list APIs with backward-compatible server-side filters while preserving their array response shape, legacy defaults and safe fields.
2. Added exact content and asset detail endpoints with catalogue, lifecycle, integrity and relationship facts, without exposing raw upstream records, locators, source URLs, host paths, exception text, credentials or signed query values. Canonical links are stripped to the matching platform's official public-domain boundary.
3. Added UUID-addressed GET and HEAD access to verified local archive blobs. The path comes only from the authoritative Asset row, must match the exact content-addressed location, and is verified and streamed through one owned file descriptor.
4. Added strict full-representation and single-range HTTP behavior with exact Content-Length and Content-Range headers, a closed safe media-type allowlist, no-store caching and browser-hardening headers.
5. Kept recovery inside the existing durable asset-download Operation. Missing, corrupt, unsafe and not-ready archives return fixed safe recovery results; no reset shortcut or new Operation kind was introduced.
6. Upgraded Contents, Assets and Library into a usable catalogue with server-side filters, safe detail views, ordered related assets, eligible inline image/audio/video preview, recovery actions and author drill-downs.

## Acceptance boundary

- Existing clients of GET /api/v1/contents and GET /api/v1/assets continue receiving arrays and may keep using the existing parameters. New filters are optional, bounded and deterministic.
- GET /api/v1/contents/{content_id} returns complete plain-text content plus ordered safe asset summaries and export facts; GET /api/v1/assets/{asset_id} returns safe lifecycle and preview eligibility facts.
- Detail and list JSON never contains Content.raw, Asset.raw, Asset.locator, Asset.source_url, Asset.local_path, download validators, error messages, export output paths or settings paths.
- The preview endpoint never accepts a path or URL. It serves only an Asset in verified/exported state with complete size and SHA-256 metadata at archive/sha256/<prefix>/<digest>.<extension>.
- Preview opens a regular, non-link, single-link, read-only file below the configured archive root; the same descriptor is used for SHA-256/size/identity checks and response streaming. Replacement, mutation, symlink, hardlink, outside-root, missing and corrupt cases fail closed.
- A Range is evaluated only for GET and only after the complete representation passes status, path, identity, size and SHA-256 validation. One ASCII case-insensitive `bytes` range supports explicit, open-ended and suffix forms; multiple, malformed and unsatisfiable ranges return 416 with the authoritative total size.
- HEAD ignores Range and returns the validated full-representation headers with no body. `If-Range` enables a GET range only when it is the exact current strong ETag; stale, weak, date and malformed validators fall back to the full 200 representation.
- An empty validated representation returns a full 200 with zero length; any GET Range against it is unsatisfiable. Representation failures take precedence over Range errors and return the fixed recovery result.
- No database revision, thumbnail cache, archive deletion, orphan cleanup, new Operation kind or implicit mutation from GET/HEAD is introduced.
- Focused Python and Web tests, local query/modal browser smoke, the complete Python suite (`2456 passed, 3 skipped`) and static repository gates pass; frozen closeout evidence is recorded separately. Live platform, CDN and real Emby/Jellyfin qualification remains `NOT_RUN` under Execution 0047.

## Explicit limits

Execution 0053 does not add a media-server connection, scan trigger, playback qualification, filesystem tree browser, generated thumbnails, archive inventory cleanup, operator authentication, destructive deletion or retention policy. Media-library tree and real Emby/Jellyfin control remain 0054; authentication, retention and destructive actions remain 0055; final migration and release remain 0056.
