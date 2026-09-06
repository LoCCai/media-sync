**English** | [中文](progress.zh.md)

# Progress

## Implemented

- Migration0012 adds a revisioned shared policy and immutable author-root bindings. GET/preview do not initialize policy or create directories. CAS saves and first binding share database locking.
- Fresh libraries use root/platform/author; published libraries retain flat layout. Persisted old scope conflicting with the environment root blocks bootstrap instead of guessing. Restore the original environment root first. Bound/published platforms reject root changes with409; unused platforms remain editable.
- Settings offers a common root, seven overrides, current/preview paths and protected-platform labels. Edits invalidate preview; conflicts preserve drafts without replay. Native absolute paths only; private/system/overlapping roots and linked ancestors are rejected.
- API, CLI, existing/new independent workers and maintenance publication share the policy. Root is bound before downloading. Private archive/credentials/jobs stay unchanged; normal publication needs no media-server connection.
- Library inspection selects an exporter per author with stable, scope-isolated paging. Optional server linkage keeps its old fixed mapping and rejects a mismatched output scope.

## Review corrections

Independent review reproduced missing OS-directory rejection and an old-scope/new-environment bootstrap mismatch; both are addressed. Old test-constructor seams, migration-head/21-table expectations, API typing and formatting were corrected, with failed initial runs retained in verification.

## Added user request: QR failures and next-version log center

Following computer-use guidance, read-only browser inspection visited accounts and one WB operation. No preflight/login/capture/download was triggered. On2026-09-06, saved states show Bili/XHS/Zhihu authenticated and DY/KS/Tieba/WB upstream browser timeouts. WB operation prefix80789097 ran12:15:18–12:16:01 (43seconds), runner_status=upstream_browser_timeout, with only authenticating events and no navigation/click/QR/confirmation stage.

Source inspection confirms child stderr and upstream fd1/2 are discarded, and the result protocol retains only status. The current support bundle is aggregate diagnostics, not a log archive. Existing data cannot reconstruct the exact failed step or prove a credential/network cause. [Next delivery](next-delivery.md) prioritizes retained logs and login-stage diagnostics; error classification is not live login acceptance.

## Remaining boundaries

The log center is not implemented and the remaining live QR failures are not fixed. No deployment, supervisor restart or credential changes. Explicit media migration, durable history-to-incremental completion and exact-subscription real download acceptance remain required. Path preflight does not prove mount writability or eliminate every ancestor-swap TOCTOU risk.

Plan frozen before application edits. Audit confirms output Jobs bind a hashed publication scope, but legacy ExportRecord paths alone cannot reconstruct an absolute root. New configuration must retain legacy roots and protect existing publications. Private archive paths do not need to change.
