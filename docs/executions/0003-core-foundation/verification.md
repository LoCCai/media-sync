**English** | [中文](verification.zh.md)

# Execution 0003 verification

- Verification date: 2026-08-30
- Network/account policy: automated tests only; no live platform calls

## Final quality gate

| Check | Command | Status |
| --- | --- | --- |
| Locked dependencies | `uv sync --all-groups --locked` | PASS — 44 resolved, 43 audited |
| Lint | `uv run ruff check .` | PASS |
| Format | `uv run ruff format --check .` | PASS — 69 files |
| Strict types | `uv run mypy src/media_sync` | PASS — 26 source files |
| Tests | `uv run pytest` | PASS — 83 tests in 6.29s |
| Coverage | `uv run pytest --cov=media_sync --cov-report=term` | PASS — 83 tests, 86% total |
| Package build | `uv build` | PASS — sdist and wheel |
| Packaged migrations | `tests/integration/test_packaged_migrations.py` in pytest | PASS — source and unpacked-wheel upgrade |
| SQLite repositories | `tests/integration/test_database.py` in pytest | PASS — 12 integration cases |
| Sync persistence | `tests/integration/test_sync_pipeline.py` in pytest | PASS — two-pass idempotency and rollback |
| CLI workflow | `tests/integration/test_cli_workflow.py` in pytest | PASS — init→account→subscription→two syncs |
| CLI discovery | `uv run media-sync --help` | PASS — db/account/subscription/sync commands listed |
| Database inspection | isolated `media-sync db status --json` in CLI tests | PASS — current revision and 10/10 tables; missing DB exits 1 without creating it |
| Doctor | `uv run media-sync doctor --json` | PASS — Python 3.11.8, tools detected, no database URL |
| Documentation | `uv run python scripts/check_docs.py` | PASS — 28 Markdown files |
| Upstream locks | `uv run python scripts/check_upstreams.py` | PASS — 2 pinned checkouts |
| Patch whitespace | `git diff --check` | PASS |

## Behavioral evidence

- The SQLite integration suite checks foreign keys, uniqueness, platform/content/asset/job vocabularies, migration/metadata parity, concurrent upsert identity, monotonic watermarks, run-state CAS, event order, exclusive claims, lease expiry and fencing.
- The synchronization integration suite performs two Fake runs through the real SQLAlchemy adapter and finishes with exactly 1 author, 4 contents, 4 assets, 2 runs and 10 ordered run events. Per-run discovered/asset counters equal the application result.
- A failure injected on the second content write proves that an outer transaction abort removes every author/content/asset/run/event write from that failed attempt.
- The wheel test imports `media_sync` from an unpacked built wheel—not the source tree—and upgrades an empty SQLite database to revision `0001_core`.
- CLI tests verify unsupported phone login, malformed enums, raw Cookie-like credential input, subscription conflicts and injected domain errors fail without persisting or printing sentinel secrets.

## Live qualification

| Platform | Login | Creator scan | Media | Status |
| --- | --- | --- | --- | --- |
| `xhs` | Not run | Not run | Not run | `NOT_RUN` |
| `dy` | Not run | Not run | Not run | `NOT_RUN` |
| `ks` | Not run | Not run | Not run | `NOT_RUN` |
| `bili` | Not run | Not run | Not run | `NOT_RUN` |
| `wb` | Not run | Not run | Not run | `NOT_RUN` |
| `tieba` | Not run | Not run | Not run | `NOT_RUN` |
| `zhihu` | Not run | Not run | Not run | `NOT_RUN` |

No credentials, browser profiles, platform endpoints or live media were used. Automated Fake/fixture results do not change this matrix.
