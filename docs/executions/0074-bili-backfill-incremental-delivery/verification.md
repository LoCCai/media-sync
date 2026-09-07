**English** | [中文](verification.zh.md)

# Verification

Implementation revision: `9c81c4b` (`feat(bili): complete durable backfill and incremental delivery`). Planning baseline: `3fa5139`.

## Final results

| Gate | Result | Evidence and boundary |
| --- | --- | --- |
| Focused Bilibili delivery regressions | `PASS` | Recorded focused runs passed `26 tests in 49.90s` and `147 tests in 4.70s`. Coverage includes 67 uploads over multiple ≤30-item units, a shifted 68-item source, source-end/head reconciliation, retry-backlog partial results, restart/transaction fences, exact receipt/public projection, one-new-upload real download/archive/NFO and byte-identical zero work. |
| Login deadline correction | `PASS` | The exact no-frame/live-child test passed `1 test in 2.05s`; the complete login contract then passed `68 tests in 81.78s`. EOF alone no longer defeats the parent deadline. |
| Complete Python suite | `PASS` | Final post-correction run: `7048 passed, 41 skipped, 108 warnings in 1667.43s (0:27:47)`. Skips are platform/PostgreSQL qualification branches plus the in-suite `uv` PATH check; the separate package build below used the configured absolute `uv` path. Warnings are the existing Starlette TestClient and Python 3.12+ SQLite adapter deprecations. |
| Corrected complete-run failures | `FIXED` | The first run allowed to finish after the login/schema corrections produced `7037 passed, 41 skipped, 11 failed`: ten immutable-preview failures shared the Windows path/handle ctime mismatch and one Kuaishou deep-JSON case showed decoder-dependent acceptance. Isolated reruns reproduced both. After repair, archive preview passed `109 tests`, the related API/console union passed `13 tests`, Kuaishou Cookie login passed `117 tests`, and the complete suite above passed. |
| Complete media-sync Web suite | `PASS` | `26 files / 802 tests` passed. Closed parsing covers legacy and source-Run receipts plus conservative Bilibili progress fallback. |
| Svelte and production Web build | `PASS` | `svelte-check` reported 0 errors and 0 warnings. Vite transformed 4,086 server and 4,095 client modules and completed the static build. |
| Frontend formatting | `PASS` | Repository-wide Prettier check passed. |
| Python lint/format/type | `PASS` | Ruff lint passed; Ruff format reported 400 files already formatted; strict mypy reported no issues in 155 source files. The login correction was rechecked with Ruff and strict mypy. |
| Locked upstreams | `PASS` | `scripts/check_upstreams.py` verified both locked checkouts. MediaCrawler remains pinned at `d6f7c5bb906b6dac40ddf343ef9e26438a3de092`; no upstream source was modified. |
| Python packaging | `PASS` | A fresh wheel and sdist built successfully. Both contain `0014_bili_delivery_baseline.py` and `bili_delivery_progress.py`. |
| Documentation links/whitespace | `PASS` | `scripts/check_docs.py` checked 746 Markdown files after adding the bilingual execution record; final `git diff --check` passed. |
| Docker/Linux deployment | `NOT_RUN` | No image was built or deployed on the target Linux host in this execution. |
| Live Bilibili login, profile adoption and UID `252671524` | `NOT_RUN` | No real account/session or platform request was used by this local verification. |
| Live CDN bytes, host archive/library directory and NFO | `NOT_RUN` | Controlled fixture bytes qualify the code path only; no real CDN response or host path was inspected. |
| Later live incremental cycle | `NOT_RUN` | Offline 67/68-item and one-new-upload fixtures are not a claim about a later real platform cycle. |
| Supervisor restart | `NOT_RUN` | No deployed supervisor was started, stopped or restarted. |

## Commands run

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q --tb=short
.\.venv\Scripts\python.exe -m pytest tests/contract/test_mediacrawler_login.py::test_parent_bounds_a_no_frame_child_by_deadline_and_joins_it -q --tb=short
.\.venv\Scripts\python.exe -m pytest tests/contract/test_mediacrawler_login.py -q --tb=short
.\.venv\Scripts\python.exe -m pytest tests/integration/test_database.py::test_alembic_upgrade_matches_metadata_and_downgrades -q --tb=short
.\.venv\Scripts\python.exe -m pytest tests/unit/test_archive_preview.py -q --tb=short
.\.venv\Scripts\python.exe -m pytest tests/unit/test_api_explorer.py tests/unit/test_console_smoke_fixture.py -q --tb=short
.\.venv\Scripts\python.exe -m pytest tests/unit/test_kuaishou_cookie_login.py -q --tb=short

pnpm --dir web test
pnpm --dir web run check
pnpm --dir web run build
pnpm --dir web run format:check

.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m ruff format --check src tests
.\.venv\Scripts\python.exe -m mypy --strict src/media_sync
.\.venv\Scripts\python.exe scripts/check_upstreams.py
.\.venv\Scripts\python.exe scripts/check_docs.py
git diff --check
C:\Users\sueli\.local\bin\uv.exe build --out-dir <temporary-directory>
```

## Qualification conclusion

The deterministic local seam is qualified through exact bounded discovery, delivery receipt, download/archive, per-complete-Content publication, source-end reconciliation and incremental scheduling. It is not a live Bilibili or Linux deployment qualification. The next authoritative evidence must come from the rebuilt target host and the explicitly authorized bounded canary.
