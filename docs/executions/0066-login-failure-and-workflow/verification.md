**English** | [中文](verification.zh.md)

# Verification

## Production evidence, not a diagnosis of the old failure

Browser inspection of the reported DY operation: `account-login`, phase `authenticating`, five events, terminal failure after approximately46seconds, with `runner_status=failed`, `login_session_status=failed`, `auth_status=failed` and `operation_login_failed`. The account/session linkage existed: the old UI's generic wording did not prove lost persistence. Only safe rendered fields were read; no raw logs, Cookie or profile storage.

The diagnostics page's environment preflight reported locked MediaCrawler `d6f7c5bb906b6dac40ddf343ef9e26438a3de092`, Chromium151.0.7922.34, Playwright1.62.0, Python3.13.15 and ffmpeg5.1.9. These launch/tool checks do not qualify login, creator capture or downloads. The deployed application Git revision was not available from these rendered facts. No new login/collection/download/deployment/media-server call or supervisor restart was submitted.

## Reproduction and implementation checks

- Before implementation, the independent audit replayed five cases through complete locked login/helper modules with synthetic pages: DY popup click timeout, DY/KS/WB QR selector timeout and both Tieba QR selectors timing out. All produced generic `failed`. This is offline control-flow evidence, not proof that a production selector changed.
- Reproducible script: [reproduce_login_classification.py](artifacts/reproduce_login_classification.py). After implementation it yields one `upstream_browser_timeout` and four `upstream_login_exited`, with the same calls and no actual browser/network. Upstream helpers still swallow some failures; exited does not identify the exact challenge failure. Run with `.venv/Scripts/python.exe -X utf8 -B` from the repository root. The first root invocation omitted UTF-8, so Chinese selector text in terminal output was garbled; classification assertions passed and no private data was involved.
- Login unit/confirmation selection:77passed/1.34s; process contract:67passed/85.29s. Covers typed versus same-named/builtin exceptions, SystemExit0 not authenticating, fixed frame rejection, private sentinels, cancellation, guardian cleanup and lock ownership.
- Root initial diagnostic/payload/application selection:193passed/26.17s. After adding real service→new session→durable Operation→exact latest diagnostic and untouched authenticated-account assertions, diagnostics alone:45passed/17.61s. API/local-library-without-server selection:23passed/15.23s. These overlap later selections; do not sum them.
- Final login selection:397passed,0skipped/120.37s, one existing Starlette/httpx deprecation warning. Exact command:

```powershell
.venv/Scripts/python.exe -m pytest tests/unit/test_login_diagnostics.py tests/unit/test_operation_payloads.py tests/unit/test_mediacrawler_login.py tests/unit/test_bilibili_login_confirmation.py tests/unit/test_login_qr_relay.py tests/integration/test_mediacrawler_login_application.py tests/contract/test_mediacrawler_login.py -q --tb=short --junitxml=docs/executions/0066-login-failure-and-workflow/artifacts/login-regression.xml
```

Local ignored JUnit SHA256: `33e1dba0ce3ef4b840848ca390cc4e649e9b66d00fb3077547dbeb6106f3ac4f`.

- New continuation policy105unit+8integration=113passed/15.17s. Existing seven-file scheduler selection173passed/29.49s. The sealed synthetic runner feeds real ingestion/checkpoints/worker finalization: seven300second continuations, then ordinary21600seconds on the eighth unit; preserved rotation, caps, early-tick refusal, restart/cancel reconciliation and one pipeline per success. Failures do not borrow old pending state; absent/changed/disabled lock and paused records retain ordinary behavior.
- Final broader workflow selection:759passed,1skipped/172.76s, one existing Starlette/httpx warning. The skip is `test_mediacrawler_scheduler_handler.py:730`, POSIX venv launchers use symlinks. Exact file selection/command (PowerShell):

```powershell
$task0066WorkflowTests = @(rg --files tests | Where-Object { $_ -match '(scheduler|scheduled_offline_pipeline|subscription_application_pipeline|pipeline_runtime|bili_scan_continuation|bili_bounded|bilibili_dynamic_scheduler|test_config|test_api_server|test_api_local_export|test_subscription_removal)' } | Sort-Object)
.venv/Scripts/python.exe -m pytest @task0066WorkflowTests -q --tb=short --junitxml=docs/executions/0066-login-failure-and-workflow/artifacts/workflow-regression.xml
```

This selected26files. Local ignored JUnit SHA256: `1a2e8d9d8ff42082495fcec1ed12de390da9b5dbc26ca31cdf11015145f0c002`.
- Pre-implementation read-only audits also ran105backend/127Web checks and130scheduler/pipeline checks; these were baseline observations, not additional final-source coverage.

## Frontend, static and package checks

- Final Web:705passed/22files/1.43s; Svelte check0errors/0warnings; build PASS7.52s; Prettier PASS. Earlier same-turn Web705passed/1.19s and build7.86s preceded the final wording/settings update; not separate cumulative tests.
- Ruff PASS; format352files unchanged; mypy138source files PASS; compileall PASS; docs672files PASS; both locked upstream checkouts PASS; `uv lock --check`62packages unchanged; `git diff --check` PASS. Two document patches initially had mismatched heading anchors and were reapplied after reading the exact headings. Formatting adjusted new test/script/Svelte lines; no product-test failure was hidden.
- `uv build` produced a wheel and sdist under local temp `media-sync-0066-build-b45f26a7010044fda706d0618a3d3300`. [check_package_sources.py](artifacts/check_package_sources.py) compares all152application Python files byte-for-byte in each archive without extraction. Both PASS. Wheel SHA256 `bf0f6cca9eafa2bd0f338a4832ee00fd4790dc08b60cca416208d015c248e4c5`; sdist `9d8f945aebcbbc290b1cdb4ab17851892cb17a3b1f520ce85022b1abf592d654`. These are local build checks, not release attachments; docs continued changing after that package snapshot.
- Independent reviews found no blocking issue after correcting the terminal login phase from ongoing wording to neutral wording and widening timeout copy to browser operations. They confirmed real-service login E2E linkage and real-ingestion continuation tests, not merely fabricated success summaries.

## Limits

Not a full repository test run. Current Linux image/suite, real platform retries, real creator/download/directory completion, native Emby/Jellyfin playback and fresh server deployment: NOT_RUN. Historical Bili canary remains failed/unresolved. Editable per-platform output, permanent backfill completion and end-to-end real risk-control pause wiring remain required. No historical diagnostic is backfilled with invented causes. Git publication is recorded after verification, not assumed from a local build.
