**English** | [中文](goal.zh.md)

# Execution 0010 goal

- Status: Function-first MVP implemented locally; complete offline gate passes
- Started: 2026-08-31 00:43 +08:00
- Predecessor: Execution 0009 functional refresh commit `98cf387`

## Delivered outcome

Deliver a resumable local `sync.subscription success → durable pipeline.subscription coordinator → download current eligible assets → export Emby layout` workflow. Scheduler success only enqueues the coordinator; it never starts downloads or export inline. Operators explicitly invoke the bounded `media-sync pipeline run` worker, which returns when its available batch is exhausted and is not a daemon.

## Functional acceptance

1. Normal sync success and succeeded-run reconciliation each idempotently create one `pipeline.subscription` Job in the same database transaction; failure, waiting and cancellation create none.
2. Closed payload v1 and natural key `sync-job:<sync_job_id>` bind the originating sync Job, successful SyncRun and exact Subscription. Duplicated Account/platform columns are execution-time authority and are checked before any child work.
3. Claiming is type-isolated and bounded by `--scan-limit`. Malformed or stale queue heads are terminalized with fixed redacted codes and scanning continues without starving later valid coordinators. The coordinator has a separate 100-attempt convergence budget rather than sharing a small child retry budget.
4. Selection resolves the exact Subscription → Account/Author, enumerates current non-tombstoned author assets and requires current exact-Subscription provenance for MediaCrawler refresh locators. Scope drift is rejected before constructing or running a download child.
5. Assets run sequentially in deterministic order through `AssetDownloadService`. Any failure or non-verified result stops before export. A second authoritative selection verifies durable generations and catches newly added/replaced blockers.
6. Once every selected asset is durably verified, `EmbyExportService` publishes the complete author snapshot. Existing generation-bound download recovery and Emby intent/result recovery make explicit reruns converge after ordinary process restarts.
7. The bounded coordinator worker renews the exact Job/worker/token lease while its handler runs and fences stale finalization. `--heartbeat-interval-seconds` is optional and must be finite, positive and shorter than the lease.
8. MediaCrawler refresh remains default-off and requires both `--enable-mediacrawler` and `--accept-mediacrawler-license` for each pipeline invocation. XHS currently accepts one ephemeral `--xhs-detail-reference-ref` for an exact note detail URL; automatic multi-note authority discovery is not implemented.

## Truth boundary

- Offline platform shapes are limited to the Assets currently normalized and refreshable: XHS image/video, Douyin image/video/audio/cover, Kuaishou video/cover and Bilibili cover. Weibo, Tieba and Zhihu currently produce no downloadable Asset; Bilibili playable video/DASH/multi-part/subtitle/danmaku is not claimed.
- No user-authorized platform login, creator request, signed CDN download or real Emby/Jellyfin scan/playback ran in execution 0010; every live row remains `NOT_RUN`.
- The production CLI handler is synchronous and runs through `asyncio.to_thread`. Cancelling its asyncio task after coordinator lease loss does not forcibly terminate the underlying thread, so an old thread may continue child/download/export work. Exact Job CAS prevents stale coordinator `complete/fail`, but full cancellation micro-windows, cooperative child authority checks and multi-worker HA are deferred.
- No resident worker, retry daemon, REST service, Docker/production supervisor or PostgreSQL HA is delivered by this execution.
