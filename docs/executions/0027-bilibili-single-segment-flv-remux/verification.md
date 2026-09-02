**English** | [中文](verification.zh.md)

# Execution 0027 verification

- Status: Frozen offline scope passes all final gates; authenticated/live qualification `NOT_RUN`
- Date: 2026-09-02
- Predecessor: `245e8e377761ee8343b33f581dfcd27295eac532`
- Plan commit: `ec7095a9cc5e85fda1aee66f256eb16345c1294a`
- Implementation commit: `7f99aa480328a25b7e9c2acc8a9c2234128e7b74`

## Baseline

| Check | Result |
| --- | --- |
| Execution 0026 focused regression | `PASS — 490 passed in 73.31s` |
| Execution 0026 complete suite | `PASS — 1814 passed, 1 skipped in 342.33s` |
| Single-/multipart/DASH closeout reruns | `PASS — 1 passed in 1.45s; 1 passed in 1.70s; 1 passed in 1.87s` |
| Documentation and upstream locks | `PASS — 120 Markdown files; 2 locked clean checkouts |
| Repository audit | `PASS — tracked 308; untracked 0; tracked runtime/upstream/dist 0 |
| Local/tracking/GitHub reconciliation | `PASS — 245e8e377761ee8343b33f581dfcd27295eac532` |

## Implemented evidence

| Scope | Result |
| --- | --- |
| Protocol-v7 closed format classification | `PASS` — only an explicit valid top-level format containing FLV grants FLV authority; absent/`None` and MP4 remain ordinary, while unknown, mixed FLV+MP4, malformed or non-string values have fixed fail-closed outcomes |
| Typed target and bridge compatibility | `PASS` — one Bilibili-profile `ResolvedLocator` is wrapped repr-safely; exact single-/multipart private markers reconstruct it, collide recursively and disappear before persistence; historical marker-free payloads remain ordinary |
| Source and final structural gates | `PASS` — video-bearing FLV is accepted, audio-only/non-FLV source is rejected, and only a final probing exactly as `video/mp4`/`.mp4` may publish |
| Fixed bounded remux | `PASS` — non-shell argv maps `0:v:0` and optional `0:a:0?`, uses `-c copy`, fixed MP4 output, timeout/output/media caps and input/output identity checks; process, empty, oversized and alias failures close safely |
| Ordered download and auth refresh | `PASS` — primary failure advances to ordered backup with strict partial continuity; one all-`401`/`403` adapter pass refreshes once, and refreshed target-type drift returns `locator_refresh_schema_changed` |
| Recovery and cleanup | `PASS` — remux/final-gate failure retains the verified generation source, removes the unprepared final, retries through strict completed-range evidence, recovers an already-published final without detail/DNS/HTTP/ffmpeg and cleans all source/final stores |
| Production FLV → Emby composition | `PASS` — a generated local H.264+AAC FLV traverses SQLite → primary `503` → backup → production ffprobe → production ffmpeg stream-copy → final ffprobe → immutable SHA-256 `.mp4` → Emby `.mp4`/NFO/source; both output copies contain video and audio |
| Zero-work replay and non-retention | `PASS` — replay adds zero detail/DNS/HTTP/probe/ffmpeg/archive/export work; retained runtime/work/archive/export/library/SQLite evidence contains no signed primary/backup URL, private marker or published `.flv` |
| Compatibility | `PASS` — no-format/MP4 progressive, single-/multipart backup paths, DASH, static media, published recovery and the twelve frozen media-shape count remain green |

## Test and quality gates

| Check | Command | Result |
| --- | --- | --- |
| Focused implementation regression | `uv run pytest -q tests/unit/test_media_locator.py tests/unit/test_media_probe.py tests/unit/test_media_mux.py tests/unit/test_media_downloader.py tests/unit/test_media_dash_downloader.py tests/unit/test_media_flv_downloader.py tests/unit/test_mediacrawler_refresh.py tests/contract/test_mediacrawler_detail_refresh.py` | `PASS — 394 passed in 59.12s` |
| Bilibili compatibility and production compositions | `uv run pytest -q tests/integration/test_bilibili_playable_pipeline.py tests/integration/test_bilibili_multipart_progressive_pipeline.py tests/integration/test_bilibili_dash_pipeline.py` | `PASS — 4 passed in 4.51s` |
| Production FLV closeout rerun | `uv run pytest -q tests/integration/test_bilibili_playable_pipeline.py::test_bilibili_flv_backup_reaches_emby_through_production_remux_with_zero_work_replay` | `PASS — 1 passed in 1.82s` |
| Complete suite | `uv run pytest -q` | `PASS — 1848 passed, 1 skipped in 347.72s`; skip is the Windows-inapplicable POSIX mode-bit boundary |
| Ruff and format | `uv run ruff check .`; `uv run ruff format --check .` | `PASS — all checks; 295 files already formatted |
| Strict mypy | `uv run mypy --strict src` | `PASS — no issues in 84 source files |
| Compileall and build | `uv run python -m compileall -q src/media_sync`; `uv build` | `PASS — wheel and source distribution built |
| Documentation and upstream locks | `uv run python scripts/check_docs.py`; `uv run python scripts/check_upstreams.py` | `PASS — 124 Markdown files; 2 locked checkouts |
| Git/upstream/diff audit | explicit status, tracked/runtime/upstream and diff checks | `PASS — tracked 313; untracked 0; tracked runtime/upstream/dist 0; both upstream dirty counts 0; locked SHAs exact |

No coverage run is claimed.

## Git reconciliation

Plan `ec7095a9cc5e85fda1aee66f256eb16345c1294a` and implementation `7f99aa480328a25b7e9c2acc8a9c2234128e7b74` are pushed and reconciled across local `main`, `origin/main` and GitHub. The commit containing this record is the bilingual documentation closeout; its self-referential SHA is intentionally left to Git history.

## Live qualification

| Row | Result |
| --- | --- |
| Real Bilibili QR/Cookie login | `NOT_RUN` |
| Authenticated FLV detail/play API | `NOT_RUN` |
| Real primary/backup bilivideo FLV CDN behavior | `NOT_RUN` |
| Real Bilibili FLV bytes with production ffmpeg/ffprobe | `NOT_RUN` |
| Real Emby/Jellyfin scan and playback | `NOT_RUN` |

Offline evidence cannot imply these live rows, multiple `durl` segments, concatenation, transcoding, CDN ranking/racing/cache or complete Bilibili support.
