**English** | [中文](verification.zh.md)

# Execution 0030 verification

- Status: Frozen offline multi-segment FLV concat scope passes all final gates; live qualification `NOT_RUN`
- Date: 2026-09-02
- Predecessor: Execution 0029 closeout `dbd06075eac67377a911b503de9aa609fdc30c79`
- Plan commit: `e7395fb`

## Baseline (before any 0030 change)

| Check | Result |
| --- | --- |
| 0029 focused regression | `PASS — 447 passed in 70.97s` |
| 0029 complete suite | `PASS — 1902 passed, 1 skipped in 409.85s` |
| Bilibili compositions | `PASS — 5 passed in 10.93s` |
| Ruff, format, strict mypy, docs, upstreams | `PASS` (recorded in the 0029 verification) |

## Implemented evidence

| Scope | Result |
| --- | --- |
| Protocol-v9 multi-segment FLV classification | `PASS` — a bounded 2–64 `durl` tuple with a top-level format classifying as FLV yields one typed FLV segments target; exactly-one-segment FLV, multi-segment ordinary and DASH payloads stay byte-compatible; empty, above-limit, duplicate-primary and malformed tuples keep fixed outcomes |
| Typed ephemeral target | `PASS` — `ResolvedFlvSegmentsLocator` wraps exactly one `ResolvedSegmentsLocator`; the resolver union, exports and lazy-refresh validation accept it; repr never contains signed URLs; persistent locator v1 is unchanged |
| Private bridge marker | `PASS` — the segments payload accepts only the exact key set with an exact `"format": "flv"` marker; non-exact markers, flat-field collisions and page-less payloads fail closed as `locator_refresh_schema_changed`; the marker and segments field appear nowhere in retained runtime trees |
| Per-segment download and probing | `PASS` — ordered primary→backup failover per segment under one shared byte cap/deadline; each completed segment must probe exactly `video/x-flv`; an MP4 probe under FLV authority or an FLV probe under ordinary authority closes with `media_type_mismatch` and publishes nothing |
| Auth refresh | `PASS` — one all-auth segment round refreshes the whole target once; a refreshed ordinary/FLV type drift or segment-count drift returns `locator_refresh_schema_changed`; a second all-auth round returns `locator_refresh_auth_expired` |
| Concat and final gate | `PASS` — one fixed-argv concat-demuxer `ffmpeg -c copy` invocation consumes the relative-name script inside the confined parts directory; only a final probing exactly `video/mp4` is published; failures retain resumable segments, remove the unprepared final and never survive the script |
| Recovery and cleanup | `PASS` — a prepared final recovers without DNS/HTTP; `cleanup_partial` discards every segment store plus the script; no raw `.flv` is archived, exported or published |
| Production multi-segment FLV composition | `PASS` — two locally generated H.264+AAC FLVs traverse SQLite → primary `503` → backup → second segment → production ffprobe per segment → production ffmpeg concat → final ffprobe → immutable SHA-256 `.mp4` → Emby `.mp4`/NFO/source with video and audio streams |
| Zero-work replay and compatibility | `PASS` — replay adds zero detail/DNS/HTTP/probe/ffmpeg/archive/export work; single-segment FLV remux, multi-segment ordinary, DASH, multipart and static shapes remain green |

## Test and quality gates

| Check | Command | Result |
| --- | --- | --- |
| Focused implementation regression | `uv run pytest -q tests/unit/test_media_locator.py tests/unit/test_media_probe.py tests/unit/test_media_mux.py tests/unit/test_media_downloader.py tests/unit/test_media_dash_downloader.py tests/unit/test_media_flv_downloader.py tests/unit/test_media_segments_downloader.py tests/unit/test_mediacrawler_refresh.py tests/contract/test_mediacrawler_detail_refresh.py` | `PASS — 460 passed in 91.95s` |
| Bilibili compositions | `uv run pytest -q tests/integration/test_bilibili_playable_pipeline.py tests/integration/test_bilibili_multipart_progressive_pipeline.py tests/integration/test_bilibili_dash_pipeline.py` | `PASS — 6 passed in 11.71s` |
| Multi-segment FLV closeout rerun | `uv run pytest -q tests/integration/test_bilibili_playable_pipeline.py::test_bilibili_multi_segment_flv_backup_reaches_emby_through_production_concat_with_zero_work_replay` | `PASS — 1 passed in 2.88s` |
| Complete suite | `uv run pytest -q` | `PASS — 1916 passed, 1 skipped in 446.64s`; the skip is the Windows-inapplicable POSIX mode-bit boundary |
| Ruff and format | `uv run ruff check .`; `uv run ruff format --check .` | `PASS — all checks; 440 files formatted` |
| Strict mypy | `uv run mypy --strict src` | `PASS — no issues in 84 source files` |
| Compileall and build | `uv run python -m compileall -q src/media_sync`; `uv build` | `PASS — compiled; wheel and source distribution built` |
| Documentation and upstream locks | `uv run python scripts/check_docs.py`; `uv run python scripts/check_upstreams.py` | `PASS — 272 Markdown files; 2 locked clean checkouts` |
| Git/upstream audit | explicit status and tracked-path scans | `PASS — intended changes only; tracked runtime/upstream/dist 0; both upstream dirty counts 0` |

## Not claimed

No coverage run is claimed. No real account, login, author, detail, play-URL, CDN or Emby/Jellyfin server interaction was performed; every live row stays `NOT_RUN`. Transcoding and codec repair remain unsupported by contract, not silently degraded.
