**English** | [中文](progress.zh.md)

# Execution 0007 progress

- Status: Implemented for the offline scope; acceptance remains `PARTIAL`
- Started: 2026-08-30 12:45 +08:00
- Implementation: IMPLEMENTED
- Verification: final automated gates PASS; AC6/AC13 remain `PARTIAL`
- Predecessor: Execution 0006 implementation commit `674e510`
- Network/account boundary: offline fixtures and repository-owned local helper processes only

## Delivered implementation

- Closed MediaCrawler subscription policy v1 now persists only `schema_version`, optional `creator_input.secret_ref`, explicit `allow_full_history`, positive `request_delay_seconds` bounded at 300, and `headless`. License acknowledgement remains a separate, explicit and default-off worker authorization. Raw Cookie and signed creator input remain non-durable.
- New artifacts are manifest v3 and completion receipt v2. Sealed legacy manifest v2/receipt v1 evidence remains strict dual-read, byte-exact and read-only through shared normalization/manual ingest; it is never resealed or rewritten. Scheduled restart recovery trusts v3 only.
- Retries reuse the durable scheduler Job UUID while deriving a unique attempt UUID and confined execution root. Stale attempts cannot seal, ingest, advance checkpoints or delete a successor root after cancel/reclaim/ABA.
- Bridge preparation, checkout/runtime probes, secret resolution, child wait, receipt validation and output normalization run off the event loop. The parent retains heartbeat/lease authority, and no process wait spans a SQLite transaction.
- Process supervision now has cooperative cancellation, process-tree termination/join, a one-way parent-liveness/control channel, Windows attach/start handshake, and account/profile locking. The child never receives the database URL, worker identity, lease token or renewal authority.
- Every SyncRun create/attach/status mutation and every ingestion/checkpoint transaction applies the exact owner/token/unexpired guard first in the same transaction. Batches committed before ownership loss may remain; no later batch may commit.
- Cleanup closes into exactly four states: `ABSENT`, `REMOVED`, `QUARANTINED`, or `UNRESOLVED`. `.quarantine` is an explicit restricted credential-bearing boundary under operator-controlled roots, tightened to `0700` on POSIX with an equivalent restrictive ACL expected elsewhere, and excluded from zero-secret claims. `UNRESOLVED` creates a fixed/redacted account block and fences secret resolution, run attachment, preparation and spawn. `.quarantine/`, `.cleanup-security-v1/` and account profile paths are ignored by Git even below a custom repository-local runtime root, but ignore rules are not an access-control boundary.
- The bounded CLI registry remains fail-closed by default. MediaCrawler execution requires both `--enable-mediacrawler` and per-run `--accept-mediacrawler-license`; missing license authorization and unsupported scheduled challenges use conservative waiting states without spawning.
- The standard `uv run pytest` collection initially failed because the new contract helpers required package imports. Adding `tests/__init__.py` and `tests/contract/__init__.py` closed that repository-local collection defect; the same focused module command then passed.

No relational schema revision was required; the migration work is the artifact-protocol v3/v2 writer plus immutable v2/v1 reader boundary.

## Acceptance status

