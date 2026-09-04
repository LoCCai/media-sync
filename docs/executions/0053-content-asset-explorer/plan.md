**English** | [中文](plan.zh.md)

# Execution 0053 plan

- Status: Active
- Plan date: 2026-09-05
- Baseline: be26cc7
- Database revision: none planned
- Plan commit: the commit containing this record (self SHA not embedded)

## Baseline decision

Execution 0052 completed durable operation ownership and observation. The next independently useful control-plane slice is the safe catalogue promised by the project plan: operators must be able to find collected content, inspect asset completeness, preview bytes already proven in the immutable archive, and submit the existing recovery workflow without learning internal paths or signed locators.

The API currently has bounded array lists but no content/asset detail or archive-byte endpoint; the Web routes fetch 500–1,000 rows and filter in memory. The Library route also displays the configured export host path. Execution 0053 will preserve the compatible list shapes, move selected filters to the server, add closed detail projections, stop displaying host paths, and keep media-server control out of scope.

## Delivery sequence

1. Record the synchronized be26cc7 baseline, current endpoint/UI inventory and focused test results.
2. Add a framework-independent explorer projection layer for safe content/asset summaries and details. Centralize URL normalization, bounded text/metric handling, archive eligibility and derived allowed actions.
3. Add repository queries for exact content/asset lookup, stable ordered relationships and optional platform, kind, state, author, content, completeness and bounded literal-text filters.
4. Preserve the legacy array payloads and parameters on the list endpoints while adding optional filters. Bound query text and limits, escape SQL wildcard characters and keep deterministic ordering.
5. Add exact content and asset detail endpoints. Return full body as plain JSON text, ordered safe assets, safe timestamps/dimensions/checksum facts and aggregate export facts without ORM/raw/path/locator/error-body leakage.
6. Implement a read-only archive-preview service. Validate status and metadata, require the canonical digest path below the archive root, open without following links, compare named/opened identities, enforce regular/single-link/read-only state, then hash and stream from that same descriptor.
7. Implement a strict single-range parser and GET/HEAD responses with 200/206/416, Accept-Ranges, Content-Length, Content-Range, ETag, safe Content-Type and no-store headers. Close the descriptor on every success, error and disconnect path.
8. Map missing, corrupt and unsafe archive states to fixed safe errors with an existing asset-download recovery link. Do not mutate database state during read or introduce another repair executor.
9. Update shared Web types and utilities, then upgrade Contents with server filters and a plain-text detail modal containing ordered asset actions/previews.
10. Upgrade Assets with server filters, a safe detail modal, preview eligibility, inline/new-tab preview and the existing durable download/verify recovery submission.
11. Upgrade Library with platform/search filtering and author drill-down links, and remove the configured host export path from the page. Keep Emby/Jellyfin tree/control language explicitly deferred.
12. Run focused security, path/range, API and Web tests; then run Ruff, format, strict mypy, compileall, package, docs, upstream, artifact and complete-suite gates. Update all bilingual records, commit in reviewable bilingual slices, push main and reconcile three SHAs.

## Frozen contracts

- Public JSON is built from explicit allowlists. No generic serializer or ORM object crosses the API boundary.
- Search is literal, trimmed, bounded and wildcard-escaped. Existing list array shapes and old filters remain valid.
- Asset recovery authority stays POST /api/v1/assets/{asset_id}/download and produces the 0052 durable asset-download Operation. Read endpoints never reset Asset state.
- Preview identity is the Asset UUID; request data cannot select a filesystem path. The configured archive root and persisted canonical metadata are jointly required.
- Validation and streaming share one descriptor. FileResponse or any validate-then-reopen path is forbidden.
- Safe media types are a closed set derived from verified probe outputs; unknown values use application/octet-stream and never become executable HTML/SVG.
- The UI renders collected body text as text, never raw HTML. It never renders or logs path, locator, source URL, raw record or exception fields.
- No database migration is expected; if implementation proves one necessary, stop and revise this plan before creating it.

## Verification plan

- Projection/repository: stable ordering, optional filters, escaped percent/underscore searches, limit bounds, exact not-found behavior and full omission of prohibited fields.
- Preview: verified/exported gates, canonical path, SHA/size checks, same-descriptor identity, writable/link/hardlink/outside-root rejection, missing/corrupt recovery result and guaranteed close.
- HTTP: GET/HEAD parity, full 200, prefix/open/suffix 206, malformed/multiple/unsatisfiable 416, exact headers, empty HEAD body and MIME fallback.
- API security: sentinel source URLs, signed queries, local paths, raw keys, validators and exception messages never appear in list/detail/error/preview headers or bodies.
- Web: filter construction, safe action derivation, detail rendering and preview/recovery behavior plus format, unit tests, Svelte check and production build.

## Commit policy

Commit this bilingual goal/plan/baseline before implementation. Prefer separate bilingual commits for explorer/read models, archive preview and API, Web catalogue upgrades, and closeout documentation. Never stage .mimosa, .upstream, local databases, archive/export/job data, XML reports, node_modules, web/build, .svelte-kit or dist.
