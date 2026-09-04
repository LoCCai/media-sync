**English** | [中文](progress.zh.md)

# Execution 0050 progress

- Status: Offline foundation delivered; Linux image and live qualification pending
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

## Browser and design result

The implementation keeps the recognizable bili-sync skeleton—fixed grouped sidebar, compact top bar, open white workspace, restrained panels, table-oriented operational views and bottom task/settings navigation—while replacing Bilibili-only charts and source semantics with media-sync's seven-platform account, subscription, archive and Emby workflows. Desktop 1440×900 and mobile 390×844 captures show no clipping or horizontal page overflow; dense tables retain local horizontal scrolling on narrow screens.

## Remaining work

Operation persistence, SSE/logs, richer detail/recovery controls, media-server scan/playback evidence, operator authentication and removal of the legacy console remain planned follow-ups. The operator must rebuild the 0050 image, verify the manifest/doctor/Chromium gates, then continue 0047's Bilibili/XHS canaries; no live row changed here.
