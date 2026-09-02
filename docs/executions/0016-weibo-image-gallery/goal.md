**English** | [中文](goal.zh.md)

# Execution 0016 goal

- Status: Complete for the frozen offline scope; every live qualification row remains `NOT_RUN`
- Started: 2026-08-31
- Predecessor: Execution 0015 closeout commit `b105d00`
- Plan commit: `b7bb818`
- Implementation commit: `a77ca74`

## Delivered outcome

Execution 0016 closes one offline-qualified ordinary original Weibo image-post path from creator discovery through exact detail refresh, two independent image downloads, immutable SHA-256 archive publication and Emby/Jellyfin filesystem layout output. The accepted boundary is a canonical positive numeric creator/note identity, no `retweeted_status`, no media `page_info`, and a flat ordered `mblog.pics` list. Each picture must carry a unique valid `pid`, originate from `sinaimg.cn` or one of its subdomains, and use one static extension from `jpg`, `jpeg`, `png` or `webp`. One picture becomes `ContentKind.IMAGE`; multiple pictures become `ContentKind.GALLERY`; image Assets retain positions `0..N-1`.

Creator discovery and detail refresh both install the same task-local integration shim after importing the verified pinned checkout. The shim captures raw `mblog.pics` at the upstream store boundary, enriches only the transient contents JSONL record and does not modify `.upstream`. This creator-side discovery is required to create the initial Assets and exact `AssetRefreshSource` rows; detail-only support would not make the automatic subscription pipeline reachable.

## Acceptance result

1. **Creator and detail shim — PASS.** The isolated creator child proves task-local capture under concurrent note work; the isolated detail child proves `platform=wb`, exact plain numeric `WEIBO_SPECIFIED_ID_LIST`, JSONL/media-off/concurrency controls, account/profile scope, bounded framing and successful attempt cleanup.
2. **Closed shape and durable boundary — PASS.** Only ordinary original numeric posts with ordered, unique Sina static-image entries emit Assets. String/nested/missing/duplicate/drifted entries, foreign source hosts, non-static extensions, retweets and `page_info` fail closed. The integration-private field, captured PID values and a nested signed-URL sentinel are recursively absent from normalized raw, SQLite and retained runtime/archive/export sinks.
3. **Exact identity and refresh — PASS.** WB accepts image Assets only. Parent request construction, resolved detail reference and child frame each require the exact same canonical plain numeric note ID; refresh also matches the exact Account, Subscription, content, remote ID, kind, position and query-free source hint. Reordered or duplicate image identity fails closed.
4. **Two-image composition — PASS.** The Gallery E2E creates two ordered IMAGE Assets and exact SQLite provenance, performs two detail refreshes, two default-profile HTTP/DNS transfers, two independent SHA-256 archive publications, then emits first-image poster, second-image backdrop, two ordered gallery files, NFO and allowlisted source metadata. Requests contain no Cookie, Authorization, Referer or Origin.
5. **Replay and gates — PASS.** Already verified/exported Assets add no detail, HTTP, DNS, probe, archive or export work. The focused gate passes 388 tests; the complete suite passes 1251 with one Windows-inapplicable POSIX mode-bit test skipped. Ruff, format, mypy, documentation, upstream lock verification, build, diff and retained-artifact gates pass.

## Review corrections

- Restricted the embedded proxy source authority to `sinaimg.cn` and its subdomains instead of accepting an arbitrary host.
- Restricted the accepted frozen media extensions to `jpg`, `jpeg`, `png` and `webp`; video, GIF animation and unknown suffixes cannot materialize IMAGE Assets.
- Required exact equality between WB `detail_reference` and `content_remote_id` at request construction, resolution and child-load boundaries.
- Expanded the composition test from one picture to a genuine two-picture Gallery with separate refresh, transfer and archive evidence.

## Explicit exclusions and remaining goal

- Weibo video, animated-image semantics, long-image special handling, media `page_info`, retweets, live/paid/restricted media, comments and creator-avatar media remain unimplemented or unqualified.
- Bounded creator pagination remains unavailable. The pinned Weibo creator path walks full history, so explicit `allow_full_history` and outer watchdogs remain mandatory.
- Sina-direct request profiles, third-party proxy availability, same-ID media replacement detection and injected cleanup-failure quarantine remain deferred.
- Every real login, creator scan, detail/proxy/CDN transfer, real platform-byte probe and Emby/Jellyfin server scan/viewing row remains `NOT_RUN`. Other platform work required by the full project objective remains active.
