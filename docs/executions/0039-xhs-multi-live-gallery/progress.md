**English** | [中文](progress.zh.md)

# Execution 0039 progress

- Status: Implementation complete; full-suite verification deferred to the Linux deployment host
- Date: 2026-09-03

## Completed

- `xhs_live.py`: v2 list capture with `XHS_LIVE_VIDEO_LIST_FIELD` and `XHS_LIVE_MAX_PAIRS = 16`; 2–16 all-live notes capture the ordered URL tuple, partial coverage captures nothing, and the one-image v1 shape stays byte-compatible. Public `capture_xhs_live_fields` exposes the capture matrix to tests.
- `normalizers.py`: paired-gallery branch materializes `MIXED` with ordered `{note}:image/video:{position}` assets, requires equal image/URL counts, an empty `video_url` and exact XHS-CDN URLs; both private fields are stripped recursively and carrying both versions fails closed.
- `refresh.py`: the creator-fallback `normal`-type branch now binds 1–16 ordered IMAGE+VIDEO pairs with per-pair live-URL revalidation instead of only the single pair.
- Tests: capture matrix (`tests/unit/test_xhs_live_capture.py`), contract drift matrix (ingestion), per-position refresh resolution plus URL-drift rejection, and a full SQLite → detail → download ×4 → archive → two-episode Emby composition with zero-work replay.

## Deviations and decisions

- Per operator direction, product verification moved from the Windows workstation to a Linux Docker deployment; this workstation ran only static gates, `pytest --collect-only` over the touched files, and (before the direction changed) the 0038 focused regression plus the new capture matrix — 9 passed, 0038 ingestion subset 8 passed, refresh subset 3 passed, 0038 integration 1 passed. The complete suite including the new multi-live tests must run on Linux before this record is pushed as a final closeout.

## Remaining

- Run the complete suite, Ruff/format, mypy, compileall, build, docs and upstream gates on the Linux host and record exact numbers before the final push.
