**English** | [中文](progress.zh.md)

# Progress: durable Weibo creator-note delivery

Status: implementation in progress in this session. Nothing deployed, no live
account or platform request used.

## Result (implemented so far)

1. **Migration `0018_weibo_creator_notes`** creates `weibo_subscription_progress`
   with the 0015–0017 constraint discipline: closed `phase` whitelist, the four
   fixed stop reasons (`total_inferred_end`, `empty_page_end`,
   `access_restricted`, `unit_cap_reached`), counter ranges, all-or-nothing
   delivery/source-end/reconciliation evidence triples, `blocked_code` iff
   `blocked`, `declared_total` range, and guarded downgrade.
2. **`weibo_creator_work.py` scan state machine.** `WeiboWorkIdentity`
   (`mblog.id` + listing digest), `WeiboPageWitness` (echoed `since_id`,
   `declared_total`, page identities), `WeiboCreatorPage.ends_after(pages)` that
   mirrors upstream's arithmetic exactly (`total > 10 * pages`), and
   `WeiboScanState`/`WeiboScanUnit`/`WeiboScanCoverage` under the opaque
   `wb-work-v1:` namespace. An inferred end keeps the declared total, pages
   consumed and first-page witness so it is never treated as completeness.
3. **`weibo_creator_capture.py` child shim.** Replaces only
   `WeiboCrawler.get_creators_and_notes`, calls the pinned
   `get_notes_by_creator(creator_id, "107603<uid>", since_id)` and
   `get_note_info_by_id`, filters `card_type == 9`, and maps a falsy body or a
   missing `cards` key to `access_restricted` rather than an end. The 0016/0031/
   0035/0036 media shim keeps producing the same frozen shapes.
4. **Bridge/runner wiring.** `RunnerManifest.weibo_scan` /
   `weibo_scan_input_cursor` are mutually exclusive with the other four bounded
   contracts, are validated both ways, and round-trip through the manifest;
   `BridgeRequest` accepts the flag and cursor; `runner.py` installs the shim.
5. **Scheduler wiring.** `weibo_delivery_progress.py` (binding, payload, receipt
   fencing, four-phase transitions, stall/restricted blocked codes),
   `weibo_scan_continuation.py` (default 300s,
   `MEDIA_SYNC_WEIBO_SCAN_CONTINUATION_DELAY_SECONDS`), `ingest_weibo_bounded`,
   pipeline-worker success/terminal publish, scheduler repository
   materialization, handler creator-binding/policy-fingerprint/bounded request,
   subscription-detail `weibo_delivery` payload, and CLI/doctor/job-diagnostics
   migration allow-lists advanced to `0018_weibo_creator_notes`.

## Verification so far

- `tests/unit/test_weibo_creator_work.py` (14 cases): cursor round-trip and
  binding rejection, the four stop reasons, page-tail replay, stall blocking,
  head reconciliation, coverage JSON round-trip, inferred end vs completeness.
- `tests/contract/test_weibo_creator_capture.py` (11 cases): page parsing
  privacy, drift rejection, sealed coverage, restricted list ≠ end, complete
  page reaching the arithmetic end.
- `tests/integration/test_weibo_creator_notes_delivery.py` (4 cases):
  inferred end → reconciling → incremental, restricted blocked code, stalled
  blocked code, terminal failure blocked code.
- Head-revision pinning tests advanced: packaged migrations include 0018,
  database domain tables, CLI expected/known revisions, table counts,
  offline/scheduled pipeline revision assertions.

## Remaining before closeout

- Run the whole Python suite, Ruff lint/format, strict mypy, docs, upstreams,
  and the Web gates on the final tree.
- Write the bilingual verification record with exact numbers.
- Refresh `status`, `roadmap`, the execution index and the next-delivery plan.

Deployment, real Weibo login and any live request stay `NOT_RUN`.
