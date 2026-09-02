**English** | [中文](progress.zh.md)

# Execution 0006 progress

- Status: Complete for the offline/Fake scope; final root gate passed
- Plan commit: `c8c4e54`
- Implementation date: 2026-08-30
- Network boundary: offline fixtures, mock transports and local SQLite/filesystems only

## Delivered

- Added migration `0004_scheduler_control_plane`: subscription schedule revisions; Job subscription/account/platform/time scope; claim/scope indexes; one-active-cycle partial uniqueness; and persistent platform/account lanes. Its downgrade removes only scheduler state and preserves execution 0005 Job evidence and asset download links across SQLite batch table replacement.

- Implemented bounded null-first due materialization, schedule-revision CAS, one durable cycle identity, fixed-delay completion and no catch-up storm. Concurrent independent SQLite ticks create at most one active cycle per subscription.

- Corrected the generic Job repository so reclaim and retry requeue predicates are type-scoped before mutation. A `sync.subscription` worker neither changes nor claims `asset_download` or `export.emby` Jobs.

- Added the closed retry/circuit policy: bounded exponential equal jitter, finite `Retry-After` lower bounds, maximum attempts, fixed failure classifications, persistent closed/open/half-open state and one exact half-open probe.

- Added global capacity plus persistent platform/account concurrency and minimum-start-interval lanes. Claiming scans past blocked heads; lane policy changes and circuit resets use revision CAS. These claims cover scheduler launch throttling only, not each upstream HTTP request.

- Added explicit pause/resume/run-now controls, dormant `waiting_auth`/`waiting_user`, safe Job resume/cancel, bounded type-scoped reclaim, exact heartbeat/ABA fencing, and redaction-safe Job/lane projections.

- Added a closed handler registry and deterministic Fake handler. The worker uses short claim/start/finalize transactions, concurrent exact-token heartbeat, cooperative cancellation, and same-session ownership guards before handler persistence. Adapter awaits hold no SQLite writer transaction.

- Closed hostile result paths: raw handler exceptions, malformed results, invalid RNG/time values, unknown adapter/domain error codes, and unknown or cross-subscription SyncRun IDs become fixed codes. SQLite, Job/lane DTOs and scheduler operator output retain no untrusted handler secret/path text; valid archive/output paths remain intentionally stored by the existing asset/export domain.

- Added CLI controls for `subscription pause|resume|run-now`, `scheduler tick|run`, `scheduler job list|resume|cancel`, and `scheduler lane list|set|reset`. Every batch/capacity/lease/policy input is bounded and output uses explicit allowlists without payloads, lease owners/tokens, credentials, locators or filesystem roots.

- Added a restart-safe offline acceptance flow: subscribe → tick → scheduled Fake sync → explicit secure mock download → explicit Emby export → reconstruct services → rerun. It proves no duplicate schedule cycle, archive identity or publication identity, while making no automatic downstream DAG claim.

## Review corrections

- A final P1 audit found a long SQLite transaction around Fake adapter awaits, missing worker heartbeat/cancel observation, open post-start exception paths, unvalidated result Run IDs and hostile error codes reaching SyncRun sinks. All findings were fixed before the final gate, with independent writer/cancel/reclaim, byte-sentinel and failure-injection regressions.

- SQLite scheduler decisions acquire the writer slot before read/decide/CAS. A handler persistence guard performs its exact owner/token/expiry no-op update in the same transaction as the application mutation, removing the cancellation time-of-check/time-of-use gap.

## Deferred truthfully

- MediaCrawler remains on the execution 0004 manual run/ingest boundary. Its scheduled handler, manifest v3 request-delay binding, long child-process heartbeat/cancellation and signed-locator refresh are not implemented by 0006.

- Automatic sync → download → export planning, REST, resident supervision, Docker/production packaging, distributed HA/PostgreSQL locking and public-network deployment remain later executions.

- Seven-platform live QR/Cookie/saved-session login/scheduling, real CDN download and actual Emby/Jellyfin scan/playback remain `NOT_RUN`; no credential or live service was authorized.

## Closeout result

- The final root gate passed 686 tests in 152.40 seconds with 80% branch-aware coverage. All focused scheduler, migration, restart, secret-sink, CLI, build, documentation, pinned-upstream, patch and runtime-artifact checks passed.

- The final clean retained-artifact gate passed 40 tests and scanned 58 files under `.media-sync/verification/0006-closeout-clean-sentinel-root`; all six exact secret/query/path patterns returned `rg` exit 1 (successful zero-match). No real account, platform/CDN endpoint or Emby/Jellyfin service was used.
