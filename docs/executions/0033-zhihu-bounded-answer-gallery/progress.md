**English** | [中文](progress.zh.md)

# Execution 0033 progress

- Status: Frozen offline bounded Zhihu answer-gallery scope implemented and gated; live rows remain `NOT_RUN`
- Date: 2026-09-03
- Plan commit: `92651bc` (documentation baseline)

## Delivered

1. `_capture_answer` now materializes one complete ordered tuple for 2–64 images (per-image frozen attribute-priority selection, static validation, pairwise distinctness) while the exactly-one-image shape keeps the 0019 v1 capture byte-compatible; forbidden media, invalid or duplicated images and galleries above 64 capture nothing.
2. One new private v2 field carries the tuple with strict v1 collision checks, recursive pre-persistence stripping and normalizer materialization of ARTICLE with `{content_id}:image:0..N-1` IMAGE assets; dual-field, malformed, single-item and above-bound payloads quarantine fail-closed.
3. The lazy adapter refresh binds the complete persisted sibling tuple through a new `zhihu_image_source_hints` context field assembled and validated by the application layer; missing, added, reordered, replaced or duplicated drift closes as `locator_refresh_schema_changed`, and v1 single-image behavior stays equivalent (one pre-existing drift expectation updated from `asset_mismatch` to the sibling-bound `schema_changed`).
4. Coverage: capture matrix through the real child process, normalizer outcomes, refresh binding and drift, and one production SQLite → detail refresh → mock DNS/HTTP → static PNG sniff gate → SHA-256 archive → Emby poster/backdrop/two gallery images/body/NFO composition with zero-work replay and durable non-retention.

## Verification snapshot

See [`verification.md`](verification.md) for the exact commands, exit codes and gate outputs.

## Not done

Articles, zvideo, animated drift beyond the static gate, same-ID byte replacement, richer HTML media and every live qualification row remain deferred or `NOT_RUN`.
