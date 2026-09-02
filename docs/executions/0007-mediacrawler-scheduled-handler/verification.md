**English** | [中文](verification.zh.md)

# Execution 0007 verification

- Verification state: `PARTIAL` — AC6 and AC13 remain incomplete
- Verification date: 2026-08-30
- Network/account policy: offline fixtures and repository-owned local helper processes only; no browser, real credential, platform/CDN endpoint or Emby/Jellyfin server
- Implementation state: IMPLEMENTED for the documented offline scope

Execution 0007 has executable offline evidence; it is no longer a planning-only record. The evidence qualifies the local scheduler/bridge/child/artifact/database protocol, not live platform behavior. The late repeated-cancellation race was repaired and its root/full gates were rerun successfully. AC6 deterministic cancellation-barrier coverage and AC13's complete failure/secret-sink cross-product nevertheless remain explicitly `PARTIAL` at the narrower boundaries recorded below.

## Recorded focused gate

The following exact command covers the policy, bridge, process supervision, guarded ingestion, scheduled handler, scheduler repository/worker and CLI surfaces. It supersedes the earlier narrow 10-test selector record.

```powershell
uv run pytest tests\unit\test_mediacrawler_subscription_policy.py tests\contract\test_mediacrawler_bridge.py tests\contract\test_mediacrawler_supervision.py tests\integration\test_mediacrawler_db_ingestion.py tests\integration\test_mediacrawler_scheduler_handler.py tests\integration\test_scheduler_repository.py tests\integration\test_scheduler_worker.py tests\unit\test_cli.py -q
```

Final result: `PASS` — exit `0`; `320 passed, 1 skipped in 128.64s`.

The single skip is the POSIX mode-bit assertion on Windows. POSIX `.quarantine` mode tightening is covered where supported; on Windows, an equivalent restrictive ACL remains an operator-controlled-root deployment boundary and is not falsely claimed by this run. The standard `uv run pytest` first exposed package-import collection failures for the new contract helpers; adding `tests/__init__.py` and `tests/contract/__init__.py` fixed collection before the passing run above.

Additional pre-final checks already recorded on the same implementation tree were `uv run ruff check .` (`PASS`), `uv run ruff format --check .` (`PASS`) and `git diff --check` (`PASS`, no output). They will be represented by the final root rerun in the closeout table rather than promoted into unknown full-suite totals.

## Behavior evidence

| Scope | Evidence | Status |
| --- | --- | --- |
| Closed policy v1 | Strict schema with `schema_version`, optional `creator_input.secret_ref`, explicit `allow_full_history`, positive delay ≤ 300 and `headless`; license authorization separate/default-off | `PASS` |
| Manifest v3/receipt v2 | New strict writers bind scheduler Job plus attempt UUID/root and reject unknown/mismatched identities | `PASS` |
| Legacy manifest v2/receipt v1 | Shared normalization/manual ingest round-trips exact bytes read-only and never reseals/rewrites; scheduled restart recovery trusts v3 only | `PASS` |
| Pinned upstream shape | Faithful `parse_cmd()` fixture preserves dummy Cookie, binds `CRAWLER_MAX_SLEEP_SEC`, sets `MAX_CONCURRENCY_NUM=1` and keeps download disabled | `PASS` — configuration only; no per-request spacing claim |
| Attempt isolation and restart | Same durable Job UUID retries through unique attempt UUID/roots; stale attempts cannot ingest/checkpoint/delete successors | `PASS` |
| Heartbeat and short transactions | A real long local child runs while parent heartbeat and an independent SQLite writer continue; process wait holds no SQLite transaction | `PASS` |
| Cooperative cancellation | Pre-spawn/running cancel, lease fencing, repeated runner cancellation and a real between-batch ownership-guard barrier pass; runner/ingestion both join before unwind, and the second batch is fenced | `PARTIAL` — deterministic post-child/pre-seal and post-seal/pre-ingest barriers remain missing |
| Parent hard death and profile lock | Repository-owned helper hard-kill exercises parent liveness/control, child/grandchild exit and bounded account/profile recovery; Windows attach/start handshake is implemented | `PASS` |
| Ownership, ABA and ingestion | Exact owner/token/unexpired guard precedes every SyncRun mutation and each ingestion/checkpoint transaction | `PASS` |
| Waiting/failure mapping | `ACCOUNT_BUSY → account_busy`, `TIMED_OUT → upstream_timeout`, `START_FAILED → upstream_unavailable`, `CONFIGURATION_FAILED → configuration_invalid`, `UPSTREAM_FAILED → temporary_upstream`, output/tree/receipt rejection → `output_security_failed`; `waiting_user`/`waiting_auth` do not spawn and require explicit resume | `PASS`; cancellation/lease loss propagates fencing and stale handlers do not finalize |
| Seven-platform real offline protocol | `xhs`, `dy`, `ks`, `bili`, `wb`, `tieba`, `zhihu`: subscribe → tick → v3 write/load → real local fake child writes versioned JSONL → v2 receipt write/read → guarded ingest → retry/restart → idempotent replay | `PASS` — offline only |
| Four-state cleanup | `ABSENT`, `REMOVED`, `QUARANTINED`, `UNRESOLVED`; unresolved cleanup creates fixed/redacted account block and fences future execution | `PASS` for implemented state machine |
| Complete failure secret-sink matrix | Existing cleanup/redaction/sentinel tests cover substantial cases | `PARTIAL` — the full known-secret/nonzero/timeout/every-output-limit/receipt/cancel/lease-loss × retained-filesystem/SQLite/operator-sink cross-product is incomplete |
| Explicit CLI enablement | Default run leaves MediaCrawler Jobs untouched; `--enable-mediacrawler` and `--accept-mediacrawler-license` are separate, redaction-safe controls | `PASS` |

