**English** | [中文](progress.zh.md)

# Progress: durable Douyin creator-work delivery

Status: the local implementation is complete and offline-verified. Deployment, Linux qualification and any live crawl remain pending.

## Outcome

One exact Douyin creator Subscription now carries the same durable delivery chain delivered for Bilibili (0074) and Xiaohongshu (0076), derived entirely from the pinned Douyin source:

```text
/crawler/ native login
  -> adopt the saved Douyin session into one Account
  -> add one creator-work Subscription
  -> bounded, max_cursor-tracked history batches (18 per page)
  -> per-work identity-gated detail fetch and verified delivery
  -> head reconciliation after a genuine has_more != 1
  -> incremental head checks for new works
```

## Implemented

1. **Migration `0016_douyin_creator_work`** creates `douyin_subscription_progress` with the same constraint discipline as 0015: closed `phase` whitelist, the four fixed stop reasons, counter ranges, all-or-nothing delivery/source-end/reconciliation evidence triples, `blocked_code` iff `blocked`, and guarded downgrade (online audit, PostgreSQL `ACCESS EXCLUSIVE`, SQLite exclusive-maintenance attestation, history refusal).
2. **`douyin_creator_work.py` scan state machine.** `DouyinWorkIdentity` (numeric `aweme_id` + listing digest), `DouyinPageWitness` (echoed `max_cursor` + page tail), `DouyinScanUnit`/`DouyinScanCoverage` with the four stop reasons: only `has_more != 1` qualifies as a source-end candidate; an empty `aweme_list` with `has_more == 1` is `empty_page_stalled`; risk-control and fetch failures are `access_restricted`; the unit's `max_items` bound is `unit_cap_reached`. Cursors round-trip canonically under the opaque `dy-work-v1:` namespace and reject any binding mutation.
3. **`douyin_creator_capture.py` child shim.** Replaces only `DouYinCrawler.get_creators_and_videos` with one page-bound unit over `get_user_aweme_posts`/`get_video_by_id`, anchoring all filesystem access on the validated working directory (never a manifest field), keeping every authority detail in child memory, and sealing one coverage JSONL line under the output root. A list-level fetch failure (`DataFetchError`/`IPBlockError`) restricts the whole feed; a detail-level failure isolates to that work.
4. **Bridge/runner wiring.** `RunnerManifest.douyin_scan`/`douyin_scan_input_cursor` with mutual exclusion against the Bili/XHS contracts, binding validation, canonical round trips in both serialization directions, and a `dy` runner branch installing the shim after checkout verification.
5. **Scheduler wiring.** `douyin_scan_continuation.py` (default 300 s via `MEDIA_SYNC_DOUYIN_SCAN_CONTINUATION_DELAY_SECONDS`, both services equal), `douyin_delivery_progress.py` (binding/repository/payload), `ingest_douyin_bounded` one-commit page publication, pipeline-worker success/terminal-failure publication, scheduler repository materialization with mutual exclusion, and the subscription-detail `douyin_delivery` payload.
6. **Expected-revision bump.** `cli.py` pins, `job_diagnostics` migration list, doctor `douyin_delay_seconds`, and the migration allowlist now carry `0016_douyin_creator_work`.

## Verification summary

26 new tests pass: 9 unit (cursor/stop-reasons/drift), 8 contract (parse privacy, shim sealing, restriction ≠ source end), 3 ingestion integration (one-commit cursor/contents, restriction commits nothing, unproven records rejected), 3 migration (empty upgrade, metadata parity, guarded downgrade), 3 delivery transitions (backfill → source-end → reconcile → incremental, restricted blocking, terminal failure). All head-pinned tests (packaged migrations, CLI, support bundles, offline/scheduled pipelines, deployment provenance) advance cleanly to `0016_douyin_creator_work`; the complete suite and remaining gates are recorded in `verification.md`.

## Not yet done

- Deployment rebuild with image identity, Linux gates and the XHS canary remain operator-side (`0077` handoff + `next-delivery.md`).
- A live Douyin login, real creator canary and supervisor restart qualification are `NOT_RUN`.
