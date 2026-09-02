**English** | [中文](plan.zh.md)

# Execution 0025 plan

- Status: Executed for the frozen offline scope
- Plan date: 2026-09-02
- Predecessor: `46905a50bbba19b7c4b74a0f7a274d5efdb013d6`
- Plan commit: `8e9467d2ecbedfd8f87e8d1d2ffb5a66d6d15591`
- Implementation commit: `fe45abcb7262c3d70437aff82a05609e43902af4`
- Database migration: None required or added

## Baseline and audit

Execution 0024 is clean and reconciled at `46905a5`. `ResolvedLocator` already validates one primary plus at most eight distinct backups, hides all URLs from repr and exposes the ordered runtime-only `.urls` tuple. Strict DASH detail/normalization carries those candidates in memory, but `_download_component` currently requests only `.url`; a `401`/`403`, transport failure or HTTP failure stops without trying a backup. Component sidecars are already URL-free and fenced by durable locator fingerprint, DASH selection and role. The pinned bili-sync-up `Stream::urls()` similarly yields primary plus backups and its downloader attempts candidates sequentially; its checkout remains read-only evidence, not copied implementation.

Baseline gates remain `456 passed in 66.47s` focused, `1780 passed, 1 skipped in 333.43s` complete, and the documentation-closeout production ffmpeg/ffprobe composition rerun passes `1 passed in 1.83s`. Documentation, upstream, diff and repository audits pass with 112 Markdown files, two locked clean checkouts, 300 tracked files and zero untracked/runtime/upstream tracked files.

## Delivery sequence

1. Add a closed internal candidate-pass helper for DASH components. Preserve primary-first ordering, one shared deadline and the existing component byte/restart limits without changing public locator or database schemas.
2. Classify only candidate-local DNS/transport/interruption/HTTP/Range failures as failover-eligible. Preserve immediate failure for network-policy, resource-limit, local capability, filesystem, probe and mux errors.
3. Reload partial state between candidates, require exact validator/length/offset continuity and defer destructive restart until all candidates reject the current partial. Preserve all-auth exhaustion as `locator_refresh_auth_expired`.
4. Add unit coverage for primary short-circuit, video/audio backup success, mixed/all-auth exhaustion, forbidden-network fail-closed behavior, cross-candidate Range resume and whole-pass restart. Keep existing no-backup interruption, failed mux and recovery tests green.
5. Extend the real local H.264+AAC integration composition so primary component endpoints fail and backup endpoints reach production ffprobe → ffmpeg → final ffprobe → SHA-256 archive → Emby, while whole-tree scans prove all signed candidates remain absent.
6. Run focused and complete suites plus Ruff, format, strict mypy, compileall, build, docs, upstream, diff and retained-artifact audits; update root truth documents, create bilingual implementation/closeout commits, push and reconcile GitHub.

## Planned commit sequence

1. Documentation baseline
2. Implementation
3. Documentation closeout

`.upstream` remains excluded, unmodified and clean.
