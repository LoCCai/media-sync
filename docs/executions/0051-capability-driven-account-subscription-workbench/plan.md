**English** | [中文](plan.zh.md)

# Execution 0051 plan

- Status: Executed and verified for the offline workbench scope
- Plan date: 2026-09-04
- Baseline: `38e0ebe`
- Database migration: None
- Implementation commits: backend `6ed7ab3`; Web `178e557`
- Closeout commit: the commit containing the final record (self SHA not embedded)

## Baseline decision

Execution 0047 remains the P0 release gate, but its remaining Linux persistence/backup/process checks and all live account/media-server evidence require operator infrastructure and credentials. They were not simulated on this Windows authoring workstation. Execution 0051 therefore delivered the independently testable P1 account/subscription workbench without claiming any live qualification.

The original follow-up design also mentioned SSE, durable login-operation history and audit events. Their storage and cross-process coordination substrate belongs to 0052, so this execution retained bounded polling and process-local Operations while closing the capability, draft, preflight, QR-ownership and UI slice.

## Executed sequence

1. Restored the locked frontend dependency graph and retained the recorded pre-change Python/repository baseline.
2. Added the typed v1 MediaCrawler capability module and `GET /api/v1/platform-capabilities`, with closed fields and complete seven-platform tests.
3. Added a shared application workbench for account/subscription validation, preview, idempotent creation, fixed errors and redaction-safe result projections; wired both CLI and REST to it.
4. Centralized conservative MediaCrawler creator-ID normalization, limited creator secret references to XHS and enforced the four audited full-history acknowledgements before mutation.
5. Added `GET /api/v1/accounts/{account_id}/login-preflight`; login start runs the same evaluator before process-local Operation allocation and excludes unrelated download/export tools.
6. Added `GET /api/v1/login-sessions/{login_session_id}/qr.png`, hardened stale-image cleanup and made the account compatibility route resolve into the exact-session path.
7. Upgraded Accounts with server capabilities, composite state, preflight facts and session-bound QR polling; upgraded Subscriptions to account selection, creator/policy input and server-preview/confirmation stages with safe detail summaries.
8. Added backend capability/workbench/preflight/API/CLI/login contracts plus frontend workbench-state tests, including concurrent convergence, no-write rejection and secret/path/cursor sentinels.
9. Ran complete Python, Web, static, package, documentation and upstream-lock gates and recorded all real-account/media-server rows without change.

## Design constraints

- FastAPI remains the browser's only business entry point; the Svelte frontend does not open SQLite or read runtime files directly.
- Capability metadata is static, bounded, versioned and server owned. It carries no credential values, creator authority, signed URLs or local paths.
- Validation precedes persistence. The SQLite immediate-writer reservation is a local idempotency/concurrency mechanism, not a schema change or a claim of distributed locking.
- QR bytes remain short-lived account-runtime material. Serving requires exact QR-session ownership, active-state proof, bounded same-file reads and a post-read durable recheck.
- Existing `/api/v1` account QR behavior remains compatible, but exact-session identity is authoritative for a particular attempt.
- UI behavior remains useful without SSE through bounded polling; durable reconnect/history semantics are not claimed in 0051.

## Recorded deviation

Preflight and login start share one evaluator, but a successful preflight result is a snapshot. Its transition into the process-local Operation registry and background application service is not atomic across multiple API processes. The subsequent durable LoginSession compare-and-set and account OS lock reject a loser safely, so this does not block the offline 0051 boundary. Removing the transient losing Operation and providing cross-process idempotent operation ownership requires the durable Operation/Event substrate planned for 0052.

## Verification result

- Python complete suite: `2135 passed, 3 skipped`.
- Web: Prettier, `svelte-check`, seven Vitest tests and adapter-static production build all pass.
- Static/package: Ruff, Ruff format, strict mypy across 90 source files, compileall and `uv build` all pass.
- Repository: bilingual documentation and both locked upstream SHA/remote/clean-checkout gates pass; `.upstream` and `.mimosa/` remain untouched.
- Live: no browser account, creator endpoint, CDN bytes or Emby/Jellyfin server was used; every such row remains `NOT_RUN` under 0047.

## Commit policy

The original goal/plan baseline remains the first bilingual checkpoint. Backend implementation/tests were committed as `6ed7ab3`, and Web implementation/tests as `178e557`; this closeout is committed separately with a bilingual subject and body. Generated frontend output, `node_modules`, local databases, raw junit XML, `.mimosa/` and both locked upstream checkouts remain outside the commit. Push and local/remote SHA reconciliation happen only after the closeout commit exists.
