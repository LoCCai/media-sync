**English** | [中文](verification.zh.md)

# Verification: durable Weibo creator-note delivery

## Final result

| Gate | Result | Evidence and boundary |
| --- | --- | --- |
| Scan state machine | `PASS` | `tests/unit/test_weibo_creator_work.py` (14 cases): cursor round-trip is byte exact and rejects a binding change; the four stop reasons are distinct; `max_items` leaves the identical `since_id` and re-lists the same page; a repeated echo accumulates stalls and blocks at the bound; head reconciliation reproduces the boundary; coverage round-trips through its JSON line; an inferred end is never reported as completeness. |
| Capture shim | `PASS` | `tests/contract/test_weibo_creator_capture.py` (11 cases): only `card_type == 9` cards become identities, the persisted page mapping contains no `mblog`, `note-*` or total payload; seven ambiguous shapes are rejected; a `DataFetchError`/falsy body/missing `cards` records `access_restricted` with no boundary; a complete page reaches `total_inferred_end`. |
| Delivery transitions | `PASS` | `tests/integration/test_weibo_creator_notes_delivery.py` (4 cases): a closed receipt moves backfill → reconciling → incremental and the payload exposes `declared_total`; a restricted unit blocks with `weibo_access_restricted` and no source end; a stalled cursor blocks with `weibo_cursor_stalled`; a terminal failure blocks with the fixed code. |
| Single-transaction ingestion | `PASS` | The same integration file drives `ingest_weibo_bounded` through the production path, so page, cursor, Run and Content commit together. |
| Migration | `PASS` | `tests/integration/test_database.py` proves the migrated schema equals the metadata (28 domain tables) and downgrades cleanly; `tests/integration/test_packaged_migrations.py` proves the wheel ships `0018_weibo_creator_notes` and reports it as head. |
| Head-revision pins | `PASS` | Packaged migrations, database domain tables, CLI expected/known revisions and table counts, offline/scheduled pipeline revision assertions, CLI support bundle and API support bundle all advanced to `0018_weibo_creator_notes`. |
| Manager/bridge wiring | `PASS` | `tests/contract/test_mediacrawler_bridge.py`, `tests/integration/test_mediacrawler_scheduler_handler.py`, `tests/integration/test_pipeline_worker.py` and `tests/integration/test_scheduler_repository.py` pass with the fifth bounded contract installed. |
| Full Python suite | `PASS` | `7257 passed, 63 skipped, 108 warnings in 1667.95s`. Skips are the documented Windows/POSIX symlink, POSIX-directory and PostgreSQL-URL branches. |
| Ruff lint / format | `PASS` | `ruff check src tests` → `All checks passed!`; `ruff format --check src tests` → all files formatted. |
| Strict mypy | `PASS` | `mypy --strict src` → `Success: no issues found in 174 source files`. |
| Docs / upstreams | `PASS` | `scripts/check_docs.py` → links OK; `scripts/check_upstreams.py` → `Upstreams OK (2 locked checkouts verified)`. |
| Web gates | `PASS` | `svelte-check` → `0 errors and 0 warnings`; `vitest` → `30 files / 843 tests`; Prettier → clean. The Web app is unchanged by this execution. |
| Docker / Linux host / live login / real requests | `NOT_RUN` | No deployment, account, platform request or real byte fetch. |

## Boundary notes

- The arithmetic end is a *declared-total inference*, exactly as upstream computes
  it. `total_inferred_end` therefore only opens reconciliation; the payload keeps
  `declared_total` visible so no reader can mistake it for proof of a complete
  history.
- An empty filtered page that still advances `since_id` is progress, not an end;
  only an absence of `total` produces `empty_page_end`, and a repeated echo is
  counted as a stall rather than silently re-requested forever.
- The shim reads only the pinned `get_notes_by_creator` and
  `get_note_info_by_id` methods. The richer `cardlistInfo` fields beyond
  `since_id` and `total` are deliberately not persisted.

## Commands run

```text
python -m pytest -q
python -m pytest tests/unit/test_weibo_creator_work.py tests/contract/test_weibo_creator_capture.py -q
python -m pytest tests/integration/test_weibo_creator_notes_delivery.py -q
python -m pytest tests/integration/test_packaged_migrations.py tests/integration/test_database.py -q
python -m ruff check src tests
python -m ruff format --check src tests
python -m mypy --strict src
python scripts/check_docs.py
python scripts/check_upstreams.py
npm --prefix web run check | test | format:check
git diff --check
```
