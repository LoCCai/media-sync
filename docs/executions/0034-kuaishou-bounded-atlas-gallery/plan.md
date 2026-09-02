**English** | [中文](plan.zh.md)

# Execution 0034 plan

- Status: Executed and verified
- Plan date: 2026-09-03
- Predecessor: `e9d1fcdb8970b5a10f84e3947e1570159c9f9011`
- Database migration: None planned
- Plan commit: recorded in the closeout index; never embedded in this file
- Implementation commit: recorded in the closeout index; never embedded in this file

## Baseline and audit

Execution 0033 is clean, pushed and reconciled at `e9d1fcd`. The pinned Kuaishou store flattens `video_item.photo` into `video_id`/`video_cover_url`/`video_play_url` and discards `ext_params`, so atlas locators disappear at the `update_kuaishou_video` boundary exactly like Weibo's `page_info` did. The 0031 Weibo capture-shim template (ContextVar boundary, private-field injection, collision checks), the DY-gallery normalization/refresh patterns and the platform-neutral static-image gate and Emby gallery publication are all proven. `_supported_kinds(KS)` already excludes IMAGE only by omission.

Baseline gates recorded before implementation: 0033 focused regression `538 passed in 71.18s`, complete `1984 passed, 1 skipped in 336.62s`, Ruff/format clean, strict mypy clean, docs (296 files) and upstreams (2 locked checkouts) passing.

## Delivery sequence

1. Add `kuaishou_media.py` with the closed `validate_ks_image_url`, the `_capture_atlas` pass over the exact `update_kuaishou_video` boundary and `install_kuaishou_media_capture` (checkout-verified `store.kuaishou` modules, marker-safe reinstall, private-field collision checks).
2. Install the shim in both the scheduled handler child and the detail child; extend `_normalize_ks` with the frozen gallery branch (exact list-of-strings shape, 1–64 bound, full revalidation, optional COVER companion) and add the field to the recursive strip set.
3. Add `AssetKind.IMAGE` to the KS refresh support set so the generic per-asset path binds each gallery position and closes path drift as `locator_refresh_asset_mismatch`.
4. Add contract coverage through a real-store fake checkout (atlas vs ordinary video vs drifted shapes) plus normalizer fail-closed outcomes and refresh compositions.
5. Add one production SQLite → detail refresh → mock DNS/HTTP → static PNG probes → SHA-256 archive → Emby poster/backdrop/gallery/NFO/source composition with zero-work replay and durable non-retention.
6. Run focused and complete suites plus Ruff, format, strict mypy, compileall, build, docs, upstream, diff and repository audits; update the four execution documents and root truth, then create bilingual implementation/closeout commits, push and reconcile GitHub.

## Planned commit sequence

1. Documentation baseline
2. Implementation
3. Documentation closeout

`.upstream` remains excluded, unmodified and clean.
