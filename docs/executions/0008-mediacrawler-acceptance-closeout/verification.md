**English** | [中文](verification.zh.md)

# Execution 0008 verification

- Verification state: `PASS` for the offline acceptance scope
- Verification date: 2026-08-30
- Plan commit: `f0c6015`
- Implementation commit: this commit
- Network/account policy: offline fixtures and repository-owned helper processes only; no browser, real credential, platform/CDN endpoint or Emby/Jellyfin server

## Verdict

Execution 0008 passes its offline successor closeout for execution 0007 AC6 and AC13. Both missing cancellation windows are now deterministic, and the exact eleven-failure × three-sink matrix proves 33 cells. The full branch-aware suite, focused and negative-boundary gates, build, repository checks and the one-shot retained-artifact gate all pass.

This verdict does not alter execution 0007's historical `PARTIAL` records and does not qualify any live platform, CDN or media-server behavior.

## Behavior evidence

| Scope | Evidence and result | Status |
| --- | --- | --- |
| Child-exit/pre-seal cancellation | Real helper returns `0` and its full tree joins; the test requests cancellation while the final-inspection barrier is held, then releases inspection; the runner observes cancellation before receipt publication; receipt writer, normalization and ingestion remain unentered; attempt cleanup and lock reacquisition pass | `PASS` |
| Post-seal/pre-ingest cancellation | A valid receipt is visible; both single and repeated cancellation join the protected normalizer before unwind; Content/Asset/checkpoint/success writes remain zero | `PASS` |
| Closed failure rows | Exact set equality for `known_secret_echo`, `nonzero_exit`, `timeout`, `output_bytes`, `output_items`, `output_files`, `output_line_bytes`, `output_tree`, `receipt_rejected`, `cancellation`, `lease_loss` | `PASS` |
| Sentinel injection | Cleanup observers prove every row's generated sentinel exists in attempt-private output before cleanup; no row can pass by omitting its injection | `PASS` |
| Filesystem sink | Ordinary roots end `ABSENT`/`REMOVED`; final traversal scans contents and path names, rejects traversal errors and scans hidden/ignored real files without exclusions | `PASS` |
| SQLite sink | Logical text/JSON plus every retained database and sidecar are scanned fail-closed; Job/SyncRun/checkpoint/Content/Asset and platform/account authority match each row's fixed disposition | `PASS` |
| Operator sink | Serialized results, Job/worker/lane CLI projections, captured output and exception/result `str`/`repr` contain no sentinel, lease authority, runtime root or raw cleanup error | `PASS` |
| Matrix completeness | Exact Cartesian product: 11 failure rows × 3 named sinks = 33 cells | `PASS` |
| Negative boundaries | Selected saved-profile, quarantine and unresolved-cleanup tests preserve their credential-bearing classification and prove fixed markers/unconditional fencing; raw cleanup-error evidence comes from this gate | `PASS` |
| Protocol compatibility | Seven-platform v3/v2 forward protocol, retry/restart, parent supervision and byte-exact immutable manual v2/v1 compatibility remain green | `PASS` |

## Exact focused gates

### Cancellation and matrix core

The exact gate selected one runner pre-seal contract, one handler pre-seal contract, the two parameterized post-seal cases, matrix completeness and all eleven matrix rows:

```powershell
uv run pytest `
  tests/contract/test_mediacrawler_supervision.py::test_cancel_after_successful_tree_join_never_starts_receipt_seal `
  tests/integration/test_mediacrawler_scheduler_handler.py::test_child_exit_pre_seal_cancellation_never_enters_normalization_or_ingestion `
  tests/integration/test_mediacrawler_scheduler_handler.py::test_post_seal_pre_ingest_cancellation_joins_before_unwind `
  tests/integration/test_mediacrawler_security_matrix.py::test_mediacrawler_security_matrix_declares_exactly_thirty_three_cells `
  tests/integration/test_mediacrawler_security_matrix.py::test_mediacrawler_failure_matrix_checks_every_sink
