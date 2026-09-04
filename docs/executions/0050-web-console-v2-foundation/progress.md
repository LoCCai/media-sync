**English** | [中文](progress.zh.md)

# Execution 0050 progress

- Status: Offline foundation and repaired Linux image preflight delivered; broader Phase B and live qualification continue in 0047
- Date: 2026-09-04
- Baseline commit: `6d68768`

## Delivered

1. MediaCrawler qualification now uses digest `aeff21de8609bec9d6e939bbbba7c2914ae0a6e7c9470ea7945c03f7d17a2a33` after CRLF→LF normalization and rejects any remaining bare CR. The operator diagnosis script and defect plan carry the same rule.
2. `web/` now contains the locked SvelteKit 5 application, shared shell/components/stores/types and nine routed operational surfaces. Its visual system uses a light-gray fixed sidebar, true-white canvas, restrained borders/shadows, compact controls and table-first information density.
3. First use opens one acknowledgement modal. Acceptance persists as versioned browser-local state; subsequent refreshes show no checkbox or modal, and Settings provides an intentional reset path.
4. Accounts, subscriptions, jobs, scheduler/pipeline actions, QR-login polling, asset download/verify and Emby export reuse the existing REST application services. Content and author-library read models fill the remaining navigation surfaces.
5. FastAPI serves the static SPA and immutable assets safely, keeps `/legacy`, returns 404 for unknown API paths, and reports a complete network-boundary object matching the diagnostic UI.
6. Docker builds and tests the frontend before Python packaging, supports a mainland npm registry override, records Node/pnpm/frontend-lock facts, and ships no Node runtime.
7. README, deployment guidance, status, journal index and this execution record now describe the one-time acknowledgement, rebuild requirement, current qualification digest and remaining Linux/live gates.
8. The operator's first real 0050 Linux image built and started successfully. Its manifest proved Chromium `151.0.7922.34`, Node `v24.20.0`, pnpm `11.19.0` and frontend lock digest `dc9a47134060f185a3942bac5262b0ca55e0457a4dcddade81803e069b9bf3a0`; a direct runtime-user Chromium launch also succeeded.
9. That image's doctor passed the licence, exact SHA, tracked blobs and clean-tree gates but failed `runtime_invalid / runtime_imports_missing`. The cause was `Path.resolve()` dereferencing `/opt/mediacrawler-venv/bin/python` to the base interpreter and bypassing the venv site-packages. All doctor, manifest, login, detail and scheduled-worker launch paths now preserve the venv launcher, and the Docker build runs the application doctor as `mediasync` so this class of drift aborts the build.
10. The operator rebuilt after the launcher repair. Doctor and deep readiness now both return `ready`; runtime Chromium launches as `151.0.7922.34`, matching the build manifest. This closes the 0050 image/runtime defect while restart, backup/restore and live-platform evidence remain under 0047.

## Browser and design result

The implementation keeps the recognizable bili-sync skeleton—fixed grouped sidebar, compact top bar, open white workspace, restrained panels, table-oriented operational views and bottom task/settings navigation—while replacing Bilibili-only charts and source semantics with media-sync's seven-platform account, subscription, archive and Emby workflows. Desktop 1440×900 and mobile 390×844 captures show no clipping or horizontal page overflow; dense tables retain local horizontal scrolling on narrow screens.

## Remaining work

Operation persistence, SSE/logs, richer detail/recovery controls, media-server scan/playback evidence, operator authentication and removal of the legacy console remain planned follow-ups. Execution 0047 now continues the remaining Linux baseline before Bilibili/XHS canaries; no live row changed here.
