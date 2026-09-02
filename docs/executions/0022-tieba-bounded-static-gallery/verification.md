**English** | [中文](verification.zh.md)

# Execution 0022 verification

- Status: Frozen offline scope passes all final gates; authenticated/live qualification `NOT_RUN`
- Date: 2026-09-02
- Predecessor: `817875bdd1902f54c72397fa7da46359fbe33207`
- Plan commit: `fbcb7cf5c642fc9da210faa5d92b6886b350a9b8`
- Implementation commit: `b6d03aa1c6705e52c2e47c63086a5b7200c208e7`

## Baseline

| Check | Result |
| --- | --- |
| Execution 0021 focused regression | `PASS — 413 passed in 44.50s` |
| Execution 0021 complete suite | `PASS — 1668 passed, 1 skipped in 314.72s` |
| Quality/build/docs/upstreams/audit | `PASS` |
| Local/tracking/GitHub reconciliation | `PASS — 817875bdd1902f54c72397fa7da46359fbe33207` |

## Implemented evidence

| Scope | Result |
| --- | --- |
| v3 capture and compatibility | `PASS` for 3 and 64 ordered images; reject 65, duplicates, malformed items and multi-version claims; retain exact v1/v2 behavior |
| Ordered normalization and storage | `PASS` for N stable remote IDs/positions, query-free durable hints and recursive private-field removal |
| Complete-gallery refresh | `PASS` for every valid position; reject missing, added, reordered, replaced and duplicated galleries |
| Three-image archive/Emby composition | `PASS` for distinct static bytes, SHA-256 archives, poster/backdrop/three gallery files/body/NFO/source and query-only zero-work replay |
| Retained-state boundary | `PASS` with no private v1/v2/v3 field or signed-query token/value in retained trees |

## Test and quality gates

| Check | Command | Result |
| --- | --- | --- |
| Focused implementation regression | `uv run pytest -q tests/unit/test_tieba_media.py tests/contract/test_tieba_upstream_first_floor_media.py tests/contract/test_mediacrawler_detail_refresh.py tests/contract/test_mediacrawler_ingestion.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_mediacrawler_download_runtime.py tests/integration/test_tieba_first_floor_image_pipeline.py tests/integration/test_asset_download_orchestration.py` | `PASS — 433 passed in 48.91s` |
| Bounded Tieba SQLite→Emby compositions | `uv run pytest -q tests/integration/test_tieba_first_floor_image_pipeline.py` | `PASS — 3 passed in 2.88s` |
| Complete suite | `$env:PYTHONDONTWRITEBYTECODE='1'; uv run pytest -q -p no:cacheprovider` | `PASS — 1688 passed, 1 skipped in 321.22s`; skip is the Windows-inapplicable POSIX mode-bit boundary |
| Ruff and format | `uv run ruff check .`; `uv run ruff format --check .` | `PASS — all checks; 266 files formatted |
| Strict mypy | `uv run mypy --strict src` | `PASS — no issues in 82 source files |
| Compileall and build | `uv run python -m compileall -q src/media_sync`; `uv build` | `PASS — wheel and source distribution built |
| Documentation and upstream locks | `uv run python scripts/check_docs.py`; `uv run python scripts/check_upstreams.py` | `PASS — 104 Markdown files; 2 locked checkouts |
| Git/upstream audit | explicit status, tracked/runtime/upstream and diff checks | `PASS — tracked 284; untracked 0; tracked runtime/upstream 0; both upstream dirty counts 0 |

No coverage run is claimed.

## Git reconciliation

Implementation `b6d03aa1c6705e52c2e47c63086a5b7200c208e7` is reconciled across local `main`, `origin/main` and GitHub. The commit containing this record is the bilingual documentation closeout; its self-referential SHA is intentionally left to Git history.

## Live qualification

| Row | Result |
| --- | --- |
| Real Tieba QR/Cookie login | `NOT_RUN` |
| Authenticated creator/detail gallery | `NOT_RUN` |
| Real CDN byte/redirect behavior | `NOT_RUN` |
| Real Emby/Jellyfin scan/display | `NOT_RUN` |

Offline evidence cannot imply these rows or complete Tieba media support.
