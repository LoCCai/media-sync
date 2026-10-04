**English** | [中文](progress.zh.md)

# Progress: durable Kuaishou creator-work delivery

Status: the local implementation is complete and offline-verified through the three-role workflow (backend engineer, frontend engineer, bug tester). Deployment, Linux qualification and any live crawl remain pending.

## Outcome

One exact Kuaishou creator Subscription now carries the same durable delivery chain delivered for Bilibili (0074), Xiaohongshu (0076) and Douyin (0080), derived entirely from the pinned Kuaishou source:

```text
/crawler/ native login
  -> adopt the saved Kuaishou session into one Account
  -> add one creator-work Subscription
  -> bounded, pcursor-tracked history batches with page-tail replay
  -> per-work identity-gated detail fetch and verified delivery
  -> head reconciliation after a genuine no_more echo or empty-page end
  -> incremental head checks for new works
```

## Implemented

1. **Migration `0017_kuaishou_creator_work`** creates `kuaishou_subscription_progress` with the 0015/0016 constraint discipline: closed `phase` whitelist, the four fixed stop reasons (`no_more_echoed`, `empty_page_end`, `access_restricted`, `unit_cap_reached`), counter ranges, all-or-nothing evidence triples, `blocked_code` iff `blocked`, and guarded downgrade.
2. **`kuaishou_creator_work.py` scan state machine.** `KuaishouWorkIdentity` (`photo.id` + listing digest), `KuaishouPageWitness` (echoed `pcursor` + page tail), `KuaishouScanUnit`/`KuaishouScanCoverage`. The two source-end candidates are separate codes: a server-echoed `no_more` is `no_more_echoed` and takes precedence; an empty `feeds` page whose echo carried no sentinel is the client-inferred `empty_page_end`. `max_items` truncation never advances the feed — the unit keeps its input `pcursor` with the page witness retained and the next unit re-issues the identical request, skipping delivered works by stable `photo.id` (page-tail replay). A non-advancing echo on a non-empty page accumulates `stalled_units` and blocks with the fixed `kuaishou_cursor_stalled` code — the protection upstream never had (client.py:416-448).
3. **`kuaishou_creator_capture.py` child shim.** Only list requests ride the signed REST channel (`__NS_hxfalcon` from the live page realm, regenerated per attempt, never constructed offline); detail and creator-profile requests ride the unsigned GraphQL channel and never carry signature material. The shim anchors on the validated working directory, keeps authority details in child memory, and seals one coverage JSONL line. A list-level failure (falsy body, `result != 1`, `DataFetchError`, transport errors) restricts the whole feed; a detail failure isolates to that work.
4. **Bridge/runner wiring.** `RunnerManifest.kuaishou_scan`/`kuaishou_scan_input_cursor` with mutual exclusion against the Bili/XHS/Douyin contracts, plus the `ks` runner branch installing the shim after checkout verification.
5. **Scheduler/ingestion/API wiring.** `kuaishou_scan_continuation.py` (default 300 s via `MEDIA_SYNC_KUAISHOU_SCAN_CONTINUATION_DELAY_SECONDS`, both services equal), `kuaishou_delivery_progress.py`, `ingest_kuaishou_bounded`, pipeline-worker publication, scheduler materialization with four-way mutual exclusion, subscription-detail `kuaishou_delivery` payload, and CLI/doctor/migration-allowlist bumps to `0017_kuaishou_creator_work`.
6. **Frontend.** The subscriptions console now renders the Douyin delivery panel that 0080 exposed, with the three platforms' panels sharing one data-mapping helper (reused for the fourth panel when 0081 ships), and unified spacing/level/status-color semantics.

## Verification summary

Through the three-role run: the bug tester confirmed the full pytest suite green (7261 tests collected; suite exit 0), svelte-check, vitest and prettier all exit 0, with zero findings after routing; static gates (compileall/ruff/strict mypy) passed after one fix round. Details in `verification.md`.

## Not yet done

- Deployment rebuild with image identity, Linux gates and the XHS canary remain operator-side (`0077` handoff + `next-delivery.md`).
- A real Kuaishou login, live creator canary and supervisor restart qualification are `NOT_RUN`.
