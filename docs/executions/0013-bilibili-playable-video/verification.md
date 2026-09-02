**English** | [中文](verification.zh.md)

# Execution 0013 verification

- Status: Offline implementation and closeout gates pass; live qualification remains `NOT_RUN`
- Environment: Windows, local workspace, Python environment resolved by `uv`
- Evidence date: 2026-08-31
- Plan commit: `46323bd`
- Implementation commit: `dd6cfec`

## Starting baseline

| Check | Command | Exit | Result |
| --- | --- | ---: | --- |
| Existing ingestion, detail refresh, locator/network/downloader, Emby layout and offline pipeline | `uv run pytest -q tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/unit/test_mediacrawler_refresh.py tests/unit/test_media_locator.py tests/unit/test_media_network.py tests/unit/test_media_downloader.py tests/unit/test_emby_layout.py tests/integration/test_offline_media_pipeline.py tests/integration/test_scheduled_offline_pipeline.py` | `0` | `PASS` — `158 passed in 6.47s` |

This was predecessor-only evidence: it proved the prior Bilibili cover path and platform-neutral media pipeline, not the new video slice. Every delivered claim below comes from post-implementation evidence.

## Focused implementation evidence

| Scope | Command | Exit | Result |
| --- | --- | ---: | --- |
| Discovery, exact aid/CID and single-`durl` child contract, nullable-slot application/runtime boundary, private normalization bridge, Bilibili network profile, downloader/re-resolution and offline playable-to-Emby pipeline | `uv run pytest -q tests/contract/test_mediacrawler_detail_refresh.py tests/contract/test_mediacrawler_ingestion.py tests/integration/test_mediacrawler_download_runtime.py tests/integration/test_bilibili_playable_pipeline.py tests/unit/test_domain.py tests/unit/test_media_downloader.py tests/unit/test_media_locator.py tests/unit/test_media_network.py tests/unit/test_mediacrawler_refresh.py` | `0` | `PASS` — `223 passed in 19.85s` |

The focused gate proves a stable `NULL`-source `<aid>:video:0` slot, exact Subscription-bound selection, aid/first-CID validation, exactly one valid progressive `durl`, fixed temporary/unsupported/invalid outcomes, memory-only URL bridging, raw stripping, cover compatibility, fixed UA/Referer/Origin without Cookie or Authorization, redirect/resume and one 401/403 re-resolution, synthetic bytes through controlled probing/archive/Emby `.mp4`, and idempotent replay. Near-miss nullable slots and non-null Bilibili video hints fail before secret lookup or child construction.

## Complete root closeout gates

| Check | Command | Exit | Result |
| --- | --- | ---: | --- |
| Complete offline suite | `uv run pytest -q` | `0` | `PASS` — `1199 passed, 1 skipped in 263.14s` |
| Lint | `uv run ruff check .` | `0` | `PASS` — `All checks passed!` |
| Format | `uv run ruff format --check .` | `0` | `PASS` — `212 files already formatted` |
| Strict typing | `uv run mypy src/media_sync` | `0` | `PASS` — `Success: no issues found in 77 source files` |
| Documentation links | `uv run python scripts/check_docs.py` | `0` | `PASS` — `Documentation links OK (68 Markdown files checked)` |
| Pinned upstreams | `uv run python scripts/check_upstreams.py` | `0` | `PASS` — `Upstreams OK (2 locked checkouts verified)` |
| Source distribution and wheel | `uv build` | `0` | `PASS` — built `dist\media_sync-0.1.0.tar.gz` and `dist\media_sync-0.1.0-py3-none-any.whl` |
| Patch whitespace | `git diff --check` and `git diff --cached --check` | `0` | `PASS` — no output |

The single skip is `tests/contract/test_mediacrawler_supervision.py:556`: POSIX mode bits are not the Windows ACL boundary. It is environment-inapplicable, not a failed feature. No coverage command ran, so execution 0013 makes no coverage claim.

## Retained and ephemeral-data audit

The final read-only PowerShell audit enumerated `git ls-files`, standard untracked files, and every real file below ignored `.media-sync` and `dist`. It rejected tracked/untracked runtime or credential filenames, constructed the execution sentinel from two non-secret literals, and byte-scanned Git-visible plus runtime/build files without printing matched values or paths. The frozen `.media-sync/verification/0007-closeout-sentinel-root` and `0008-closeout-sentinel-root` were retained and never removed or rewritten.

| Audit | Exit | Final counts |
| --- | ---: | --- |
| Git/runtime/build inventory and exact ephemeral-marker scan | `0` | `tracked=230`; `untracked=0`; `tracked_forbidden=0`; `suspicious_untracked=0`; `runtime_and_build_files=914`; `git_ephemeral_marker_hits=0`; `runtime_ephemeral_marker_hits=0` |

The offline end-to-end test separately scans its disposed SQLite database and sidecars, MediaCrawler runtime, download work tree, archive and Emby library for the signed URL and private bridge value. It also verifies durable JSON, object `repr`, retained attempt data and emitted metadata contain none of them.

## Live qualification matrix

No real browser, QR scan, account credential, creator endpoint, WBI play-url request, CDN transfer, FFmpeg probe against platform bytes, or Emby/Jellyfin server was used.

| Platform | Real login/session | Real creator sync | Real signed CDN media | Real Emby/Jellyfin scan/playback |
| --- | --- | --- | --- | --- |
| XHS | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| Douyin | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| Kuaishou | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| Bilibili | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| Weibo | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| Tieba | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| Zhihu | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |

## Known limitation and exclusions

Forward JSONL has no CID, so the durable identity remains the logical `<aid>:video:0` slot. Each unresolved lookup validates the current first CID, but a later same-aid first-CID replacement cannot automatically bump the Asset generation or invalidate already-verified bytes. CID-aware discovery and replacement belong with multi-page identity.

DASH audio/video selection and muxing, FLV remux, multi-segment concatenation, multiple pages, subtitles, danmaku, backup-URL failover, bangumi/paid/live media, broader seven-platform downloadable media, REST and deployment/HA work remain deferred. These are unsupported or unimplemented scope, not successful qualification claims.
