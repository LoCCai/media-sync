**English** | [中文](goal.zh.md)

# Execution 0050 goal

- Status: Web Console v2 foundation implemented and offline-verified; operator Docker/live gates remain open
- Date: 2026-09-04
- Predecessor: `6d68768` (deep MediaCrawler readiness diagnostics and console gates)
- Scope: portable MediaCrawler license qualification plus the first complete Console v2 migration slice
- Database migration: None
- Implementation and closeout commit: the commit containing this record (self SHA not embedded)

## Outcome

1. Replace the platform-dependent raw LICENSE digest with one canonical-LF content identity. LF and CRLF checkouts qualify identically, bare carriage returns fail closed, and the locked SHA, tracked Git blob and clean-worktree checks remain mandatory.
2. Deliver a SvelteKit 5 + TypeScript + Tailwind static SPA with a compact bili-sync-inspired shell and routed dashboard, accounts, subscriptions, jobs, content, assets/archive, media library, diagnostics and settings surfaces.
3. Replace repeated operation-time checkboxes with one non-dismissible first-browser acknowledgement stored in `localStorage`. Login and worker requests automatically carry both gate fields afterwards; the backend continues to enforce the license and checkout boundary on every operation.
4. Serve the SPA from FastAPI at `/`, preserve the old console at `/legacy`, support history-route fallback, cache fingerprinted assets immutably, and apply CSP, anti-framing, `nosniff`, referrer and API no-store headers.
5. Add bounded, redaction-safe content and per-author library projections for the new read-only surfaces without exposing signed locators, cookies or host archive paths.
6. Build the frontend in an isolated Node/pnpm Docker stage, copy only static output into the Python package, record Node/pnpm/lock identity in the build manifest, and keep Node out of the final image.

## Acceptance boundaries

- The SPA reuses existing application services and `/api/v1`; it does not access SQLite directly or create a second business runtime.
- Existing in-memory Operation history remains explicitly labeled as process-local. Persistence, SSE and structured logs are not claimed by this foundation.
- Browser QA uses local fixture data only. No real platform login, crawl, CDN byte, Emby scan or playback row changes from `NOT_RUN`.
- The 0050 image is not claimed built on this Windows workstation; the operator's Linux rebuild and in-container doctor/Chromium checks remain phase-B gates.

## Explicitly deferred

Persistent operations/events/logs (0052), richer content/asset recovery (0053), media-server scan qualification (0054), operator authentication and backup/upgrade UI (0055), and final 0.2 migration/removal of `/legacy` (0056) remain separate executions.
