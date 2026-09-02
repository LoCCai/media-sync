**English** | [中文](progress.zh.md)

# Execution 0010 progress

- Status: Function-first MVP implemented locally
- Started: 2026-08-31 00:43 +08:00
- Predecessor: Execution 0009 commit `98cf387`
- Implementation: `IMPLEMENTED LOCALLY`
- Focused verification: `PASS` — combined pipeline/scheduler/CLI gate `154 passed`
- Final full-suite rerun: `PASS` — `930 passed, 1 skipped in 191.06s`

## Implemented

- Added `pipeline.subscription` payload v1, idempotent natural key and a 100-attempt coordinator budget. Normal scheduler success and succeeded-run reconciliation enqueue it atomically; other outcomes enqueue none.
- Added bounded claim scanning. Invalid payload/scope and stale source/run coordinators become fixed terminal failures, so one corrupt queue head cannot starve valid work behind it.
- Added exact Subscription → Account/Author asset selection and current MediaCrawler provenance checks. Durable Account/platform scope is checked before any download child.
- Added sequential download orchestration, failure-before-export behavior, authoritative pre-export re-selection and complete-author Emby export. Existing child Jobs provide generation/publication restart convergence.
- Added production runtime composition with per-asset downloader construction. MediaCrawler refresh is bound lazily to the exact coordinator Subscription; direct locators do not require MediaCrawler enablement.
- Added `PipelineSubscriptionWorker` with sync/async handler support, closed result mapping, retry delay, exact lease heartbeat and stale-finalization fencing. `run_once` and `run_bounded` accept `scan_limit` and `heartbeat_interval_seconds`.
- Added `media-sync pipeline run` with bounded job count, worker identity, lease, scan, heartbeat and retry controls; MediaCrawler enable/license gates; and optional one-note XHS detail reference.

## Actual workflow

`scheduler tick` materializes due sync Jobs. `scheduler run` executes only the selected sync Jobs; a successful sync transaction enqueues `pipeline.subscription` and then returns. Downloads and export do not start until a separate explicit `pipeline run` invocation claims that coordinator. Both commands are bounded one-shot workers and return when idle; neither is a daemon.

## Review repairs

- Raised the coordinator budget from five to 100 so independently durable child retries do not share one small counter.
- Terminalized malformed/stale claimed rows and bounded the scan with `--scan-limit`.
- Made download-result scope mismatch terminal and enforced Account/platform scope before child construction.
- Added heartbeat renewal and CLI validation requiring a finite positive interval shorter than the lease.
- Added side-effect-free production preflight for network-bearing pipelines. Before any child Job/Asset lifecycle mutation, it verifies the pinned MediaCrawler lock, checkout and Python runtime plus an actually launchable mandatory `ffprobe`; invalid non-empty configuration is rejected too.
- Updated the historical scheduled-offline regression to expect the new queued coordinator while preserving the proof that scheduler success itself performs no downstream work.

## Deferred

- The synchronous production handler runs in `asyncio.to_thread`; task cancellation does not terminate the underlying thread. Old child/export work may continue after coordinator lease loss even though stale coordinator finalization is fenced. Cooperative cancellation, forced termination and HA stress remain deferred.
- XHS requires one operator-supplied exact note detail reference; automatic multi-note lookup is not implemented. Weibo/Tieba/Zhihu Asset discovery and Bilibili playable media derivatives remain unavailable.
- No live platform/CDN/real Emby qualification, resident worker or REST/Docker production operations has been completed in this execution. The final code/test/build/upstream gates pass; documentation and diff checks run after these records are finalized.
