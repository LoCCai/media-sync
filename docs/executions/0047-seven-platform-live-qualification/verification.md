**English** | [中文](verification.zh.md)

# Execution 0047 verification

- Status: Phase B partial pass; no live platform row has run
- Evidence date: 2026-09-04
- Deep-readiness timestamp: `2026-09-04T09:40:06.067622+00:00`

## Verified Linux container slice

| Check | Result |
| --- | --- |
| MediaCrawler doctor | `PASS` — `ok=true`, `code=ready`, checkout/runtime ready, every reported checkout/runtime check passed |
| Locked upstream | `PASS` — exact SHA `d6f7c5bb906b6dac40ddf343ef9e26438a3de092`, canonical licence, tracked blobs and clean worktree |
| Database | `PASS` — SQLite reachable, revision `0005_asset_refresh_sources` current, 12/12 required tables present |
| Runtime tools | `PASS` — Git, ffmpeg, ffprobe and Xvfb available |
| Persistent roots | `PASS` — state, archive, export, jobs and MediaCrawler runtime directories exist and are writable |
| Browser | `PASS` — runtime Chromium launched and returned `151.0.7922.34` |
| Build identity | `PASS` — Chromium `151.0.7922.34`, Playwright `1.62.0`, Python `3.13.15`, uv `0.9.18`, Node `v24.20.0`, pnpm `11.19.0`, web lock `dc9a47134060f185a3942bac5262b0ca55e0457a4dcddade81803e069b9bf3a0` |
| API network boundary | `REVIEW_REQUIRED` — application listens on container `0.0.0.0:8632`; host publication has not yet been reported |
| Live qualification | `NOT_RUN` |

## Not yet verified

The Linux complete suite, explicit host-port publication, restart persistence, backup/restore to a fresh volume, process-leak baseline, Bilibili/XHS login and every crawl/download/Emby row remain unverified. No fixture or readiness result substitutes for those live rows.
