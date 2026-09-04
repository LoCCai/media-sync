**English** | [中文](verification.zh.md)

# Execution 0006 verification

- Verification date: 2026-08-30 12:34 +08:00
- Network/account policy: offline fixtures, mock transports, generated media and local SQLite/filesystems only
- Result: PASS for the complete offline/Fake scope

## Behavior evidence

The final root run exercised the complete branch-aware suite and every focused gate below. No real credential, platform/CDN endpoint or Emby/Jellyfin server was used. Mock/Fake success qualifies only the offline contracts and does not promote any live row.

| Scope | Evidence | Final status |
| --- | --- | --- |
| Retry and circuit policy | Injected clock/RNG, equal jitter, `Retry-After`, bounds, invalid numbers/times, maximum attempts and exact half-open outcomes | PASS |
| Atomic due materialization | Bounded null-first ordering, schedule-revision CAS, concurrent independent SQLite ticks, fixed delay and no catch-up storm | PASS |
| Launch lanes and capacity | Independent-connection global capacity, account capacity, persisted minimum-start deadline, queue scan fairness and one half-open probe winner | PASS |
| Execution 0005 isolation | Type-scoped reclaim/requeue/claim leaves download/export payload, attempts, lease and recovery evidence unchanged | PASS |
| Worker fencing and waiting | Short transactions, exact heartbeat, cancel/reclaim/ABA races, same-session ownership guard and explicit-only waiting resume | PASS |
| Closed handler registry | Fake handler lifecycle plus a due MediaCrawler subscription terminalizing as `handler_unsupported` without runner, ingest, SyncRun, content, downstream Job or runtime-root side effects | PASS |
| Restart pipeline | Subscribe → tick → Fake sync → explicit secure mock download → explicit Emby export → reconstruct → rerun with identity reuse | PASS |
| Secret and hostile-result sinks | SQLite, Job/lane DTO, scheduler operator output, archive/export and retained-artifact exact scans | PASS |
| Migration | Empty/current DB, real source `0003 → 0004 → 0003 → 0004`, and unpacked-wheel empty-DB upgrade | PASS |

Migration evidence is deliberately narrow. The real source round trip proves that Job fields expressible by `0003`, including JSON storage type, ExportRecords and `assets.download_job_id`, remain field-for-field equal while scheduler identity is released. It does not claim physical SQLite-file byte equality. The unpacked-wheel test proves packaged-resource import and empty-database upgrade to `0004`; it is not a wheel-based real-`0003` round trip.

## Final quality gates

| Check | Exact final command | Status and evidence |
| --- | --- | --- |
| Locked dependencies | `uv sync --all-groups --locked` | PASS — 58 resolved, 43 audited |
| Lint | `uv run ruff check .` | PASS |
| Format | `uv run ruff format --check .` | PASS — 144 files |
| Strict types | `uv run mypy src\media_sync` | PASS — 62 source files |
| Full tests and coverage | `uv run pytest --cov=media_sync --cov-report=term` | PASS — 686 passed in 152.40s; 80% branch-aware total |
| Scheduler/concurrency/handler gate | `uv run pytest tests\unit\test_scheduler_policy.py tests\unit\test_scheduler_handlers.py tests\integration\test_scheduler_repository.py tests\integration\test_scheduler_worker.py tests\integration\test_scheduler_handler_safety.py tests\integration\test_scheduled_offline_pipeline.py tests\integration\test_scheduler_secret_sinks.py -q` | PASS — 127 passed in 10.80s |
| Database and migration gate | `uv run pytest tests\integration\test_database.py tests\integration\test_packaged_migrations.py -q` | PASS — 25 passed in 14.10s |
| Restart and secret-sink gate | `uv run pytest tests\integration\test_scheduled_offline_pipeline.py tests\integration\test_scheduler_secret_sinks.py tests\integration\test_secret_sinks.py -q` | PASS — 8 passed in 2.92s |
| CLI and workflow gate | `uv run pytest tests\unit\test_cli.py tests\integration\test_cli_workflow.py -q` | PASS — 61 passed in 12.14s |
| Build | `uv build` | PASS — sdist and wheel |
| Packaged migrations | `uv run pytest tests\integration\test_packaged_migrations.py -q` | PASS — 6 passed in 8.31s |
| Documentation links | `uv run python scripts\check_docs.py` | PASS — 40 Markdown files |
| Pinned upstreams | `uv run python scripts\check_upstreams.py` | PASS — 2 locked checkouts |
| Patch whitespace | `git diff --check` | PASS — no output |
| Final clean artifact sentinel | Reproducible retained-artifact gate below | PASS — 40 passed; six exact scans zero-match |
| Runtime artifacts untracked | `git ls-files -- archive exports jobs .media-sync dist` and `git status --short -- archive exports jobs .media-sync dist` | PASS — both emitted no lines; all retained roots are ignored |

## Final retained-artifact sentinel

The final code tree generated evidence below `.media-sync/verification/0006-closeout-clean-sentinel-root`. It contains 58 files, 86 directories and 10,664,504 bytes: 40 test artifacts, 40 SQLite databases, archive/library output where applicable, and captured operator output. The complete procedure was:

