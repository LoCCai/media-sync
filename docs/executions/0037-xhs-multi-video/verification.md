**English** | [中文](verification.zh.md)

# Execution 0037 verification

- Status: Frozen offline bounded XHS multi-video scope passes all final gates; live qualification `NOT_RUN`
- Date: 2026-09-03
- Predecessor: Execution 0036 closeout `145176f8624f5c1518b6cd28cea3f9aa3d938454`
- Plan commit: `d858147`

## Baseline (before any 0037 change)

| Check | Result |
| --- | --- |
| 0036 focused regression | `PASS — 341 passed in 4.29s` |
| 0036 complete suite | `PASS — 2016 passed, 1 skipped in 370.47s` |
| Ruff, format, strict mypy, docs, upstreams | `PASS` (recorded in the 0036 verification) |

## Implemented evidence

| Scope | Result |
| --- | --- |
| Bounded materialization | `PASS` — 1–16 comma-joined candidates materialize ordered `{note_id}:video:0..N-1` VIDEO assets; a 17-candidate record quarantines as `INVALID_RECORD`; the established tolerant parsing otherwise stays unchanged |
| Refresh scalar widening | `PASS` — `_validated_xhs_media_scalar` accepts the bounded 1–16 ordered distinct tuple with every candidate revalidated as a legal `xhscdn.com` URL; duplicates, embedded drift and above-bound scalars close |
| Creator-target binding | `PASS` — the fresh detail assets must reproduce the video tuple exactly (count, positions 0..N-1, URL order); replaced paths close as `locator_refresh_asset_mismatch` and 17-candidate scalars close as `locator_refresh_schema_changed` |
| Download and publication | `PASS` — both positions download through the DEFAULT profile with MP4 probes, archive under distinct SHA-256 digests and publish two Emby episodes with zero-work replay |
| Non-retention | `PASS` — the multi-video sentinel and both signed URLs appear nowhere in retained runtime/work/archive/export/library trees or SQLite artifacts |

## Test and quality gates

| Check | Command | Result |
| --- | --- | --- |
| Focused implementation regression | `uv run pytest -q tests/unit/test_mediacrawler_refresh.py tests/contract/test_mediacrawler_ingestion.py tests/integration/test_xhs_playable_video_pipeline.py tests/integration/test_xhs_creator_authority_pipeline.py tests/integration/test_scheduled_offline_pipeline.py` | `PASS — 344 passed in 6.32s` |
| Multi-video closeout rerun | `uv run pytest -q tests/integration/test_xhs_playable_video_pipeline.py::test_xhs_multi_video_reaches_emby_with_zero_work_replay` | `PASS — 1 passed in 2.18s` |
| Complete suite | `uv run pytest -q` | `PASS — 2020 passed, 1 skipped in 370.56s`; the skip is the Windows-inapplicable POSIX mode-bit boundary |
| Ruff and format | `uv run ruff check .`; `uv run ruff format --check .` | `PASS — all checks; 498 files formatted` |
| Strict mypy | `uv run mypy --strict src` | `PASS — no issues in 85 source files` |
| Compileall and build | `uv run python -m compileall -q src/media_sync`; `uv build` | `PASS — compiled; wheel and source distribution built` |
| Documentation and upstream locks | `uv run python scripts/check_docs.py`; `uv run python scripts/check_upstreams.py` | `PASS — 328 Markdown files; 2 locked clean checkouts` |
| Git/upstream audit | explicit status and tracked-path scans | `PASS — intended changes only; tracked runtime/upstream/dist 0; both upstream dirty counts 0` |

## Not claimed

No coverage run is claimed. No real account, login, creator feed, XHS API, CDN byte or Emby/Jellyfin server interaction was performed; every live row stays `NOT_RUN`.
