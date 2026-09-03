**English** | [中文](progress.zh.md)

# Execution 0040 progress

- Status: Implementation complete; runtime verification scoped to the Linux deployment host
- Date: 2026-09-03

## Completed

- `api.py` with the full `/api/v1` surface (health/ready/settings, accounts, login-status, login-qr.png, background login, subscriptions + pause/resume/run-now, scheduler tick/run, pipeline run, jobs, assets, emby export, operations), an exclusive-key operation registry and per-request database sessions.
- `console.html` Chinese single-page console with QR-login dialog polling the relayed image and operation state.
- `media-sync serve` command wiring uvicorn to `MEDIA_SYNC_API_HOST/PORT`.
- Login child QR relay: atomic `login-qr.png` inside the existing account root, deleted with the attempt; `DISPLAY`/`XAUTHORITY` were already allowlisted for the child environment, so no protocol change was needed.
- `tests/unit/test_api_server.py` covering health/console, account lifecycle and login gates, subscription/scheduler surface and background-operation gates.

## Deviations and decisions

- The account-create endpoint intentionally hardcodes the `mediacrawler` adapter (the only real adapter) and validates against `_MEDIACRAWLER_LOGIN_METHODS` exactly like the CLI's mediacrawler branch.
- Static gates only on this workstation (operator direction); `pytest --collect-only` confirmed all touched files import and collect (385 tests).

## Remaining

- Execute the API tests and the complete suite on Linux during deployment verification.
