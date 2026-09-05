**English** | [中文](verification.zh.md)

# Safe console verification

- Date: 2026-09-05
- Status: Local source and combined browser gates passed

## Baseline and executed checks

Published baseline: `2e1949fc85eaa83973dc54c2c7f13f3c4334817e`, fresh fetch divergence `0 0` and clean worktree at that boundary. Eight-file frozen planning commit: `714c849`. Prior 2999 Python / 69 Web / 508 docs / wheel 125 / sdist 824 results are historical, not this increment.

| Check | Command or procedure | Actual result |
| --- | --- | --- |
| Preflight/CLI | `uv run --frozen pytest -q tests/unit/test_serve_check_config.py tests/unit/test_container_entrypoint.py tests/unit/test_operator_auth_cli.py` | 76 passed, 23.53s; earlier broader selection: 202 passed, one warning, 26.03s |
| Final shell refinement | `uv run --frozen pytest -q tests/unit/test_container_entrypoint.py` | 23 passed, 6.37s; prefixed check-only/invalid serve tested through real shell/CLI on fresh/existing DB |
| Console entry/auth/API | `uv run --frozen pytest -q tests/unit/test_operator_console_entry.py tests/unit/test_operator_auth.py tests/unit/test_operator_auth_api.py tests/unit/test_api_server.py` | 132 passed, one warning, 11.57s |
| Full Python | `uv run --frozen pytest -q` | 3155 passed, 22 skipped, one existing warning, 670.16s (0:11:10) |
| Final fixture regression | `uv run --frozen pytest -q tests/unit/test_console_smoke_fixture.py` | 4 passed, 1.76s, no skips; after the full suite, including two new immutable preview cases. Production Python unchanged |
| Final Web | In `web/`, serial `pnpm format:check`, `pnpm test`, `pnpm check`, `pnpm build` | 9 files / 114 tests; format passed, type check 0 errors / 0 warnings, static build passed; last auth/client focused selection: 44 passed |
| Python static | `uv run --frozen ruff check .`; `uv run --frozen ruff format --check .`; `uv run --frozen mypy src/media_sync`; `uv run --frozen python -m compileall -q src tests` | Passed; format 758 files, strict mypy 107 source files; final fixture separately passed Ruff/format |
| Upstreams | `uv run --frozen python scripts/check_upstreams.py` | Both locked checkouts verified |
| Shell syntax | `sh -n docker/entrypoint.sh` through Git Bash | Passed; shell dispatch/order evidence, not Linux image qualification |

The warning is the existing Starlette/httpx TestClient deprecation. The 22 skips are three Windows/POSIX differences, 11 operation PostgreSQL cases and eight playback-evidence PostgreSQL races. The later four-test fixture check is separate: there was no 3157-pass full run.

## Actual backend + built browser

Build Web; run `uv run --frozen python tests/unit/_console_smoke_fixture.py --root <empty-absolute-temp-directory> --video`; serve with the ordinary authenticated CLI. All MEDIA_SYNC inputs are isolated to the fixture with an explicit fixture-local SQLite URL, disposable operator credential and 600-second TTL. Loopback ports 8765/8766 were used. No auth bypass, real platform account or external media; this record retains no credential, Cookie, CSRF, raw QR or fixture path.

| Check | Actual observation and limit |
| --- | --- |
| Anonymous entry | `/accounts?ignored=fixture` redirects to `/?return_to=%2Faccounts`, dropping arbitrary query; only login mounts. Fresh-origin `/assets` similarly reaches login |
| Login/CSRF | Disposable operator login followed by session mounts private pages. Actual account form created “Browser CSRF fixture” and displayed two accounts; no platform authentication granted |
| Refresh/explorers | Authenticated reload preserves access; assets and contents each load two synthetic records after async auth mounting |
| Exact login image | Synthetic LoginSession image loads at 160 × 90 using same-origin Cookie. Not a scannable platform QR or proof of real QR polling/login |
| Archive media | Image decodes at 160 × 90. MP4 loads/decodes at readyState 4, error null, 160 × 90, duration 2s; frame visually inspected. Playback was not started; not real-platform/Emby/Jellyfin playback evidence |
| SSE | Jobs displays connected stream, cursor 0. Local tick with zero subscriptions returns zero jobs; no platform job launched |
| Natural expiry | Earlier 600s session returns to login-only tree with explicit expiry notice |
| Logout/other tab | Confirmed logout removes private UI; another Jobs tab also returns to login after session loss |
| Onboarding | Fresh origin prompts only after login. Browse-only dismissal does not accept license; another same-origin tab prompts again, proving no persistent acceptance |

