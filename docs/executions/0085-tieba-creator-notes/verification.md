**English** | [中文](verification.zh.md)

# Verification: durable Tieba creator-work delivery

## Final result

| Gate | Result | Evidence and boundary |
| --- | --- | --- |
| Scan state machine | `PASS` | `tests/unit/test_tieba_creator_work.py` (12 cases): the `tb-work-v1:` cursor round-trips byte exactly and rejects a binding change; the four stop reasons stay distinct; `max_items` keeps the identical page number and re-lists the same page; a repeated identity tuple accumulates stalls and blocks at the bound; head reconciliation reproduces the boundary; coverage round-trips through its JSON line; page numbers and thread ids are bounded. |
| Capture shim | `PASS` | `tests/contract/test_tieba_creator_capture.py` (10 cases): only `thread_info.tid`/`id` identities survive, the persisted page mapping carries no `thread_info` or title; six ambiguous shapes are rejected; an empty list is accepted as a valid page; a `DataFetchError` records `access_restricted` with no boundary; a complete page reaches `has_more_false`. |
| Delivery transitions | `PASS` | `tests/integration/test_tieba_creator_notes_delivery.py` (3 cases): a closed receipt moves backfill → reconciling → incremental and records `last_page_number == 1`; a restricted unit blocks with `tieba_access_restricted` and no source end; a terminal failure blocks with the fixed code. |
| Single-transaction ingestion | `PASS` | The same integration file drives `ingest_tieba_bounded` through the production path, so page, cursor, Run and Content commit together. |
| Migration | `PASS` | `tests/integration/test_database.py` proves the migrated schema equals the metadata (29 domain tables) and downgrades cleanly; `tests/integration/test_packaged_migrations.py` proves the wheel ships `0019_tieba_creator_notes` and reports it as head. |
| Head-revision pins | `PASS` | Packaged migrations, database domain tables, CLI expected/known revisions and table counts (29), offline/scheduled pipeline revision assertions, CLI support bundle and API support bundle all advanced to `0019_tieba_creator_notes`. |
| Manager/bridge wiring | `PASS` | `tests/contract/test_mediacrawler_bridge.py`, `tests/integration/test_mediacrawler_scheduler_handler.py`, `tests/integration/test_pipeline_worker.py` and `tests/integration/test_scheduler_repository.py` pass with the sixth bounded contract installed. |
| Full Python suite | `PASS` | `7281 passed, 63 skipped, 108 warnings in 1525.68s`. Skips are the documented Windows/POSIX symlink, POSIX-directory and PostgreSQL-URL branches. |
| Ruff lint / format | `PASS` | `ruff check src tests` → `All checks passed!`; `ruff format --check src tests` → all files formatted. |
| Strict mypy | `PASS` | `mypy --strict src` → `Success: no issues found in 178 source files`. |
| Docs / upstreams | `PASS` | `scripts/check_docs.py` → links OK (846 files); `scripts/check_upstreams.py` → `Upstreams OK (2 locked checkouts verified)`. |
| Web gates | `PASS` | `svelte-check` → `0 errors and 0 warnings`; `vitest` → `30 files / 843 tests`; Prettier → clean. The Web app is unchanged by this execution. |
| Docker / Linux host / live login / real requests | `NOT_RUN` | No deployment, account, platform request or real byte fetch. |

## One gate observation

The first full run on this tree ended `1 failed, 7281 passed`. The failure,
`test_log_center_api.py::test_old_operation_has_explicit_missing_stage_evidence_and_bounded_controls`,
passed on an isolated rerun of the whole file (`30 passed`), so it is recorded as
an order- or timing-sensitive test rather than a defect introduced here. No
mechanism was found, so nothing was changed for it.

## Boundary notes

- `has_more_false` is a *server-declared* end and is retained with its page
  witness, but it still only opens reconciliation; only a stable head re-list
  advances to incremental.
- Because the page number always increments, a server that keeps serving the same
  page is invisible to the cursor itself. The durable layer therefore compares
  page identity tuples and blocks after a bounded number of non-advancing units
  with `tieba_page_stalled`.
- A business `error_code != 0`, a malformed body, `DataFetchError`/`IPBlockError`
  or a transport failure is `access_restricted`, never an end.

## Commands run

```text
python -m pytest -q
python -m pytest tests/unit/test_tieba_creator_work.py tests/contract/test_tieba_creator_capture.py -q
python -m pytest tests/integration/test_tieba_creator_notes_delivery.py -q
python -m pytest tests/integration/test_packaged_migrations.py tests/integration/test_database.py -q
python -m ruff check src tests
python -m ruff format --check src tests
python -m mypy --strict src
python scripts/check_docs.py
python scripts/check_upstreams.py
npm --prefix web run check | test | format:check
git diff --check
```
