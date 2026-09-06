[**English**](verification.md) | [中文](verification.zh.md)

# Verification

Status: focused offline evidence, the complete Python unit suite, the complete 782-test media-sync Web suite, a staged build of the real pinned upstream React source, and the hardened production-dependency audit pass for implementation commit `ea64938`. The complete Docker image/runtime and online deployment are `NOT_RUN`; the all-dependency audit retains eight build-only development findings, so 0072 is not deployment-qualified.

## Status matrix

| Gate | State | Exact evidence / boundary |
| --- | --- | --- |
| Focused Python integration/authentication | `PASS` | Final seven-file union: `142 passed, 1 warning in 29.19s`; its disjoint components are the 13-test WebUI-manager file and the 129-test license/auth/config selection. The warning is the existing Starlette `TestClient`/httpx deprecation. Coverage includes the default-closed license gate, exact environment token parsing, fixed interpreter/checkout and deterministic environment check, same-origin/CORP and quiet polling, managed roots/process trees/shutdown, bounded/redacted logs, 64-KiB private Cookie handoff and cleanup, browser-child environment/policy, QR relay, fixed unavailable behavior, mounted HTTP authentication/CSRF, exact WebSocket Host/Origin/session rules, and login returns. |
| Focused media-sync Web test | `PASS` | One Vitest file, `26 passed`; includes the exact `/crawler/` login return path. This is not the full Web suite and does not execute the upstream React application. |
| media-sync Web check and production build | `PASS` | `svelte-check` reported 0 errors and 0 warnings; the media-sync Vite production build completed. Relevant-file Prettier check passed. |
| Focused Python static checks | `PASS` | Ruff reported `All checks passed!`; Ruff format reported 13 files already formatted. Strict mypy reported no issues in 6 source files. |
| Documentation links | `PASS` | `scripts/check_docs.py` reported `Documentation links OK (730 Markdown files checked).` |
| Working-tree whitespace | `PASS` | `git diff --check` exited 0 with no output after the documentation changes. |
| Complete Python suite | `PASS` | `tests/unit -q --tb=short` completed with `4633 passed, 3 skipped, 1 warning in 547.80s` (wall time 552.725s). The three skips are Windows/POSIX-specific filesystem/DACL cases; the warning is the existing Starlette `TestClient`/httpx deprecation. The run began with the exact implementation in the working tree at `dcd3881` and ended after that unchanged implementation was committed as `ea64938`; only documentation remained outside the commit. |
| Complete Web test suite | `PASS` | `pnpm --dir web test` passed all 782 tests on the current 0072 working tree. The 26-test file above remains the focused login-return selection. |
| Patched pinned upstream React build | `PASS` | A fresh temporary copy ran the security patch, copied-lock regeneration, clean install, production audit, integration patch, and TypeScript/Vite build in order; 1,836 modules transformed. The generated index contains `/crawler/assets/` and `/crawler/static/vite.svg`; the bundle contains `/crawler/api`, operator CSRF, `/crawler/api/ws/logs`, and the QR endpoint. |
| Current Docker image/runtime | `NOT_RUN` | The Dockerfile stage is implemented but a complete image was not built or run because Docker is unavailable on this workstation. The standalone React build is not Docker evidence. |
| Current online deployment | `NOT_RUN` | No running deployment was inspected or changed, so the image identity, `/crawler/` reachability, persistence, browser behavior, and runtime ownership remain unvalidated. |
| Hardened production dependency audit | `PASS` | The build-copy security patch selects `axios@1.18.0`, `follow-redirects@1.16.0`, and `form-data@4.0.6`; after copied-lock regeneration and `npm ci`, `npm audit --omit=dev --audit-level=low` reported `found 0 vulnerabilities`. The versioned upstream checkout/lock remain unchanged. |
| Full build dependency audit | `FAIL` / dev-only residual | The hardened copy's all-dependency audit reports 8 package entries: 6 high, 2 low, 0 moderate, 0 critical. They are `@babel/core`, `browserslist`, `nanoid`, `picomatch`, `postcss`, `postcss-selector-parser`, `rollup`, and `vite`; all are development/build dependencies and their packages are not copied into the final runtime image. They remain build-time supply-chain exposure, so the nonzero result is not described as a universal audit PASS. |
| Raw pinned-upstream audit baseline | Historical finding | Before the build-copy security patch, `npm audit --json` on the untouched checkout reported 11 package entries: 8 high, 1 moderate, 2 low, 0 critical. This discovery is retained rather than silently rewritten; it is superseded only for the generated production bundle by the three exact build-copy overrides above. |
| Synthetic QR relay contract | `PASS` within focused Python | Synthetic raster bytes prove bounded normalization, managed-file visibility during a child run, cleanup, response size/age checks, `no-store`, `nosniff`, and digest headers. This is implementation evidence only. |
| Real browser QR scan / platform login | `NOT_RUN` | No QR was scanned and no real platform login or saved-session reuse was attempted. The synthetic test cannot grant QR/login readiness. |
| Console output → Subscription/history/scheduled incremental/ingestion/NFO | `NOT_IMPLEMENTED` in this slice | The roots and ownership boundary are frozen, but no automatic completion ingestion or durable scheduling/publication chain is connected. |
| Real seven-platform crawl/download/CDN qualification | `NOT_RUN` | No real account, creator, item, media byte, CDN behavior, history completeness, incrementality, or download was exercised for any of the seven platforms. |
| Real Emby/Jellyfin server scan/playback | `NOT_RUN` / optional | No server was required or used. Local folder/NFO responsibility remains with media-sync, but this slice did not connect console ingestion to that boundary. |

