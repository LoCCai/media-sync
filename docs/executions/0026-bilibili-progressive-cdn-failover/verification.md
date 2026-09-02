**English** | [中文](verification.zh.md)

# Execution 0026 verification

- Status: Frozen offline scope passes all final gates; authenticated/live qualification `NOT_RUN`
- Date: 2026-09-02
- Predecessor: `7cb84fc6c93b832492b95513d9cb6a9708ee6cc9`
- Plan commit: `0694934bc9230151a85c040a061d6e704dffc4fc`
- Implementation commit: `190488f77d1704492cc148b890d6f9ae16d84f84`

## Baseline

| Check | Result |
| --- | --- |
| Execution 0025 focused regression | `PASS — 466 passed in 66.96s` |
| Execution 0025 complete suite | `PASS — 1790 passed, 1 skipped in 331.33s` |
| Production backup-path closeout rerun | `PASS — 1 passed in 1.74s` |
| Documentation and upstream locks | `PASS — 116 Markdown files; 2 locked clean checkouts |
| Repository audit | `PASS — tracked 304; untracked 0; tracked runtime/upstream 0 |
| Local/tracking/GitHub reconciliation | `PASS — 7cb84fc6c93b832492b95513d9cb6a9708ee6cc9` |

## Implemented evidence

| Scope | Result |
| --- | --- |
| Strict protocol-v6 parsing | `PASS` — exactly one progressive `durl` accepts one primary plus equivalent `backup_url`/`backupUrl` aliases and at most eight validated distinct backups; malformed, conflicting, duplicate, primary-equal and over-bound candidates fail closed |
| Private bridge compatibility | `PASS` — the single-page private backup field and optional multipart `backup_urls` reach runtime `ResolvedLocator`; historical primary-only payloads remain accepted |
| Shared candidate order | `PASS` — ordinary progressive and DASH locators share one primary-first pass under the existing asset lock, deadline, byte caps and restart budget; primary success touches no backup DNS/HTTP |
| Eligible and immediate failures | `PASS` — DNS, timeout, transport, interruption, HTTP and Range incompatibility may advance; network-policy, redirect/header/encoding, chunk/size, filesystem, probe, mux, archive and publication failures remain immediate |
| Strict partial continuity | `PASS` — cross-candidate append requires exact offset, total length, validator type and value; mixed failures preserve valid partials, and bounded discard/restart occurs only after the complete candidate pass rejects the partial |
| Adapter refresh semantics | `PASS` — one adapter pass containing only `401`/`403` re-resolves detail once; a second all-auth pass returns `locator_refresh_auth_expired`; mixed/non-auth exhaustion and direct locators do not refresh |
| Ephemeral boundary | `PASS` — primary/backup signed values and all private fields are recursively absent from retained SQLite, Job, runtime, work, archive, export and operator evidence |
| Single-page composition | `PASS` — SQLite → exact-CID detail → primary `503` → backup bytes → controlled probe → SHA-256 archive → Emby MP4/NFO/source succeeds; replay performs zero new detail/DNS/HTTP/probe/archive/export work |
| Multipart composition | `PASS` — all three page primaries return `503`, ordered backups supply distinct bytes, primary/part publication succeeds and replay is zero-work |
| Compatibility | `PASS` — no-backup progressive, DASH backup failover, static media, recovery and the twelve frozen media-shape count remain green |

## Test and quality gates

| Check | Command | Result |
| --- | --- | --- |
| Focused implementation regression | `uv run pytest tests/unit/test_media_locator.py tests/unit/test_mediacrawler_refresh.py tests/unit/test_media_mux.py tests/unit/test_media_dash_downloader.py tests/unit/test_media_downloader.py tests/unit/test_cli.py tests/contract/test_mediacrawler_detail_refresh.py tests/integration/test_asset_download_orchestration.py tests/integration/test_pipeline_runtime.py tests/integration/test_bilibili_playable_pipeline.py tests/integration/test_bilibili_multipart_progressive_pipeline.py tests/integration/test_bilibili_dash_pipeline.py -q` | `PASS — 490 passed in 73.31s` |
| Single-page progressive backup → Emby | `uv run pytest -q tests/integration/test_bilibili_playable_pipeline.py` | `PASS — 1 passed in 1.45s` on the documentation-closeout rerun (`1.64s` on the implementation run) |
| Multipart progressive backup → Emby | `uv run pytest -q tests/integration/test_bilibili_multipart_progressive_pipeline.py` | `PASS — 1 passed in 1.70s` on the documentation-closeout rerun (`1.95s` on the implementation run) |
| DASH failover compatibility | `uv run pytest -q tests/integration/test_bilibili_dash_pipeline.py` | `PASS — 1 passed in 1.87s` on the documentation-closeout rerun (`2.11s` on the implementation run) |
| Complete suite | `uv run pytest -q` | `PASS — 1814 passed, 1 skipped in 342.33s`; skip is the Windows-inapplicable POSIX mode-bit boundary |
| Ruff and format | `uv run ruff check .`; `uv run ruff format --check .` | `PASS — all checks; 290 files already formatted |
| Strict mypy | `uv run mypy --strict src` | `PASS — no issues in 84 source files |
| Compileall and build | `uv run python -m compileall -q src/media_sync`; `uv build` | `PASS — wheel and source distribution built |
| Documentation and upstream locks | `uv run python scripts/check_docs.py`; `uv run python scripts/check_upstreams.py` | `PASS — 120 Markdown files; 2 locked checkouts |
| Git/upstream/diff audit | explicit status, tracked/runtime/upstream and diff checks | `PASS — tracked 308; untracked 0; tracked runtime/upstream/dist 0; upstream diff 0; both upstream dirty counts 0 |

No coverage run is claimed.

## Git reconciliation

Plan `0694934bc9230151a85c040a061d6e704dffc4fc` and implementation `190488f77d1704492cc148b890d6f9ae16d84f84` are pushed and reconciled across local `main` and `origin/main`. The commit containing this record is the bilingual documentation closeout; its self-referential SHA is intentionally left to Git history.

## Live qualification

| Row | Result |
| --- | --- |
| Real Bilibili QR/Cookie login | `NOT_RUN` |
| Authenticated progressive detail/play API | `NOT_RUN` |
| Real primary/backup bilivideo CDN behavior | `NOT_RUN` |
| Real progressive bytes with production ffprobe | `NOT_RUN` |
| Real Emby/Jellyfin scan and playback | `NOT_RUN` |

Offline evidence cannot imply these rows, segmented `durl`, FLV, CDN ranking/racing/cache or complete Bilibili support.
