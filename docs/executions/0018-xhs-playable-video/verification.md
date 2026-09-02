**English** | [中文](verification.zh.md)

# Execution 0018 verification

- Status: Offline implementation and documentation gates pass; live qualification `NOT_RUN`
- Date: 2026-09-01
- Plan commit: `c9d3586`
- Implementation commit: `356e254`

## Selection evidence

| Candidate | Locked evidence | Decision |
| --- | --- | --- |
| XHS video | `store/xhs/__init__.py` emits origin-key or H.264 `video_url`; media-sync already normalizes VIDEO, refreshes XHS and probes/archives/publishes video. | Execution 0018 |
| Tieba static images | `TiebaNote` has no media field; first-floor API/HTML media is discarded before JSONL and anti-hotlink fields require a frozen redacted fixture. | Future integration shim |
| Zhihu static/video | `ZhihuContent` retains text/landing URL only; HTML image attributes and nested playable-video structures are discarded before JSONL. | Future integration shim |

## Implementation evidence

| Scope | Result | Evidence |
| --- | --- | --- |
| Locked upstream source shape | `PASS` | The contract verifies the pinned checkout, AST-extracts and executes its real XHS store functions, covering `origin_video_key`, `originVideoKey`, H.264 `master_url`, comma-scalar video and scalar image output. |
| Initial XHS media locator | `PASS` | Ordinary bounded HTTP/HTTPS, strict LDH/IDNA XHS CDN host, default port and non-root-path cases pass; userinfo, whitespace/control, fragment, malformed/foreign/custom-port cases fail closed. Redirects retain the existing per-hop public-network policy. |
| Automatic creator-video target | `PASS` | Exactly one raw scalar VIDEO and zero or one raw scalar IMAGE map one-to-one to ordinary `type="video"` VIDEO/MIXED content; duplicates, empty segments, whitespace, malformed+valid lists, multiple candidates, container drift and identity drift are rejected. |
| Process and refresh contract | `PASS` | A real isolated fake checkout proves bounded creator mode, exact URL selection, DEFAULT profile, successful cleanup and repr-safe authority handling; the explicit exact-note compatibility path remains unchanged. |
| Video validity | `PASS` | An embedded real H.264 MP4 passes production `FFprobeMediaProbe`; this proof is separate from the deterministic recording-probe composition. |
| Download/archive/Emby composition | `PASS` | Exact SQLite provenance, creator lookup, mock public DNS/HTTP, controlled MP4/PNG, SHA-256 archive and idempotent `.mp4`/poster/NFO/source publication pass. Query-only replay adds no detail, DNS, HTTP, probe, archive or export work. |
| Durable/ephemeral boundary | `PASS` | Durable raw, Asset hints, SQLite, archive metadata, Emby output and completed attempt cleanup retain no signed query, userinfo or fragment; `.upstream` remains clean and untracked. |

## Test and quality gates

| Check | Command | Result |
| --- | --- | --- |
| Pre-edit seven-file baseline | `uv run pytest -q tests/contract/test_mediacrawler_detail_refresh.py tests/integration/test_asset_download_orchestration.py tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_mediacrawler_download_runtime.py tests/integration/test_pipeline_runtime.py tests/integration/test_xhs_creator_authority_pipeline.py tests/unit/test_mediacrawler_refresh.py` | `PASS` — `167 passed in 46.50s` |
| Focused nine-file pytest | `uv run pytest -q tests/contract/test_mediacrawler_detail_refresh.py tests/contract/test_xhs_upstream_video_store.py tests/integration/test_asset_download_orchestration.py tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_mediacrawler_download_runtime.py tests/integration/test_pipeline_runtime.py tests/integration/test_xhs_creator_authority_pipeline.py tests/integration/test_xhs_playable_video_pipeline.py tests/unit/test_mediacrawler_refresh.py` | `PASS` — `222 passed in 43.69s` |
| Locked upstream source contract | `uv run pytest -q tests/contract/test_xhs_upstream_video_store.py` | `PASS` — `4 passed` |
| Real H.264 + upstream + composition | `uv run pytest -q tests/contract/test_xhs_upstream_video_store.py tests/integration/test_xhs_playable_video_pipeline.py` | `PASS` — `6 passed in 8.84s` |
| Complete suite | `uv run pytest -q` | `PASS` — `1353 passed, 1 skipped in 338.48s`; only skip: Windows POSIX mode-bit: Windows POSIX mode-bit |
| Ruff | `uv run ruff check .` | `PASS` |
| Format | `uv run ruff format --check .` | `PASS` — `241 files already formatted` |
| Strict mypy | `uv run mypy src/media_sync` | `PASS` — `80 source files` |
| Compileall | `uv run python -m compileall -q src/media_sync` | `PASS` |
| Upstream locks | `uv run python scripts/check_upstreams.py` | `PASS` — 2 checkouts |
| Build | `uv build` | `PASS` — wheel and sdist |
| Documentation | `uv run python scripts/check_docs.py` | `PASS` — 88 Markdown files checked |
| Diff checks | `git diff --check`; `git diff --cached --check` | `PASS` |
| Independent final review | Read-only review plus selected regression gate | `PASS` — no P0–P2 findings |

No coverage run is claimed.

## Retained/Git audit

The final read-only PowerShell audit ran `git ls-files`, `git ls-files --others --exclude-standard`, `git ls-files -- archive exports jobs .media-sync dist .upstream`, recursively counted real files below ignored `.media-sync`/`dist`, checked both frozen sentinel roots with `Test-Path`, and counted `git -C <checkout> status --short` for both pinned upstreams. It printed counts only, not retained values or matched paths. Result: `tracked=259`; `untracked=0`; `tracked_runtime_upstream=0`; `runtime_and_build_files=914`; `sentinel_roots_preserved=2/2`; `mediacrawler_dirty_paths=0`; `bili_sync_up_dirty_paths=0`.

## Live qualification

| Row | Result |
| --- | --- |
| Real XHS QR/Cookie login | `NOT_RUN` |
| Real creator/feed/detail lookup | `NOT_RUN` |
| Real XHS CDN video/artwork bytes | `NOT_RUN` |
| Real Emby/Jellyfin scan/playback | `NOT_RUN` |

Offline mocks do not imply these rows. Execution 0018 is complete for one ordinary `type="video"` row with exactly one VIDEO and zero or one static IMAGE; multi-video, multi-image, broader mixed/live-photo/animation shapes, remaining platforms and the broader user goal remain active work.
