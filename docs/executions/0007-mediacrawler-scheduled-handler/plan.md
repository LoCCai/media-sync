**English** | [中文](plan.zh.md)

# Execution 0007 plan

- Status: Planned — frozen before implementation
- Plan date: 2026-08-30
- Predecessor: Execution 0006 implementation commit `674e510`
- Network policy: offline fixtures and local helper processes only

## Amendment 2026-08-30

The frozen design below remains the original planning record. Security review refined failed-attempt cleanup into four explicit outcomes: `ABSENT`, `REMOVED`, `QUARANTINED` and `UNRESOLVED`. `QUARANTINED` means the exact attempt was atomically moved below ignored `.quarantine` but could not be scrubbed; it is a fixed terminal security result, not a successful whole-tree cleanup. `UNRESOLVED` means neither removal nor isolation was proven; it requires a durable redacted account block and hard fencing before future secret resolution, run attachment, bridge preparation or process spawn. Final whole-tree zero-match gates may cover only safe artifacts and must explicitly exclude quarantine-retention and unresolved-retention negative tests. This amendment narrows no process, database or operator-output safety requirement and does not authorize exposing retained paths.

## Frozen design

### Trust and authorization

- The scheduler worker/parent exclusively owns the database URL, worker identity, lease token and renewal authority. The MediaCrawler child receives none of them and cannot renew or finalize a Job. It receives only the confined manifest, the existing bounded private-input channel, and one-way liveness/cancellation control.
- License acknowledgement is an explicit, default-off operator authorization. Full-history acknowledgement, headless behavior and crawl delay are explicit subscription policy, not inferred from platform, account state or a previous interactive run.

### Policy and artifact protocol

- Freeze MediaCrawler subscription policy v1 as a closed object containing `schema_version`, optional `creator_input.secret_ref`, `allow_full_history`, bounded positive `request_delay_seconds` and `headless`. Only an opaque secret reference may be durable; raw Cookie and signed creator input remain memory-only.
- Manifest v3 separates the durable scheduler Job identity from an attempt-scoped execution identity and binds schedule revision, attempt, SyncRun, checkpoint, forward mode, upstream/license identity, login and creator fingerprints, item/watchdog policy and delay. Completion receipt v2 authenticates the corresponding v3 identity and exact output snapshot.
- Existing sealed manifest-v2/receipt-v1 evidence remains strict dual-read and byte-exact. It is never rewritten or promoted into scheduler ownership. New scheduled attempts write only v3/v2.

### Attempt identity and artifact lifecycle

- Every scheduler retry gets a unique confined execution root derived from the scheduler Job plus attempt/execution identity. A retry never reuses or recursively overwrites a predecessor root.
- Failed, unsealed, cancelled and lease-lost attempt-owned artifacts are safely removed after the process tree stops. Recovery validates ownership and exact manifest/receipt identity before using a sealed artifact; it never follows links or deletes a successor root.
- The private account browser profile is intentionally persistent and credential-bearing. It is isolated from attempt cleanup, excluded from false whole-tree zero-secret claims, and never shown by scheduler operator output.

### Process supervision

- All bridge preparation, checkout/runtime probes, secret-provider reads, child waits, receipt validation and normalization run off the event loop. The scheduler heartbeat remains parent-owned and uses independent short database transactions.
- Cancellation uses an explicit signal understood by the synchronous runner. The handler shields and joins runner completion, and does not return until child/grandchild termination, attempt cleanup and account-lock release are confirmed.
- Parent-death handling uses a one-way liveness/control channel plus an account-lock lifetime that cannot end while the child tree is still using the profile. POSIX orphaning and the Windows startup-to-Job/control handshake are implementation acceptance boundaries, not production assumptions.
- The child never receives the scheduler lease. A lost parent heartbeat causes the trusted parent/control boundary to cancel the child; an untrusted child cannot keep a lease alive.

### Application and database fencing

- Extract MediaCrawler validation, immutable snapshot normalization, SyncRun lifecycle and ingestion orchestration from the CLI into a reusable application service. Manual v2 ingestion delegates to the same validation core without gaining scheduler ownership.
- Before every SyncRun create/attach/status mutation and every content/checkpoint batch, the same database session obtains SQLite's writer slot and validates exact Job, worker, token, running status and unexpired lease. No external wait occurs inside that transaction.
- Cancel/reclaim terminalizes or detaches the currently linked non-terminal SyncRun using fixed codes. A stale owner may retain batches committed before ownership loss, but cannot commit another batch, receipt publication or Job result afterward.
- Scheduled execution is forward-only. Existing checkpoint recovery may fill missing records from an older sealed crawl but cannot publish continuation or regress a newer cursor/watermark.

