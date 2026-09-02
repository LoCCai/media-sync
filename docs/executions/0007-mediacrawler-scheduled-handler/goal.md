**English** | [中文](goal.zh.md)

# Execution 0007 goal

- Status: Implemented for the offline scope; acceptance remains `PARTIAL`
- Started: 2026-08-30 12:45 +08:00
- Predecessor: Execution 0006 implementation commit `674e510`
- Network boundary: offline fixtures and local helper processes only

## Amendment 2026-08-30

Acceptance criterion 13 below is preserved verbatim as the committed planning baseline. Implementation review proved that its whole-runtime zero-secret wording is not attainable in the deliberate scrub-denied negative case without either losing the security evidence or making a false claim. The accepted implementation contract is therefore refined as follows: ordinary active attempt roots must be removed; if atomic isolation succeeds but no-follow scrubbing fails, unsafe evidence may remain only below ignored `.quarantine`; if neither removal nor isolation can be proven, the handler must hard-fence the account and write only durable redacted account/incident markers outside the attempt root. Account browser profiles and deliberate quarantine/unresolved evidence are credential-bearing boundaries below dedicated operator-controlled roots and ancestors. Safe-artifact scans cover SQLite, successful and normally cleaned attempt trees, projections and operator output, and must list every intentionally retained negative case they exclude. No quarantine path or raw cleanup error may enter operator output. For acceptance criterion 3, legacy manifest-v2/receipt-v1 recovery means strict shared-normalization/manual-ingestion read compatibility only; it never establishes scheduler ownership, and scheduled restart/reclaim accepts manifest v3 only.

## Outcome

Deliver an opt-in, license-gated and offline-proven MediaCrawler `sync.subscription` handler for the pinned upstream. It must isolate every retry attempt, keep scheduler renewal authority in the trusted parent, terminate the complete child tree on cancellation or parent death, and fence every SyncRun/checkpoint/content mutation without exposing credentials, local roots in operator surfaces, or lease authority.

## Acceptance criteria

1. A closed subscription policy v1 stores only `schema_version`, optional opaque creator `secret_ref`, explicit `allow_full_history`, bounded positive `request_delay_seconds` and `headless`. License acknowledgement is a default-off operator authorization and is bound into every new manifest with the pinned license identity; no raw Cookie or signed creator URL is persisted.
2. Manifest v3 and completion receipt v2 bind the pinned upstream SHA, account, subscription, scheduler Job, schedule revision, attempt, attempt-scoped execution ID, SyncRun, crawl checkpoint, forward mode, login method, item cap, headless/watchdog policy, creator fingerprints and request delay. Newly written artifacts are v3/v2 only.
3. Previously sealed manifest-v2/receipt-v1 artifacts remain dual-read, byte-exact and read-only recoverable. They are never rewritten in place because the existing receipt authenticates the exact manifest bytes. Unsealed or failed legacy artifacts do not gain trust.
4. Scheduler retries reuse the durable Job UUID but derive a unique, confined execution root for every attempt. Attempt 2 can run after attempt 1 leaves or removes state; stale attempts cannot seal output, ingest, advance checkpoints or delete a successor's root after cancel/reclaim/ABA.
5. Bridge preparation, checkout/runtime probes, secret-provider reads, child waiting, receipt validation and normalization run off the event loop. No SQLite transaction spans browser/process/filesystem waits, while the trusted scheduler parent continues exact lease heartbeat.
6. Cooperative cancellation is explicit: task cancellation signals the synchronous runner, terminates and joins the complete child/grandchild tree, safely removes attempt-owned artifacts and releases the account/profile lock before the handler returns or propagates fencing. A plain cancelled `asyncio.to_thread` task is not accepted as evidence.
7. A parent-liveness/control channel prevents orphan crawlers after a hard worker-process death. A fresh worker cannot use the same browser profile until the old child tree has exited; Windows startup must close the `Popen`-to-Job/control-handshake gap. Local helper-process hard-kill tests prove bounded exit and lock release.
8. The database URL, worker ID, lease owner/token and renewal authority never enter child argv, environment, manifest or output. Every SyncRun create/attach/status mutation and every ingestion/checkpoint batch invokes the exact owner/token/unexpired guard first in the same transaction. Batches committed before ownership loss may remain; no batch commits afterward.
9. A faithful pinned-shape test exercises the upstream configuration and `parse_cmd()` ordering without launching the real crawler. The pinned upstream receives the manifest-bound delay through `config.CRAWLER_MAX_SLEEP_SEC` and receives `MAX_CONCURRENCY_NUM=1`. This proves a configured upstream crawl-delay knob only, not spacing for every HTTP request.
10. Closed status mapping is fixed and secret-free: `ACCOUNT_BUSY → account_busy`, `TIMED_OUT → upstream_timeout`, `START_FAILED → upstream_unavailable`, `CONFIGURATION_FAILED → configuration_invalid`, `UPSTREAM_FAILED → temporary_upstream`, output/tree/receipt rejection → `output_security_failed`; cancellation/lease loss propagates fencing and the stale handler never finalizes.
11. Missing license authorization or scheduled QR/challenge presentation enters explicit `waiting_user` without spawning. Missing/unavailable Cookie or saved-session authentication enters `waiting_auth`. Only explicit Job resume can retry either state.
12. All seven platform identifiers pass a mocked-process, versioned-fixture flow: subscribe → tick → v3 prepare → fake child → receipt → guarded forward ingestion → restart/retry. The flow proves idempotent content/checkpoint identity but does not claim live login, live creator traffic or bounded upstream pagination.
13. Known-secret output, nonzero exit, timeout, output-limit failure, receipt rejection, cancel and lease loss all leave no attempt-owned secret bytes in the returned runtime tree. Sentinel scans cover SQLite, manifests/receipts, successful and failed attempt roots, Job/lane projections and scheduler CLI output; the private account session profile is documented as a credential-bearing boundary, not included in a false zero-secret claim.
14. CLI exposes explicit MediaCrawler enablement/license acknowledgement and closed policy creation without returning payloads, secret references, locators, lease material or filesystem roots. The default without authorization is fail-closed.
15. Ruff, format, strict mypy, full branch-aware pytest, focused v2/v3, cancellation/parent-death, ownership, seven-platform, retry/restart and retained-artifact sentinel suites, build, packaged resources, documentation, upstream pins, patch and untracked-runtime checks all pass and are recorded exactly in `verification.md`.

## Truth boundary and non-goals

- Scheduled mode is forward-only in execution 0007. Scheduled backfill, automatic sync → download → Emby export planning and signed-locator refresh remain later work.
- QR/challenge presentation UX remains manual/later work; the scheduled handler may only enter `waiting_user` safely.
- Live QR/Cookie/saved-session login, seven-platform creator scans, real CDN retrieval and Emby/Jellyfin scan/playback remain `NOT_RUN` until the user supplies and authorizes those environments.
- Per-request HTTP throttling, proxy pools, CAPTCHA/protection bypass, upstream source modification, REST, resident production supervision, Docker, distributed HA/PostgreSQL and public-network deployment are outside execution 0007.
- MediaCrawler binary downloading stays disabled; the handler ingests metadata and stable `adapter_refresh` asset identities only.
