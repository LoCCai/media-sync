**English** | [中文](verification.zh.md)

# Login diagnostics verification

- Status: Available local gates passed; current combined repair is not deployed

Baseline: clean `f61a3c4`, frozen diagnostics plan `488ce20`; additive runtime/QR plan `7268352`. Previous full-suite results are historical, not a full run for this increment.

## Python checks and corrections

The final backend command was:

```powershell
.venv/Scripts/python.exe -m pytest -q tests/unit/test_login_diagnostics.py tests/unit/test_api_operations.py tests/unit/test_api_server.py tests/unit/test_operator_auth_api.py tests/unit/test_cli_login.py tests/unit/test_operation_payloads.py tests/integration/test_operation_repository.py tests/integration/test_operation_coordinator.py tests/integration/test_operation_postgresql_races.py tests/integration/test_mediacrawler_login_application.py tests/integration/test_login_session_repository.py --junitxml=artifacts/login-diagnostics-backend-regression.xml
```

Result: **355 passed, 11 skipped, one existing Starlette/httpx warning in 51.64s**. All 11 skips require an unavailable real PostgreSQL server. The initial existing-test run had 318 passes, 11 skips and one failure in 47.16s: the old CLI exact-output assertion omitted the new `diagnostic: null`. That assertion was updated; it was not a production exception. Projection review added rejection of extra execution-subject types, contradictory completion tuples, invalid raw JSON, stale/latest identity and safe generic recovery.

The final combined runtime command was:

```powershell
uv run --frozen --with pillow==12.3.0 pytest -q tests/unit/test_browser_launch_diagnostics.py tests/unit/test_mediacrawler_login.py tests/contract/test_upstream_browser_policy.py tests/contract/test_browser_policy_wiring.py tests/contract/test_mediacrawler_login.py tests/unit/test_login_qr_relay.py tests/contract/test_upstream_qr_relay.py tests/unit/test_mediacrawler_javascript_preflight.py tests/unit/test_mediacrawler_browser_environment.py tests/unit/test_mediacrawler_browser_preflight.py tests/unit/test_login_preflight.py tests/unit/test_login_browser_smoke_script.py --junitxml=artifacts/login-diagnostics-runtime-regression.xml
```

Result: **370 passed, no skips in 72.83s**, including real Pillow image normalization. Platform/browser work in pinned helper/entry tests is synthetic, not real authentication. Earlier root entry wiring passed 36 tests; lifecycle/policy union passed 204 in 23.29s; separate isolated login contract passed 53 in 71.15s. The extra doctor/bridge union passed 93 with one POSIX-on-Windows skip in 82.81s. These overlapping runs are not summed into a full-suite total.

## Web and static gates

Web commands ran serially in `web`: `pnpm test`, `pnpm check`, `pnpm format:check`, `pnpm build`. Final result: **179 tests in 11 files**, 493 ms; Svelte zero errors/warnings; formatting and static production build passed (Vite 6.38s). Earlier check found nullable-summary and incomplete test-fixture typing errors; both were corrected. Tests include all five terminal states, image failure/hang, stale/current Operation/session races, late responses/close, legacy diagnostics and closed non-reflecting explanations. This increment has no synthetic rendered-browser fixture run; production browser inspection was read-only evidence of the old deployed failure, not validation of this local Web patch.

`.venv/Scripts/python.exe -m ruff check src scripts tests`, `ruff format --check src scripts tests` (256 files), `mypy src/media_sync` (110 source files), and `compileall -q src/media_sync scripts/check_login_browser.py` all passed. One intermediate helper-format finding and one new JS test enum-identity assertion were corrected; their failed runs are not PASS.

## Package and documentation snapshot

`uv build --offline` in an isolated system temporary output directory produced a 128-entry wheel and 888-entry sdist with all current implementation files. This build preceded final documentation/Cookie-draft edits; it is a code packaging snapshot, not the final documentation archive. Neither default package includes compiled Web output; Docker builds that separately. Private Compose, actual `.env`, credentials, profiles, databases, logs and tool/runtime roots were absent. Seven private-IP-like candidate paths were inspected as existing CIDR/examples/tests and all were unchanged from `f61a3c4`; the historical exact LAN-plan blob also matched. No blanket private-address exemption was used.

Documentation/upstream checks and final Git publication will be recorded at closeout. Raw local test XMLs stay ignored under `artifacts`.

## Remaining gates

Independent runtime/projection/Web/QR reviews found no unresolved blocking issue in this increment. The existing hard-kill QR temporary-file cleanup limitation is documented in [runtime follow-up](../login-runtime-followup/verification.md). Docker build/current combined image, real QR scan/session reuse, capture and Emby/Jellyfin remain unverified. The operator's previous Linux blank-browser PASS and later `NODE_MISSING` are separate observations, not a platform PASS. Cookie-login functionality remains unimplemented; only its [draft](../cookie-login/plan.md) is recorded.