### Status, delay and operator contract

- Freeze the process-to-scheduler mapping from `goal.md`. Authentication and human-interaction outcomes remain dormant in `waiting_auth`/`waiting_user` until explicit resume; raw process output and exception text never select a durable code.
- A faithful pinned-shape fixture exercises upstream `parse_cmd()` and configuration ordering. `request_delay_seconds` maps only to `config.CRAWLER_MAX_SLEEP_SEC`, while `MAX_CONCURRENCY_NUM=1`; this is not a per-request limiter or a seven-platform pagination guarantee.
- Scheduler CLI enablement is explicit and default-off. Account/subscription/Job projections continue to omit policy payloads, secret references, lease material, locators and filesystem roots.

### Migration and compatibility decision

- No database schema migration is planned initially. Existing `Subscription.policy`, `SyncRun.attempt`, `SyncRun.manifest`, `Job.run_id` and schedule payload revision can represent the required state; implementation adds exact-owner repository operations and exposes the existing schedule revision to handler context.
- Do not create an empty Alembic revision. If implementation proves relational attempt lineage cannot be represented safely, stop, revise this frozen plan first, then add a real migration with current/source/wheel upgrade and downgrade-preservation tests.
- The artifact protocol migration is mandatory: v3/v2 writers plus strict v2/v1 readers. Legacy files are never modified because their receipt hashes bind exact bytes.

## Implementation sequence

1. Add closed policy v1 and manifest-v3/receipt-v2 types, exact bounds, legacy dual-read and malformed/unknown-field tests.
2. Add a faithful pinned-upstream shape fixture and prove seven-platform configuration, Cookie non-disclosure, delay binding and binary-download disablement without invoking the real crawler.
3. Introduce attempt-scoped paths and safe owned-artifact cleanup; preserve sealed legacy evidence and prevent cross-attempt deletion.
4. Refactor the runner into a cancellable supervision boundary with confirmed tree termination, parent-death liveness, account-lock lifetime and Windows startup fencing.
5. Extract the MediaCrawler application orchestration and add same-session ownership guards to SyncRun and every ingestion/checkpoint transaction.
6. Add the MediaCrawler scheduler handler, conservative status mapping, explicit waiting recovery and registry/CLI enablement.
7. Add offline seven-platform, retry/restart, crash recovery, cancel/ABA and secret-sink acceptance without automatic download/export planning.
8. Close every P0/P1 finding, run the exact final gates, update all four execution documents and create one bilingual local implementation commit. Never push.

## Required offline tests

- Policy/manifest/receipt bounds, unknown fields, identifier mismatches, v2/v1 immutable recovery and v3/v2 strict writing.
- Same scheduler Job across attempts 1 and 2, distinct roots, stale-root fencing, sealed-output recovery and no successor deletion.
- Long fake child heartbeat with an independent SQLite writer proving no process wait holds a database transaction.
- Cancellation before spawn, while running, after child exit/before seal, after seal/before ingest and between ingestion batches.
- Lease loss, independent cancel, ABA reclaim and heartbeat failure proving tree join and zero post-loss writes.
- Helper-process hard kill on supported POSIX and Windows paths, including child/grandchild exit, profile-lock exclusion and bounded recovery.
- Known-secret echo, nonzero exit, timeout, each output limit, malformed receipt and unsafe tree cleanup with byte scans over returned attempt roots and SQLite/operator sinks.
- Seven platform identifiers using only fake process results and versioned JSONL fixtures; no browser, platform endpoint, real credential, CDN or Emby server.
- Full branch-aware suite, focused protocol/supervision/ownership/restart/sentinel gates, build, packaged resources, docs, pinned upstream, patch and ignored-runtime checks.

## Rollback and safety

- Automated tests may launch only repository-owned helper processes that perform no network or browser work. Hard-kill tests target exact temporary helper PIDs/process trees and verify those targets before termination.
- No test resolves a real secret reference. Generated sentinel values stay inside temporary, ignored roots and must be absent from retained safe artifacts.
- No upstream source is modified or vendored. The exact locked checkout is inspected read-only and its license boundary remains unchanged.
- No Git push, live platform request, CDN retrieval or Emby/Jellyfin operation is authorized by this plan.

## Deferred explicitly

- Scheduled backfill, automatic sync → download → export planning, signed-locator refresh and real binary retrieval.
- QR/challenge presentation UX beyond safe `waiting_user`, plus live login and creator-scan qualification.
- Per-request HTTP throttling, proxy pools, CAPTCHA/protection bypass and upstream-source modification.
- REST, resident production supervision, Docker/production packaging, public-network deployment and distributed HA/PostgreSQL.
