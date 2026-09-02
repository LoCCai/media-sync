**English** | [中文](plan.zh.md)

# Execution 0010 plan

- Status: Implemented locally; complete offline MVP gate passes
- Plan date: 2026-08-31
- Schema decision: reuse existing `jobs` scope/lease/natural-key columns; no migration

## Frozen design

### Durable enqueue boundary

- Add Job type `pipeline.subscription` with closed payload v1 and natural key `sync-job:<sync_job_id>`.
- Enqueue exactly once inside both scheduler normal-success and succeeded-run reconciliation transactions. Scheduler success stops after enqueue; it does not call downloads or Emby export.
- Keep the coordinator retry budget at 100 so failures from several independently durable children do not accidentally exhaust a shared five-attempt budget.

### Claim and scope boundary

- Claim only `pipeline.subscription` rows and inspect at most `scan_limit` candidates per call. Terminalize malformed/stale coordinators with fixed codes, then continue to later candidates.
- Treat the coordinator's duplicated Subscription, Account, platform, successful Run and source sync Job as authoritative. Recheck mutable Subscription/Account scope before any child side effect.
- For MediaCrawler `adapter_refresh` Assets, require an eligible current `asset_refresh_sources` observation for the exact Subscription.

### Explicit execution and recovery

1. An operator runs a bounded coordinator batch; no daemon wakes it automatically.
2. Claim/start one coordinator, renew its lease during the handler, and fence finalization by exact token.
3. Download selected assets sequentially in deterministic order. Existing verified generations return `already_verified`; any failure prevents export.
4. Re-read selection and durable asset generations, then export the complete author snapshot through the existing Emby service.
5. Mark only the coordinator succeeded. A later explicit invocation re-enumerates durable state and converges after retry delay or process restart.

## Operator flow

The scheduler materializer and sync worker remain separate from the pipeline worker:

```powershell
uv run media-sync scheduler tick --json
uv run media-sync scheduler run --max-jobs 1 --scan-limit 100 --json
uv run media-sync pipeline run --max-jobs 1 --scan-limit 100 --lease-seconds 3600 --heartbeat-interval-seconds 20 --json
```

For an authorized MediaCrawler runtime, both network-bearing bounded workers remain default-off and require an explicit per-run license acknowledgement:

```powershell
uv run media-sync scheduler run --max-jobs 1 --scan-limit 100 --enable-mediacrawler --accept-mediacrawler-license --json
uv run media-sync pipeline run --max-jobs 1 --scan-limit 100 --heartbeat-interval-seconds 20 --enable-mediacrawler --accept-mediacrawler-license --json
```

An XHS pipeline may additionally receive one opaque secret-provider reference such as `--xhs-detail-reference-ref env:MEDIA_SYNC_XHS_NOTE_DETAIL_URL`. The referenced value is an exact note detail URL with required `xsec` authority; it is not copied into documentation, Job payloads or operator output.

## Implemented sequence

1. Pipeline payload/repository and atomic enqueue from both sync-success paths.
2. Exact Subscription selector and sequential application pipeline using existing download/export services.
3. Bounded worker, fixed result vocabulary, independent coordinator budget, invalid/stale queue-head terminalization and bounded scanning.
4. Exact scope checks, production runtime composition, MediaCrawler lazy refresh binding and CLI wiring.
5. Heartbeat renewal, CLI interval validation and focused concurrency regressions.

## Deferred hardening

- Cooperative cancellation/ownership guards before and during every synchronous child, forced thread/process termination, all cancellation micro-windows and multi-worker/HA stress.
- Resident scheduling/supervision, automatic retry daemon, dependency graph fan-out/fan-in, REST, Docker and production packaging.
- Automatic XHS multi-note detail-authority discovery; additional platform assets and platform-specific derivatives.
- Authorized live login/creator/CDN qualification, real Emby/Jellyfin scan/playback, exhaustive retained-secret/cancellation matrix and PostgreSQL HA.
