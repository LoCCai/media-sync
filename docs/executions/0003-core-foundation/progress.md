**English** | [中文](progress.zh.md)

# Execution 0003 progress

- Status: Complete
- Started: 2026-08-30 03:50 +08:00
- Completed: 2026-08-30 04:26 +08:00

## Delivered

- Added an installable Python 3.11 package, locked `uv` environment, environment-based settings, and secret-free diagnostics.
- Defined immutable domain snapshots, the exact seven-platform vocabulary, adapter ports, classified errors, and validated auth/run/job/asset state machines.
- Added the deterministic Fake adapter with QR/Cookie/saved-session capability truth, repeated IDs, multi-page results, and same-timestamp fixtures.
- Added a bounded synchronization service that rejects unsupported platform/login combinations before a run is created, redacts raw failures, and preserves safe retry timing.
- Implemented ten SQLAlchemy tables and package-owned Alembic migrations for accounts, login sessions, authors, subscriptions, content, assets, sync runs/events, jobs, and export records.
- Enabled SQLite foreign keys, WAL, busy timeout, and explicit transaction begin semantics so nested savepoints still roll back with their outer transaction on Python 3.11.
- Implemented atomic SQLite upserts, monotonic publish-watermark boundary IDs, compare-and-swap run transitions, atomic event sequencing, and lease fencing tokens that reject expired or ABA-stale workers.
- Connected `SyncService` to SQLAlchemy without internal commits. Two fixture passes leave one author, four unique contents and four unique assets while preserving runs, events, counters, cursor state, publish watermark and boundary IDs.
- Added packaged migration tests that build and unpack the wheel, then initialize a database using only migration resources inside the wheel.
- Added secret-safe CLI commands for database initialization, account add/list, subscription add/list and deterministic sync run. Unsupported login methods and inline Cookie-like values are rejected before persistence.
- Added a read-only `db status` command that verifies connectivity, the current Alembic revision and all ten required tables without creating a missing database or exposing its URL.
- Marked secret-adjacent dataclass fields such as credential references, cursors, raw envelopes and signed asset URLs as excluded from `repr`.

## Review fixes

- Fixed expired-lease completion and same-worker ABA completion by checking both expiry and a per-claim token.
- Fixed SQLite legacy savepoint behavior that could otherwise survive an outer rollback.
- Removed read-before-write paths that produced `SQLITE_BUSY_SNAPSHOT` in concurrent SQLite upserts and status updates.
- Made Alembic read the configured runtime URL and made `db init` migrate rather than calling `metadata.create_all`.
- Prevented database URLs, credential references and raw domain/adapter exception text from appearing in CLI output.

## Deferred by design

- This execution uses only the network-free Fake adapter. MediaCrawler process integration, real secret resolution, binary downloads and Emby export belong to executions 0004-0005.
- The foundation persists continuation cursor, publish watermark and same-timestamp boundary IDs, but the Fake CLI deliberately does not claim bounded upstream incrementality. Consuming those checkpoints through overlap/known-ID stop rules belongs to the bridge milestone.
- Live login/content/media qualification remains `NOT_RUN`; no account, browser or platform endpoint was used.
