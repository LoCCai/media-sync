**English** | [中文](verification.zh.md)

# Verification

Date: 2026-09-05. Source baseline: clean published `0eefea7`; frozen plan: `fe54aba`. Tests below use isolated local databases and synthetic records, not production.

## Completed checks

Commands use `.venv/Scripts/python.exe` below; the deletion agent used equivalent `uv run pytest` in the same locked environment.

| Check | Command / selection | Result |
| --- | --- | --- |
| Local output independent of connector | `-m pytest tests/unit/test_api_local_export_without_media_server.py -q` | 2 passed; real authenticated API and exporter, connector construction tripwire untouched; verified files required |
| Export regression | New local-export test plus API library inspection, library application and Emby application tests | 64 passed, 19.15s |
| Exact report | `-m pytest tests/unit/test_job_diagnostics.py -q` | First corrected run: 14 passed; four later actual revision/phase/code cases are included in the 175-test union below |
| API/CLI/auth/report/support | `-m pytest tests/unit/test_job_diagnostics.py tests/unit/test_api_subscription_removal.py tests/unit/test_operator_auth_api.py tests/unit/test_api_server.py tests/unit/test_api_workbench.py tests/unit/test_cli.py tests/unit/test_api_support_bundle.py tests/unit/test_support_bundle.py -q --tb=short` | 175 passed, 56.61s; all 62 route objects checked against exact anonymous whitelist |
| Removal and migration | `tests/integration/test_subscription_removal.py tests/integration/test_subscription_removal_migration.py` | 50 passed, 6.10s: 46 lifecycle/locking cases and four migration cases |
| Backend regression | `tests/unit/test_workbench.py tests/integration/test_scheduler_worker.py tests/integration/test_scheduler_repository.py tests/integration/test_pipeline_worker.py tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_subscription_removal.py tests/integration/test_subscription_removal_migration.py tests/integration/test_playback_evidence_migration.py` | 250 passed, 24.35s |
| Web, final serial gate | In `web/`: `pnpm test`, `pnpm check`, `pnpm format:check`, `pnpm build` | 440 tests / 18 files; zero Svelte errors/warnings; format and static build passed. After final Library copy change, `pnpm test -- src/lib/utils/local-export-independence.test.ts` actually reran all 440 tests at 20:41:15 UTC+8; format/check/build passed again |
| Python static | `-m ruff check .`, `-m ruff format --check .`, `-m mypy src/media_sync`, `-m compileall -q src tests` | Passed; 847 formatted files, 112 typed source files |
| Documentation/upstreams | `scripts/check_docs.py`, `scripts/check_upstreams.py`, `git diff --check` | 580 Markdown files, two locked checkouts, clean whitespace check at this checkpoint |
| Package | `uv build --out-dir <new system temporary directory>` | Wheel 131 entries / sdist 948 entries; new services/migration and Web sources present. Filename checks found no private .env, SQLite DB, key files, upstream checkout or node_modules. This is not a claim of exhaustive secret-content scanning |

The first full offline suite (`-m pytest -q --tb=short`) completed with **2 failed, 3800 passed, 29 skipped**, one existing warning in 749.87s. It caught a real SQLite checkpoint read-to-write upgrade regression introduced by the tombstone pre-read, and an old-schema migration fixture incorrectly using the newest Subscription ORM. Both were corrected and reverified below; this first full run is not a pass. The recurring warning is the existing Starlette/httpx TestClient deprecation. Skips are three Windows/POSIX differences, 19 unconfigured PostgreSQL cases, and seven QR-image tests without the isolated upstream Pillow dependency.

Post-fix checkpoint publication restores the original first-statement CAS, with `deleted_at IS NULL` in the same UPDATE; only a failed CAS reads revision/removal state. The old migration fixture uses historical columns without adding modern columns. Exact Job claim and scoped enqueue obtain SQLite's writer slot using a no-row UPDATE before the added lifecycle read. Six real two-connection claim/enqueue cases and two checkpoint-order/tombstone cases were added. The final database/checkpoint/packaged-migration/removal union passed **97 tests in 25.59s**, including both original failures and a built-wheel migration check. The first added concurrency fixture omitted a required display name (two fixture failures / ten passes); that seed was corrected before the final run.

