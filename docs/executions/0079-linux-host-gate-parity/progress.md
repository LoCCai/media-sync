**English** | [中文](progress.zh.md)

# Execution 0079 progress

- Status: Complete — all local gates pass on the Linux deployment host; the image was rebuilt and upgraded in place to `5622f4d` per the 0077 handoff and verified healthy
- Date: 2026-09-26
- Environment: Linux deployment server (the host running the production container), uv + Python 3.13, Node 22 with pnpm 11.19.0, both `.upstream` checkouts present

## Completed

- Repository sync: fast-forwarded `main` from `3c31dce` to `764f46b` with the uncommitted 2026-09-12 deployment records stashed and re-applied cleanly, then committed and pushed as `ec67097`.
- Strict mypy is now platform-independent. On Linux the gate previously failed with 39 errors (Windows-only `subprocess`/`ctypes`/`msvcrt` attributes plus six platform-tuned ignores). Guards enclosing those accesses now use `sys.platform == "win32"` comparisons that mypy narrows per view (`src/media_sync/security/paths.py`, `infrastructure/observability/store.py`, `exporters/emby/exporter.py`, `integrations/mediacrawler/runner.py`, `login_runner.py`); helpers whose mocked native contract deliberately runs on POSIX keep paired `attr-defined, unused-ignore` comments (`archive_preview.py`, `store.py`, `exporter.py`, `webui.py`). The `webui.py` spawn guard stays on `os.name` because its unit test drives the branch through a module-level os proxy.
- Full pytest baseline on the pulled tree: 81 failed / 7052 passed. Re-running the identical set against the pristine tree reproduced 80 of 81, proving exactly one early regression (fixed by keeping the `webui.py` guard) and 80 pre-existing host failures.
- All 80 pre-existing failures were triaged and fixed:
  - Venv launcher symlink class (Windows venv pythons are copies, POSIX are symlinks): fixtures and manifests that used `Path(sys.executable).resolve()` desynchronized from the child's un-resolved launch path. `tests/contract/test_mediacrawler_bridge.py`, `test_mediacrawler_login.py`, `tests/integration/test_mediacrawler_scheduler_handler.py`, `test_zhihu_scheduled_creator_bound.py` and `tests/unit/test_mediacrawler_saved_session.py` now mirror production `normalize_python_executable` semantics; `test_mediacrawler_detail_refresh.py` asserts the normalized path.
  - POSIX-only launcher test (`test_runtime_preserves_posix_venv_launcher_symlink`, skipped on Windows so never validated anywhere): its global `subprocess.run` mock broke `prepare()`'s real git verification; the mock now passes non-launcher commands through.
  - Load-sensitive bounding assertion (`test_parent_bounds_a_no_frame_child_by_deadline_and_joins_it`): 5 s wall bound widened to 15 s — still four times below the 60 s child lifetime the contract bounds.
  - `tests/integration/test_emby_application.py::test_concurrent_children_of_one_predecessor_leave_one_durable_head`: the loser recorded `stale_publish` inside a deferred SQLite session whose read snapshot the winner's commit invalidated; WAL raises busy-snapshot immediately (busy timeout does not apply), and the generic handler reclassified the outcome as `export_failure_finalize_failed`.
- Emby failure recording now takes BEGIN IMMEDIATE on SQLite with a bounded retry (`src/media_sync/application/emby.py`), mirroring `operations.py`'s durable-write pattern; `LeaseLostError` still propagates untouched and exhaustion still maps to `export_failure_finalize_failed`.
- 0078 documentation debt: the duplicated 0078 index rows (three in `docs/README.md`, two in `docs/README.zh.md`) are deduplicated, and the 0078 progress records now state the pushed three-commit closeout instead of "in progress".

## Deviations and decisions

- The 0077 freeze is untouched: no XHS/Douyin delivery logic changed; the only production edits are platform guard expressions, paired ignores and the failure-recording transaction pattern.
- The paired-ignore form is used only where a runtime platform guard would break tests that deliberately exercise Windows helpers on POSIX through mocked native contracts.

## Closeout deployment (same session)

- Pre-upgrade backup under `/root/media-sync-backups/2026-09-26-pre-upgrade/`: online SQLite backup (`sqlite3.Connection.backup`, 639 KB), full `/data` volume tar (118 MB) and copies of the private Compose/.env; the supervisor profile stayed stopped throughout.
- `docker-compose build --no-cache media-sync` with `MEDIA_SYNC_SOURCE_REVISION=5622f4db4539f97194fec1befb2cf504589826fa` succeeded, including the in-build Web gates (`pnpm check && pnpm test && pnpm build`); the image OCI `org.opencontainers.image.revision` label equals that SHA.
- After `up -d --no-deps --force-recreate` the container is healthy; `GET /api/v1/health` (with the allowed Host) returns `{"status":"ok"}`; unauthenticated `/crawler/` returns 401; a health request with a wrong Origin returns 403.
- In-container `media-sync doctor --deep --accept-mediacrawler-license --json`: `ok:true / status:"ready"`, `build_manifest.source_revision` equals `5622f4db…26fa`, database migration `0015_xhs_creator_notes` is current, all 10 pinned MediaCrawler checks pass, `live_qualification: NOT_RUN` (expected).
- Rollback path: the pre-0077 image is retained and the pre-upgrade backup can restore the whole volume; live rows remain operator-gated per the 0077 handoff.
