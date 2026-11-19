**English** | [中文](verification.zh.md)

# Verification: durable Zhihu creator-answer delivery

## Final result

| Gate | Result | Evidence and boundary |
| --- | --- | --- |
| Scan state machine | `PASS` | `tests/unit/test_zhihu_creator_work.py` (13 cases): the `zh-work-v1:` cursor round-trips byte exactly and rejects a binding change; the four stop reasons stay distinct; a small `max_items` requests and consumes exactly its own `limit`; an unfinished page keeps the identical offset; a repeated identity tuple accrues shifts and blocks with `zhihu_window_shifted`; head reconciliation reproduces the boundary through `unchanged` answers; coverage round-trips through its JSON line; a failed detail never hides unrelated answers; offsets and content ids are bounded. |
| Capture shim | `PASS` | `tests/contract/test_zhihu_creator_capture.py` (9 cases): only answer ids survive, the persisted page mapping carries no body or `content_text`; six ambiguous shapes are rejected; a `DataFetchError` records `access_restricted` with no boundary; a complete page reaches `is_end`. |
| Delivery transitions | `PASS` | `tests/integration/test_zhihu_creator_answers_delivery.py` (3 cases): a closed receipt moves backfill → reconciling → incremental and records `last_offset == 0`; a restricted unit blocks with `zhihu_access_restricted` and no source end; a terminal failure blocks with the fixed code. |
| Single-transaction ingestion | `PASS` | The same integration file drives `ingest_zhihu_bounded` through the production path, so page, cursor, Run and Content commit together. |
| Migration | `PASS` | `tests/integration/test_database.py` proves the migrated schema equals the metadata (30 domain tables) and downgrades cleanly; `tests/integration/test_packaged_migrations.py` proves the wheel ships `0020_zhihu_creator_answers` and reports it as head. |
| Head-revision pins | `PASS` | Packaged migrations, database domain tables, CLI expected/known revisions and table counts (30), offline/scheduled pipeline revision assertions, CLI support bundle and API support bundle all advanced to `0020_zhihu_creator_answers`. |
| Bridge/handler wiring | `PASS` | `tests/contract/test_mediacrawler_bridge.py`, `tests/integration/test_mediacrawler_scheduler_handler.py`, `tests/integration/test_pipeline_worker.py` and `tests/integration/test_scheduler_repository.py` pass with the seventh bounded contract installed. |
| Full Python suite | `PASS` | `7308 passed, 62 skipped, 108 warnings in 1757.28s`. Skipped checks are the documented Windows/POSIX symlink, POSIX-directory and PostgreSQL-URL branches; the packaged-wheel artifact check now executes instead of skipping. |
| Ruff lint / format | `PASS` | `ruff check src tests` → `All checks passed!`; `ruff format --check src tests` → all files formatted. |
| Strict mypy | `PASS` | `mypy --strict src` → `Success: no issues found in 182 source files`. |
| Docs / upstreams | `PASS` | `scripts/check_docs.py` → links OK; `scripts/check_upstreams.py` → `Upstreams OK (2 locked checkouts verified)`. |
| Web gates | `PASS` | `svelte-check` → `0 errors and 0 warnings`; `vitest` → `30 files / 843 tests`; Prettier → clean. The Web app is unchanged by this execution. |
| Docker / Linux host / live login / real requests | `NOT_RUN` | No deployment, account, platform request or real byte fetch. |

## Boundary notes

- `paging.is_end` is a *server-declared* end and is retained with its page witness,
  but it only opens reconciliation; only a stable head re-list advances to
  incremental.
- The integer offset is a page*limit product, so an insertion or deletion shifts
  the window while every response still looks valid. The durable layer therefore
  compares page identity tuples; a non-empty intersection replays the same offset
  and blocks after a bounded number of shifted units with `zhihu_window_shifted`.
- A falsy or malformed body, `DataFetchError`/`IPBlockError` or a transport failure
  is `access_restricted`, never an end.

## Commands run

```text
python -m pytest -q
python -m pytest tests/unit/test_zhihu_creator_work.py tests/contract/test_zhihu_creator_capture.py -q
python -m pytest tests/integration/test_zhihu_creator_answers_delivery.py -q
python -m pytest tests/integration/test_packaged_migrations.py tests/integration/test_database.py -q
python -m ruff check src tests
python -m ruff format --check src tests
python -m mypy --strict src
python scripts/check_docs.py
python scripts/check_upstreams.py
npm --prefix web run check | test | format:check
git diff --check
```
