**English** | [中文](goal.zh.md)

# Execution 0051 goal

- Status: Implemented and offline-verified; live qualification remains `NOT_RUN`
- Date: 2026-09-04
- Predecessor: `38e0ebe` (green Linux runtime preflight after Console v2)
- Scope: capability-driven account login and creator-subscription workbench
- Database migration: None
- Implementation commits: backend `6ed7ab3`; Web `178e557`
- Closeout commit: the commit containing the final record (self SHA not embedded)

## Outcome

1. Deliver one static, bounded and versioned seven-platform MediaCrawler capability contract. It describes the stable platform order, login methods, QR availability, creator-input guidance, secret-reference eligibility, full-history acknowledgement, qualified offline media shapes, limitations and honest `NOT_RUN` live state.
2. Put account/subscription validation and idempotent creation behind one application workbench used by both CLI and REST. Invalid or unacknowledged MediaCrawler drafts fail before Account, Author or Subscription mutation; safe previews and results never return credential or creator-authority references.
3. Add an account-scoped login preflight limited to login prerequisites. Database, account eligibility, licence, checkout, Python runtime, browser, profile writability and account-lock failures stop before a new process-local Operation or child launch; ffmpeg and ffprobe are deliberately irrelevant to login.
4. Bind QR retrieval to an exact active QR `LoginSession`, retain the account route as a compatibility resolver, remove stale QR material under the account lock before publishing a new session and preserve the `202` pending, `200` image, `410` terminal and `404` unknown/ineligible lifecycle.
5. Upgrade the account and subscription pages into a capability-driven workbench: composite account state and preflight diagnostics gate login, while account selection, creator/policy input, server preview and explicit confirmation gate subscription creation.
6. Expose allowlisted subscription-policy and checkpoint summaries without raw cursor values, signed creator URLs, credential references, QR material, profile paths or runtime paths.

## Acceptance result

- The server-owned v1 capability endpoint covers `xhs`, `dy`, `ks`, `bili`, `wb`, `tieba` and `zhihu` in stable order. Only XHS permits an opaque creator secret reference; Bilibili and Weibo recommend numeric IDs without narrowing the compatibility validator.
- MediaCrawler creator IDs share the conservative `[A-Za-z0-9._-]{1,255}` validator. Bilibili, Douyin, Kuaishou and Weibo require `allow_full_history=true` before any Author or Subscription write; equivalent CLI and API drafts use the same policy builder.
- SQLite same-draft concurrent creates converge to one Account or Subscription through a workbench-scoped immediate writer reservation; no schema or migration changed.
- Login start invokes the same preflight evaluator immediately before allocating its process-local Operation. Failed mandatory checks allocate no new Operation, LoginSession or child.
- Exact-session QR tests cover active-session ownership, non-QR rejection, abandoned-session reconciliation, bounded regular-file reads, post-read session revalidation and terminal non-disclosure.
- The complete Python suite passes with `2135 passed, 3 skipped`; all frontend and static/package gates pass. No offline test is treated as real platform qualification.

## Accepted deviation and deferred boundaries

The successful preflight snapshot and the later process-local Operation/background login service are not one cross-process atomic transaction. Two API processes can therefore pass preflight concurrently before the durable login boundary selects a winner. Existing `LoginSession` compare-and-set rules and the account OS lock remain authoritative and make the losing attempt fail closed, so this is a non-blocking coordination/UX residual rather than a credential or QR-authority bypass. Durable Operations, cross-process idempotency, Event storage, SSE, structured logs, cancellation, restart-surviving history, subscription audit/deletion and support bundles remain Execution 0052.

Rich content recovery remains 0053, media-server control/qualification remains 0054, operator authentication remains 0055, and final migration/release remains 0056. Execution 0047 still owns Linux persistence/backup/process evidence, all seven real-account rows and real Emby/Jellyfin rescan/playback.
