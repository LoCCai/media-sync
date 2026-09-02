**English** | [中文](plan.zh.md)

# Execution 0032 plan

- Status: Executed and verified
- Plan date: 2026-09-02
- Predecessor: `2e9e3b5378dd8966f56e068dced5f799e115f92b`
- Database migration: None planned
- Plan commit: `286dac9b78710c8fd99e9ec8f260d0fac6d4f5ac`
- Implementation commit: `95758c2e6b3623a02f3a035590934da816e3cc6f`

## Baseline and audit

Execution 0031 is clean, pushed and reconciled at `2e9e3b5`. The pinned Douyin store already joins `_extract_note_image_list` into the scalar `note_download_url` (comma-separated, non-watermarked `url_list[-1]` per image), and `_normalize_dy` already splits that field into IMAGE (one) or GALLERY (many) with `{aweme_id}:image:{position}` assets. `_supported_kinds(DY)` already includes IMAGE, the DEFAULT-profile refresh path is per-asset, the structural static-image gate and the Emby gallery publication are platform-neutral, and 0015 left exactly the bounded multi-image end to end plus any strictness unqualified: the current parser silently drops invalid candidates and imposes no gallery bound.

Baseline gates recorded before implementation: 0031 focused regression `302 passed in 4.04s`, detail contracts `100 passed in 70.92s`, complete `1956 passed, 1 skipped in 408.57s`, Ruff/format clean, strict mypy clean, docs (280 files) and upstreams (2 locked checkouts) passing.

## Delivery sequence

1. Add a strict `_dy_note_images` parser for the frozen comma-joined shape: string or JSON-frozen sequence input, per-item string/no-embedded-comma/valid-URL checks, closed duplicate handling and the 1–64 bound; drift raises `RecordNormalizationError` instead of dropping items, while empty/absent fields stay empty.
2. Keep the video/music/cover fields on the established tolerant `_dy_url_list` parsing and the pinned crawler's image-over-video choice unchanged.
3. Add ingestion-contract coverage for 1/2/64-image materialization, the 65-image bound, per-item drift (non-string, embedded comma, invalid URL, duplicates) and the empty-field fallback.
4. Add refresh coverage proving each gallery position re-resolves its current signed URL through one exact numeric-ID detail run and that path drift closes fail-closed.
5. Add one production SQLite → refresh → mock DNS/HTTP → static JPEG/PNG probes → SHA-256 archive → Emby poster/backdrop/gallery/NFO/source composition with zero-work replay and durable non-retention.
6. Run focused and complete suites plus Ruff, format, strict mypy, compileall, build, docs, upstream, diff and repository audits; update the four execution documents and root truth, then create bilingual implementation/closeout commits, push and reconcile GitHub.

## Planned commit sequence

1. Documentation baseline
2. Implementation
3. Documentation closeout

`.upstream` remains excluded, unmodified and clean.