## Commands executed

Focused Python:

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/unit/test_mediacrawler_webui.py `
  tests/unit/test_api_mediacrawler_webui.py `
  tests/unit/test_mediacrawler_webui_license_gate.py `
  tests/unit/test_operator_auth_websocket.py `
  tests/unit/test_operator_auth_api.py `
  tests/unit/test_serve_check_config.py `
  tests/unit/test_config.py -q
```

Complete Python unit suite:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit -q --tb=short
```

Complete/focused Web and media-sync Web static/build checks:

```powershell
pnpm --dir web test
pnpm --dir web exec vitest run src/lib/stores/operator-auth.test.ts
pnpm --dir web run check
pnpm --dir web run build
pnpm --dir web exec prettier --check src/lib/components/AppShell.svelte src/lib/stores/operator-auth.ts src/lib/stores/operator-auth.test.ts
```

Focused Python static checks (the Ruff commands used the same 13 source/test paths shown here):

```powershell
.\.venv\Scripts\python.exe -m ruff check src/media_sync/config.py src/media_sync/interfaces/api.py src/media_sync/security/operator_auth.py src/media_sync/integrations/mediacrawler/license_gate.py src/media_sync/integrations/mediacrawler/webui.py src/media_sync/integrations/mediacrawler/webui_child.py tests/unit/test_operator_auth_api.py tests/unit/test_operator_auth_websocket.py tests/unit/test_api_mediacrawler_webui.py tests/unit/test_mediacrawler_webui.py tests/unit/test_mediacrawler_webui_license_gate.py tests/unit/test_serve_check_config.py tests/unit/test_config.py
.\.venv\Scripts\python.exe -m ruff format --check src/media_sync/config.py src/media_sync/interfaces/api.py src/media_sync/security/operator_auth.py src/media_sync/integrations/mediacrawler/license_gate.py src/media_sync/integrations/mediacrawler/webui.py src/media_sync/integrations/mediacrawler/webui_child.py tests/unit/test_operator_auth_api.py tests/unit/test_operator_auth_websocket.py tests/unit/test_api_mediacrawler_webui.py tests/unit/test_mediacrawler_webui.py tests/unit/test_mediacrawler_webui_license_gate.py tests/unit/test_serve_check_config.py tests/unit/test_config.py
.\.venv\Scripts\python.exe -m mypy --strict src/media_sync/config.py src/media_sync/integrations/mediacrawler/license_gate.py src/media_sync/integrations/mediacrawler/webui.py src/media_sync/integrations/mediacrawler/webui_child.py src/media_sync/interfaces/api.py src/media_sync/security/operator_auth.py
```

Pinned upstream React build (from a fresh temporary copied WebUI root; the two patch scripts were copied there and generated output went to the adjacent `artifacts/api/webui`, not the locked checkout):

```powershell
node mediacrawler-webui-security-patch.mjs
npm install --package-lock-only --ignore-scripts
npm ci
npm audit --omit=dev --audit-level=low
node mediacrawler-webui-patch.mjs
npm run build -- --base=/crawler/
```

All-dependency audits, documentation, and final whitespace checks:

```powershell
Push-Location .mediacrawler-local/webui
npm audit --json
Pop-Location
# The same command in the hardened temporary copy reports the remaining
# eight development/build entries.
.\.venv\Scripts\python.exe scripts/check_docs.py
git diff --check
```

The production audit passes; the full audit's nonzero development-only result and the original 11-entry discovery are both retained rather than normalized away. No Docker, deployment, platform, CDN, or media-server command is claimed.
