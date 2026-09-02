**English** | [中文](verification.zh.md)

# Execution 0029 verification

- Status: Frozen offline multi-segment ordinary `durl` scope passes all final gates; live qualification `NOT_RUN`
- Date: 2026-09-02
- Predecessor: Execution 0028 closeout `2621f6a119aac60eaf89f0195d4fbe23bd5160f0`
- Plan commit: `9a40968`

## Baseline (before any 0029 change)

| Check | Result |
| --- | --- |
| 0028 deferred Python docs recheck | `PASS — uv run python scripts/check_docs.py; Documentation links OK (256 Markdown files checked)` |
| Upstream locks | `PASS — uv run python scripts/check_upstreams.py; Upstreams OK (2 locked checkouts verified)` |
| Ruff and format | `PASS — all checks; 427 files already formatted` |
| Bilibili composition baseline | `PASS — 4 passed in 6.95s` |

## Implemented evidence

| Scope | Result |
| --- | --- |
| Protocol-v8 bounded multi-segment parsing | `PASS` — 2–64 ordered `durl` entries each yield one primary plus at most eight backups; DASH keeps precedence; exactly-one-segment stays byte-compatible; empty, above-limit, duplicate-primary and malformed tuples close with fixed outcomes; top-level FLV with more than one segment stays unsupported |
| Typed ephemeral target | `PASS` — `ResolvedSegmentsLocator` enforces the 2–64 bound, Bilibili profiles and pairwise-distinct primaries; repr never contains signed URLs; the resolver union, exports and lazy-refresh validation accept it while persistent locator v1 is unchanged |
| Private bridge | `PASS` — `{"cid", "segments"}` carries per-segment primary/backups for single-page and multipart tuples, collides recursively with every existing private field, is stripped before persistence and reconstructs only when the payload CID matches the selected page; no-page, colliding and malformed payloads fail closed as `locator_refresh_schema_changed` |
| Per-segment download | `PASS` — ordered candidate failover advances primary→backups per segment under one shared byte cap and deadline; each completed segment must probe exactly `video/mp4`; mixed/non-MP4 or over-budget segments close without publication |
| Auth refresh | `PASS` — one all-auth segment round refreshes the whole target once; a refreshed segment-count or type drift returns `locator_refresh_schema_changed`; a second all-auth round returns `locator_refresh_auth_expired` |
| Concat and final gate | `PASS` — one fixed-argv concat-demuxer `ffmpeg -c copy` invocation consumes a relative-name script written only inside the confined parts directory; identity/size/timeout/bounded-output checks close failures; only a final probing exactly `video/mp4` is published; the script never survives the attempt |
| Recovery and cleanup | `PASS` — concat/final-gate failure retains resumable segment stores and removes the unprepared final; a prepared final recovers without DNS/HTTP; `cleanup_partial` discards every segment store plus the script |
| Production multi-segment composition | `PASS` — two locally generated H.264+AAC MP4s traverse SQLite → primary `503` → backup → second segment → production ffprobe per segment → production ffmpeg concat → final ffprobe → immutable SHA-256 `.mp4` → Emby `.mp4`/NFO/source; both segment URLs and the private field appear nowhere in retained runtime/work/archive/export/library/SQLite evidence |
| Zero-work replay and compatibility | `PASS` — replay adds zero detail/DNS/HTTP/probe/ffmpeg/archive/export work; no-format/MP4 progressive, FLV remux, DASH, multipart and static shapes remain green |

## Test and quality gates

| Check | Command | Result |
| --- | --- | --- |
| Focused implementation regression | `uv run pytest -q tests/unit/test_media_locator.py tests/unit/test_media_probe.py tests/unit/test_media_mux.py tests/unit/test_media_downloader.py tests/unit/test_media_dash_downloader.py tests/unit/test_media_flv_downloader.py tests/unit/test_media_segments_downloader.py tests/unit/test_mediacrawler_refresh.py tests/contract/test_mediacrawler_detail_refresh.py` | `PASS — 447 passed in 70.97s` |
| Bilibili compositions | `uv run pytest -q tests/integration/test_bilibili_playable_pipeline.py tests/integration/test_bilibili_multipart_progressive_pipeline.py tests/integration/test_bilibili_dash_pipeline.py` | `PASS — 5 passed in 10.93s` |
| Multi-segment closeout rerun | `uv run pytest -q tests/integration/test_bilibili_playable_pipeline.py::test_bilibili_multi_segment_backup_reaches_emby_through_production_concat_with_zero_work_replay` | `PASS — 1 passed in 2.26s` |
| Complete suite | `uv run pytest -q` | `PASS — 1902 passed, 1 skipped in 409.85s`; the skip is the Windows-inapplicable POSIX mode-bit boundary |
| Ruff and format | `uv run ruff check .`; `uv run ruff format --check .` | `PASS — all checks; 432 files formatted` |
| Strict mypy | `uv run mypy --strict src` | `PASS — no issues in 84 source files` |
| Compileall and build | `uv run python -m compileall -q src/media_sync`; `uv build` | `PASS — compiled; wheel and source distribution built` |
| Documentation and upstream locks | `uv run python scripts/check_docs.py`; `uv run python scripts/check_upstreams.py` | `PASS — 260 Markdown files; 2 locked clean checkouts` |
| Git/upstream audit | explicit status and tracked-path scans | `PASS — intended changes plus one new test file only; tracked runtime/upstream/dist 0; both upstream dirty counts 0` |

## Workstation gate-infrastructure note

The first two complete-suite runs on this workstation failed 10 then 6 pre-existing contract tests in `test_mediacrawler_supervision.py`/`test_mediacrawler_login.py`. Stashing all 0029 changes reproduced the identical failures on the clean predecessor `9a40968`, proving they predate this execution. Root cause: both files' `_pid_is_alive` helpers decode `tasklist.exe` output with `text=True`, and on this Chinese-locale Windows host the localized GBK bytes break the UTF-8 reader thread (`UnicodeDecodeError`, `completed.stdout is None`). The two test-only helpers now pass `encoding="utf-8", errors="replace"` — PID CSV rows are ASCII, so liveness semantics are unchanged — and both files pass in isolation (`14 passed, 1 skipped`; `43 passed`) before the final complete-suite gate above ran fully green. No production code changed for this.

## Not claimed

No coverage run is claimed. No real account, login, author, detail, play-URL, CDN or Emby/Jellyfin server interaction was performed; every live row stays `NOT_RUN`. Multi-segment FLV concatenation remains unsupported by contract, not silently degraded.
