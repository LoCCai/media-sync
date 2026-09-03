**English** | [中文](plan.zh.md)

# Execution 0044 plan

- Status: Closed as absorbed — the minimal set was implemented by execution 0048; semantics fixes and lifecycle tests landed in execution 0049
- Date: 2026-09-03

## Delivery sequence (when implemented)

1. Detail endpoints (subscription, scheduler Job) projecting existing repository/scheduler data with the redaction rules already used by the CLI payloads. (Rescoped 0048: this plus items 2/3/4 are the whole slice.)
2. Asset download endpoint running the existing AssetDownloadService as a background operation for one asset — the exact service the CLI asset download command drives; tests cover the operation lifecycle and gate failures.
3. Console additions (detail drawer, re-download, operations page) against the same endpoints.
4. Extend `tests/unit/test_api_server.py`; run the full gate family on the Linux deployment host and record exact numbers before closeout.

## Risks and rollback

- Additive endpoints only; rollback deletes the new routes and console sections without touching existing behavior.
