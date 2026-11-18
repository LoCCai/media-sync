**English** | [中文](verification.zh.md)

# Verification: SQLite scratch-credential residue hardening

## Final result

| Gate | Result | Evidence and boundary |
| --- | --- | --- |
| Reproduction of the leak | `CONFIRMED` | Before the fix, the `0003` upgrade left the sentinel at byte 132972 (page 32) on the default long temporary path; the same test passed with a short `--basetemp`. |
| Mechanism isolation | `CONFIRMED` | Same pre-upgrade copy upgraded with a `secure_delete=ON` connect listener left no sentinel; without the pragma it did. `VACUUM` after upgrade also removed it, so the residue is freed-page retention. |
| Connection policy test | `PASS` | `tests/integration/test_database.py::test_sqlite_pragmas_and_nested_work_rollback` now asserts `PRAGMA secure_delete == 1` beside the existing `foreign_keys`/`journal_mode`/`busy_timeout` assertions. |
| `0003` outcome test | `PASS` | `tests/integration/test_packaged_migrations.py::test_0003_upgrade_preserves_only_complete_verified_legacy_asset` passes on both the default long temporary path and the previously failing deep `--basetemp`. |
| Database slice | `PASS` | `tests/integration/test_database.py`: `26 passed in 11.16s`. |
| Full Python suite | `PASS` | `7198 passed, 63 skipped, 108 warnings in 1514.94s`. Skips are the documented Windows/POSIX symlink, POSIX-directory and PostgreSQL-URL branches. |
| Ruff lint / format | `PASS` | `ruff check src tests` → `All checks passed!`; `ruff format --check src tests` → `438 files already formatted`. |
| Strict mypy | `PASS` | `mypy --strict src` → `Success: no issues found in 169 source files`. |
| Docs / upstreams | `PASS` | `scripts/check_docs.py` → `Documentation links OK (814 Markdown files checked)`; `scripts/check_upstreams.py` → `Upstreams OK (2 locked checkouts verified)`. Note: doc counts were captured before the four 0082 files were added; the closeout rerun covers them. |
| Web gates | `PASS` | `svelte-check` → `0 errors and 0 warnings`; `vitest` → `30 files / 843 tests`; source untouched by this execution. |
| Deployment / Linux host | `NOT_RUN` | No deployment was performed. |
| Retroactive scrub of existing deployments | `NOT_RUN` | Requires an operator `VACUUM`; explicitly out of scope. |

## One additional finding while running the gates

The first full-suite run on this workstation ended `2 failed, 7196 passed`. The
second failure, `test_timeout_and_cancellation_kill_entire_tree[cancel]`, is a
timing-sensitive process-tree assertion; it passed on three consecutive
isolated reruns and on the final full suite. It is recorded as flaky rather than
fixed, because no deterministic mechanism was observed.

Two 0081 test files were also committed unformatted, which made
`ruff format --check` fail on an otherwise clean tree. They were reformatted in
this execution so the whole-repository gate reflects reality.

## Commands run

```text
python -m pytest -q
python -m pytest tests/integration/test_database.py -q
python -m pytest tests/integration/test_packaged_migrations.py::test_0003_upgrade_preserves_only_complete_verified_legacy_asset -q
python -m ruff check src tests
python -m ruff format --check src tests
python -m mypy --strict src
python scripts/check_docs.py
python scripts/check_upstreams.py
npm --prefix web run check | test
git diff --check
```

## Operator note

Erasing pages that a pre-0082 deployment already freed requires an explicit
operator action on a stopped writer:

```bash
docker compose stop media-sync supervisor
docker compose run --rm --no-deps --entrypoint /app/.venv/bin/python media-sync \
  -c "import sqlite3,os; p='/data/state/media-sync.sqlite3'; c=sqlite3.connect(p); c.execute('VACUUM'); c.close()"
docker compose up -d --no-deps media-sync
```

The exact database path must be read from the deployment's `MEDIA_SYNC_DATABASE_URL`
before running this; do not copy the illustrative path.