## Cancellation and secret-sink acceptance gaps

AC6 remains `PARTIAL`. Pre-spawn cancellation, running cancellation, lease fencing, repeated cancellation during runner wait and deterministic cancellation at the second ingestion-batch guard are covered. The unified join helper now records the first cancellation, signals cancellable work once and shields through any later cancellation until runner/ingestion reaches a definite verdict. The between-batch test preserves the first committed batch and fences the second. Deterministic tests are still missing only at child exit/before seal and after seal/before ingest.

AC13 remains `PARTIAL`. Cleanup/redaction/sentinel evidence is substantial, but it does not yet exercise the complete cross-product of known-secret output, nonzero exit, timeout, every output limit, receipt rejection, cancel and lease loss against every retained filesystem, SQLite and operator sink.

## Credential-bearing retained boundaries

- Ordinary active attempt roots must end as `ABSENT` or `REMOVED`.
- If atomic isolation succeeds but no-follow scrubbing fails, exact unsafe evidence may remain only below ignored `.quarantine`. That directory is operator-controlled, tightened to `0700` on POSIX, expects an equivalent restrictive ACL elsewhere, and is explicitly excluded from zero-secret claims.
- If neither removal nor isolation can be proven, `UNRESOLVED` creates only a fixed/redacted durable account/incident block outside the attempt root and hard-fences future secret resolution, run attachment, preparation and spawn. Raw cleanup errors and retained paths never enter operator output.
- Persistent account browser profiles are also credential-bearing boundaries and are excluded from whole-tree zero-secret claims.
- Repository ignore rules cover `.quarantine/`, `.cleanup-security-v1/` and account profile paths, including custom repository-local runtime roots. They prevent accidental Git tracking but are not a substitute for dedicated operator-controlled roots, ancestors and restrictive permissions/ACLs.

## Final root quality gates

The first full gate was deliberately interrupted after the late cancellation race was reproduced. It is not counted below. Every command in the table was rerun on the repaired tree; the retained-artifact gate is recorded separately in the next section.

