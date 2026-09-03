**English** | [中文](progress.zh.md)

# Execution 0045 progress

- Status: Complete for the documentation scope
- Date: 2026-09-03

## Completed

- `docs/operations.md` / `.zh.md`: state inventory table, offline volume backup, online SQLite-stdlib consistent backup, restore procedure with automatic idempotent migration catch-up, partial-loss guidance (database-only, profile-only), and the upgrade procedure with rollback caveats.
- Every command cross-checked against the actual image: the online backup uses the container's Python stdlib (an initial draft cited a `db backup` CLI command that does not exist — caught in self-review and corrected before commit); `db init` idempotency and the git-ignored compose copy are consistent with execution 0041.

## Deviations and decisions

- No restore/upgrade drill was executed (operator direction: no local deployment verification); the procedures are recorded as ready-to-run and their first real execution belongs to the deployment host.

## Remaining

- Operator: execute one backup/restore drill and one upgrade on the deployment host and record outcomes (may be folded into execution 0047's checklist).
