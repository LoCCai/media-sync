**English** | [中文](plan.zh.md)

# Execution 0033 plan

- Status: Executed and verified
- Plan date: 2026-09-03
- Predecessor: `41508b1cc57672aa9e18252498d10d98bc371b90`
- Database migration: None planned
- Plan commit: recorded in the closeout index; never embedded in this file
- Implementation commit: recorded in the closeout index; never embedded in this file

## Baseline and audit

Execution 0032 is clean, pushed and reconciled at `41508b1`. The 0019 Zhihu shim already parses every `<img>` candidate through the frozen attribute priority and rejects forbidden media, but captures only the exactly-one-image shape; multi-image answers fall back to TEXT. The Tieba 0020–0022 sibling-hint refresh binding (context tuple, app-layer sibling assembly, exact drift closure) is the proven template, and the static-image gate, per-asset refresh, SHA-256 archive and Emby gallery publication are platform-neutral.

Baseline gates recorded before implementation: 0032 focused regression `316 passed in 5.09s`, DB-ingestion contracts `25 passed in 2.64s`, complete `1971 passed, 1 skipped in 390.84s`, Ruff/format clean, strict mypy clean, docs (288 files) and upstreams (2 locked checkouts) passing.

## Delivery sequence

1. Extend `_capture_answer` with the bounded 2–64 ordered tuple path (per-image attribute-priority selection, static validation, pairwise distinctness) and one new private v2 field with strict v1 collision checks.
2. Extend `_normalize_zhihu` with the v2 branch (exact list-of-strings shape, 2–64 bound, full revalidation, dual-field quarantine) and add the field to the recursive strip set.
3. Mirror the Tieba sibling binding: `MediaCrawlerRefreshContext` carries `zhihu_image_source_hints`, the app layer assembles and validates the complete sibling tuple from SQLite, and the refresher closes missing/added/reordered/replaced/duplicated drift as `locator_refresh_schema_changed` while v1 single-image behavior stays equivalent.
4. Add unit/contract coverage for the capture matrix (1/2/64 capture, 65/invalid/duplicate/forbidden-media no-capture), normalizer outcomes, refresh binding and drift, real-child compositions and durable non-retention.
5. Add one production SQLite → refresh → mock DNS/HTTP → static JPEG/PNG probes → SHA-256 archive → Emby poster/backdrop/gallery/body/NFO/source composition with zero-work replay.
6. Run focused and complete suites plus Ruff, format, strict mypy, compileall, build, docs, upstream, diff and repository audits; update the four execution documents and root truth, then create bilingual implementation/closeout commits, push and reconcile GitHub.

## Planned commit sequence

1. Documentation baseline
2. Implementation
3. Documentation closeout

`.upstream` remains excluded, unmodified and clean.
