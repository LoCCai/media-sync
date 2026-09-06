**English** | [中文](goal.zh.md)

# Goal: durable Bilibili uploads backfill to incremental local delivery

Status: **PLANNED ONLY**. No 0074 application code, migration, deployment or live crawl has started.

Execution 0074 will make one exact Bilibili `uploads` Subscription useful after the native MediaCrawler session adoption delivered in 0073. It will reuse the existing Account profile, MediaCrawler runner, scheduler, Job-scoped ingestion, downloader, SHA-256 archive and Emby/Jellyfin-compatible directory/NFO writer. It will not add another login page, crawler, downloader, scheduler or export product.

The intended operator result is straightforward:

```text
/crawler/ native login
  -> adopt the saved session into one Bilibili Account
  -> add one uploads Subscription
  -> paced, bounded historical batches
  -> verified media written under the configured library root
  -> reconcile the current head after reaching source end
  -> periodic bounded head checks for new uploads
```

An Emby/Jellyfin API connection remains optional. The durable product output is the configured local directory tree and NFO/sidecar files, which another container or media server may scan.

## Required behavior

1. **Exact subscription ownership.** Every continuation, Job, Run, receipt and publication remains bound to one Subscription, Account, author, `uploads` scope and locked upstream identity. It must never consume another subscription's queue or the shared `/data/mediacrawler/webui-output` directory.
2. **Bounded history batches.** Each discovery unit processes at most `min(max_items, 30)` verified upload details and preserves the existing request-attempt limits. More history is continued by later durable units, never by an unbounded in-process loop.
3. **Paced continuation.** A successful batch with proven remaining history schedules the next unit no sooner than the configured continuation delay. Authentication, challenge, rate-limit and transient failures retain the existing pause/backoff policy. There is no challenge bypass, credential rotation or proxy rotation.
4. **Truthful baseline state.** Reaching a historical source end is not enough by itself. The service performs one bounded head reconciliation against the captured boundary. Only a stable result may publish `baseline_snapshot_complete`; this means a time-bounded snapshot was reconciled, not that platform history is permanently complete.
5. **Safe invalidation.** A changed Account authentication revision, author identity, Subscription scope, relevant policy generation or locked upstream identity invalidates the baseline and requires a new bounded reconciliation path. It must not silently reuse incompatible continuation state.
6. **Incremental operation.** After baseline completion, ordinary scheduled cycles perform bounded head checks with overlap and stable-ID deduplication. A newly injected upload produces only its missing download/archive/publication work; a zero-work cycle neither rewrites existing bytes nor duplicates NFO entries.
7. **Content-unit visibility.** A failed or unsupported old work must not indefinitely hide unrelated verified works. Publication is decided per complete Content unit: a multi-part video or gallery remains all-or-nothing within that Content, while other complete Contents may publish. The overall result reports partial failure honestly.
8. **Pause, deletion and recovery.** Pause prevents new continuation units; removal prevents new work while preserving history/media; authentication expiry moves the exact work to the existing waiting-auth path. Restart, lease loss and duplicate supervisor/API attempts recover or fence the same durable unit without double download or publication.
9. **User-visible evidence.** Subscription details expose a bounded phase (`backfill`, `reconciling`, `incremental`, `blocked`), batch counts, last proven source-end/reconciliation evidence, next eligible run and exact failed Content counts. No Cookie, locator, host path or raw upstream response is exposed.

## Acceptance evidence

- A deterministic locked-runner fixture with at least 65 ordinary uploads crosses at least three batches, survives restarts around discovery, pipeline and state publication, reaches source end, reconciles head and enters incremental mode.
- Pagination drift or a new head item during backfill forces reconciliation instead of a false completion claim.
- A later single new upload downloads and publishes once; an unchanged rerun is zero work.
- Two valid works publish even when one unrelated old work fails; incomplete multi-part media never publishes partially.
- Pause, removal, authentication expiry, lease loss, duplicate execution and continuation delay are all exercised against the exact subscription.
- Final tree/NFO validation passes with no media-server provider configured.
- Current Linux image, real Bilibili login/profile adoption, UID `252671524`, CDN bytes, final host directory and a later real incremental cycle remain `NOT_RUN` until the operator explicitly runs and records the canary.

## Explicit non-goals

- Bilibili dynamics, bangumi, live, paid media, subtitles or danmaku.
- The other six platforms; they require their own pagination and source-end evidence.
- Automatic import of interactive crawler-console output.
- Automated anti-challenge bypass or credential/proxy rotation.
- Requiring or automatically controlling an Emby/Jellyfin server.
- A general subscription-policy editor. That is the next UI candidate after this delivery; it must use paused-state and schedule-revision fencing.
