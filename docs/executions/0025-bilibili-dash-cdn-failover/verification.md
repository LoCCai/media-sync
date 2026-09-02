**English** | [中文](verification.zh.md)

# Execution 0025 verification

- Status: Frozen offline scope passes all final gates; authenticated/live qualification `NOT_RUN`
- Date: 2026-09-02
- Predecessor: `46905a50bbba19b7c4b74a0f7a274d5efdb013d6`
- Plan commit: `8e9467d2ecbedfd8f87e8d1d2ffb5a66d6d15591`
- Implementation commit: `fe45abcb7262c3d70437aff82a05609e43902af4`

## Baseline

| Check | Result |
| --- | --- |
| Execution 0024 focused regression | `PASS — 456 passed in 66.47s` |
| Execution 0024 complete suite | `PASS — 1780 passed, 1 skipped in 333.43s` |
| Production ffmpeg/ffprobe closeout rerun | `PASS — 1 passed in 1.83s` |
| Documentation/upstreams/repository audit | `PASS — 112 Markdown files; 2 locked clean checkouts; tracked 300; untracked 0; tracked runtime/upstream 0 |
| Local/tracking/GitHub reconciliation | `PASS — 46905a50bbba19b7c4b74a0f7a274d5efdb013d6` |

## Implemented evidence

| Scope | Result |
| --- | --- |
| Candidate order and bound | `PASS` — each DASH component uses validated `primary + 0..8 backups` in source order; primary success causes zero backup DNS/HTTP |
| Eligible failover | `PASS` — DNS, timeout, transport, interruption, HTTP and partial Range incompatibility advance candidates under one deadline |
| Fail-closed classes | `PASS` — forbidden/mixed network policy, redirect/header/encoding, chunk/size, filesystem, probe and mux failures do not touch later candidates |
| Strict partial continuity | `PASS` — backup append requires exact offset, total length and validator; interruption resumes across candidates; mixed invalid candidates preserve bytes; full-pass `200`/bad-`206` rejection precedes bounded discard/restart |
| Exhaustion semantics | `PASS` — all `401`/`403` returns `locator_refresh_auth_expired`; mixed exhaustion returns the last fixed error without URL/host disclosure |
| Independent components | `PASS` — video primary `503` and audio primary `403` independently reach their backups, are probed, combined within the byte cap and muxed once |
| Production-process composition | `PASS` — backup H.264/AAC components traverse SQLite → mock public DNS/HTTP → production ffprobe → production ffmpeg → final ffprobe → SHA-256 archive → Emby/NFO/source; final MP4 has video+audio |
| Ephemeral boundary | `PASS` — signed primary/backup values, private fields and winning indices are absent from retained SQLite, Job, runtime, work, archive and export trees and from errors |
| Compatibility and recovery | `PASS` — no-backup, silent DASH, single-/multi-page progressive, failed mux, published-final recovery, cleanup and zero-work replay remain green |

## Test and quality gates

| Check | Command | Result |
| --- | --- | --- |
| Focused implementation regression | `uv run pytest tests/unit/test_media_locator.py tests/unit/test_mediacrawler_refresh.py tests/unit/test_media_mux.py tests/unit/test_media_dash_downloader.py tests/unit/test_media_downloader.py tests/unit/test_cli.py tests/contract/test_mediacrawler_detail_refresh.py tests/integration/test_asset_download_orchestration.py tests/integration/test_pipeline_runtime.py tests/integration/test_bilibili_playable_pipeline.py tests/integration/test_bilibili_multipart_progressive_pipeline.py tests/integration/test_bilibili_dash_pipeline.py -q` | `PASS — 466 passed in 66.96s` |
| DASH candidate unit boundary | `uv run pytest -q tests/unit/test_media_dash_downloader.py` | `PASS — 17 passed in 1.43s` |
| Production backup ffmpeg/ffprobe composition | `uv run pytest -q tests/integration/test_bilibili_dash_pipeline.py` | `PASS — 1 passed in 1.74s` on the documentation-closeout rerun (`1.78s` on the implementation run); final archive and Emby MP4 contain video+audio |
| Complete suite | `uv run pytest -q` | `PASS — 1790 passed, 1 skipped in 331.33s`; skip is the Windows-inapplicable POSIX mode-bit boundary |
| Ruff and format | `uv run ruff check .`; `uv run ruff format --check .` | `PASS — all checks; 286 files already formatted |
| Strict mypy | `uv run mypy --strict src` | `PASS — no issues in 84 source files |
| Compileall and build | `uv run python -m compileall -q src/media_sync`; `uv build` | `PASS — wheel and source distribution built |
| Documentation and upstream locks | `uv run python scripts/check_docs.py`; `uv run python scripts/check_upstreams.py` | `PASS — 116 Markdown files; 2 locked checkouts |
| Git/upstream/diff audit | explicit status, tracked/runtime/upstream and diff checks | `PASS — tracked 304; untracked 0; tracked runtime/upstream 0; upstream diff 0; both upstream dirty counts 0 |

No coverage run is claimed.

## Git reconciliation

Implementation `fe45abcb7262c3d70437aff82a05609e43902af4` is pushed and reconciled across local `main` and `origin/main`. The commit containing this record is the bilingual documentation closeout; its self-referential SHA is intentionally left to Git history.

## Live qualification

| Row | Result |
| --- | --- |
| Real Bilibili QR/Cookie login | `NOT_RUN` |
| Authenticated DASH detail/play API | `NOT_RUN` |
| Real primary/backup bilivideo CDN behavior | `NOT_RUN` |
| Real Emby/Jellyfin scan and playback | `NOT_RUN` |

Offline evidence cannot imply these rows, progressive backup failover or complete Bilibili support.
