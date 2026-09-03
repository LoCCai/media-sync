**English** | [中文](plan.zh.md)

# Execution 0044 plan

- Status: Planned
- Date: 2026-09-03

## Delivery sequence (when implemented)

1. Detail endpoints (subscription, scheduler Job) projecting existing repository/scheduler data with the redaction rules already used by the CLI payloads.
2. Asset re-download endpoint composing the existing reset + enqueue path; contract tests prove one reset produces exactly one pipeline coordinator.
3. Console additions (detail drawer, re-download, operations page) against the same endpoints.
4. Extend `tests/unit/test_api_server.py`; run the full gate family on the Linux deployment host and record exact numbers before closeout.

## Risks and rollback

- Additive endpoints only; rollback deletes the new routes and console sections without touching existing behavior.
