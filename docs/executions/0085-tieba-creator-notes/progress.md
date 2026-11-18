**English** | [中文](progress.zh.md)

# Progress: durable Tieba creator-work delivery

Status: implemented and verified locally. Nothing deployed, no live account or
platform request used.

## Result

A Tieba creator subscription now has the same durable chain as Bilibili (0074),
XHS (0076), Douyin (0080), Kuaishou (0081) and Weibo (0084), with every rule
re-derived from the pinned Tieba source.

```text
/crawler/ native login
  -> claim the saved Tieba session into one Account
  -> add one creator-thread Subscription
  -> bounded 1-based page batches with page witnesses
  -> identity-guarded detail fetch and verified delivery
  -> head reconciliation after the server-declared end
  -> incremental head checks for new threads
```

## Implemented

1. **Migration `0019_tieba_creator_notes`** creates `tieba_subscription_progress`
   with the 0015–0018 discipline: closed `phase` whitelist, four fixed stop
   reasons, counter ranges, all-or-nothing delivery/source-end/reconciliation
   triples, `last_page_number` range, `blocked_code` iff `blocked`, and a guarded
   downgrade.
2. **`tieba_creator_work.py` scan state machine.** `TiebaWorkIdentity`
   (`thread_id` + listing digest), `TiebaPageWitness` (1-based `page`,
   `has_more`, page identities), the opaque `tb-work-v1:` cursor, and a stalled
   detection based on a repeated identity tuple — the only signal available
   because the page number always increments.
3. **`tieba_creator_capture.py` child shim.** Replaces only
   `get_all_notes_by_creator_url`, calls `get_notes_by_creator_portrait(portrait,
   pn, rn=20)` and `get_note_by_id`, and maps a non-zero `error_code`, a malformed
   body, `DataFetchError`/`IPBlockError` or any transport failure to
   `access_restricted` rather than an end. The 0020–0022 first-floor image shim
   keeps producing the same frozen shapes.
4. **Bridge/runner wiring.** `RunnerManifest.tieba_scan` /
   `tieba_scan_input_cursor` are mutually exclusive with the other five bounded
   contracts and round-trip through the manifest; `BridgeRequest` accepts the flag
   and cursor; `runner.py` installs the shim after the media capture.
5. **Scheduler surface.** `tieba_delivery_progress.py`,
   `tieba_scan_continuation.py` (default 300 s, both services agree), the
   `MEDIA_SYNC_TIEBA_SCAN_CONTINUATION_DELAY_SECONDS` setting,
   `ingest_tieba_bounded`, pipeline-worker publish, scheduler materialization,
   handler creator binding, subscription-detail `tieba_delivery`, and the
   CLI/doctor/job-diagnostics revision allow-lists advanced to
   `0019_tieba_creator_notes`.

## Verification

- `tests/unit/test_tieba_creator_work.py` (12 cases): cursor round-trip and
  binding rejection, the four stop reasons, page-tail replay, stall blocking,
  head reconciliation, coverage JSON round-trip, bounded page/thread shapes.
- `tests/contract/test_tieba_creator_capture.py` (10 cases): page parsing
  privacy, six drift shapes rejected, an empty page accepted as a page, sealed
  coverage, restricted feed ≠ end.
- `tests/integration/test_tieba_creator_notes_delivery.py` (3 cases): server end →
  reconciling → incremental with `last_page_number`, restricted blocked code,
  terminal failure blocked code.
- Head-revision pinning tests advanced: packaged migrations ship `0019`, domain
  tables include `tieba_subscription_progress`, CLI expected/known revisions and
  table counts (29) updated.

## Not done

- Deployment, Linux host gate, real Tieba login and any live request remain
  `NOT_RUN`.
