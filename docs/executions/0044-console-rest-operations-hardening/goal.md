**English** | [中文](goal.zh.md)

# Execution 0044 goal

- Status: Rescoped by execution 0048 to the minimum operations-recovery slice; UI polish is deferred to 0.2
- Date: 2026-09-03 (rescoped)
- Predecessor: Execution 0042 (completion archive)
- Scope: The operations endpoints an operator actually needs during live qualification — subscription detail with recent jobs, scheduler Job detail, and asset re-download through the existing download service — plus the minimal console affordances to drive them

## Outcome

1. `GET /api/v1/subscriptions/{id}`: schedule state, recent sync runs (status/counters/dates) and recent scheduler Jobs, projected with the CLI's redaction rules.
2. `GET /api/v1/scheduler/jobs/{id}`: one redaction-safe Job projection.
3. `POST /api/v1/assets/{id}/download`: runs the existing `AssetDownloadService` for one asset as a tracked background operation (the same service the CLI `asset download` command uses), honoring the pipeline capability gates; no reset/CAS shortcut, no state mutation beyond the service's own fenced lifecycle.
4. Console: subscription detail drawer (schedule + recent jobs + recent runs) and a per-asset re-download button wired to the new endpoints.
5. Offline API tests extend `tests/unit/test_api_server.py`; no new authority, credential surface or schema.

## Acceptance boundaries

- Read-only detail endpoints plus one service-backed download trigger; no delete/cleanup, no lane editing from the UI.
- Deferred to 0.2: consolidated operations dashboard, job-control buttons (resume/cancel) in the UI, failure-diagnostics views beyond payload projections.
- Full suite runs wherever the 0048 calibration ran; live rows stay `NOT_RUN`.

## Explicitly deferred

Everything listed in the acceptance boundaries plus authentication/multi-user/remote hardening.
