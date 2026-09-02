**English** | [中文](plan.zh.md)

# Execution 0023 plan

- Status: Executed for the frozen offline scope
- Plan date: 2026-09-02
- Predecessor: `27e45c89f20e8eb6bc871ab1505fe25167b70ae3`
- Plan commit: `bd45478b28cc61a7f35b6211faf3a0fc1eb94138`
- Implementation commit: `24fd41c600eb30fb2df22079e3cf52778589959e`
- Database migration: None planned

## Baseline and audit

Execution 0022 is clean and reconciled at `27e45c8`. The current Bilibili slice emits only `<aid>:video:0`, selects only `pages[0].cid`, accepts exactly one progressive `durl`, and publishes one verified MP4. The pinned MediaCrawler detail response exposes `View.pages` and its client accepts `(aid, cid)`, but its JSONL store drops page identities. The pinned bili-sync-up models every `PageInfo` by CID/page/name/duration, selects DASH video/audio independently and muxes with ffmpeg; that DASH derivative lifecycle is deliberately not folded into this progressive-only execution.

## Delivery sequence

1. Add a verified Bilibili page-capture shim for forward creator/detail storage, bounded to 1–64 canonical ordered pages and installed only in the media-sync child process.
2. Extend normalization with a private page contract, preserve exact single-page compatibility, emit stable CID-bound multi-page Assets and strip all private fields before durable state.
3. Version the strict detail child request, carry the requested CID, resolve only that page, and enrich in-memory JSONL with the complete page tuple plus one ephemeral target URL.
4. Extend lazy database refresh and parent validation to bind every target to the complete persisted VIDEO sibling tuple and reject structural drift before any network byte download.
5. Add source/unit/contract/integration coverage for 1, 2, 3, 64 and 65 pages, duplicate/malformed/reordered/replaced CIDs, targeted play calls, signed-URL non-retention, three archives, Emby multipart output and zero-work replay.
6. Run focused and complete tests plus Ruff, format, strict mypy, compileall, build, docs, upstream, diff and retained-artifact audits; update root truth documents, make bilingual implementation/closeout commits, push and reconcile GitHub.

## Commit sequence

1. `bd45478` — `docs: 启动 Bilibili 有界多分P progressive / start bounded Bilibili multipart progressive`
2. `24fd41c` — `feat: 闭环 Bilibili 有界多分P progressive / close bounded Bilibili multipart progressive`
3. This documentation closeout commit; self SHA intentionally omitted — `docs: 收尾 Bilibili 有界多分P progressive / close bounded Bilibili multipart progressive`

`.upstream` remains excluded, unmodified and clean.