```powershell
$sentinelRoot = Join-Path $PWD '.media-sync\verification\0006-closeout-clean-sentinel-root'
if (Test-Path -LiteralPath $sentinelRoot) { throw "Verification root unexpectedly exists: $sentinelRoot" }
New-Item -ItemType Directory -Path $sentinelRoot | Out-Null
$sentinelPytestRoot = Join-Path $sentinelRoot 'pytest-artifacts'
$sentinelOutput = Join-Path $sentinelRoot 'operator-output.txt'
$sentinelStarted = Get-Date
uv run pytest tests/integration/test_scheduler_worker.py tests/integration/test_scheduler_handler_safety.py tests/integration/test_scheduled_offline_pipeline.py tests/integration/test_scheduler_secret_sinks.py -q --basetemp $sentinelPytestRoot 2>&1 | Tee-Object -FilePath $sentinelOutput
$sentinelPytestExit = $LASTEXITCODE
$sentinelElapsed = (Get-Date) - $sentinelStarted
if ($sentinelPytestExit -ne 0) { throw 'Clean sentinel tests failed' }
$sentinelPatterns = @(
  'SENTINEL-runtime-signed-query-0005',
  'SENTINEL-scheduler-handler-secret-must-not-persist',
  'SENTINEL-hostile-sync-error',
  'SENTINEL-scheduler-raw-exception-secret',
  '?signature=',
  $sentinelRoot
)
foreach ($sentinelPattern in $sentinelPatterns) {
  rg -a -F -- $sentinelPattern $sentinelRoot
  $sentinelScanExit = $LASTEXITCODE
  if ($sentinelScanExit -ne 1) { throw "Sentinel scan matched or failed: $sentinelPattern" }
}
git check-ignore -v -- .media-sync/verification/0006-closeout-clean-sentinel-root
git status --short --untracked-files=all -- .media-sync/verification/0006-closeout-clean-sentinel-root
git ls-files -- .media-sync/verification/0006-closeout-clean-sentinel-root
```

Observed results:

```text
40 passed in 5.92s
pytest_exit=0
elapsed_seconds=7.45
files=58 directories=86 bytes=10664504
scan_exit=1 for all six exact patterns / 六个精确模式均为 scan_exit=1
.gitignore:31:.media-sync/  .media-sync/verification/0006-closeout-clean-sentinel-root
```

For `rg`, exit `1` means a successful scan with zero matches; exit `0` would mean a leak and exit `2+` a scan failure. Scoped `git status` and `git ls-files` emitted no lines. The final retained tree therefore contains none of the exact handler secret, hostile error, signed-query or absolute-root patterns and is not tracked.

Two earlier ignored diagnostic roots were deliberately retained rather than deleted. `.media-sync/verification/0006-final-sentinel-root` contains 117 tests, 103 files, 308 directories and 22,874,763 bytes, including intentional negative-test sentinel rows; it is not used for a whole-tree zero-match claim. `.media-sync/verification/0006-final-clean-sentinel-root` is the pre-closeout clean run with 39 tests, 57 files, 84 directories and 10,398,264 bytes; its six exact scans also returned exit 1. The 40-test closeout root above is the authoritative final evidence.

## Required conclusions

- A bounded tick creates at most one active cycle for each selected due subscription, and fixed-delay completion prevents downtime catch-up storms.
- SQLite writer serialization plus schedule/lane/lease CAS gives independent local processes one winner for materialization, capacity slots, start deadlines, half-open probes, heartbeat, cancel and reclaim.
- The generic worker handles only `sync.subscription`; downloader and Emby Jobs remain owned by their execution 0005 services.
- `waiting_auth` and `waiting_user` remain dormant until explicit resume; retry exhaustion terminalizes once and advances the schedule once.
- Adapter awaits hold no SQLite writer transaction. Exact heartbeat plus the same-session ownership guard prevents stale/cancelled/reclaimed handlers from persisting.
- Raw handler exceptions, malformed results, hostile codes and unknown/foreign SyncRun IDs map to fixed closed codes before persistence.
- The shipped registry is Fake-only. A scheduled MediaCrawler subscription fails closed as `handler_unsupported` and does not spawn a child, ingest, create a SyncRun or create runtime/download/export state.
- Scheduler lanes qualify launch throttling only, not every upstream HTTP request. The offline restart acceptance invokes download and export explicitly; there is no automatic sync → download → export DAG.

## Live qualification and deferred implementation

| Target | Status | Reason |
| --- | --- | --- |
| XHS, Douyin, Kuaishou, Bilibili, Weibo, Tieba and Zhihu QR/Cookie/saved-session login, creator sync and scheduled run | `NOT_RUN` | No user-authorized account or interactive challenge was used |
| Seven-platform signed-locator refresh and live CDN retrieval | `NOT_RUN` | No CDN traffic was authorized; refresh remains unimplemented |
| Emby/Jellyfin rescan and playback | `NOT_RUN` | No server was started or modified |

MediaCrawler scheduler integration, manifest v3 request-delay binding, long child-process heartbeat/cancellation, signed-locator refresh, per-request upstream throttling, automatic downstream DAG planning, REST, resident supervision, Docker/production packaging and distributed HA remain unavailable or deferred implementation scope, not `NOT_RUN` outcomes.
