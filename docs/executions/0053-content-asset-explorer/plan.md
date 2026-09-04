**English** | [中文](plan.zh.md)

# Execution 0053 plan

- Status: Completed
- Plan date: 2026-09-05
- Baseline: be26cc7
- Database revision: none
- Plan commit: `66e18ff`

## Baseline decision

Execution 0052 completed durable operation ownership and observation. Execution 0053 delivered the next independently useful control-plane slice: operators can find collected content, inspect asset completeness, preview bytes already proven in the immutable archive, and submit the existing recovery workflow without learning internal paths or signed locators.

At the baseline, the API had bounded array lists but no content/asset detail or archive-byte endpoint; the Web routes fetched 500–1,000 rows and filtered in memory, while Library displayed the configured export host path. Execution 0053 preserved compatible list shapes, moved selected filters to the server, added closed detail projections, removed host-path display and kept media-server control out of scope.

## Delivery sequence

1. Recorded the synchronized `be26cc7` baseline, endpoint/UI inventory and focused test results.
2. Added a framework-independent explorer projection layer for safe content/asset summaries and details, centralizing official-platform URL normalization, bounded text/metrics, archive eligibility and derived allowed actions.
3. Added repository queries for exact content/asset lookup, stable ordered relationships and optional platform, kind, state, author, content, completeness and bounded literal-text filters.
4. Preserved legacy array payloads, parameters and default ordering while adding optional filters, bounded query text and limits, escaped SQL wildcards and deterministic ordering.
5. Added exact content and asset detail endpoints with full body text, ordered safe assets, safe timestamp/dimension/checksum facts and aggregate export facts, without ORM/raw/path/locator/error-body leakage.
6. Added a read-only archive-preview service that validates status and metadata, requires the canonical digest path, rejects links and writable or multiply linked files, and hashes, seeks and streams through one descriptor. On Windows, the handle denies write/delete sharing; reads require an existing archive root and never create a missing directory.
7. Added strict full-representation and single-range responses with exact 200/206/416 headers, strong ETag handling, a safe Content-Type boundary, no-store policy and descriptor closure on success, failure, abort and disconnect.
8. Mapped missing, corrupt, unsafe and not-ready archive states to fixed safe errors with the existing asset-download recovery link, without database mutation or another repair executor.
9. Updated shared Web types and utilities and upgraded Contents with server filters and a plain-text detail modal containing ordered asset actions and previews.
10. Upgraded Assets with server filters, safe detail, preview eligibility, inline/new-tab preview and the existing durable download/verify recovery submission.
11. Upgraded Library with platform/search filtering and author drill-down links and removed the configured host export path. Emby/Jellyfin tree and control remain explicitly deferred.
12. Completed focused security, path/range, API and Web verification, local query/modal browser smoke, Ruff, format, strict mypy and Web production gates. The complete Python suite passed with `2456 passed, 3 skipped`; packaging, documentation, artifact and publication evidence remains recorded in the closeout verification log rather than being inferred here.

## Frozen contracts

- Public JSON is built from explicit allowlists. No generic serializer or ORM object crosses the API boundary.
- Search is literal, trimmed, bounded and wildcard-escaped. Existing list array shapes and old filters remain valid.
- Asset recovery authority stays POST /api/v1/assets/{asset_id}/download and produces the 0052 durable asset-download Operation. Read endpoints never reset Asset state.
- Preview identity is the Asset UUID; request data cannot select a filesystem path. The configured archive root and persisted canonical metadata are jointly required.
- Validation and streaming share one descriptor. FileResponse or any validate-then-reopen path is forbidden.
- The complete archive representation is validated before Range is interpreted. Only GET honors one ASCII case-insensitive `bytes` Range; malformed, multiple and unsatisfiable ranges on a valid representation return 416 with its total size. An empty representation has no satisfiable range.
- HEAD ignores Range and returns full validated metadata with an empty body. `If-Range` activates a GET range only when it exactly matches the current strong ETag; stale, weak, date and malformed validators fall back to full 200.
- Safe media types are a closed set derived from verified probe outputs; unknown values use application/octet-stream and never become executable HTML/SVG.
- The UI renders collected body text as text, never raw HTML. It never renders or logs path, locator, source URL, raw record or exception fields.
- No database migration was introduced.

## Verification coverage

- Projection/repository: stable ordering, optional filters, escaped percent/underscore searches, limit bounds, exact not-found behavior and full omission of prohibited fields.
- Preview: verified/exported gates, canonical path, SHA/size checks, same-descriptor identity, writable/link/hardlink/outside-root rejection, missing/corrupt recovery result and guaranteed close.
- HTTP: validated full GET 200; explicit/open-ended/suffix GET 206; malformed/multiple/unsatisfiable GET 416; strong `If-Range`; stale/weak/date fallback; Range-ignoring HEAD; exact headers, empty and zero-length behavior, and MIME fallback.
- API security: sentinel source URLs, signed queries, local paths, raw keys, validators and exception messages never appear in list/detail/error/preview headers or bodies.
- Web: filter construction, safe action derivation, detail rendering and preview/recovery behavior plus format, unit tests, Svelte check and production build.
- External qualification: no real platform account, creator API/CDN, downloaded creator media, Linux persistence drill or real Emby/Jellyfin server was exercised. Those rows remain `NOT_RUN` under Execution 0047.

## Delivery policy

The bilingual goal/plan baseline was committed before implementation as `66e18ff`. Closeout records retain the reviewable implementation and verification boundaries. `.mimosa`, `.upstream`, local databases, archive/export/job data, XML reports, `node_modules`, `web/build`, `.svelte-kit` and `dist` remain excluded from commits.