```

Result: `PASS` — exit `0`; `16 passed in 29.08s`.

### Scanner contracts and related modules

| Scope | Exact command | Result |
| --- | --- | --- |
| Complete matrix module | `uv run pytest tests/integration/test_mediacrawler_security_matrix.py` | `PASS` — exit `0`; `14 passed in 24.29s` |
| Related MediaCrawler modules | `uv run pytest tests/contract/test_mediacrawler_bridge.py tests/contract/test_mediacrawler_supervision.py tests/integration/test_mediacrawler_scheduler_handler.py tests/integration/test_mediacrawler_security_matrix.py` | `PASS` — exit `0`; `151 passed, 1 skipped` |

The matrix module count is one completeness case, two fail-closed scanner contracts and eleven failure rows.

### Credential-bearing negative boundary

The exact 13-function gate below contains the saved-session/profile contract; five quarantine/unresolved supervision functions; and seven handler authority/cancellation functions. The final recovery function expands to two cases, so the command collects 14 cases. It deliberately remains outside ordinary safe-tree zero-match evidence.

```powershell
uv run pytest `
  tests/contract/test_mediacrawler_bridge.py::test_saved_session_and_profile_path_isolation `
  tests/contract/test_mediacrawler_supervision.py::test_runner_hard_stops_and_records_redacted_block_when_attempt_cleanup_is_unresolved `
  tests/contract/test_mediacrawler_supervision.py::test_cleanup_is_unresolved_when_atomic_quarantine_and_direct_removal_both_fail `
  tests/contract/test_mediacrawler_supervision.py::test_cleanup_quarantines_when_post_move_scrub_is_denied `
  tests/contract/test_mediacrawler_supervision.py::test_existing_quarantine_directory_mode_is_tightened_before_isolation `
  tests/contract/test_mediacrawler_supervision.py::test_quarantined_cleanup_returns_only_fixed_operator_status `
  tests/integration/test_mediacrawler_scheduler_handler.py::test_unresolved_cleanup_fences_current_and_recovery_without_successor_or_spawn `
  tests/integration/test_mediacrawler_scheduler_handler.py::test_cleanup_incident_persistence_failure_still_fences_without_terminal_write `
  tests/integration/test_mediacrawler_scheduler_handler.py::test_lease_loss_cancels_and_joins_runner_before_worker_returns `
  tests/integration/test_mediacrawler_scheduler_handler.py::test_task_cancellation_signals_and_joins_runner `
  tests/integration/test_mediacrawler_scheduler_handler.py::test_repeated_task_cancellation_still_joins_runner_before_unwind `
  tests/integration/test_mediacrawler_scheduler_handler.py::test_repeated_cancellation_during_unresolved_cleanup_records_block_before_unwind `
  tests/integration/test_mediacrawler_scheduler_handler.py::test_repeated_cancellation_during_untrusted_recovery_records_block
```

Result: `PASS` — exit `0`; `13 passed, 1 skipped in 7.31s`. The skip is the Windows-inapplicable POSIX mode-bit boundary

## Full quality gates

| Check | Exact command | Result |
| --- | --- | --- |
| Locked dependencies | `uv sync --all-groups --locked` | `PASS` — exit `0`; `Resolved 58 packages`; `Audited 43 packages` |
| Lint | `uv run ruff check .` | `PASS` — exit `0` |
| Format | `uv run ruff format --check .` | `PASS` — exit `0`; `162 files already formatted` |
| Strict types | `uv run mypy src/media_sync` | `PASS` — exit `0`; `Success: no issues found in 65 source files` |
| Full branch-aware suite | `uv run pytest --cov=media_sync --cov-report=term` | `PASS` — exit `0`; `838 collected`; `837 passed, 1 skipped in 248.20s`; total branch-aware coverage `79%` |
| Build | `uv build` | `PASS` — exit `0`; wheel and source distribution built |
| Packaged migrations/resources | Covered by the full suite and built wheel/sdist; no Alembic revision was added | `PASS` |
| Documentation links | `uv run python scripts/check_docs.py` | `PASS` — exit `0`; `Documentation links OK (48 Markdown files checked).` |
| Locked upstreams | `uv run python scripts/check_upstreams.py` | `PASS` — exit `0`; `Upstreams OK (2 locked checkouts verified).` |
| Patch whitespace | `git diff --check` | `PASS` — exit `0`; no output |

The single full-suite skip is the POSIX mode-bit boundary that is not applicable on Windows. No browser, network, real platform account, CDN or media server is used by these gates.

## Authoritative retained-artifact gate

The complete one-shot recipe is frozen in [`closeout-gate.ps1`](closeout-gate.ps1). Its canonical LF repository bytes are Git blob `6f5e8119de66a36f0f93f75a5f5e27ef1bf2ec18`, SHA-256 `d56f9108c2f5d2ddc01d8d9da26657ef5f95a25024017d52c6c169db7016c853`; the checkout may render PowerShell files with CRLF according to `.gitattributes`. It preserves the exact 22 function nodes, pytest invocation, twelve value/prefix scans, fail-closed path/content traversal, Windows alias validation, SQLite logical/sidecar and eleven-row authority checks, exact retained-tree statistics, scoped Git checks and receipt write. The authoritative run created the previously absent ignored root `.media-sync/verification/0008-closeout-sentinel-root` with a fresh pytest `--basetemp` and retained JUnit, pytest output and `closeout-sentinel-PASS.txt`. The root must not be deleted, rebuilt or used for another authoritative run. The execution 0007 retained root was not touched.

Canonical one-shot invocation from the repository root

```powershell
pwsh -NoProfile -File docs/executions/0008-mediacrawler-acceptance-closeout/closeout-gate.ps1
```

