**English** | [中文](verification.zh.md)

# Execution 0050 verification

- Status: Changed frontend/API/qualification gates pass; the complete Windows suite reproduces the previously documented process-sealing instability
- Date: 2026-09-04
- Baseline: `6d68768`
- Raw local junit: `artifacts/pytest-windows-0050.xml` (git-ignored; sanitized summary below)

## Automated gates

| Check | Command | Result |
| --- | --- | --- |
| Frontend formatting | `pnpm format:check` | `PASS` |
| Svelte/TypeScript | `pnpm check` | `PASS` — 0 errors, 0 warnings |
| Frontend units | `pnpm test` | `PASS` — 2 tests |
| Static production bundle | `pnpm build` | `PASS` — adapter-static wrote `web/build` |
| API suite | `python -m pytest -q tests/unit/test_api_server.py` | `PASS` — 9 tests; includes explicit clean-clone SPA fixture, route fallback, immutable-cache, security headers, content and library contracts |
| Checkout/license focus | `python -m pytest -q tests/contract/test_mediacrawler_bridge.py -k "checkout or license"` | `PASS` — 16 tests, 61 deselected |
| Python static/package gates | `ruff check`, `ruff format --check`, strict `mypy`, `compileall`, docs, upstream locks, `uv build` | `PASS` — 624 files formatted, 87 typed source files, 446 Markdown files, 2 clean locked checkouts, sdist + wheel built |
| Packaged migrations | `uv run pytest -q tests/integration/test_packaged_migrations.py` | `PASS` — 7 tests |
| Complete Python suite | `uv run pytest -q --junitxml=artifacts/pytest-windows-0050.xml` with uv + ffmpeg/ffprobe on `PATH` | `2038 passed, 33 failed, 1 skipped` in 502.82 s; failures are classified below, not suppressed |
| Docker build/run | Operator Linux host | `NOT_RUN` for this revision on this workstation |

The final complete run includes the network-boundary response completion and the full local uv/ffmpeg/ffprobe toolchain, so package and production media integration checks executed rather than becoming environment skips.

## Browser and fidelity evidence

- In-app browser at `http://127.0.0.1:8765`: all nine routes returned the expected title and meaningful DOM; no framework overlay; console warnings/errors: 0.
- Final diagnostic-route QA caught and fixed an acknowledgement-hydration ordering race that could leave a returning browser on `Checking...` without issuing the preflight request. A fresh in-app tab and independent Playwright/Chrome run now both render `runtime_unconfigured`, `Local safe`, and `127.0.0.1:8765`; the request returns 200 and browser warnings/errors remain 0. The fixed-state capture is `console-diagnostics-desktop.png`.
- Interaction: Settings → reset first-use acknowledgement → onboarding modal appears → accept → reload Settings. The modal count after reload is 0 and the state reads 已确认.
- Accounts shows the two fixture accounts and QR actions without either old repeated checkbox.
- Existing Playwright captures cover 1440×900 desktop and 390×844 mobile; the in-app browser also inspected the current rendered route after the final production build.
- Direct `view_image` comparison used `bili-sync-reference.jpg` and `console-dashboard-desktop.png`, with mobile checked separately. The inspected ledger covered sidebar hierarchy, compact top bar, true-white palette, border/shadow weight, table/panel density, icon treatment, operational copy and responsive collapse. No fixable material mismatch remains for the requested “similar to bili-sync” direction.
- Above-the-fold copy contains only media-sync operational labels; Bili Sync's unrelated storage/CPU charts and Bilibili-only wording were intentionally not copied. This is a domain adaptation, not a fidelity defect.

## Full-suite honesty note

The junit summary is `tests=2072 failures=33 errors=0 skipped=1`. Failures group as 19 in `test_mediacrawler_bridge`, 10 in `test_mediacrawler_scheduler_handler`, and one each in login, supervision, CLI ingest and the security matrix. They are the same Windows-native completion-receipt/process family already recorded as nondeterministic in executions 0048/0049 (0048 observed 33/35 failures; 0049 later observed one green run): most fail closed as `unsafe_path`, with the remaining child timing/command races cascading into the same integration paths. None touches the 0050 frontend, API projection or LICENSE qualification changes; their focused suites are green. The Linux phase-B run remains authoritative, and no security check was weakened to force Windows green.

## Not claimed

No 0050 Docker image build, in-container static-bundle inspection, `mediacrawler doctor`, runtime-user Chromium launch, restart/backup drill, real account login, crawl, CDN download or Emby/Jellyfin scan/playback is claimed. Those remain operator phase-B/0047 evidence.
