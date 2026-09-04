**English** | [中文](progress.zh.md)

# Execution 0054 Phase B progress

- Status: Planning baseline recorded; implementation not started
- Date: 2026-09-05
- Baseline: `4945df1`
- Database revision: none planned

## Baseline

Phase B starts from the published Execution 0054-A closeout at `4945df1`. Before this planning package, the worktree had no tracked changes and contained only the pre-existing untracked `.mimosa/` directory. That directory is outside project scope and remains excluded.

The baseline already implements the managed-tree inspector, immutable server profile, hardened connector, accepted-only targeted refresh, two media-server Operation kinds, qualification schema v1, and Library/Settings/Jobs integration. Scan completion polling and provider/path item lookup remain explicitly `NOT_IMPLEMENTED` at this boundary.

## Frozen design

The Phase-B review checked the official Emby 4.8.10/4.9.5 and Jellyfin 10.10.7/10.11.11 API descriptions plus Jellyfin's queued item-refresh controller. No common durable task identity is returned by targeted refresh. Scheduled Tasks, WebSocket messages, server idle state, timestamps, and Etag changes cannot correlate a provider task to the request.

The frozen implementable claim is therefore `post_refresh_item_observation`: a complete absent baseline, one accepted refresh, and two consecutive observations of the same unique provider/path item. `provider_task_completion` stays unimplemented with an explicit provider-API limitation.

The design also freezes:

- provider-specific lookup and refresh query templates;
- full local provider/path equality and uniqueness;
- incomplete-versus-not-found truth;
- per-response, per-pass, and per-Operation budgets;
- all-answer DNS policy, pinning, Host/SNI, no proxy/redirect/next-link, and header-only credential flow;
- query-log constantization and raw-selector non-persistence;
- distinct acceptance-unknown and completion-unknown states;
- pre-dispatch failure for an already-matched author baseline, with legacy `{}` retained for acceptance-only refresh;
- targetless legacy `{}` Operations versus `target_type=author` observation Operations, with the publication Job atomically attached as a `related` subject before worker start;
- phase-aware cancellation, final CAS, and conservative restart handling, with accepted and observed running checkpoints stored in the existing `result_summary` and projected through the reused `operation_phase_changed` Event;
- database exclusivity only for durable probe and scan Operations; synchronous direct lookup is an independent snapshot bounded only by the connector's process-local gate;
- no new Operation kind, Event kind, or database migration because revision `0007` already provides the required target, subject, result, and Event vocabulary.

## Compatibility decision

The existing `POST /api/v1/media-server/scan` request `{}` remains acceptance-only and targetless and keeps the exact 0054-A safe result and `{profile_fingerprint}` request-fingerprint parameters. The same route gains a strict author object for observation mode. A matched baseline ends that mode before POST; acceptance-only refresh remains an explicit legacy request. This avoids silently changing old clients, idempotency replays, existing Operation rows, or the top-level manual refresh action.

The author mode uses the same `media-server-scan` kind with `target_type=author` and `target_id=<author UUID>`. The existing target relation links that author, and the publication Job is attached as a `related` subject before worker start. The target plus `{profile_fingerprint, mode=post_refresh_item_observation, publication_fingerprint}` form its request fingerprint without redefining historical targetless rows. The synchronous author lookup creates no Operation, has no database-exclusive key or cross-process correlation, and cannot itself serve as correlated scan evidence.

No migration is needed: the current `0007` schema already permits the author target, author/Job subjects and target/related roles, the `result_summary` checkpoint field, and the `operation_phase_changed` Event code. Phase B adds no database kind, state, Event kind, subject type, role, table, column, or constraint value.

## Work status

Completed in this planning slice:

1. Read-only review of current connector, Operation, payload, publication, API, Web, migration, and qualification boundaries.
2. Route-level comparison of the four supported Emby/Jellyfin versions.
3. Frozen error taxonomy, success evidence, compatibility strategy, security budgets, API/Web contract, restart policy, and acceptance matrix.
4. Created this bilingual `phase-b/` goal, plan, progress, and verification package.

No production source, test, migration, deployment configuration, or parent 0054 document has been changed. The running accepted/observed checkpoint described by this plan requires a future repository/coordinator extension and is not represented as an existing capability; it will reuse `result_summary` and `operation_phase_changed`. No implementation test result is claimed.

## Qualification state

At baseline:

- `connection_probe`, `library_discovery`, and `targeted_scan_acceptance` are implemented but human `NOT_RUN`.
- `item_lookup` and `post_refresh_item_observation` are not yet implemented; they have no human status.
- `provider_task_completion`, `playback_evidence`, and `automatic_post_export_scan` remain `NOT_IMPLEMENTED`.

After implementation, only the first two Phase-B capabilities move to implementation `IMPLEMENTED`; their human status remains `NOT_RUN` until exercised against an authorized real server.

## Workspace discipline

This planning task changes only eight Markdown files below `docs/executions/0054-media-library-server-integration/phase-b/`. It does not inspect, add, modify, delete, stage, commit, or push `.mimosa/`. Runtime data, secrets, databases, archives, export/job trees, build output, caches, and reports remain excluded.

After implementation, rollback to an old binary must not occur while an author-observation Operation is active. Operators must wait until every such row is terminal or deploy a binary with compatible reconciliation; audit rows and accepted/observed evidence must never be deleted to make rollback appear compatible.

## Next checkpoint

The next implementation checkpoint begins only after review accepts these contracts. Delivery starts with the publication target resolver and read-only lookup; mutation orchestration follows only after the selector, completeness, budget, and log boundaries have focused tests. Each later progress update must record exact commands and results without upgrading mocked evidence to live qualification.
