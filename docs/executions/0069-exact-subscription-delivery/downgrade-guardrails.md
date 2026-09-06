**English** | [中文](downgrade-guardrails.zh.md)

# Migration 0013 downgrade guardrails

Downgrading `0013_exact_subscription_delivery` is destructive schema maintenance, not an online rollback. It removes the `subscription_scan_progress` table and narrows the allowed Operation kinds.

## Required maintenance procedure

Before starting the downgrade:

1. Stop every media-sync API process.
2. Stop every scheduler, worker, and supervisor process. Confirm the supervisor cannot restart them during maintenance.
3. Confirm that no other process or operator can write to the database.
4. Back up the database and the associated media/state metadata. Verify that the backup can be restored.

Do not start the API or supervisor again until the downgrade has completed or failed and the database revision and integrity have been checked.

## SQLite

SQLite cannot hold one database lock across this migration's constraint-replacement autocommit boundaries. The downgrade therefore fails closed unless the operator supplies this explicit attestation:

```bash
alembic -x exclusive-maintenance=true downgrade 0012_library_output_policy
```

`exclusive-maintenance=true` is an operator attestation, not a lock. It does not stop the API, supervisor, scheduler, workers, or any other writer. Missing, false, or duplicate maintenance arguments are rejected.

## PostgreSQL

Before reading either history table, the downgrade acquires `ACCESS EXCLUSIVE` locks on `operations` and `subscription_scan_progress`. Lock acquisition can block while another transaction is active. A lock timeout or cancellation is not evidence that the database is safe to downgrade; stop the writers, investigate the competing session, and retry the complete maintenance procedure.

## Fail-closed checks

The downgrade is rejected if either condition is present:

- any `operations` row whose kind is `subscription-delivery`;
- any row in `subscription_scan_progress`, regardless of its state.

Offline SQL downgrade generation is unsupported because the history audit must run against the live database. Other database dialects are also unsupported for this downgrade.

Never delete history merely to force the downgrade without an approved retention and recovery plan. A later re-upgrade recreates schema only; it cannot recreate removed Operation or scan-progress history. Keep the backup until the downgraded deployment has been fully validated.
