**English** | [中文](progress.zh.md)

# Execution 0037 progress

- Status: Frozen offline bounded XHS multi-video scope implemented and gated; live rows remain `NOT_RUN`
- Date: 2026-09-03
- Plan commit: `d858147` (documentation baseline)

## Delivered

1. `_normalize_xhs` now quarantines records whose video field splits into more than 16 candidates while keeping the established tolerant comma-split parsing otherwise; 1–16 candidates materialize ordered `{note_id}:video:0..N-1` VIDEO assets.
2. `_validated_xhs_media_scalar` widened from exactly-one to the bounded 1–16 ordered distinct tuple, and `_validate_xhs_creator_video_target` now binds the complete video tuple — count, positions 0..N-1 and exact URL order — instead of requiring one video at position 0.
3. One stale 0018-era reject parameter (two distinct video URLs) was removed from the ambiguity gate and replaced by per-position acceptance and drift coverage: each position resolves its current URL through the creator fallback, replaced paths close as `locator_refresh_asset_mismatch` and 17-candidate scalars close as `locator_refresh_schema_changed`.
4. Integration coverage: a two-video note materializes two bounded assets, downloads both through the DEFAULT profile with MP4 probes, archives distinct SHA-256 digests and publishes two Emby episodes with zero-work replay; the 17-candidate record quarantines during normalization.

## Verification snapshot

See [`verification.md`](verification.md) for the exact commands, exit codes and gate outputs.

## Not done

Live-photo semantics, animated drift, same-ID byte replacement and every live qualification row remain deferred or `NOT_RUN`.
