**English** | [中文](goal.zh.md)

# Execution 0006 goal

- Status: Complete for the offline/Fake scope
- Started: 2026-08-30 10:48 +08:00
- Predecessor: Execution 0005 implementation commit `8d5b48a`

## Outcome

Deliver a restart-safe, multi-process-safe single-host scheduler for creator subscriptions. It must materialize due subscription cycles into durable Jobs, run supported sync handlers with bounded retries, and enforce global worker capacity plus persistent platform/account launch throttling without weakening the exact-claim download and Emby protocols delivered by execution 0005.

## Acceptance criteria

1. Migration `0004_scheduler_control_plane` adds scheduler identity and lane state without changing the payload, status, attempt, lease or recovery evidence of existing `asset_download` and `export.emby` Jobs.
2. A bounded scheduler tick atomically materializes every selected due subscription as one `sync.subscription` Job. Concurrent ticks create at most one non-terminal cycle per subscription; a completed cycle advances by fixed delay instead of producing a catch-up storm.
3. `claim_next` reclaim/queue mutation is scoped by accepted Job type before it changes any row. Generic sync workers never claim or reclaim execution 0005 download/export Jobs.
4. Claiming obeys injected global capacity and persistent platform/account lanes: maximum concurrency, minimum start interval, closed/open/half-open circuit state and one half-open probe winner. Independent SQLite connections prove the CAS behavior.
5. Retry policy implements bounded exponential backoff, equal jitter, `Retry-After` as a lower bound, maximum attempts and fixed error classes. Invalid numeric/time inputs fail closed; tests inject the clock and RNG and never sleep.
6. `waiting_auth` and `waiting_user` never retry automatically. Only an explicit safe resume operation may make them claimable again.
7. A closed handler registry ships with the deterministic Fake subscription handler. MediaCrawler keeps its execution 0004 manual run/ingest boundary unchanged in this execution; scheduler integration, manifest v3 and child-process heartbeat/cancellation are explicitly deferred.
8. The offline acceptance test explicitly invokes execution 0005 download/export services after a scheduled Fake sync. Execution 0006 does not claim an automatic downstream DAG/planner, and the generic worker never preclaims download/export Jobs.
9. CLI surfaces pause/resume/run-now, bounded tick/run, redaction-safe Job listing/resume, lane policy inspection/update and circuit reset. Output omits payloads, lease tokens, credentials, locators and filesystem roots.
10. An offline restart test covers subscribe → tick → Fake sync → mock secure download → Emby export → reconstruct services → rerun without duplicate cycle, archive or publication identities.
11. Ruff, format, strict mypy, full pytest/coverage, focused scheduler/concurrency/restart/sentinel suites, build, source and unpacked-wheel migrations, documentation, upstream pins, patch checks and untracked-runtime checks all pass and are recorded exactly in `verification.md`.

## Truth boundary and non-goals

- All automated acceptance is offline and uses Fake adapters/handlers, mock transports, generated media and temporary SQLite/filesystem roots.
- Live QR/Cookie/saved-session login, real platform scheduling behavior, signed-locator refresh/CDN retrieval and Emby/Jellyfin scan/playback remain `NOT_RUN` until the user supplies and authorizes those environments.
- MediaCrawler scheduler integration, manifest v3 request-delay binding, long-child heartbeat/cancellation and automatic download/export DAG planning are deferred to a later execution.
- REST API, Docker/production supervision, public-network binding, distributed HA/PostgreSQL locking, proxy pools, CAPTCHA automation and platform-protection bypass are outside execution 0006.
- Platform concurrency and start intervals qualify scheduler launch throttling only; this execution makes no claim about every upstream HTTP request.
