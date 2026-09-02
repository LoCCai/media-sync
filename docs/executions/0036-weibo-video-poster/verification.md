**English** | [中文](verification.zh.md)

# Execution 0036 verification

- Status: Frozen offline Weibo video-poster scope passes all final gates; live qualification `NOT_RUN`
- Date: 2026-09-03
- Predecessor: Execution 0035 closeout `5a27e99949c54a5032454d91b8809d28afad7086`
- Plan commit: `1ad49a7`

## Baseline (before any 0036 change)

| Check | Result |
| --- | --- |
| 0035 focused regression | `PASS — 451 passed in 74.84s` |
| 0035 complete suite | `PASS — 2010 passed, 1 skipped in 360.55s` |
| Ruff, format, strict mypy, docs, upstreams | `PASS` (recorded in the 0035 verification) |

## Implemented evidence

| Scope | Result |
| --- | --- |
| Closed poster validator | `PASS` — HTTPS `sinaimg.cn`-family hosts with static extensions and bounded paths accept; foreign hosts, GIF/MP4 extensions, fragments, userinfo and ports reject |
| Store-boundary capture | `PASS` — the poster captures only alongside a capturable video (scalar or `playback_list`); absent, malformed, foreign or non-static posters capture video only |
| Normalizer branch | `PASS` — the `{note_id}:cover:0` COVER asset materializes alongside VIDEO; malformed poster payloads quarantine; the poster field is recursively stripped |
| Refresh | `PASS` — WB COVER joined the support set so the poster re-resolves through one exact numeric-note detail child run like the video |
| Download and publication | `PASS` — the poster passes the static PNG gate, archives under its own SHA-256 digest and publishes as the Emby episode poster while the video stays the main media, with zero-work replay |
| Non-retention | `PASS` — the poster field and its signed URL appear nowhere in retained runtime/work/archive/export/library trees or SQLite artifacts |

## Test and quality gates

| Check | Command | Result |
| --- | --- | --- |
| Focused implementation regression | `uv run pytest -q tests/unit/test_mediacrawler_refresh.py tests/contract/test_mediacrawler_ingestion.py tests/integration/test_weibo_playable_video_pipeline.py tests/integration/test_weibo_image_pipeline.py` | `PASS — 341 passed in 4.29s` |
| Weibo pipeline suite | `uv run pytest -q tests/integration/test_weibo_playable_video_pipeline.py` | `PASS — 6 passed in 4.01s` |
| Poster closeout rerun | `uv run pytest -q tests/integration/test_weibo_playable_video_pipeline.py::test_weibo_video_with_poster_reaches_emby_with_zero_work_replay` | `PASS — 1 passed in 2.20s` |
| Complete suite | `uv run pytest -q` | `PASS — 2016 passed, 1 skipped in 370.47s`; the skip is the Windows-inapplicable POSIX mode-bit boundary |
| Ruff and format | `uv run ruff check .`; `uv run ruff format --check .` | `PASS — all checks; 490 files formatted` |
| Strict mypy | `uv run mypy --strict src` | `PASS — no issues in 85 source files` |
| Compileall and build | `uv run python -m compileall -q src/media_sync`; `uv build` | `PASS — compiled; wheel and source distribution built` |
| Documentation and upstream locks | `uv run python scripts/check_docs.py`; `uv run python scripts/check_upstreams.py` | `PASS — 320 Markdown files; 2 locked clean checkouts` |
| Git/upstream audit | explicit status and tracked-path scans | `PASS — intended changes only; tracked runtime/upstream/dist 0; both upstream dirty counts 0` |

## Not claimed

No coverage run is claimed. No real account, login, creator feed, Weibo API, CDN byte or Emby/Jellyfin server interaction was performed; every live row stays `NOT_RUN`. The frozen `pic_info.pic_big.url` shape is a documented store-input contract, not a live-verified one.
