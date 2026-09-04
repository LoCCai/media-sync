**English** | [中文](goal.zh.md)

# Execution 0051 goal

- Status: Planned; implementation not started
- Date: 2026-09-04
- Predecessor: `38e0ebe` (green Linux runtime preflight after Console v2)
- Scope: capability-driven account login and creator-subscription workbench
- Database migration: None
- Plan commit: the commit containing this record (self SHA not embedded)

## Outcome

1. Establish one bounded seven-platform capability contract for login methods, creator-input rules, required full-history acknowledgement, qualified offline media shapes, known limitations and honest live-qualification state.
2. Move account/subscription draft validation and creation into a shared application service used by both CLI and REST API. Reject invalid or unacknowledged drafts before any Account, Author or Subscription row is written, and never return credential or creator-secret reference values.
3. Add an account-scoped login preflight that checks only login prerequisites. Missing ffmpeg/ffprobe must not block login, while database, license, checkout, runtime, browser/profile and account-lock failures must stop before an Operation or child process starts.
4. Bind QR retrieval to the exact `LoginSession` while retaining the account-scoped endpoint for compatibility. Preserve the explicit `202` pending, `200` image, `410` terminal and `404` unknown lifecycle.
5. Upgrade the accounts and subscriptions routes into a capability-driven workbench: explain composite account state and preflight failures, then guide subscription creation through account/platform selection, validated creator preview and policy confirmation.
6. Expose safe subscription-policy and checkpoint summaries in detail views without returning raw cursor values, signed creator URLs, credential references, profile paths or private runtime paths.

## Acceptance boundaries

- All seven MediaCrawler platform identifiers have one server-owned capability description and frontend rendering consumes that description instead of duplicating platform rules.
- Bilibili, Douyin, Kuaishou and Weibo subscription drafts require explicit full-history acknowledgement before any persistent mutation; CLI and API produce the same policy payload for an equivalent accepted draft.
- Login preflight and login start use the same evaluator. A failed mandatory check cannot allocate an in-memory Operation, create a `LoginSession`, or launch a child.
- QR responses are tied to an exact session identity; compatibility behavior cannot return an image for a different attempt.
- Sentinel tests prove secrets, signed URLs, raw cursors and local paths do not appear in capability, preview, account, subscription or QR metadata responses.
- Offline tests do not qualify a real platform. Every live login/crawl/CDN and real Emby/Jellyfin row remains `NOT_RUN` until Execution 0047 operator evidence exists.

## Explicitly deferred

Durable Operation/Event storage, SSE, structured logs, generic cancellation, restart-surviving operation history, subscription deletion/audit and support bundles remain Execution 0052. Rich content recovery remains 0053, media-server control/qualification remains 0054, operator authentication remains 0055, and final migration/release remains 0056.
