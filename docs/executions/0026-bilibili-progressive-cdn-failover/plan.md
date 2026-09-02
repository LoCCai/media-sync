**English** | [中文](plan.zh.md)

# Execution 0026 plan

- Status: Executed for the frozen offline scope
- Plan date: 2026-09-02
- Predecessor: `7cb84fc6c93b832492b95513d9cb6a9708ee6cc9`
- Plan commit: `0694934bc9230151a85c040a061d6e704dffc4fc`
- Implementation commit: `190488f77d1704492cc148b890d6f9ae16d84f84`
- Database migration: None required or added

## Baseline and audit

Execution 0025 is clean and reconciled at `7cb84fc`. `ResolvedLocator` already validates, bounds, deduplicates and hides one primary plus at most eight backup URLs. DASH uses those ordered candidates with strict partial continuity, but `_bili_playback_result` discards progressive `durl[0].backup_url`, the private progressive bridge carries only the primary, and `_download_locked` requests only `locator.url`. Stable fingerprints and partial sidecars are already URL-free, so no schema or migration is required.

The pinned MediaCrawler checkout still selects only a primary progressive URL. The pinned bili-sync-up analyzer models DASH primary/backups and its stream cache exposes generic `backup_urls`, while mixed `durl` currently remains primary-only; both are read-only design evidence and will not be copied or modified. Baseline gates are Execution 0025 focused `466 passed in 66.96s`, complete `1790 passed, 1 skipped in 331.33s`, production backup-path composition `1 passed in 1.74s`, 116 Markdown files, two locked clean checkouts, 304 tracked files and zero untracked/runtime/upstream tracked files.

## Delivery sequence

1. Add one private single-page progressive backup field and extend the multipart private payload with `backup_urls`; include the new field in collision detection and recursive stripping while preserving historical primary-only payloads.
2. Parse `durl[0]` primary and backup aliases through a closed helper, enforce the existing eight-backup/distinct/URL constraints, and return a repr-safe runtime `ResolvedLocator`.
3. Extract a shared ordered candidate-pass helper from the proven DASH path and use it for ordinary resolved locators. Preserve primary-first ordering, one deadline, exact partial fences, whole-pass restart and fail-closed error classes.
4. Preserve adapter-refresh semantics by re-resolving once only after an all-`401`/`403` pass; reject refreshed DASH/schema drift on the progressive path and retain direct-locator behavior.
5. Add parser/normalizer/unit coverage for aliases and invalid shapes, primary short-circuit, ordered backup success, DNS/HTTP exhaustion, network-policy/limit fail-closed behavior, strict cross-candidate resume, whole-pass restart and fresh-detail auth rotation.
6. Extend Bilibili progressive SQLite → exact-CID detail → failed primary → backup HTTP → probe → SHA-256 archive → Emby composition and retained-tree scans, for both single-page compatibility and multipart part publication as appropriate.
7. Run focused and complete suites plus Ruff, format, strict mypy, compileall, build, docs, upstream, diff and repository audits; update the four execution documents and root truth, then create bilingual implementation/closeout commits, push and reconcile GitHub.

## Planned commit sequence

1. Documentation baseline
2. Implementation
3. Documentation closeout

`.upstream` remains excluded, unmodified and clean.
