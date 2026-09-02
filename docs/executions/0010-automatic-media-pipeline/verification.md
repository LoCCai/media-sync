**English** | [中文](verification.zh.md)

# Execution 0010 verification

- Verification state: `PASS` for the complete offline MVP gate
- Verification date: 2026-08-31
- Predecessor: Execution 0009 commit `98cf387`
- Qualification boundary: offline SQLite/Fake/direct/mock workflow only; authorized platform/CDN/Emby rows remain `NOT_RUN`

## Recorded checks

| Scope | Command or evidence | Result |
| --- | --- | --- |
| Combined pipeline/scheduler/CLI gate | `uv run pytest -q tests/integration/test_pipeline_job_repository.py tests/integration/test_pipeline_runtime.py tests/integration/test_pipeline_worker.py tests/integration/test_subscription_application_pipeline.py tests/integration/test_scheduler_worker.py tests/integration/test_scheduled_offline_pipeline.py tests/unit/test_cli.py` | `PASS` — `154 passed in 15.85s` |
| Atomic enqueue and recovery | Included above: normal success, duplicate success and succeeded-run reconciliation create one coordinator; failure/wait/cancel create none | `PASS` |
| Claim hardening | Included above: bounded scan; malformed/stale head terminalization; valid row behind it remains claimable | `PASS` |
| Exact scope before side effects | Included above: Account/platform drift fails before request factory, downloader or exporter | `PASS` |
| Download/restart/export | Included above: 0/1/N selection, retry stop, verified reuse, re-selection and offline Emby publication | `PASS` |
| Runtime composition | Included above: direct locator without MediaCrawler; exact Subscription-bound lazy refresh construction | `PASS (offline)` |
| Network preflight regression | New missing/invalid lock-checkout-Python and launchable-ffprobe nodes, all before child Job/Asset lifecycle mutation | `PASS` — `5 passed` |
| Runtime + CLI regression | `uv run pytest tests/integration/test_pipeline_runtime.py tests/unit/test_cli.py -q` | `PASS` — `73 passed` |
| Heartbeat/fencing | Included above: renewal during a blocking async handler, replacement-token fencing and invalid interval matrix | `PASS (focused)` |
| CLI controls | Included above: `--scan-limit`, `--heartbeat-interval-seconds`, default-off MediaCrawler enable/license and invalid-combination rejection | `PASS` |
| Whole-tree lint | `uv run ruff check .` | `PASS` — `All checks passed!` |
| Whole-tree format | `uv run ruff format --check .` | `PASS` — `185 files already formatted` |
| Strict source typing | `uv run mypy src/media_sync` | `PASS` — `Success: no issues found in 72 source files` |
| Full non-coverage suite before final compatibility repair | `uv run pytest -q` | `PARTIAL` — `926 passed, 1 skipped, 1 failed`; the only failure was the historical scheduled-offline Job-set assertion, not a runtime failure |
| Repaired historical node | `uv run pytest tests/integration/test_scheduled_offline_pipeline.py::test_scheduled_offline_pipeline_survives_restart_without_duplicate_identities -q` | `PASS` — `1 passed`; it now expects the coordinator to remain `queued` until explicit `pipeline run` |
| Final full-suite rerun after repair | `uv run pytest -q` | `PASS` — `930 passed, 1 skipped in 191.06s`; the skip is the Windows-inapplicable POSIX mode-bit case |
| Pinned upstreams | `uv run python scripts/check_upstreams.py` | `PASS` — `Upstreams OK (2 locked checkouts verified).` |
| Build | `uv build` | `PASS` — sdist and wheel generated |
| Documentation | `uv run python scripts/check_docs.py` | `PASS` — `Documentation links OK (56 Markdown files checked).` |
| Patch whitespace | `git diff --check` | `PASS` — exit `0`, no output |

The earlier `926 passed, 1 skipped, 1 failed` run is retained above as the regression that found the stale historical assertion; it is not combined with a one-node rerun. The authoritative post-repair full suite is the later independent `930 passed, 1 skipped` invocation.

## Concurrency and cancellation truth

The heartbeat renews exact Job/worker/token ownership, and complete/fail uses the same CAS, so a stale coordinator cannot normally overwrite a successor's Job result. However, the CLI handler is synchronous and is offloaded with `asyncio.to_thread`; cancelling its asyncio wrapper cannot forcibly stop the underlying thread. Lease loss or heartbeat-storage failure may therefore leave old download/export work running while a successor or later bounded Job proceeds. This execution does not qualify cooperative cancellation, forced termination, multi-worker HA or every cancellation micro-window.

## Live qualification

| Platform | Live login | Creator/detail traffic | Signed CDN download | Real Emby/Jellyfin scan/playback |
| --- | --- | --- | --- | --- |
| `xhs` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `dy` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `ks` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `bili` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `wb` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `tieba` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `zhihu` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |

Offline fixture/fake-child/direct transport evidence never changes this live table. Phone login remains unsupported, and no seven-platform complete-download claim is made.
