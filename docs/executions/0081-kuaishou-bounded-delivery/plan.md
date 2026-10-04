**English** | [中文](plan.zh.md)

# Plan

Status: **FROZEN FOR A LATER TURN**. This document authorizes no deployment, platform request or supervisor restart by itself.

## 1. Trace and record before writing state

- Follow the pinned Kuaishou creator flow from the adopted Account profile through `parse_creator_info_from_url` (help.py:115-138), `get_creator_info`/`userProfile` (client.py:389-396), `get_all_videos_by_creator` pagination (first empty `pcursor` client.py:414, body `{user_id, pcursor, page: "profile"}` client.py:169-170, top-level echo client.py:434), the per-page detail callback `fetch_creator_video_detail` → `get_video_info_task` → `get_video_info` (GraphQL `visionVideoDetail` with variables `{photoId, page: "search"}` over the unsigned `post()`/`request()` channel, core.py:453-466, 220-254, client.py:243-254, 88-92, 68-78), and the flat media fields `coverUrl`/`photoUrl` (store/kuaishou/__init__.py:73-74).
- Reuse the 0080 delivery skeleton (scan unit/coverage, continuation policy, delivery progress repository, Job-scoped ingestion, downloader, archive, library writer) but re-derive every parameter from Kuaishou evidence; record the pinned MediaCrawler SHA and observed page shapes in the verification.
- Name the exact points where Douyin or XHS assumptions would be wrong for Kuaishou (string sentinel `no_more` instead of integer `has_more`, client-inferred empty-page end instead of empty-page stall, no client page size — so the Douyin fixed-page-size clamp `DOUYIN_CREATOR_PAGE_SIZE` cannot be copied — signed list channel over an unsigned GraphQL detail channel, live-realm `__NS_hxfalcon` signing instead of a pinned signing script, no upstream creator cap) and write each down as a contract with a test.

## 2. Durable cursor and stop-reason state

- Migration `0017_kuaishou_creator_work` (revises `0016_douyin_creator_work`) creates `kuaishou_subscription_progress` with the same constraint discipline as 0016: closed `phase` whitelist, the four fixed stop reasons (`no_more_echoed`, `empty_page_end`, `access_restricted`, `unit_cap_reached`), counter ranges, all-or-nothing evidence triples for delivery/source-end/reconciliation, `blocked_code` iff `phase = 'blocked'`, and guarded downgrade.
- Persist the server-echoed `pcursor` verbatim, wrapped under the opaque `ks-work-v1:` cursor namespace. Store only bounded counters, fingerprints and timestamps; never raw responses, sign material or Cookies.

## 3. Bounded continuation with fenced units

- One page-bound unit per step after the prior unit's discovery and pipeline receipt are durably consistent; honor `max_items` — load-bearing here because the upstream creator loop is unbounded (client.py:398-449) and the server alone decides each page's size (no `count` in client.py:169), so the Douyin fixed-page-size clamp (douyin_creator_work.py:496) cannot be copied. A unit never truncates a server page and then advances: when `max_items` stops a unit before the page tail, the durable input `pcursor` stays unchanged and the next unit re-issues the identical request, skipping already-delivered works by stable `photo.id`, until the page tail is consumed; only a fully consumed page advances on the echoed cursor. Also honor the configured continuation delay (default 300 s via `MEDIA_SYNC_KUAISHOU_SCAN_CONTINUATION_DELAY_SECONDS`, identical in both services), pause/removal and auth/backoff state.
- Only list requests are signed by the live Playwright page realm: the signed REST channel `request_rest_v2_signed` (client.py:117-159) serves the two list endpoints (client.py:170, 189) with `KS_SIGN_CAPTURE_SCRIPT` (help.py:35-57) and `get_ks_sign_from_playwright` (help.py:60-86), regenerated per attempt (client.py:130); detail and creator-profile requests ride the unsigned GraphQL channel (`post()` client.py:88-92 → `request()` client.py:68-78) and must never carry or require `__NS_hxfalcon` material. The durable layer never constructs or caches a signature offline, and a realm recapture (reload-and-rewait, help.py:72-77) is a bounded retry state for list steps, never cursor loss.
- API exact execution and the resident supervisor compete through the same durable ownership fence used by 0074/0076/0080; duplicate submissions reuse the authoritative unit.

## 4. Reconciliation and incremental head checks

- After retained end evidence (`no_more_echoed` or `empty_page_end`), run one bounded head re-list from the empty `pcursor`: the recorded boundary must reproduce (same newest work set, stable echo shape) before entering incremental mode; drift re-opens reconciliation while keeping delivered data.
- Incremental cycles re-list bounded head pages, deduplicate by stable `photo.id`, fetch details only for unseen or changed works, and treat restrictions or realm loss as bounded retry states — never as cursor loss.

## 5. Delivery and publication per complete Content unit

- Kuaishou works carry a single flat media shape with no gallery/video branch upstream: a work publishes only when the detail-derived `photoUrl` video bytes (and cover where used, store/kuaishou/__init__.py:73-74) are complete; unrelated works are never blocked by one failed work; partial outcomes carry exact failed-work counts and fixed codes.
- Prove restart and zero-work replay preserve content-addressed bytes and deterministic NFO output.

## 6. Operator surface

- Subscription details expose the phase, cursor-step counts, last source-end/reconciliation evidence including which end path closed the feed, next eligible run and exact failed-work counts. No cursor blob, sign material, host path or raw response is exposed.

## 7. Verification sequence

1. Unit tests for cursor round-trip, the four stop reasons, page-tail replay (mid-page `max_items` stop with same-`pcursor` re-list), failed-detail advance, head drift and cursor-binding mutation rejection.
2. Contract tests for page parsing privacy, the capture shim sealing coverage (each signature captured with its exchange, never re-derived), restriction ≠ source end, echoed-end vs empty-page-end evidence, and the list-only live-realm signing contract (list requests signed, GraphQL details and profiles unsigned).
3. Integration tests: three or more `pcursor` steps with restart barriers, empty-page and restricted backoff, sentinel end, head drift, transition to incremental, partial delivery, zero-work replay, one-commit ingestion, migration round trips pinned at `0017`.
4. Update every head-pinned test (packaged migrations, CLI/support-bundle revisions, table counts, offline/scheduled pipelines, deployment provenance).
5. Complete Python and Web suites, Ruff, strict mypy, documentation/upstream checks, package build and `git diff --check`; record exact bilingual results.
6. Linux host build, real Kuaishou session adoption and a live creator canary stay `NOT_RUN` until the operator explicitly runs them.
