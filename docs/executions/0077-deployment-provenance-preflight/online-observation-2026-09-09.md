**English** | [中文](online-observation-2026-09-09.zh.md)

# Online observation: deployment predates 0077

## Status

**STOPPED BEFORE DEPLOYMENT OR CANARY.** This was an authenticated, read-only browser inspection of `https://cc.icai.top:52144/diagnostics` after GitHub `main` reached `70c041f`. It did not rebuild or restart a container, mutate the database, start the supervisor, log in to a platform, create/resume a Subscription, crawl or download.

## Observed evidence

At the page's displayed check time `2026/09/09 00:58:38`, the existing deployment reported:

| Evidence | Observation |
| --- | --- |
| Overall deep readiness | `ready`; the page said all deep checks passed |
| MediaCrawler revision | `d6f7c5bb906b6dac40ddf343ef9e26438a3de092` |
| Checkout checks | License acknowledgement, lock, path, repository root, required files, license digest, revision, tracked blobs, clean worktree and Python runtime all displayed `pass` |
| Runtime Chromium | `151.0.7922.34`, displayed as launchable |
| Build browser/toolchain | Chromium `151.0.7922.34`, Playwright `1.62.0`, Python `3.13.15`, ffmpeg `5.1.9-0+deb12u1` |
| Required tools and paths | Git, ffmpeg, ffprobe, Xvfb and all five displayed persistent/runtime directories showed `pass` |
| API bind | `0.0.0.0:8632`, with the existing network-boundary review warning |

This replaces the earlier `git_inspection_failed` observation as current evidence for that existing container: its pinned checkout now passes. It does not identify which media-sync application commit produced the container.

## Decisive negative evidence

The rendered **Build and runtime facts** section did not contain any of the three rows added by implementation `d6db86a`:

- `media-sync source revision`;
- current/expected database migration;
- Bilibili and XHS continuation delays.

Therefore the running UI cannot be the published 0077 bundle and cannot prove deployed revision `70c041f`. The exact application commit and database migration remain unknown. A healthy report, package version, upstream SHA or matching Chromium version cannot substitute for the missing application identity.

## Decision and next action

The XHS canary remains `NOT_RUN`. Do not start it against this unidentified image. The next action is still the [deployment handoff](deployment-handoff.md): back up `/data`, pull GitHub `main` by fast-forward, export its exact clean HEAD as `MEDIA_SYNC_SOURCE_REVISION`, rebuild/recreate the API container, and compare the new deep report under both API and supervisor service definitions while the supervisor remains stopped.

Only a report that shows the exact deployed application SHA, current/expected `0015_xhs_creator_notes`, matching Bilibili/XHS continuation values and the already healthy checkout/runtime may unlock the bounded XHS canary.
