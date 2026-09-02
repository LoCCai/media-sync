**English** | [中文](progress.zh.md)

# Execution 0004 progress

- Status: Complete
- Started: 2026-08-30 04:40 +08:00
- Finished: 2026-08-30 06:22 +08:00

## Delivered

- Preserved both exact upstream pins and kept MediaCrawler as a separately installed, license-gated runtime; no upstream source was vendored or modified.
- Added typed `env:`, optional `keyring:` and confined `file:` secret references. A resolved signed creator reference retains `SecretValue` provenance through bridge preparation; ambiguous plain query URLs fail closed. Raw Cookie and signed creator-reference values are rejected or redacted at CLI, manifest, exception, event, JSON and SQLite sinks.
- Implemented exact-SHA checkout verification, account-isolated browser profiles, unique job/output roots, bounded watchdogs, an independent child runner and the Zhihu creator-input shim.
- Bound manifest schema v2 to account, subscription, job, crawl revision, intended mode, login method, item cap and author/creator-reference fingerprints. Ingest recomputes the subscription-authorized creator fingerprint, resolving signed references only in memory. The public child argument vector contains no secret.
- Added a sealed completion receipt written only after successful child exit, descendant cleanup and a quiet period. Receipt validation binds exact files, byte sizes and SHA-256 digests and rejects symlink/reparse, hardlink, descriptor-swap, missing, failed or truncated output. The parent refuses to seal output that echoes an exact known Cookie or signed creator reference, including JSON-escaped values.
- Made ingestion consume an immutable in-memory byte snapshot from that receipt. Any semantic quarantine or truncated JSONL tail rejects the complete forward ingest before a run or checkpoint is created.
- Added versioned fixtures and normalized author/content/ordered-asset contracts for `xhs`, `dy`, `ks`, `bili`, `wb`, `tieba` and `zhihu`, including Bilibili dynamics.
- Added migration `0002_checkpoint_fencing`, independent forward/backfill cursors, publish-time plus same-timestamp-ID watermarks and optimistic checkpoint revisions.
- Implemented bounded short transactions, oldest-first forward batches and atomic content/checkpoint/run publication. A sealed older crawl can recover only its missing records after an interleaved newer run without regressing the newer watermark or cursor.
- Added MediaCrawler doctor/dry-run, adapter-aware account creation, secret creator-reference subscription input and sealed-output ingest CLI paths.
- Proved command, receipt, normalization, checkpoint, recovery and secret-sink behavior with offline tests for all seven platform identifiers.

## Deferred truthfully

- Media downloading and Emby/Jellyfin export belong to execution 0005; this bridge intentionally leaves upstream binary downloading disabled.
- Scheduler/API/operations and release readiness remain later executions.
- No authorized account, browser challenge or platform endpoint was used. Every live qualification remains `NOT_RUN`.