| AC | Scope | Status | Evidence and remaining boundary |
| ---: | --- | --- | --- |
| 1 | Closed policy and authorization | `PASS` | Strict v1 keys/bounds, optional opaque creator ref, separate default-off license authorization |
| 2 | Manifest v3/receipt v2 | `PASS` | New writers bind durable Job plus attempt-specific identities |
| 3 | Legacy v2/v1 compatibility | `PASS` | Shared normalization/manual ingest is byte-exact and read-only; scheduled recovery rejects legacy |
| 4 | Retry/attempt isolation | `PASS` | Durable Job UUID reused; attempt UUID/root unique; stale roots fenced |
| 5 | Off-loop work and heartbeat | `PASS` | Real long local child plus concurrent heartbeat and independent SQLite writer |
| 6 | Deterministic cancellation barriers | `PARTIAL` | Pre-spawn/running cancellation, lease fencing, repeated runner cancellation and a real between-batch guard barrier pass. Both repeated-cancel paths prove join-before-unwind; the second batch is fenced while the first committed batch remains. Deterministic child-exit/pre-seal and post-seal/pre-ingest barriers remain missing. |
| 7 | Parent death and profile exclusion | `PASS` | Liveness/control handshake, complete-tree hard-stop and account/profile lock exercised with local helpers |
| 8 | Exact ownership fencing | `PASS` | Exact owner/token/unexpired guard precedes every SyncRun and ingestion/checkpoint transaction |
| 9 | Pinned upstream configuration | `PASS` | Faithful `parse_cmd()` shape preserves Cookie and sets `CRAWLER_MAX_SLEEP_SEC` plus `MAX_CONCURRENCY_NUM=1`; no per-request spacing claim |
| 10 | Closed status mapping | `PASS` | `ACCOUNT_BUSY → account_busy`, `TIMED_OUT → upstream_timeout`, `START_FAILED → upstream_unavailable`, `CONFIGURATION_FAILED → configuration_invalid`, `UPSTREAM_FAILED → temporary_upstream`, output/tree/receipt rejection → `output_security_failed`; cancellation/lease loss propagates fencing |
| 11 | Waiting recovery | `PASS` | License/challenge paths use `waiting_user`; missing/unavailable auth uses `waiting_auth`; explicit resume required |
| 12 | Seven-platform offline protocol | `PASS` | `xhs`, `dy`, `ks`, `bili`, `wb`, `tieba`, `zhihu` pass the real local fake-child retry/restart/replay chain |
| 13 | Complete failure secret-sink matrix | `PARTIAL` | Cleanup, redaction and sentinel coverage is substantial, but the full known-secret/nonzero/timeout/every-limit/receipt/cancel/lease-loss × retained-filesystem/SQLite/operator-sink cross-product is incomplete |
| 14 | Explicit redaction-safe CLI | `PASS` | Enablement/license are separate switches; payloads, refs, locators, lease material and roots are omitted |
| 15 | Final quality gate | `PASS` | Final full suite: 819 passed, 1 Windows-boundary skip, 79% branch-aware coverage; focused gate: 320 passed, 1 skip. Build/package/docs/upstream/patch/runtime gates and the retained safe-artifact sentinel also pass; exact evidence is in `verification.md`. |

## Seven-platform offline evidence

All seven platform identifiers pass the same real local protocol chain:

`subscribe → tick → manifest-v3 write/load → local fake child writes versioned JSONL → receipt-v2 write/read → guarded ingestion → retry/restart → idempotent replay`

This is offline protocol evidence only. It does not prove QR/Cookie/saved-session live login, real creator traffic, live CDN retrieval, real Emby/Jellyfin scan/playback, or bounded upstream pagination.

## Final automated evidence

- The repaired final tree passed 819 tests with one Windows-only POSIX-mode skip in 212.99 seconds and 79% branch-aware coverage. The focused execution 0007 gate passed 320 tests with the same single skip in 128.64 seconds.
- The retained safe-artifact gate passed 29 exact cases in 40.90 seconds below `.media-sync/verification/0007-closeout-sentinel-root`. Eight generated secret/signed-query sentinels had zero matches; logical Job authority was absent from 21 SQLite databases; 19 pytest `current` aliases were proven to target same-parent real directories inside the retained root; 279 files, 364 directories and 5,958,937 bytes remain ignored for audit.
- Dependency lock, Ruff, format, strict source mypy, build, packaged migrations, documentation links, both upstream pins, patch whitespace, custom-runtime ignore patterns and runtime-untracked checks passed. Exact commands and the deliberately excluded retention-negative tests are recorded in `verification.md`.

## Deferred truthfully

- Scheduled backfill, signed-locator refresh, real CDN retrieval and automatic sync → download → export planning are outside execution 0007.
- `CRAWLER_MAX_SLEEP_SEC` with `MAX_CONCURRENCY_NUM=1` is a proven configuration boundary, not evidence of per-request HTTP spacing. Proxy/CAPTCHA/protection-bypass work remains excluded.
- REST, resident supervision, Docker/production packaging, distributed HA/PostgreSQL and live Emby/Jellyfin operations remain later work.
