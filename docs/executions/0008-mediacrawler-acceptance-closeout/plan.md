**English** | [中文](plan.zh.md)

# Execution 0008 plan

- Status: Planned — frozen before implementation
- Plan date: 2026-08-30
- Predecessor: Execution 0007 implementation commit `d071618`
- Network policy: offline fixtures and repository-owned local helper processes only

## Frozen design

### Closed evidence model

- Execution 0008 is an acceptance closeout, not a feature bundle. It closes only execution 0007 AC6 and AC13, while preserving all existing live `NOT_RUN` and deferred implementation boundaries.
- The required failure rows are a closed eleven-value enum in the tests: `known_secret_echo`, `nonzero_exit`, `timeout`, `output_bytes`, `output_items`, `output_files`, `output_line_bytes`, `output_tree`, `receipt_rejected`, `cancellation` and `lease_loss`.
- Each row owns one generated runtime-only sentinel and records three explicit assertions: filesystem, SQLite and operator. A separate completeness test compares the produced cell keys with the exact Cartesian product; sampling or implied coverage is not accepted.

### Deterministic cancellation barriers

- The child-exit/pre-seal contract uses events or a pipe around the existing final inspection/receipt boundary. The test observes a real helper exit and complete tree join, blocks before receipt publication, signals cancellation, and releases the barrier. No timing-only sleep establishes the verdict.
- The runner must check cancellation after final output inspection and immediately before receipt publication. If cancelled, it returns the fixed cancelled result; its outer cleanup secures the exact attempt before releasing the account/profile lock.
- The post-seal/pre-ingest contract blocks the injected normalizer after a valid receipt is visible. One or repeated task cancellation must signal/record cancellation, join the protected offloaded task, secure the attempt and unwind without `_set_ingesting` or ingestion writes.

### Failure matrix and sinks

- Use a repository-owned helper and bounded watchdog settings to produce real nonzero, timeout and every output-limit verdict. Receipt and known-secret rejection use the real parent seal/validation path. Cancellation and lease loss cross the real scheduler handler and exact ownership boundary.
- A row must never place its sentinel in a pytest parameter ID, assertion message, JUnit property or planned operator string. The sentinel is generated after collection and is scanned only by value.
- Filesystem evidence scans the exact returned/retained safe roots, including hidden and ignored files and SQLite sidecars. Ordinary failure roots must be absent or removed. Deliberate quarantine/unresolved/profile cases live in a separately enumerated negative set.
- SQLite evidence performs both exact byte scans of retained database files and logical inspection of every text/JSON value plus Job/SyncRun authority. A cancellation race may retain already committed pre-loss state, but no stale-owner mutation or terminal success is permitted afterward.
- Operator evidence covers serialized scheduler results, CLI/captured stdout and stderr, and exception/result `str`/`repr`. It rejects the sentinel, lease owner/token, local roots, quarantine locations and raw cleanup exceptions.

### Credential-bearing negative boundaries

- Keep the execution 0007 four-state cleanup contract unchanged. `ABSENT` and `REMOVED` support safe-tree zero-match evidence. `QUARANTINED` may retain deliberate bytes only below ignored restricted storage. `UNRESOLVED` attempts to record fixed redacted markers and hard-fences the account even if marker persistence itself fails.
- The retained-artifact allowlist names every excluded negative test exactly. It never deletes quarantine/unresolved evidence merely to satisfy a scan, and it never exposes a retained path in operator output.

### Recovery, compatibility and next execution

- Do not rewrite execution 0007 records. Execution 0008 progress and verification will state whether the successor gate closes its two partial criteria.
- Legacy manifest v2/receipt v1 remains immutable, byte-exact and accepted only by shared normalization/manual ingest. Scheduled restart/reclaim continues to trust v3 only.
- Successful sealed v3 output remains a crash-recovery artifact in this execution. Because it may contain an unknown signed query, it is explicitly credential-bearing. Execution 0009 must implement terminal cleanup/isolation as part of signed refresh; execution 0008 does not silently broaden its zero-match claim to that root.

### Schema and migration decision

- No Alembic revision is planned. The closeout should add deterministic tests and, only if needed, minimal runner/handler race repairs. If durable relational state becomes necessary, implementation stops and this frozen plan is amended before a real migration is added.

## Implementation sequence

1. Add the child-exit/pre-seal red test, then add the smallest cancellation check needed to make it pass.
2. Add the repeated post-seal/pre-ingest cancellation test and repair join/cleanup only if the current handler fails it.
3. Build the eleven-row, three-sink security matrix and completeness meta-test using generated sentinels.
4. Re-run existing quarantine/unresolved/profile, parent-death, retry/restart, v3/v2 and immutable v2/v1 suites to prevent boundary regression.
5. Run the complete quality gates and a fresh retained safe-artifact sentinel below `.media-sync/verification/0008-closeout-sentinel-root`.
6. Update the execution records and project indexes with exact results, then create one bilingual local implementation commit without pushing.

## Required offline tests

- Exact child exit/tree join → final inspect → cancel → no receipt barrier.
- Exact sealed receipt → blocking normalization → repeated cancel → joined cleanup → zero ingest barrier.
- Eleven failure rows, each with filesystem + SQLite + operator sink assertions, plus 33-cell equality.
- Fixed status mapping, no post-cancel/lease-loss writes, and no stale success finalization.
- Four cleanup states, marker persistence failure, quarantined fixed output, profile isolation and same-root alias checks.
- Existing seven-platform offline protocol, legacy read compatibility and package/migration tests.

## Retained sentinel rules

- `.media-sync/verification/0008-closeout-sentinel-root` must not exist before its one authoritative run and must never be deleted or recreated afterward. The 0007 sentinel root is read-only evidence and is not reused.
- The allowlist includes only safe-artifact tests. Every retention-negative function is listed explicitly; no broad module entry or fragile negative `-k` expression is accepted.
- Scan hidden/ignored real files, SQLite/WAL/SHM, pytest/JUnit and operator output. Windows pytest `current` aliases must resolve to existing same-parent targets inside the retained root, whose real targets are scanned independently.
- Record exact case count, 33 matrix cells, sentinel count, SQLite count, aliases, files, directories, bytes and elapsed time.

## Rollback and safety

- No upstream source is modified or vendored. No live credential, browser profile, account, platform/CDN endpoint, media server or remote Git operation is authorized.
- Helper termination targets only exact repository-created process identities. Destructive cleanup remains confined to validated attempt roots and never follows links.
- Existing 0007 sentinel evidence is never removed. New temporary and retained roots stay ignored and untracked.

## Deferred explicitly

- Signed-locator refresh with implemented successful/recovery-attempt terminal cleanup/isolation: execution 0009.
- Durable automatic `sync → download → Emby` DAG: execution 0010.
- Live seven-platform login/creator traffic/CDN qualification and real Emby/Jellyfin scan/playback.
- Platform derivatives, per-request HTTP spacing, bounded live pagination, QR/challenge presentation UX, REST, resident supervision, Docker, public deployment and HA/PostgreSQL.
