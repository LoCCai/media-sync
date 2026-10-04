**English** | [中文](goal.zh.md)

# Goal: durable Kuaishou creator-work delivery with source-backed cursors

Status: **PLANNED ONLY**. No 0081 application code, migration, deployment or live crawl has started.

Execution 0081 extends the durable subscription delivery delivered for Bilibili (0074), Xiaohongshu creator notes (0076) and Douyin creator works (0080) to Kuaishou creator works. It follows the mandated source-first posture: every pacing, end-detection, reconciliation and incremental rule below is derived from the pinned MediaCrawler's Kuaishou code and response shapes, not copied from the Douyin or XHS implementations.

The upstream Kuaishou creator flow (`media_platform/kuaishou/core.py`, `client.py`, `help.py`, `exception.py`) defines the facts this execution builds on:

- Creator works paginate on the signed REST endpoint `/rest/v/profile/feed` with body `{user_id, pcursor, page: "profile"}` (client.py:169-170). The opaque string `pcursor` starts empty (client.py:414) and the server echoes the next cursor at the top level, replayed verbatim (client.py:434). No client-side page-size parameter exists — the server alone decides each page's size (client.py:169 carries no `count` field).
- The stop signal is the string sentinel `no_more`: the upstream loop continues only while `pcursor != "no_more"` (client.py:416). A server-echoed `no_more` (client.py:434) is the primary genuine source-end candidate.
- An empty `feeds` array is the second end path: the client itself sets `pcursor = "no_more"` and breaks (client.py:436, 440-442). Unlike Douyin's empty-page stall, upstream Kuaishou terminates on emptiness; the durable layer records this client-inferred end under its own stop reason instead of merging it with the echoed one.
- Access restriction is distinct from feed exhaustion: a falsy response is logged as a possible ban and breaks the loop (client.py:418-422), a business `result != 1` breaks the loop (client.py:426-432), the shared GraphQL path raises `DataFetchError` on an `errors` key (client.py:75-76), and the signed channel raises `DataFetchError` on `result != 1` (client.py:158-159) while retrying `result == 2` rate limiting with exponential backoff at most three times (client.py:126, 150-157). `IPBlockError` is defined but never raised or caught anywhere in the Kuaishou module (exception.py:28-29). None of these is a source end.
- Only list requests are signed. The signed REST channel `request_rest_v2_signed` (client.py:117-159) is reached solely from the two list endpoints (client.py:170, 189): the injected `KS_SIGN_CAPTURE_SCRIPT` hooks the page's own signing realm into `window.__ks_realm` (help.py:35-57) and `get_ks_sign_from_playwright` evaluates `$encode` per request (help.py:60-86), producing the `?__NS_hxfalcon={sign}&caver=2` query (client.py:131-136, 142). The signature is bound to the request content and a time window and must be regenerated per attempt (client.py:130); no pinned script can sign offline. Detail and creator-profile requests carry no signature — they ride the unsigned GraphQL channel `post()` → `request()` (client.py:88-92, 68-78; `get_video_info` client.py:254, `get_creator_profile` client.py:290).
- Work identity is `photo.id` from the feed item and detail payload (core.py:448-450, 234-241, store/kuaishou/__init__.py:56-57); creator identity is the `user_id` parsed from the protected creator URL — a `/profile/` URL or a pure ID (help.py:115-138, model/m_kuaishou.py:32-34, config/ks_config.py:36-40). There is no gallery/video media branch anywhere upstream: media facts are the flat `video_cover_url = photo.coverUrl` and `video_play_url = photo.photoUrl` fields (store/kuaishou/__init__.py:73-74) with `video_type = str(item.type)` (store/kuaishou/__init__.py:63), and `ENABLE_GET_MEIDAS` is never consumed by the Kuaishou module.
- The upstream creator loop has no total cap (unlike the search flow's `CRAWLER_MAX_NOTES_COUNT` bound, core.py:149-151); the durable layer must supply its own unit cap.

The intended operator result:

```text
/crawler/ native login
  -> adopt the saved Kuaishou session into one Account
  -> add one creator-work Subscription
  -> bounded, pcursor-tracked history batches
  -> per-work identity-gated detail fetch and verified delivery
  -> head reconciliation after a genuine source end
  -> incremental head checks for new works
```

## Required behavior

1. **Exact subscription ownership.** Every continuation, Job, Run, receipt and publication stays bound to one Subscription, Account, author, `profile`-shaped creator scope and the locked `user_id` fingerprint.
2. **Verbatim-cursor progression.** The echoed `pcursor` is stored and replayed exactly as the server sent it. Nothing may parse, reorder, regenerate or "optimize" it. A unit processes at most one upstream page and stops at the subscription's `max_items` for that unit — a cap the durable layer owns, because the upstream loop runs unbounded and the server alone decides each page's size. A unit never truncates a server page and then advances: when `max_items` stops a unit before the page's tail, the unit ends with its input `pcursor` unchanged and the next unit re-issues the identical request, skipping already-delivered works by stable `photo.id`, until the page tail is consumed; only a fully consumed page advances the feed to the echoed cursor. The durable layer must also guard what upstream never checks (client.py:416-448): a non-empty page whose echoed `pcursor` equals its input `pcursor` makes no progress, so after a bounded number of such stalled units the chain stops into the blocked state with a fixed code instead of looping silently.
3. **Four stop reasons, four fixed codes.** `no_more_echoed` (server-echoed sentinel, the primary source-end candidate, retained with page evidence), `empty_page_end` (empty `feeds` array with the client-inferred `no_more` — upstream-terminal, also a source-end candidate retained with page evidence), `access_restricted` (banned-break on a falsy body, business `result != 1`, `DataFetchError` from `errors`/`result` keys, rate-limit exhaustion after the three-attempt backoff, and any transport-level failure — httpx errors, unparseable JSON bodies (client.py:74, 147) or proxy-refresh errors — that aborts the exception-free upstream loop client.py:416-448), and `unit_cap_reached` (the unit's `max_items` bound). When an empty `feeds` page coincides with a server-echoed `no_more`, the server echo wins and the unit records `no_more_echoed` — the client inference at client.py:440-442 is the fallback for pages whose echo carried no sentinel, so the server-attested evidence always takes precedence. Only the two end candidates may later qualify as source end, each under its own code so the operator can see which path closed the feed.
4. **Identity-gated delivery.** Work details are fetched per `photo_id` from the same page that surfaced the identity (the upstream per-page detail callback under `MAX_CONCURRENCY_NUM` concurrency, core.py:453-466, 220-254) over the unsigned GraphQL channel — no `__NS_hxfalcon` material is required, constructed or attached to a detail fetch. A failed detail marks that work failed with its fixed code and never blocks unrelated works. Kuaishou works publish as a single video-shaped Content unit with all-or-nothing semantics over the recorded `photoUrl` bytes — there is no gallery branch to model.
5. **Head reconciliation before incrementality.** After retained end evidence (`no_more_echoed` or `empty_page_end`), one bounded head re-list from the empty `pcursor` must reproduce the recorded newest boundary (same newest work set, stable echo shape) before the subscription may enter incremental polling. Drift keeps delivered data and re-opens reconciliation; a glitch-empty end is caught here rather than trusted.
6. **Incremental operation.** Incremental cycles re-list bounded head pages, deduplicate by stable `photo.id`, and produce work only for unseen or changed works. An unchanged cycle writes no bytes and no NFO rows.
7. **Pause, deletion and recovery.** The paused-state editor fences policy changes; auth expiry routes to the existing waiting-auth path; restart, lease loss and duplicate execution fence the same durable unit. A lost page signing realm (the reload-and-rewait path, help.py:72-77) or any signature/risk-control restriction never discards the durable `pcursor`.

## Acceptance evidence

- A deterministic capture-replay fixture replays at least three captured `/rest/v/profile/feed` page exchanges verbatim — each carrying its own `__NS_hxfalcon` signature, never re-derived — records each echoed `pcursor`, survives restart between steps and reaches a genuine sentinel end.
- An empty-`feeds` exchange records `empty_page_end`, and a banned/restricted exchange (falsy body, `result != 1`, rate-limit exhaustion, or a transport-level failure) records `access_restricted` and resumes without fabricating source end.
- After source end, head drift (one inserted work) re-opens reconciliation and later closes it; an unchanged head enters incremental mode.
- One new work is fetched once and published as one complete video-shaped Content unit; an unchanged rerun is zero work.
- Final tree/NFO validation passes with no media server configured.
- Linux image, real Kuaishou login and a live creator canary remain `NOT_RUN` until the operator runs them.

## Explicit non-goals

- Kuaishou comments, search subscriptions or any non-creator scope.
- Treating Douyin's integer `has_more`, XHS token semantics or Bilibili page numbers as Kuaishou-shaped.
- Any offline construction, caching or re-derivation of `__NS_hxfalcon` signatures; the live page realm is the only signing authority.
- Automated handling of risk control beyond the existing pause/backoff policy.
- Any Emby/Jellyfin server control.