The final post-fix union used `-m pytest -q --tb=short` and the exact arguments in [post-fix-tests.txt](post-fix-tests.txt): all unit tests plus affected database/checkpoint/scheduler/pipeline/ingestion/download/migration integration tests. Result: **2849 passed, eight skipped, one existing warning in 287.24s**. Skips are seven isolated-Pillow cases and one Windows/POSIX handler case. This is not a second complete suite; unchanged upstream contracts were not rerun after the localized repository/fixture corrections. Final static checks after these source corrections passed: Ruff, format (849 files), mypy (112 source files), compileall, documentation (582 Markdown files), upstreams and whitespace.

## Browser smoke and its limits

Using the computer-use skill and its preferred browser interface, served the built frontend through the ordinary authenticated API on loopback port 8767. An explicitly new temporary dataset extended `_console_smoke_fixture.py` with one synthetic failed Job/running Run/succeeded Worker association and a separate removed subscription. No platform or media-server requests, real credentials or auth bypass were used.

- Ordinary fixture login and browse-only onboarding mounted the private console.
- Current/removed subscription lists loaded, with enabled distinct from running. Removal confirmation stated retained files/history, cancellation of unstarted work and busy refusal; restore confirmation stated paused restoration and no task revival. Both confirmations were cancelled: destructive UI submission was not performed. Actual lifecycle mutations are covered by authenticated API/CLI tests.
- Exact report retrieval through the Jobs UI showed failed Job, running Run, zero counts and one associated Worker, plus both contradiction explanations. Layout was visually inspected. Closing/reopening cleared the report and required explicit retrieval again.
- The JSON download button was invoked, but browser download completion/disk bytes were not verified; clipboard writing was not attempted. Serializer, size/whitelist and request fences were tested offline; do not call this a complete clipboard/download browser gate.
- Library visibly separated independent local output from unconfigured optional linkage. Browser review found dashboard enabled-count and Library English-jargon wording issues; both were corrected and rebuilt. No local media export was submitted in the browser.
- The created tab was closed and fixture server stopped; a fresh listener query found no port 8767 listener. Temporary synthetic data and package artifacts remain outside the repository, not committed.

## Review and correction trail

- Initial report tests had fixture-only invalid subscription keyword/unique-name/OperationSubject-role mistakes; corrected, along with a read-only query assertion allowing the normal `BEGIN`. No production data was involved.
- Independent review caught inaccurate old migration identifiers, omitted real Worker phases and omitted `scheduler_run_failed`; exact known values and regressions were added. Unknown errors/revisions still remain unknown rather than being guessed or reflected.
- First API/CLI union had 171 passes and four expected-shape failures due to additive `deleted_at`; the closed field set and null assertion were updated before the final 175 passes.
- First Web run had 401 passing tests but report-suite import failure from a runtime alias; relative import fixed it. An unused CSS warning was removed. All later full gates passed. A final cancellation wording test avoids claiming process cleanup from a cancelled record.
- New migration fixture initially omitted required author timestamps (one failure / 66 passes); corrected, then four migration cases passed. Two initial backend typing issues were corrected. One incorrect test-path command collected zero tests and is not counted as validation.
- Independent concurrency review found Subscription/Job/Lane lock-order waits with PostgreSQL-style maintenance. Removal now locks existing Jobs/lanes with NOWAIT, never lazily creates missing lanes, and passes exact already-locked lane scope into cancellation/reconciliation. Exact SQLSTATE 55P03 is translated to `subscription_busy` only after rollback. Compilation and fault-injected rollback tests are offline evidence, not actual PostgreSQL concurrency qualification. SQLite uses `BEGIN IMMEDIATE` and actual competing-thread tests.

## Remaining gates and publication

Docker CLI and a PostgreSQL test URL are unavailable. Current Docker build/deployment, real PostgreSQL migration/concurrency, production removal/restore, live profile lookup/login/capture/download/export/playback are NOT_RUN. Automatic nickname/avatar lookup remains NOT_IMPLEMENTED; 0056 and the overall goal remain open. No production history was rewritten and the stopped supervisor was not restarted.

An initial HTTPS fetch failed with TLS unexpected EOF; retry with Git's Schannel TLS backend and HTTP/1.1 succeeded without weakening certificate validation. Fresh remote main remained `0eefea7`. The implementation commit containing this record follows plan `fe54aba`; publish with a non-force push and record remote equality separately. Package checks above precede final documentation updates; the post-fix 97-test union rebuilt and exercised the corrected wheel's migrations.