| Check | Exact final command | Status and evidence |
| --- | --- | --- |
| Locked dependencies | `uv sync --all-groups --locked` | `PASS` — 58 packages resolved, 43 audited |
| Lint | `uv run ruff check .` | `PASS` — `All checks passed!` |
| Format | `uv run ruff format --check .` | `PASS` — 156 files |
| Strict types | `uv run mypy src\media_sync` | `PASS` — 65 source files |
| Full tests and coverage | `uv run pytest --cov=media_sync --cov-report=term` | `PASS` — 819 passed, 1 skipped in 212.99s; 79% branch-aware total |
| Focused execution 0007 gate | Exact eight-module command recorded above | `PASS` — 320 passed, 1 skipped in 128.64s |
| Build | `uv build` | `PASS` — sdist and wheel |
| Packaged resources/database compatibility | `uv run pytest tests\integration\test_packaged_migrations.py -q` | `PASS` — 6 passed in 7.47s |
| Documentation links | `uv run python scripts\check_docs.py` | `PASS` — 44 Markdown files |
| Pinned upstreams | `uv run python scripts\check_upstreams.py` | `PASS` — 2 locked checkouts |
| Custom runtime ignore boundary | `git check-ignore -v --no-index -- custom-runtime/.quarantine/evidence.json custom-runtime/.cleanup-security-v1/account-blocks/xhs/account.json custom-runtime/accounts/xhs/00000000-0000-0000-0000-000000000000/profile/cookies.json .media-sync/verification/0007-closeout-sentinel-root` | `PASS` — all four paths matched the intended rules |
| Patch whitespace | `git diff --check` | `PASS` — no output |
| Runtime artifacts untracked | `git ls-files -- archive exports jobs .media-sync dist` and `git status --short -- archive exports jobs .media-sync dist` | `PASS` — both emitted no lines |
| Retained safe-artifact sentinel | Exact 29-case allowlist and scans below | `PASS` — 29 passed; eight zero-match scans; 21 logical SQLite authority checks |

## Final retained safe-artifact sentinel

The authoritative retained root is `.media-sync/verification/0007-closeout-sentinel-root`. It was required not to exist before the run and was never deleted or replaced. The allowlist below expands to exactly 29 cases. It retains successful scheduled-handler roots, manifest/receipt evidence, temporary SQLite databases, captured pytest/operator output and local helper-process evidence without selecting deliberate quarantine/unresolved-retention negatives.

```powershell
$relativeRoot = '.media-sync/verification/0007-closeout-sentinel-root'
$sentinelRoot = [IO.Path]::GetFullPath((Join-Path (Resolve-Path -LiteralPath '.').Path $relativeRoot))
if (Test-Path -LiteralPath $sentinelRoot) { throw 'Closeout sentinel root already exists' }
git check-ignore -q -- "$relativeRoot/probe"
if ($LASTEXITCODE -ne 0) { throw 'Sentinel root is not ignored' }
New-Item -ItemType Directory -Path $sentinelRoot | Out-Null

$nodes = @(
  'tests/integration/test_mediacrawler_scheduler_handler.py::test_all_platform_fixtures_prepare_v3_and_ingest_forward_off_loop'
  'tests/integration/test_mediacrawler_scheduler_handler.py::test_all_platforms_cross_real_v3_v2_process_protocol_retry_and_idempotent_restart'
  'tests/integration/test_mediacrawler_scheduler_handler.py::test_real_handler_process_wait_keeps_heartbeat_and_independent_sqlite_writer_live'
  'tests/integration/test_mediacrawler_scheduler_handler.py::test_bridge_late_failure_removes_the_exact_attempt_root'
  'tests/contract/test_mediacrawler_bridge.py::test_manifest_v3_binds_scheduler_and_attempt_identity'
  'tests/contract/test_mediacrawler_bridge.py::test_sealed_v2_v1_artifacts_round_trip_byte_exact_and_read_only'
  'tests/contract/test_mediacrawler_supervision.py::test_start_token_is_sent_only_after_tree_attachment'
  'tests/contract/test_mediacrawler_supervision.py::test_running_cancel_joins_child_and_grandchild_before_cleanup'
  'tests/contract/test_mediacrawler_supervision.py::test_receipt_failure_removes_secret_bytes_but_preserves_profile'
  'tests/contract/test_mediacrawler_supervision.py::test_hard_parent_death_stops_real_child_tree_and_allows_safe_recovery'
  'tests/contract/test_mediacrawler_supervision.py::test_pinned_shape_parse_cmd_preserves_cookie_delay_and_single_concurrency'
  'tests/integration/test_scheduler_worker.py::test_worker_heartbeats_blocking_handler_then_cancel_returns_durable_terminal_state'
  'tests/integration/test_scheduler_secret_sinks.py::test_raw_handler_secret_stays_out_of_scheduler_and_retained_artifacts'
  'tests/integration/test_secret_sinks.py::test_all_json_error_and_url_sinks_redact_before_sqlite'
  'tests/integration/test_scheduled_offline_pipeline.py::test_scheduled_offline_pipeline_survives_restart_without_duplicate_identities'
  'tests/unit/test_cli.py::test_mediacrawler_dry_run_rejects_signed_creator_url_without_echoing_token'
  'tests/unit/test_cli.py::test_scheduler_mediacrawler_enablement_and_license_are_explicit'
)
uv run pytest -vv --tb=short -p no:cacheprovider `
  --basetemp (Join-Path $sentinelRoot 'pytest') `
  --junitxml (Join-Path $sentinelRoot 'pytest-junit.xml') @nodes 2>&1 |
  Tee-Object -FilePath (Join-Path $sentinelRoot 'pytest-output.txt')
```

