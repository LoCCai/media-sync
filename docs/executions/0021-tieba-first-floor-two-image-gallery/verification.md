**English** | [中文](verification.zh.md)

# Execution 0021 verification

- Status: Frozen offline scope passes all final gates; authenticated/live qualification `NOT_RUN`
- Date: 2026-09-02
- Predecessor: `e5d871050cdf25da1a51e2f057ba317dea2cffb1`
- Plan commit: `5095ed6e803a8a2f0a3134e756dd3e101fef10bd`
- Implementation commit: `e0fb8d572c8f5535a5495c2dfbf5b9cdf78461e7`

## Baseline

| Check | Result |
| --- | --- |
| Execution 0020 focused regression | `PASS — 368 passed in 41.18s` |
| Execution 0020 complete suite | `PASS — 1650 passed, 1 skipped in 310.82s` |
| Quality/build/docs/upstreams/audit | `PASS` |
| Real two-image response-shape observation | `PASS as transient bounded evidence only |

## Implemented evidence

| Scope | Result |
| --- | --- |
| Exact-two-image capture and single-image compatibility | `PASS` — separate v2 ordered list; v1 string unchanged; dual claims, duplicate durable identity and three-or-more images rejected |
| Locked loss boundary and concurrency | `PASS` — pinned extractor still discards both locators; exact-object gather-child → parent-store carry and peer isolation proven |
| Ordered ARTICLE + two IMAGE normalization | `PASS` — exact `<note_id>:image:0/1`; both private fields recursively absent; only distinct query-free hints durable |
| Position 0/1 detail refresh and drift rejection | `PASS` — full persisted gallery is bound into refresh context; complete current order/hints required; missing, reorder, replacement and dual claim rejected |
| Credential-free transfer and static gates | `PASS` — both URLs use DEFAULT profile without Cookie/Authorization/Referer/Origin; production Tieba static gate accepts tested JPEG/PNG |
| Two-image SQLite/archive/Emby composition | `PASS` — two exact downloads and SHA-256 archives; poster/backdrop/two gallery files/body/NFO/source; query-only replay adds zero detail/DNS/HTTP/archive/export work |
| Retained-state boundary | `PASS` — SQLite/runtime/work/archive/export/library whole-tree assertions retain neither private field nor any `tbpicau` token/value |

## Test and quality gates

| Check | Command | Result |
| --- | --- | --- |
| Focused implementation regression | `uv run pytest -q tests/unit/test_tieba_media.py tests/contract/test_tieba_upstream_first_floor_media.py tests/contract/test_mediacrawler_detail_refresh.py tests/contract/test_mediacrawler_ingestion.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_mediacrawler_download_runtime.py tests/integration/test_tieba_first_floor_image_pipeline.py tests/integration/test_asset_download_orchestration.py` | `PASS — 413 passed in 44.50s` |
| Locked Tieba source contract | `uv run pytest -q tests/contract/test_tieba_upstream_first_floor_media.py` | `PASS — 6 passed in 3.42s` |
| Two-image SQLite→Emby composition | `uv run pytest -q tests/integration/test_tieba_first_floor_image_pipeline.py` | `PASS — 2 passed in 1.94s` |
| Complete suite | `$env:PYTHONDONTWRITEBYTECODE='1'; uv run pytest -q -p no:cacheprovider` | `PASS — 1668 passed, 1 skipped in 314.72s`; skip is the Windows-inapplicable POSIX mode-bit boundary |
| Ruff and format | `uv run ruff check .`; `uv run ruff format --check .` | `PASS — all checks; 262 files formatted |
| Strict mypy | `uv run mypy --strict src` | `PASS — no issues in 82 source files |
| Compileall and build | `uv run python -m compileall -q src/media_sync`; `uv build` | `PASS — wheel and source distribution built |
| Documentation and upstream locks | `uv run python scripts/check_docs.py`; `uv run python scripts/check_upstreams.py` | `PASS — 100 Markdown files; 2 locked checkouts |
| Git/upstream audit | explicit status, tracked/untracked/runtime/upstream and diff checks | `PASS — tracked 280; untracked 0; tracked runtime/upstream 0; both upstream dirty counts 0 |

No coverage run is claimed.

## Git reconciliation

Implementation `e0fb8d572c8f5535a5495c2dfbf5b9cdf78461e7` is reconciled across local `main`, `origin/main` and GitHub. The commit containing this record is the bilingual documentation closeout; its self-referential SHA is intentionally left to Git history.

## Live qualification

| Row | Result |
| --- | --- |
| Real Tieba QR/Cookie login | `NOT_RUN` |
| Authenticated creator/detail gallery | `NOT_RUN` |
| Future real CDN byte/redirect behavior | `NOT_RUN` |
| Real Emby/Jellyfin scan/display | `NOT_RUN` |

Offline evidence cannot imply these rows. Three-or-more images and complete Tieba gallery/media support also remain outside this execution.
