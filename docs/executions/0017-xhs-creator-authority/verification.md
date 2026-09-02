**English** | [中文](verification.zh.md)

# Execution 0017 verification

- Status: Offline and documentation gates pass; live qualification `NOT_RUN`
- Date: 2026-09-01
- Plan commit: `9d19e7e`
- Implementation commit: `2f8dbaa`

## Implementation evidence

| Scope | Result | Evidence |
| --- | --- | --- |
| Authority XOR and schema v3 | `PASS` | Exact note/creator URL, identity and decoded xsec validation repeat at parent/request/child boundaries. |
| Exact fallback and override | `PASS` | Exact Subscription creator secret and bounded `max_items`; explicit detail wins with no creator-secret resolution. |
| Static target and composition | `PASS` | One ordinary IMAGE/GALLERY all-IMAGE target reaches DEFAULT HTTP, image validation, SHA-256 archives and idempotent Emby output; replay adds no work. |
| Preflight and taxonomy | `PASS` | Missing/damaged VERIFIED repair preflights before mutation; valid replay is zero-secret; fixed causes remain distinct; non-XHS option use is rejected. |
| Durable raw and secret sinks | `PASS` | Field-specific authority/query removal preserves accepted value shapes and retains no execution marker. |

## Six review repairs

1. Unique ordinary-static creator result gate.
2. Duplicate target rejection before Asset selection.
3. VERIFIED archive repair preflight before quarantine/reset with valid replay zero-secret.
4. Dedicated pipeline error taxonomy and scheduler vocabulary.
5. Durable raw shape preservation plus field-specific authority/query removal.
6. Non-XHS CLI use of the XHS option rejected.

## Test and quality gates

| Check | Command | Result |
| --- | --- | --- |
| Focused nine-file pytest | `uv run pytest -q tests/contract/test_mediacrawler_detail_refresh.py tests/integration/test_asset_download_orchestration.py tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_mediacrawler_download_runtime.py tests/integration/test_pipeline_runtime.py tests/integration/test_pipeline_worker.py tests/integration/test_xhs_creator_authority_pipeline.py tests/unit/test_cli.py tests/unit/test_mediacrawler_refresh.py` | `PASS` — `266 passed in 56.90s` |
| Post-format related | `uv run pytest -q tests/unit/test_cli.py tests/integration/test_pipeline_runtime.py` | `PASS` — `89 passed in 13.74s` |
| Complete suite | `uv run pytest -q` | `PASS` — `1298 passed, 1 skipped in 365.73s`; only skip: Windows POSIX mode-bit: Windows POSIX mode-bit |
| Final pipeline/worker | `uv run pytest -q tests/integration/test_pipeline_runtime.py tests/integration/test_pipeline_worker.py` | `PASS` — `52 passed in 4.57s` |
| Ruff | `uv run ruff check .` | `PASS` |
| Format | `uv run ruff format --check .` | `PASS` — 234 files |
| Strict mypy | `uv run mypy src/media_sync` | `PASS` — 79 sources |
| Compileall | `uv run python -m compileall -q src/media_sync` | `PASS` |
| Upstream locks | `uv run python scripts/check_upstreams.py` | `PASS` — 2 entries |
| Build | `uv build` | `PASS` — 2 artifacts |
| Diff checks | `git diff --check` and `git diff --cached --check` | `PASS` |
| Post-edit docs | `uv run python scripts/check_docs.py` | `PASS` — 84 Markdown files checked |

No coverage run is claimed.

## Retained/Git audit

`tracked=252`; `untracked=0`; `tracked_forbidden=0`; `suspicious_untracked=0`; `runtime_and_build_files=914`; `runtime_execution0017_marker_hits=0`; `sentinel_roots_preserved=2/2`; MediaCrawler dirty paths `0`; bili-sync-up dirty paths `0`.

## Live qualification

| Row | Result |
| --- | --- |
| Real XHS QR/Cookie login | `NOT_RUN` |
| Real creator/feed/detail lookup | `NOT_RUN` |
| Real XHS CDN image bytes | `NOT_RUN` |
| Real Emby/Jellyfin scan/playback | `NOT_RUN` |

Offline mocks do not imply these rows. Execution 0017 is complete, while automatic XHS video/mixed/dynamic/expiry recovery, remaining platform shapes and the broader user goal remain active work.
