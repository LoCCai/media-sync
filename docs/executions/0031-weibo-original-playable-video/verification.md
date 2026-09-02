**English** | [中文](verification.zh.md)

# Execution 0031 verification

- Status: Frozen offline ordinary original playable-video scope passes all final gates; live qualification `NOT_RUN`
- Date: 2026-09-02
- Predecessor: Execution 0030 closeout `e242b16097b2fb1f0f6ee1dc8e863ace1c68ab32`
- Plan commit: `1c79c6d`

## Baseline (before any 0031 change)

| Check | Result |
| --- | --- |
| 0030 focused regression | `PASS — 460 passed in 91.95s` |
| 0030 complete suite | `PASS — 1916 passed, 1 skipped in 446.64s` |
| Ruff, format, strict mypy, docs, upstreams | `PASS` (recorded in the 0030 verification) |

## Implemented evidence

| Scope | Result |
| --- | --- |
| Closed URL validator | `PASS` — HTTPS `sinaimg.cn`/`*.sinaimg.cn`/`f.video.weibocdn.com` hosts with non-root case-insensitive `.mp4` paths accept signed queries; http, foreign hosts, non-mp4 extensions, fragments, userinfo, explicit ports, empty path segments, dot-leading filenames and oversized names reject |
| Shim capture matrix | `PASS` — the real-child pinned-store boundary captures exactly one valid `stream_url` for `page_type == "video"` originals; retweets, `article`/`None` page types, foreign or non-mp4 URLs capture nothing and never emit the private field |
| Normalizer branch | `PASS` — `ContentKind.VIDEO` with one position-0 `{note_id}:video:0` VIDEO asset and `video/mp4` mime; dual private fields, retained `page_info`, retweets, non-canonical identities and malformed payloads quarantine fail-closed; the private field is stripped recursively from durable raw envelopes |
| Refresh | `PASS` — WB VIDEO joins the support set; one exact numeric-note detail child re-captures the current signed URL in memory, the refresher returns the DEFAULT-profile ephemeral locator, and hint or identity drift closes as `locator_refresh_asset_mismatch` |
| Download and publication | `PASS` — the DEFAULT-profile request carries no Cookie/Authorization/Referer/Origin; the MP4 probe, SHA-256 archive, Emby `.mp4`/NFO/source publication and zero-work replay all hold |
| Non-retention | `PASS` — the signed URL, its query sentinels and the private field appear nowhere in retained runtime/work/archive/export/library trees or SQLite artifacts |
| Compatibility | `PASS` — 0016 image semantics, TEXT fallback for media-less posts and every prior platform slice remain green |

## Test and quality gates

| Check | Command | Result |
| --- | --- | --- |
| Focused implementation regression | `uv run pytest -q tests/unit/test_mediacrawler_refresh.py tests/contract/test_mediacrawler_ingestion.py tests/integration/test_weibo_image_pipeline.py tests/integration/test_weibo_playable_video_pipeline.py` | `PASS — 302 passed in 4.04s` |
| Detail-refresh contract suite | `uv run pytest -q tests/contract/test_mediacrawler_detail_refresh.py` | `PASS — 100 passed in 70.92s` |
| Playable-video closeout rerun | `uv run pytest -q tests/integration/test_weibo_playable_video_pipeline.py::test_weibo_playable_video_reaches_emby_without_persisting_signed_queries` | `PASS — 1 passed in 1.82s` |
| Complete suite | `uv run pytest -q` | `PASS — 1956 passed, 1 skipped in 408.57s`; the skip is the Windows-inapplicable POSIX mode-bit boundary |
| Ruff and format | `uv run ruff check .`; `uv run ruff format --check .` | `PASS — all checks; 449 files formatted` |
| Strict mypy | `uv run mypy --strict src` | `PASS — no issues in 84 source files` |
| Compileall and build | `uv run python -m compileall -q src/media_sync`; `uv build` | `PASS — compiled; wheel and source distribution built` |
| Documentation and upstream locks | `uv run python scripts/check_docs.py`; `uv run python scripts/check_upstreams.py` | `PASS — 280 Markdown files; 2 locked clean checkouts` |
| Git/upstream audit | explicit status and tracked-path scans | `PASS — intended changes plus one new integration test file; tracked runtime/upstream/dist 0; both upstream dirty counts 0` |

## Not claimed

No coverage run is claimed. No real account, login, creator feed, Weibo API, CDN byte or Emby/Jellyfin server interaction was performed; every live row stays `NOT_RUN`. The frozen `stream_url` shape is a documented m.weibo.cn contract, not a live-verified one; `playback_list` payloads remain unsupported rather than silently degraded.
