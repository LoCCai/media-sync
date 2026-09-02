**English** | [中文](verification.zh.md)

# Execution 0035 verification

- Status: Frozen offline `playback_list` quality-selection scope passes all final gates; live qualification `NOT_RUN`
- Date: 2026-09-03
- Predecessor: Execution 0034 closeout `3cdd0fc`
- Plan commit: `ecc08da`

## Baseline (before any 0035 change)

| Check | Result |
| --- | --- |
| 0034 focused regression | `PASS — 445 passed` |
| 0034 detail contracts | `PASS — 106 passed in 69.98s` |
| 0034 complete suite | `PASS — 2002 passed, 1 skipped in 352.79s` |
| Ruff, format, strict mypy, docs, upstreams | `PASS` (recorded in the 0034 verification) |

## Implemented evidence

| Scope | Result |
| --- | --- |
| Closed quality selection | `PASS` — a 1–8-entry `playback_list` selects the highest valid entry under the closed `1080p > 720p > 540p > 480p > 360p` preference with every candidate URL revalidated by the 0031 closed validator |
| Scalar precedence | `PASS` — the `stream_url` path stays first and byte-compatible; `playback_list` is consulted only when the scalar is absent or invalid |
| Closure | `PASS` — unknown or missing quality labels, invalid URLs, nine-entry lists and wrong shapes capture nothing and the post falls back to its non-video outcome |
| Contract compositions | `PASS` — the real child resolves the highest closed quality across a two-entry list and closes unusable shapes with `locator_refresh_asset_mismatch`; neither list URL survives in the retained runtime tree |
| Integration | `PASS` — a playback-sourced post normalizes to VIDEO with the query-free hint, downloads through the DEFAULT profile, archives, publishes Emby `.mp4` and replays with zero work and no retained sentinel |

## Test and quality gates

| Check | Command | Result |
| --- | --- | --- |
| Focused implementation regression | `uv run pytest -q tests/unit/test_mediacrawler_refresh.py tests/contract/test_mediacrawler_detail_refresh.py tests/contract/test_mediacrawler_ingestion.py tests/integration/test_weibo_image_pipeline.py tests/integration/test_weibo_playable_video_pipeline.py` | `PASS — 451 passed in 74.84s` (pre-integration snapshot; final integration additions below) |
| Weibo pipeline suite | `uv run pytest -q tests/integration/test_weibo_playable_video_pipeline.py` | `PASS — 4 passed in 2.70s` |
| Playback closeout rerun | `uv run pytest -q tests/integration/test_weibo_playable_video_pipeline.py::test_weibo_playback_list_sourced_video_reaches_emby_with_zero_work_replay` | `PASS — 1 passed in 1.57s` |
| Complete suite | `uv run pytest -q` | `PASS — 2010 passed, 1 skipped in 360.55s`; the skip is the Windows-inapplicable POSIX mode-bit boundary |
| Ruff and format | `uv run ruff check .`; `uv run ruff format --check .` | `PASS — all checks; 481 files formatted` |
| Strict mypy | `uv run mypy --strict src` | `PASS — no issues in 85 source files` |
| Compileall and build | `uv run python -m compileall -q src/media_sync`; `uv build` | `PASS — compiled; wheel and source distribution built` |
| Documentation and upstream locks | `uv run python scripts/check_docs.py`; `uv run python scripts/check_upstreams.py` | `PASS — 312 Markdown files; 2 locked clean checkouts` |
| Git/upstream audit | explicit status and tracked-path scans | `PASS — intended changes only; tracked runtime/upstream/dist 0; both upstream dirty counts 0` |

## Not claimed

No coverage run is claimed. No real account, login, creator feed, Weibo API, CDN byte or Emby/Jellyfin server interaction was performed; every live row stays `NOT_RUN`. The frozen `playback_list` shape and quality labels are documented m.weibo.cn contracts, not live-verified ones.
