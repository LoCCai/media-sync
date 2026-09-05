**English** | [中文](verification.zh.md)

# Projection verification

- Date: 2026-09-05
- Status: Local regression, quality, documentation and package gates passed

| Check | Evidence |
| --- | --- |
| Repository | Clean `main` at `13de3b7`; `git fetch --prune origin` and `git pull --ff-only origin main` succeed; already up to date |
| Parent requirements | Frozen 0055 goal/plan inspected; items 11–12 implemented in this increment; parent and child frozen goal/plan unchanged |
| Historical baseline | `13de3b7` records 2941 Python passes, 22 skips and one warning; this is historical evidence, not a projection test result |

## Executed checks

| Check | Command or evidence | Result |
| --- | --- | --- |
| Focused regression | `uv run --frozen pytest -q tests/unit/test_playback_evidence_query.py tests/unit/test_api_playback_evidence_query.py tests/integration/test_playback_evidence_query.py tests/unit/test_qualifications.py tests/unit/test_api_media_server.py tests/unit/test_operator_auth_api.py tests/unit/test_playback_evidence_service.py tests/unit/test_api_playback_evidence.py tests/integration/test_playback_evidence_service.py tests/integration/test_playback_evidence_repository.py` | 220 passed, one existing warning, 51.09s; earlier narrower selections passed 91 and 117 |
| Full Python | `uv run --frozen pytest -q` | 2999 passed, 22 skipped, one existing warning, 613.66s (`0:10:13`) |
| Web | In `web/`, serial `pnpm test`, `pnpm format:check`, `pnpm check`, `pnpm build` | 7 files / 69 tests; format pass; 0 errors / 0 warnings; adapter-static build pass |
| Python quality | `uv run --frozen ruff check .`; `uv run --frozen mypy src/media_sync`; `uv run --frozen ruff format --check .`; `uv run --frozen python -m compileall -q src tests` | Passed; strict mypy checks 107 source files; format checks 743 files |
| Locked references | `uv run --frozen python scripts/check_upstreams.py` | Both locked checkouts verified |
| Database read bounds | 62-row real SQLite fixture with SQL capture | Independently finds oldest current row; two bounded SELECTs; no COUNT, INSERT, UPDATE, DELETE or BEGIN IMMEDIATE; at most limit + 2 rows |
| Security and state | Auth-before-work, strict queries, safe payload, authority/transaction ordering, drift/failure/deadline tests | Passed; safe Cookie/Bearer GET uses the existing boundary; uncertain authority never grants PASS |

The first Ruff attempt found two import-order issues and two regex patterns that needed raw strings; these were corrected before the successful gates. The only pytest warning is the pre-existing Starlette/httpx TestClient deprecation. No source changed after the final focused/full runs.

## Unexecuted and review boundaries

The 22 skips are three Windows/POSIX differences, 11 Operation PostgreSQL cases and eight playback-evidence PostgreSQL races. The availability check found no Docker CLI and no `MEDIA_SYNC_TEST_POSTGRESQL_URL`; current Docker/Compose and real PostgreSQL remain NOT_RUN. Web tests validate response types and existing code, not a working login frontend or a real backend/browser workflow. No authorized platform, CDN, media-server or playback run occurred; checked-in live rows remain NOT_RUN.

Static review of the user's `13de3b7` findings confirms the current layout has no login shell, the client lacks CSRF injection, the image runs as UID 1000, Compose uses a file-backed secret, and the entrypoint calls `db init` before `serve`. Root-owned 0600 unreadability is a conditional Linux deployment risk, not a reproduced host incident. The manual runtime-user read check is documented but not run here. GitHub Actions history was not independently rechecked; workstation results are not CI evidence. See the [priority addendum](../delivery-priorities.md).

## Publication gate

`scripts/check_docs.py` passes all 508 Markdown files. A fresh system-temporary `uv build` creates one wheel (125 entries) and one sdist (824 entries). Both include the query service, repository and revision 0008; archive path/content inspection finds no private/runtime roots, actual .env, database/private-key files or workstation paths. `git diff --check` passes; all eight parent/child frozen goal/plan files have empty diffs. Independent read-only code review found no actionable P0/P1/P2 in this increment; it did not qualify the outstanding frontend/deployment work.

The implementation commit containing this record is the Git publication reference. Stage explicit source/test/docs/type paths only; exclude credentials, runtime output and `.mimosa/`. The next checkpoint's baseline records the exact published commit and remote reconciliation. This checkpoint does not complete 0055 or the product goal.