This invocation is now documentary only: the script's first write-side precondition rejects the existing retained root. It was not rerun while transcribing the fixed recipe. Only PowerShell and embedded-Python syntax were parsed afterward; neither syntax check executes the gate or reads/writes the retained root.

Exact syntax-only checks:

```powershell
$path = (Resolve-Path -LiteralPath 'docs/executions/0008-mediacrawler-acceptance-closeout/closeout-gate.ps1').Path
$tokens = $null
$errors = $null
[void][Management.Automation.Language.Parser]::ParseFile($path, [ref]$tokens, [ref]$errors)
if ($errors.Count -ne 0) { $errors | Format-List; exit 1 }

$lines = Get-Content -LiteralPath $path
$python = ($lines[96..345] -join [Environment]::NewLine)
$python | uv run python -c "import sys; compile(sys.stdin.read(), 'closeout-gate-embedded.py', 'exec'); print('Embedded Python syntax OK')"
```

Result: `PASS` — PowerShell parser reported zero errors; embedded Python printed `Embedded Python syntax OK`; neither command invoked the gate

| Measurement | Exact result |
| --- | ---: |
| Gate process | `CLOSEOUT_PASS`, exit `0` |
| Function nodes | 22 |
| Pytest cases | 45 |
| Pytest result | `45 passed in 69.82s` |
| Gate wall time | `71.41s` |
| Matrix cases | 12 |
| Matrix cells | 33 |
| Exact value/prefix scans | 12 |
| SQLite authority rows | 11 |
| SQLite files | 35 |
| SQLite sidecars | 22 |
| Validated pytest `current` aliases | 24 |
| Real files | 370 |
| Real directories including root | 483 |
| Retained bytes | 10,104,859 |
| Tracked files below root | 0 |
| Git status lines below root | 0 |

All 24 Windows pytest `current` aliases were proved to have exactly one existing same-parent target inside the retained root. Every real target was independently enumerated and scanned. The final scan covered all hidden and ignored real files and path names with no exclusions. Scanner errors, SQLite locks at final scan, non-regular databases, unreadable sidecars or traversal failures make the gate fail closed.

The twelve zero-match values/prefixes combine the eight execution 0007 safe-artifact fixtures with four execution 0008 matrix/pre-seal runtime sentinels. They are test-only values, not real credentials. `QUARANTINED`, `UNRESOLVED` and persistent browser profiles are intentionally excluded and covered by the negative-boundary gate instead.

### Exact retained-negative exclusions

The 22-node allowlist is closed; it is not a module-level selection with a fragile `-k` exclusion. The following credential-bearing, authority-retaining or deliberate scanner-fixture functions are therefore named explicitly outside the whole-tree zero-match claim:

- Persistent profile: `tests/contract/test_mediacrawler_bridge.py::test_saved_session_and_profile_path_isolation`.
- Supervision quarantine/unresolved
- Handler authority/cleanup
- Deliberate CLI redaction fixture: `tests/unit/test_cli.py::test_scheduler_controls_are_bounded_and_redact_every_output_sink`; it intentionally persists three raw projection fixtures in temporary SQLite and is covered by the full suite, not the zero-match retained tree
- Fail-closed scanner fixtures: `test_filesystem_sink_scanner_checks_path_names_and_fails_closed` and `test_sqlite_sink_scanner_requires_a_regular_database_and_sidecars` in `tests/integration/test_mediacrawler_security_matrix.py`; they deliberately create rejected path/sidecar conditions and are covered by the 14-case matrix-module gate

The exact negative-boundary command above selects the profile, five supervision and seven handler functions needed for the credential/authority claim. The additional between-batch, CLI and scanner functions remain explicitly outside the retained root and are covered by the related-module or full-suite gates.

## Live qualification

| Platform | QR login | Cookie login | Saved session | Creator scheduled run | Live CDN | Real Emby/Jellyfin |
| --- | --- | --- | --- | --- | --- | --- |
| `xhs` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `dy` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `ks` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `bili` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `wb` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `tieba` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `zhihu` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |

Phone login remains unsupported rather than merely untested. The offline fake-child and fixture results must not be represented as live compatibility.

## Deferred implementation and residual boundary

Signed-locator refresh remains unimplemented through execution 0008 and is execution 0009 scope. Successful sealed v3 attempt JSONL may still contain an unknown short-lived signed query that the parent could not pre-register; it remains an explicit credential-bearing temporary boundary until execution 0009 implements refresh plus successful/recovery terminal cleanup or isolation.

Durable automatic `sync → download → Emby` planning remains execution 0010 scope. Real platform/CDN/Emby qualification, downloadable assets for `wb`/`tieba`/`zhihu`, platform derivatives, per-request HTTP spacing, bounded live pagination, QR/challenge UX, REST, resident supervision, Docker and HA/PostgreSQL remain deferred or `NOT_RUN` according to their truthful category.
