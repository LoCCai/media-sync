**English** | [中文](progress.zh.md)

# Progress: durable Bilibili uploads now reconcile into incremental delivery

Status: the local implementation is complete in `9c81c4b`. Docker/Linux deployment, live Bilibili access and host-directory acceptance remain pending.

## Outcome

The existing exact-subscription path now has a delivery-qualified Bilibili lifecycle:

```text
adopted Bilibili Account profile
  -> one bounded uploads Run (at most 30 observed Contents)
  -> exact Run-content receipt
  -> download/archive and publication per complete Content
  -> paced continuation while history remains
  -> source-end evidence
  -> bounded head reconciliation
  -> periodic overlapping incremental head checks
```

The service does not call an Emby/Jellyfin server. Its durable output remains the configured local library tree and NFO/sidecar files.

## Implemented

1. **Delivery-qualified state.** Migration `0014_bili_delivery_baseline` adds `bili_subscription_progress` with closed `backfill`, `reconciling`, `incremental` and `blocked` phases. Evidence is bound to the exact Subscription, Account authentication revision, author fingerprint, uploads scope, delivery-relevant policy fingerprint and locked MediaCrawler SHA.
2. **Exact bounded source batches.** `sync_run_contents` records the ordered Content identities and asset counts observed by one successful Run. The database and ingestion path enforce the existing 30-item ceiling, so the pipeline no longer has to infer a source batch from the author's accumulated snapshot.
3. **Durable history-to-incremental transition.** A delivered history unit with source-end evidence resets a bounded head lane. Only a stable delivered head reconciliation publishes `baseline_snapshot_complete` and enters `incremental`; pagination drift or incompatible cursor evidence returns to a conservative path.
4. **Safe invalidation and recovery.** Authentication, identity, scope, policy or upstream-lock changes cannot reuse an incompatible baseline. Where the exact source identity and cursor remain valid, delivered history is retained but must be reconciled again. Terminal coordinator failures block automatic materialization; explicit exact execution can resume the same safe generation.
5. **Pacing after delivery, not discovery alone.** A scan Run does not advance the baseline. The next 300-second continuation is published only in the same transaction as a closed successful pipeline receipt. Ordinary interval scheduling resumes after a stable incremental head unit. Retryable failed backlog also retains continuation pacing.
6. **Per-complete-Content delivery.** The pipeline isolates download failures by Content. A multipart Content remains unpublished if any required member is incomplete, while unrelated complete Contents may still publish. Existing predecessor Content is carried forward through the verified manifest instead of being dropped by a partial source batch.
7. **Exact partial receipts.** Receipt schema v2 separately reports source-Run and retry-backlog observed, delivered and failed Content counts, retryable/terminal totals and fixed failure codes. `partial` covers both the current source batch and retry backlog; legacy author-snapshot receipts remain readable as schema v1.
8. **Idempotent real file path.** Controlled integration fixtures run the actual secure downloader, SHA-256 archive and Emby-compatible exporter. One later upload is downloaded and published once; an unchanged zero-work Run reuses the export Job and leaves archive/library bytes and mtimes unchanged.
9. **Operator projection.** The subscription detail API and Web page expose only closed, public-safe phase, batch, source-end, reconciliation, next-eligible and failed-Content evidence. Raw cursors, host paths, Cookies, signed locators and upstream responses remain hidden.

## Review corrections

The complete regression gate exposed an existing login-runner deadline bug: a child could close stdout without exiting, causing the parent to return `RESULT_INVALID` immediately instead of enforcing the requested timeout. The parent now treats only a complete frame or a truly exited child as completion; EOF from a still-running child remains bounded by cancellation/deadline. The focused case and the complete 68-test login contract pass.

Later complete runs found three more deterministic gate gaps. The generic Alembic schema contract omitted the two 0014 tables. CPython's Windows path `stat` and handle `fstat` exposed unequal `st_ctime_ns` values for the same NTFS file, intermittently rejecting valid immutable previews; named-path comparison now uses identity, size and mtime while the owned descriptor still fences its full ctime snapshot. Finally, Kuaishou JSON nesting relied on an interpreter `RecursionError`; a lexical 64-level bound now rejects hostile depth independently of Python's decoder implementation.

## Remaining live work

- Pull and build the published revision on the Linux host.
- Adopt a real Bilibili session and run the explicitly authorized UID `252671524` canary.
- Record real platform requests, downloaded CDN bytes, archive hashes, final host library directory/NFO and a later unchanged/new-upload incremental cycle.
- Verify the deployed supervisor restart and scheduling behavior.

All four steps are `NOT_RUN`; deterministic fixtures do not qualify them.