These are synthetic application wiring checks, not seven-platform qualification. Delayed responses, malformed/stalled 401 bodies, no write replay, uncertain logout and QR/SSE cancellation races are covered by state-machine/client tests, not all reproduced in the browser.

## Attempts and review findings

- Initial Web check found seven mock-signature errors, corrected before final 0/0. Browser found stale Jobs stream copy and missing initial assets/contents fetch; explicit reactive dependencies and mount/navigation guards fixed both with regressions.
- Review found Click's `-- serve` could bypass shell preflight. Exact-prefix normalization plus shell-to-CLI regressions prove invalid config does not migrate fresh/existing DB.
- Fixture review caught ambient `MEDIA_SYNC_DATABASE_URL` overriding intended isolation. Explicit fixture DB and outside sentinel regression fixed it; original manual fixture had no ambient DB URL. Initial fixture import-layout/format issues were corrected.
- One pre-fix full run was deliberately interrupted around 2%, not counted as a pass. Completed 3155-pass run followed the entrypoint and DB-isolation fixes.
- Initial direct video navigation was browser-blocked; subsequent inline image/video exposed writable fixture archives rejected by the existing immutable gate. Only generated fixture blobs were made read-only; real ArchivePreviewService regression and final browser decoding pass. Production security unchanged.
- A second local server attempt used unsupported `python -m media_sync` and exited without starting; ordinary console entry point succeeded.
- Independent frontend review found current-epoch 401 depended on body parsing. Immediate authority revocation, nonblocking body cancellation and malformed/stalled-body regressions fixed it while old-epoch responses cannot lock a newer login. No other actionable P0/P1/P2 found in the reviewed auth lane.

## External exclusions and publication

Docker CLI is unavailable; `MEDIA_SYNC_TEST_POSTGRESQL_URL` is unset. Current Docker/Compose, effective Linux UID/secret permissions, fresh/upgrade/restart/restore and real PostgreSQL remain NOT_RUN. No live platform/CDN/media-server scan/playback was run; qualification rows remain NOT_RUN. Local results are not GitHub Actions evidence.

Final `uv run --frozen python scripts/check_docs.py` passed 516 Markdown files; `git diff --check` passed and all frozen parent/child goal/plan diffs were empty. A fresh system-temporary `uv build --out-dir <absolute-temp-directory>` passed: wheel 125 entries, sdist 842. Required production files, container entrypoint, new Web sources and fixture tests were present in their expected archives; path/content checks found no private/runtime data, actual .env/databases/private keys, compiled build output, workstation paths or disposable credential. The first archive inspection accidentally included uv's generated .gitignore; limiting input to wheel/tar.gz fixed the inspection without rebuilding. Default wheel/sdist do not include the compiled Web bundle: source users must build it, and Docker uses its separate Web build stage.

All four browser tabs created for the fixture were closed. The two test-server process handles were gone at closeout, and a fresh listener check confirmed neither loopback port 8765 nor 8766 remained listening; no service was restarted. The first remote reconciliation attempt failed with a TLS unexpected-EOF error; retry using `git -c http.version=HTTP/1.1 fetch --prune origin` succeeded with normal TLS validation. No force push or weakened TLS was used.

The implementation commit containing this record identifies the source. Explicit reviewed-path staging excludes local state; push planning and implementation together and verify a fresh remote divergence/clean worktree. This does not complete the parent or product goal.
