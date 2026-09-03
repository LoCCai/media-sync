**English** | [中文](goal.zh.md)

# Execution 0044 goal

- Status: Planned — start record committed for review before implementation
- Date: 2026-09-03
- Predecessor: Execution 0042 (completion archive)
- Scope: Operations hardening of the execution 0040 web console and REST API — read-only subscription/account detail, scheduler Job detail with per-job operations, asset re-download triggering, and a consolidated operations view — closing the remaining gap against bili-sync-up's task-administration workflow

## Outcome (target)

1. `GET /api/v1/subscriptions/{id}` detail (schedules, recent runs, recent jobs) and `GET /api/v1/scheduler/jobs/{id}` detail with redaction-safe payload projection.
2. `POST /api/v1/assets/{id}/redownload` that resets a verified asset through the existing fenced CAS path and enqueues the pipeline coordinator — reusing, not duplicating, the execution 0005 recovery semantics.
3. Console: job detail drawer, per-asset state with re-download button, and one operations page combining operations history, lane status and scheduler controls.
4. Every endpoint stays a thin projection over existing services; no new authority, credential surface or schema.

## Acceptance boundaries

- Read-only or recovery-path operations only; no delete/cleanup endpoints in this execution.
- Offline API tests extend `tests/unit/test_api_server.py`; the full suite runs on the Linux deployment host; no local deployment verification.
- Live rows remain `NOT_RUN`.

## Explicitly deferred

Authentication/multi-user, remote access hardening, config editing from the UI.
