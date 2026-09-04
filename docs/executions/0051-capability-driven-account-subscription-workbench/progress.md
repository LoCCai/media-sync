**English** | [中文](progress.zh.md)

# Execution 0051 progress

- Status: Implemented and offline-verified; live qualification remains `NOT_RUN`
- Date: 2026-09-04
- Baseline: `38e0ebe`
- Database migration: None

## Delivered

1. Added `GET /api/v1/platform-capabilities` and one server-owned v1 contract in the fixed order `xhs`, `dy`, `ks`, `bili`, `wb`, `tieba`, `zhihu`. The contract describes login methods, QR support, creator guidance, qualified media shapes, limitations and honest live-evidence state.
2. Centralized MediaCrawler creator input at the conservative `[A-Za-z0-9._-]{1,255}` boundary. Only XHS accepts an opaque creator secret reference; Bilibili, Douyin, Kuaishou and Weibo require `allow_full_history=true` before any Author or Subscription mutation.
3. Added a shared application `WorkbenchService` for CLI and REST account/subscription validation, preview and idempotent creation. The CLI retains its legacy JSON output while both entry points now use the same policy and persistence rules.
4. Added login-specific preflight for database, account eligibility, licence, checkout, runtime, browser, profile writability and account lock. Login start invokes the same evaluator before allocating a process-local Operation; ffmpeg and ffprobe are deliberately excluded.
5. Added exact `LoginSession` QR routing while retaining the account route as a compatibility resolver. A new QR attempt removes stale material under the account lock, and serving uses a bounded 2 MiB regular-file read with inode/size checks followed by durable session revalidation.
6. Upgraded Accounts with capability metadata, composite state, preflight diagnostics and session-bound QR polling. Upgraded Subscriptions to the three stages of account selection, creator/policy input, and server preview plus explicit confirmation.
7. Added allowlisted policy and checkpoint summaries. Raw cursor values, signed creator URLs, credential/secret references and local profile/runtime paths are not returned, and request-validation failures do not echo malicious input.

## Security and concurrency result

- Invalid or unacknowledged drafts fail before Account, Author or Subscription writes. SQLite fresh mutations take a workbench-scoped `BEGIN IMMEDIATE` writer reservation, so equivalent concurrent drafts converge to one durable Account or Subscription without a schema change or migration.
- QR responses retain the `202` pending, `200` image, `410` terminal and `404` unknown/ineligible lifecycle. Exact active-session ownership, QR method eligibility, abandonment reconciliation, regular-file and size bounds, same-file checks and the post-read session check all fail closed.
- A successful login preflight is a snapshot. Its transition through a process-local Operation into the background login service is not atomic across API processes, so two processes may both pass preflight. Durable `LoginSession` compare-and-set and the account OS lock remain authoritative and close the losing attempt safely.
- That preflight-to-Operation race is a non-blocking coordination and UX residual, not the QR read/revalidation interval and not a credential or QR-authority bypass. Durable Operations and cross-process idempotency are assigned to Execution 0052.

## Verification result

- Complete Python suite: `2135 passed, 3 skipped`.
- Web: Prettier, `svelte-check` with 0 errors and 0 warnings, seven Vitest tests, and the adapter-static production build all pass.
- Static/package: Ruff, Ruff format, strict mypy across 90 source files, compileall and `uv build` all pass; both sdist and wheel were produced.
- Documentation and locked-upstream checks pass. MediaCrawler remains at `d6f7c5bb906b6dac40ddf343ef9e26438a3de092`, bili-sync-up remains at `dcb5bb73b56ac45b2525da14b389e185b0ea6dbd`, and both checkouts are clean.
- Focused contracts cover capability shape/order, CLI/API equivalence, no-write rejection, same-draft convergence, preflight allocation boundaries, QR ownership/read hardening, UI state and secret/path/cursor sentinels.

## Remaining work

- No real browser account, creator endpoint, platform API/CDN or Emby/Jellyfin server was used. All seven live-account rows and real rescan/playback evidence remain `NOT_RUN` under Execution 0047.
- Execution 0052 owns durable Operations, cross-process idempotency, Event storage, SSE, structured logs, cancellation, restart-surviving history, subscription audit/deletion and support bundles.
- Execution 0053 retains rich-content recovery; 0054 retains media-server control and qualification; 0055 retains operator authentication; 0056 retains final migration and release work.
