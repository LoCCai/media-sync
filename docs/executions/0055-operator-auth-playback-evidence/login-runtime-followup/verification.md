**English** | [中文](verification.zh.md)

# Login integration follow-up verification

- Status: Available local gates passed; new Docker image and live QR NOT_RUN

Evidence before code: pinned sources inspected, Docker stages inspected, operator-supplied Linux blank launch passed; fresh platform failures directly observed through read-only browser UI. Exact deployed Git SHA/image digest and failure exception are not available. No root-cause certainty or platform PASS is claimed. Commands/results/corrections will be recorded here after execution.

## Implementation and evidence

The operator subsequently ran the credential-free `command -v node` check in the active container and supplied `NODE_MISSING`. Public exact PyExecJS 1.5.1 source confirms `compile()` calls runtime selection immediately. An isolated test with no registered runtimes raised `RuntimeUnavailableError` without executing JavaScript or launching a browser. This supports the missing-runtime failure path; the historical server exception itself was never captured.

The final Docker stage now installs `nodejs`, records its version, and retains the non-root doctor build gate. The isolated Python doctor executes a fixed `1 + 1` JavaScript function and safely returns `runtime_javascript_unavailable` on missing/import/compile/call/wrong-result failure. Existing 20-second timeout, isolated interpreter, secret-denying environment and suppressed output remain. This probe does not import upstream or access a platform/profile.

The QR relay accepts bounded canonical base64 and explicit PNG/JPEG/WebP base64 data URIs, validates actual format, maximum axis 4096, total pixels 4 Mi, and one frame before loading. Lazy upstream Pillow normalizes string input to metadata-free PNG with a 2 MiB output bound; encoded input also caps at 2 MiB. Existing bounded byte inputs remain unchanged. Private exclusive temporary creation, atomic replace and ordinary failure cleanup prevent partial QR publication; no URL fetching, native viewer or raw logging is added.

## Verification results and corrections

- Initial `uv run --offline --no-project --with pyexecjs==1.5.1 ...` inspection failed because the exact package was not cached. Retrieval from the official PyPI index succeeded without changing project dependencies; the missing-runtime experiment above then ran offline. A real local `execjs.compile('function media_sync_probe() { return 1 + 1; }').call('media_sync_probe')` returned 2 (`javascript_probe_ok: True`). This is local JavaScript evidence, not Linux image evidence.
- `.venv/Scripts/python.exe -m pytest tests/unit/test_mediacrawler_javascript_preflight.py tests/unit/test_login_preflight.py tests/contract/test_mediacrawler_bridge.py -q`: **93 passed, one POSIX symlink skip in 82.81s**. A preceding 16-test run had one incorrect enum-identity assertion (15 passed); it was changed to value comparison and rerun. Docker assertions are static wiring, not a build.
- QR focused default environment: **60 passed, 7 skipped** because Pillow is an upstream dependency, not an app development dependency. `uv run --frozen --with pillow==12.3.0 pytest -q -x tests/unit/test_login_qr_relay.py tests/contract/test_upstream_qr_relay.py`: **67 passed in 2.15s**, including real PNG/JPEG/WebP conversion. The verified pinned inline/remote/canvas helper bodies run against fake page/HTTP boundaries; seven call sites are checked. No live QR/account is used.
- Final combined runtime regression: **370 passed, no skips in 72.83s** with real Pillow; related backend **355 passed, 11 PostgreSQL skips, one existing warning in 51.64s**; Web **179 passed** and format/check/build passed. Full commands, static/package snapshot and failed first runs are recorded in [diagnostics verification](../login-diagnostics/verification.md). No full Python suite was rerun for this bounded increment.
- Independent Docker/doctor and QR reviews found no new blocking defect. Normal write/replace errors clean temporary files. A hard-killed process can still leave a `.login-qr.png.*.tmp` in the private account root; parent cleanup currently removes the final QR and job tree, not these temporary remnants. This is a pre-existing hard-kill limitation, not a claimed complete cleanup guarantee.

## Operator handoff and remaining work

Preserve the working private Compose, exact Origin, named data volume and credential permissions; back up state first. After GitHub publication, run `git pull --ff-only`, `docker-compose build media-sync`, the existing configuration-only check, and `docker-compose up -d --no-deps --force-recreate media-sync`, stopping on any failed command. The final build now requires working JavaScript; a restart of the old image is insufficient. Recreate an active supervisor from the same new image too. Do not use `down -v` or overwrite deployment configuration.

Refresh the accounts page, preflight one account, then let the operator start and scan its QR. Record the actual outcome before widening platforms. Exact deployed SHA/image digest, new-image build/QR scan/session reuse, capture and Emby/Jellyfin are still unverified. Pasted-Cookie login has an accepted goal and [draft plan](../cookie-login/plan.md), but no implementation in this increment.
