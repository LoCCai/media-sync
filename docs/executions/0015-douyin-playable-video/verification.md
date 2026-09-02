**English** | [中文](verification.zh.md)

# Execution 0015 verification

- Status: Offline implementation and closeout gates pass; live qualification remains `NOT_RUN`
- Environment: Windows, local workspace, Python environment resolved by `uv`
- Evidence date: 2026-08-31
- Plan commit: `76b1973`
- Implementation commit: `95d314d`

## Starting baseline

| Check | Command | Exit | Result |
| --- | --- | ---: | --- |
| Existing ingestion, detail, refresh/runtime, downloader/network, Emby application/layout and Bilibili/Kuaishou playable compositions | `uv run pytest -q tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_mediacrawler_download_runtime.py tests/unit/test_media_downloader.py tests/unit/test_media_locator.py tests/unit/test_media_network.py tests/unit/test_emby_layout.py tests/integration/test_emby_application.py tests/integration/test_bilibili_playable_pipeline.py tests/integration/test_kuaishou_playable_pipeline.py` | `0` | `PASS` — `269 passed in 34.05s` |

This baseline proves predecessor Douyin unit refresh/process cases and both existing playable-platform pipelines. It does not prove Douyin durable raw closure, exact composed runtime, video+cover transfer, Emby primary-media layout or platform replay.

## Focused implementation evidence

| Scope | Command | Exit | Result |
| --- | --- | ---: | --- |
| Douyin discovery/raw, pinned detail process, exact Account/Subscription refresh, video+cover download/probe/archive, Emby publication, replay and Kuaishou regression | `uv run pytest -q tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_mediacrawler_download_runtime.py tests/integration/test_douyin_playable_pipeline.py tests/integration/test_kuaishou_playable_pipeline.py tests/unit/test_media_downloader.py tests/unit/test_media_locator.py tests/unit/test_media_network.py tests/unit/test_emby_layout.py` | `0` | `PASS` — `231 passed in 41.79s` |

The focused gate proves exact video/cover remote IDs, positions, MIME/source hints and provenance; query/userinfo/fragment/nested sentinels absent from normalized raw, ORM and disposed SQLite/sidecars across all four Douyin media fields; comma-list normalization into an ordered flat sequence; and accepted transient Asset URLs preserved in memory. A real fake checkout goes through `MediaCrawlerDetailProcessRunner` for the pure-ID process contract. The composed E2E separately uses a fake detail runner, mock public DNS/HTTP, synthetic MP4/PNG bytes and a controlled video probe; it does not use a real account, Douyin endpoint, CDN, FFmpeg process or media server.

Exact lazy runtime binding covers Account, Subscription and `AssetRefreshSource`; existing negative cases close missing, drifted, duplicate and wrong-source selections before transfer. Media HTTP uses `MediaRequestProfile.DEFAULT` without Cookie, Authorization, Referer, Origin or caller-controlled headers. Video receives mandatory controlled probing; video and cover receive SHA-256 archive identities and local Emby `.mp4`/poster/NFO/source output. Query-only replay preserves generation and re-reads live counters to prove no second fake detail runner, detail call, HTTP request, DNS resolution or probe.

## Complete root closeout gates

| Check | Command | Exit | Result |
| --- | --- | ---: | --- |
| First complete offline suite | `uv run pytest -q` | `1` | `FAIL` — `1208 passed, 1 skipped, 1 failed in 365.17s`; exposed the account-lock readiness race described below |
| Final complete offline suite | `uv run pytest -q` | `0` | `PASS` — `1209 passed, 1 skipped in 438.39s` |
| Lint | `uv run ruff check .` | `0` | `PASS` — `All checks passed!` |
| Format | `uv run ruff format --check .` | `0` | `PASS` — `222 files already formatted` |
| Strict typing | `uv run mypy src/media_sync` | `0` | `PASS` — `Success: no issues found in 77 source files` |
| Documentation links | `uv run python scripts/check_docs.py` | `0` | `PASS` — `Documentation links OK (76 Markdown files checked)` |
| Pinned upstreams | `uv run python scripts/check_upstreams.py` | `0` | `PASS` — `Upstreams OK (2 locked checkouts verified)` |
| Source distribution and wheel | `uv build` | `0` | `PASS` — built `dist\media_sync-0.1.0.tar.gz` and `dist\media_sync-0.1.0-py3-none-any.whl` |
| Patch whitespace | `git diff --check` and `git diff --cached --check` | `0` | `PASS` — no output |

### First-run failure and repair

The first full run failed `tests/contract/test_mediacrawler_bridge.py::test_account_profile_lock_serializes_same_account`. Its former readiness signal polled for generated JSONL, which did not establish that the first runner had already acquired the per-account lock on a cold Windows start. The contract now monkeypatches the same runner and waits on a `threading.Event` reached inside the lock-owned `_run_locked` path before starting the competing call. This makes lock ownership, not file timing, the readiness authority.

Windows cold process startup and real-time scanning could also consume the former four-second wall-clock budget before a byte/item/file/line/tree watchdog became authoritative. Non-timeout watchdog cases now use ten seconds; the dedicated timeout case retains its explicit 0.8-second limit. The final full run passed, so the repair does not weaken the timeout contract.

The single skip is `tests/contract/test_mediacrawler_supervision.py:556`: POSIX mode bits are not the Windows ACL boundary. It is environment-inapplicable, not a failed feature. No coverage command ran, so execution 0015 makes no coverage claim.

## Retained and ephemeral-data audit

The read-only audit enumerates tracked and standard-untracked files plus every real file below ignored `.media-sync` and `dist`. It rejects tracked/untracked runtime or credential paths, constructs the three execution markers from split non-secret literals, byte-scans Git-visible/runtime/build files without printing matched data, and verifies that the frozen `0007`/`0008` sentinel roots still exist.

| Audit | Exit | Counts |
| --- | ---: | --- |
| Pre-closeout Git/runtime/build inventory and exact marker scan | `0` | `tracked=239`; `untracked=1`; `runtime_and_build_files=914`; `ephemeral_marker_hits=0`; `sentinel_roots_preserved=1` |
| Final closeout inventory and exact marker scan | `0` | `tracked=240`; `untracked=0`; `tracked_forbidden=0`; `suspicious_untracked=0`; `runtime_and_build_files=914`; `git_ephemeral_marker_hits=0`; `runtime_ephemeral_marker_hits=0`; `sentinel_roots_preserved=1` |

The end-to-end tests separately scan Author/Content/Asset raw and locators, Job/SyncRun payloads, disposed SQLite and sidecars, detail runtime, download/export work roots, archive, Emby library, source metadata and object representations. Dynamic query, fragment, userinfo, nested-shape and comma-drift sentinels are absent from those durable sinks.

## Live qualification

| Item | Status |
| --- | --- |
| Real QR/Cookie/saved-session login | `NOT_RUN` |
| Real creator scan and incremental rerun | `NOT_RUN` |
| Real detail and signed CDN transfer | `NOT_RUN` |
| Real platform bytes through FFmpeg/ffprobe | `NOT_RUN` |
| Real Emby/Jellyfin scan and playback | `NOT_RUN` |

Offline fake checkout, fake detail runner, mock DNS/HTTP, synthetic bytes and controlled probing do not promote any live row. Same-ID/same-origin/path byte replacement, trusted-Subscription author ownership and injected detail-cleanup failure remain the explicit limitations recorded in `goal.md` and `progress.md`.