Observed pytest result: `29 passed in 40.90s`. Pytest created 19 Windows `current` directory symlinks. The first generic “reject every reparse point” postcondition therefore stopped before scanning. Each alias was then checked to be a single directory symlink whose existing target is inside the sentinel root and has the same parent; every real target directory is independently present and scanned. No alias escaped the root. The retained tree was not rerun, deleted or rewritten; the scan resumed against that exact evidence.

The resumed gate used `rg --hidden --no-ignore --text --fixed-strings` over every real file for eight generated values: the fixture Cookie, supervision Cookie, parse Cookie, scheduler-handler secret, SQLite sink secret, signed-query secret, signed-creator token and late-bridge attempt secret. All eight returned `rg` exit `1`, meaning a successful zero-match. A read-only SQLite query checked every database containing `jobs` and found no logical row with a non-null `lease_owner` or `lease_token` across 21 databases. Behavioral tests separately prove that scheduler authority never enters the child boundary. Scoped `git ls-files` and `git status` emitted no lines.

Final retained result:

```text
CLOSEOUT_PASS cases=29 pytest_seconds=40.90 scans=8 sqlite_authority=PASS aliases=19
files=279 directories=364 bytes=5958937
```

The exact retained-negative functions excluded from this safe-artifact allowlist were:

- Supervision: `test_runner_hard_stops_and_records_redacted_block_when_attempt_cleanup_is_unresolved`, `test_cleanup_is_unresolved_when_atomic_quarantine_and_direct_removal_both_fail`, `test_cleanup_quarantines_when_post_move_scrub_is_denied`, `test_existing_quarantine_directory_mode_is_tightened_before_isolation`, `test_quarantined_cleanup_returns_only_fixed_operator_status`.
- Scheduled handler: `test_unresolved_cleanup_fences_current_and_recovery_without_successor_or_spawn`, `test_cleanup_incident_persistence_failure_still_fences_without_terminal_write`, `test_lease_loss_cancels_and_joins_runner_before_worker_returns`, `test_task_cancellation_signals_and_joins_runner`, `test_repeated_task_cancellation_still_joins_runner_before_unwind`, `test_repeated_cancellation_between_ingestion_batches_joins_before_unwind`, `test_repeated_cancellation_during_unresolved_cleanup_records_block_before_unwind`, `test_repeated_cancellation_during_untrusted_recovery_records_block`.
- CLI projection fixture: `test_scheduler_controls_are_bounded_and_redact_every_output_sink` intentionally stores raw redaction fixtures in temporary SQLite and is covered by the full suite, not by a whole-tree zero-match claim.

The zero-match claim applies only to the eight exact generated values in this 29-case safe-artifact tree. It does not claim that arbitrary unknown secrets cannot exist in a real browser profile or deliberate quarantine/unresolved evidence.

## Live qualification

| Platform | QR login | Cookie login | Saved session | Live creator traffic | Live CDN retrieval | Real Emby/Jellyfin scan/playback |
| --- | --- | --- | --- | --- | --- | --- |
| `xhs` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `dy` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `ks` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `bili` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `wb` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `tieba` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `zhihu` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |

## Deferred implementation

Scheduled backfill, signed-locator refresh, real CDN/media retrieval, automatic sync → download → export planning, per-request HTTP spacing, QR/challenge presentation UX, REST, resident production supervision, Docker, distributed HA/PostgreSQL and live Emby/Jellyfin operations are outside execution 0007. The pinned-shape evidence proves only `CRAWLER_MAX_SLEEP_SEC` configuration with `MAX_CONCURRENCY_NUM=1`, not spacing for every request.
