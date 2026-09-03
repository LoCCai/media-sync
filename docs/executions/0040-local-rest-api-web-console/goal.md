**English** | [中文](goal.zh.md)

# Execution 0040 goal

- Status: Implementation complete; runtime verification scoped to the Linux deployment host
- Date: 2026-09-03
- Predecessor: Execution 0039 implementation (same working session)
- Scope: A local-first REST API with an embedded Chinese web console that mirrors the bounded CLI control surface, including QR-login with a container-display QR relay

## Outcome

1. `src/media_sync/interfaces/api.py` exposes `/api/v1` endpoints for health/readiness/settings, account CRUD and login status, blocking QR login as a tracked background operation, subscription CRUD with pause/resume/run-now, scheduler tick/run, pipeline run, scheduler Jobs, assets, Emby export and an operation registry; long-running operations run in bounded background threads and are polled through `/api/v1/operations`.
2. `media-sync serve` starts uvicorn with `MEDIA_SYNC_API_HOST/PORT` (default `127.0.0.1:8632`) and serves the embedded console at `/`.
3. The login child now mirrors the QR challenge image to `<account_root>/login-qr.png` (atomic 0o600 write, removed after the attempt) so a container deployment can display the QR in the web console while the headed browser runs on Xvfb; without the relay the QR stays in the browser exactly as before.
4. The console (`console.html`) is a no-build single page in Chinese covering accounts, QR login with live QR/status polling, subscriptions, tick/sync/pipeline runs with the double MediaCrawler gate, jobs, assets, operations and Emby export.
5. No authentication is added: the API binds loopback by default and documentation requires trusted-network publishing only.

## Acceptance boundaries

- No new credential surface, no remote crawling capability, and no change to any evidence rule; every endpoint reuses the CLI's service layer and redaction-safe payloads.
- The QR relay writes one image file inside the existing 0o700 account root and deletes it with the attempt; it never alters login outcomes.
- Offline API contract tests are added (`tests/unit/test_api_server.py`); the complete suite runs on Linux.

## Explicitly deferred

Docker packaging is execution 0041. Real QR login, real crawl and real download qualification happen only in the deployment execution with operator authorization.
