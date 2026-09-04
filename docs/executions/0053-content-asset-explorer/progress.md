**English** | [中文](progress.zh.md)

# Execution 0053 progress

- Status: Complete; implementation, frozen verification and publication reconciliation pass
- Closeout date: 2026-09-05
- Baseline: `be26cc7`
- Plan commit: `66e18ff`
- Database migration: none

## Delivered

1. Fetched and pulled `origin/main` with `--ff-only`. GitHub had no incoming commit beyond `be26cc7`; the local branch contained only the committed 0053 plan plus the preserved implementation worktree.
2. Added a framework-independent `ContentAssetExplorer` with bounded literal search, stable legacy ordering and optional platform/kind/status/author/content/archive/export filters. Existing content and asset list responses remain arrays.
3. Added explicit safe content and asset projections and exact detail endpoints. They include catalogue, lifecycle, integrity, archive and aggregate export facts while excluding raw records, locators, source URLs, local/export paths, validators and exception text. Canonical links drop userinfo, query and fragment, reject local/private network targets and are limited to the matching platform's official domain boundary.
4. Added UUID-only archive GET/HEAD. A preview requires verified/exported state, complete SHA-256 and size metadata, the exact `archive/sha256/<prefix>/<digest>.<extension>` path, a regular non-link single-link read-only file and a matching digest.
5. Verification and streaming retain one descriptor. Windows uses a native read handle that permits read sharing but denies write/delete sharing; POSIX retains no-follow opening and identity checks. Both paths recheck identity, size, permissions and timestamps before any yielded chunk, and every normal, error, consumer-abort and ASGI-disconnect path closes ownership.
6. Added read-only existing-root filesystem primitives so GET/HEAD never create a missing archive directory. A root-removal race fails closed without filesystem repair or database mutation.
7. Added one strict GET byte range with 200/206/416 behavior, ASCII case-insensitive `bytes`, prefix/open-ended/suffix forms and exact headers. The representation is fully validated before Range evaluation. `If-Range` permits 206 only for an exact strong current ETag; stale, weak, date or malformed validators fall back to full 200. RFC 9110 requires HEAD to ignore Range, so HEAD validates the full representation and returns matching full metadata with no body.
8. Missing, corrupt, unsafe and not-ready archives return fixed safe 409 results with the existing `POST /api/v1/assets/{asset_id}/download` durable `asset-download` recovery link. No reset shortcut, new Operation kind or preview-side persistence was added.
9. Upgraded Contents, Assets and Library to bounded server-side filtering, request-race protection, plain-text detail modals, ordered asset actions, safe inline or new-tab previews, persistent recovery submission and author drill-down. Library no longer requests or displays the configured host export path.
10. Unified the public verified MIME boundary with the archive allowlist, preserved PDF/SRT/VTT values, kept unknown values out of JSON, and limited inline Web rendering to a smaller exact browser-safe set.

## Review hardening

An independent backend review found six P1 and four P2 issues in the first implementation: a Windows same-length mutation bypass, disconnect cleanup, MIME divergence, Range precedence, ranged HEAD, missing `If-Range`, Range token casing, read-side directory creation, changed legacy ordering and ASGI-level HEAD bodies. All ten were fixed and the second review found no remaining P0/P1/P2.

An independent Web review then found two P1 issues—same-route query navigation left stale filters and detail modals did not manage keyboard focus—and one P2 action-gating issue. All were fixed with `afterNavigate` state synchronization, modal initial/trapped/restored focus plus nested inert ownership, and strict `allowed_actions` recovery gating. Its additional browser-navigation P2 observation led to the official-domain canonical-link boundary above.

## Verification so far

- Security, archive, explorer and API regression selection: 228 passed with one existing Starlette/httpx deprecation warning.
- Whole-repository Ruff and format checks pass across 199 Python files; strict mypy passes 96 source files.
- Web Prettier passes; 50 Vitest tests in 5 files pass; Svelte/TypeScript reports 0 errors and 0 warnings; the adapter-static production build passes.
- A local static-build browser smoke proves Assets/Contents same-route query clearing and browser-back restoration, modal initial focus, forward/reverse Tab wrapping, background inerting, Escape close and trigger-focus restoration. The API was intentionally absent in this UI-only smoke, so it grants no backend or live qualification.
- The frozen complete Python suite passes 2456 tests with 3 Windows-inapplicable skips and one existing warning in 479.63 seconds. Compileall, wheel/sdist, 474-document, two-upstream, tracked-output, local-path and whitespace gates pass. Focused selections overlap and are not added together.

## Deferred scope and external gates

Media-library tree browsing, Emby/Jellyfin connection configuration, scan triggering and qualification remain 0054. Authentication, destructive deletion, retention and orphan cleanup remain 0055; final migration/release remains 0056.

Execution 0047 remains P0. Linux persistence/backup/process evidence, all real platform login/crawl/CDN rows and real Emby/Jellyfin rescan/playback remain `NOT_RUN`; no local catalogue test changes those qualifications.
