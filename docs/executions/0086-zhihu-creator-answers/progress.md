**English** | [中文](progress.zh.md)

# Progress: durable Zhihu creator-answer delivery

Status: implemented and verified locally. Nothing deployed, no live account or
platform request used.

## Result

A Zhihu creator subscription now has the same durable chain as Bilibili (0074),
XHS (0076), Douyin (0080), Kuaishou (0081), Weibo (0084) and Tieba (0085), with
every rule re-derived from the pinned Zhihu source.

```text
/crawler/ native login
  -> claim the saved Zhihu session into one Account
  -> add one creator-answer Subscription
  -> bounded offset units with page witnesses
  -> identity-guarded delivery and verified media
  -> head reconciliation after the server-declared end
  -> incremental head checks for new answers
```

## Implemented

1. **Migration `0020_zhihu_creator_answers`** creates
   `zhihu_subscription_progress` with the 0015–0019 discipline: closed `phase`
   whitelist, four fixed stop reasons, counter ranges, all-or-nothing
   delivery/source-end/reconciliation triples, `last_offset` range, `blocked_code`
   iff `blocked`, and a guarded downgrade.
2. **`zhihu_creator_work.py` scan state machine.** `ZhihuWorkIdentity`
   (`content_id` + listing digest), `ZhihuPageWitness` (offset, limit, `is_end`,
   identities), the opaque `zh-work-v1:` cursor, page-tail replay by identical
   offset, and **window-shift detection** by comparing page identity tuples — the
   only signal a client-chosen integer offset gives.
3. **`zhihu_creator_capture.py` child shim.** Replaces only
   `get_all_anwser_by_creator`, calls `get_creator_answers(url_token, offset,
   limit)`, cross-checks the extractor's `content_id` order against the raw ids,
   and maps a falsy/malformed body, `DataFetchError`/`IPBlockError` or a transport
   failure to `access_restricted` rather than an end. The 0033 gallery shim keeps
   producing the same frozen shapes.
4. **Bridge/runner wiring.** `RunnerManifest.zhihu_scan` /
   `zhihu_scan_input_cursor` are mutually exclusive with the other six bounded
   contracts and round-trip through the manifest; `BridgeRequest` accepts the flag
   and cursor; `runner.py` installs the shim after the media capture.
5. **Scheduler surface.** `zhihu_delivery_progress.py`,
   `zhihu_scan_continuation.py` (default 300 s, both services agree), the
   `MEDIA_SYNC_ZHIHU_SCAN_CONTINUATION_DELAY_SECONDS` setting,
   `ingest_zhihu_bounded`, pipeline-worker publish, scheduler materialization,
   handler creator binding, subscription-detail `zhihu_delivery`, and the
   CLI/doctor/job-diagnostics revision allow-lists advanced to
   `0020_zhihu_creator_answers`.

## Verification

- `tests/unit/test_zhihu_creator_work.py` (13 cases): cursor round-trip and
  binding rejection, the four stop reasons, small-cap unit limits, offset replay,
  shifted-window blocking with `zhihu_window_shifted`, head boundary
  reproduction, coverage JSON round-trip, failed-detail isolation, bounded shapes.
- `tests/contract/test_zhihu_creator_capture.py` (9 cases): page parsing privacy,
  six drift shapes rejected, sealed coverage, restricted feed ≠ end.
- `tests/integration/test_zhihu_creator_answers_delivery.py` (3 cases): `is_end` →
  reconciling → incremental with `last_offset`, restricted blocked code, terminal
  failure blocked code.
- Head-revision pinning tests advanced: packaged migrations ship `0020`, domain
  tables include `zhihu_subscription_progress`, CLI expected/known revisions and
  table counts (30) updated.

## Not done

- Deployment, Linux host gate, real Zhihu login and any live request remain
  `NOT_RUN`.
