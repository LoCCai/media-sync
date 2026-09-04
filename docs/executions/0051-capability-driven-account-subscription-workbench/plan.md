**English** | [中文](plan.zh.md)

# Execution 0051 plan

- Status: Active
- Plan date: 2026-09-04
- Baseline: `38e0ebe`
- Database migration: None
- Plan commit: the commit containing this record (self SHA not embedded)

## Baseline decision

Execution 0047 remains the P0 release gate, but its remaining Linux persistence/backup/process checks and all live account/media-server evidence require operator infrastructure and credentials. They remain open and are not simulated on this Windows authoring workstation. Execution 0051 is the next independently deliverable P1 slice.

The original 0051 design also mentioned SSE, durable login-operation history and audit events, although their storage/event substrate is assigned to 0052. This execution therefore closes the account/subscription correctness and workbench slice without silently pulling 0052 forward. The deferred boundaries remain explicit in the goal and closeout.

## Delivery sequence

1. Restore the locked frontend dependency graph and run the pre-change Python/Web baseline.
2. Add a typed MediaCrawler platform-capability module and a redaction-safe `/api/v1/platform-capabilities` projection with complete seven-platform contract tests.
3. Add a shared application workbench service for account and subscription drafts; route both CLI and API through it, normalize supported creator inputs, require platform-specific full-history acknowledgement before writes, and return only safe summaries.
4. Add an account-login preflight evaluator and endpoint. Reuse it atomically from login start before Operation allocation, and distinguish mandatory login checks from unrelated download/export tooling.
5. Add an exact LoginSession QR endpoint and make the account compatibility endpoint resolve and prove the current session before serving any image. Update the frontend polling flow to switch to the returned session identity.
6. Upgrade the account UI with capabilities, composite status and a login-preflight panel; upgrade subscription creation to a three-step capability-driven wizard and extend detail with safe policy/checkpoint summaries.
7. Add backend unit/API/CLI integration tests and frontend state/formatting tests, including no-write-on-reject, concurrency, lifecycle and secret-sentinel cases.
8. Run focused tests, frontend formatting/type/tests/build, Ruff/format/mypy/compileall/package/docs/upstream gates and the complete Python suite. Record platform/Docker/live rows as `NOT_RUN` unless real evidence is supplied.
9. Update bilingual progress, verification, status, roadmap and execution index records; create bilingual implementation/closeout commits, push `main`, and reconcile local/remote SHA.

## Design constraints

- FastAPI remains the only browser business entry point; the frontend never opens SQLite or reads runtime files directly.
- Capability metadata is static, bounded, versioned and server owned. It must not carry cookies, tokens, signed URLs or paths.
- Draft validation completes before persistence. Transaction rollback is defense in depth, not the primary validation mechanism.
- Existing schema and migration count stay unchanged; this slice reads existing `Account`, `LoginSession`, `Subscription`, `SyncRun` and scheduler records.
- The account-scoped QR route remains compatible, but only the session-scoped route is authoritative for a particular attempt.
- UI behavior remains useful without SSE through bounded polling; persistence/reconnect semantics are not claimed before 0052.

## Verification plan

- Python focus: new workbench/capability/preflight units, API contract, CLI workflow, authentication/login repository and scheduler compatibility.
- Frontend: frozen pnpm install, Prettier, `svelte-check`, Vitest and adapter-static production build.
- Static/package: Ruff, Ruff format, strict mypy, compileall and `uv build`.
- Repository: bilingual documentation checker, upstream lock verifier, clean locked checkouts, forbidden-output audit and `git diff --check`.
- Complete suite: run the full Windows suite and report its exact result, including any recurrence of the known completion-receipt/process family; Linux Phase B stays authoritative.

## Commit policy

Commit the bilingual goal/plan and initial baseline record before implementation. Commit implementation/tests with a bilingual subject and body after focused gates. Commit final progress/verification/status closeout separately when useful, then push `main` and compare `HEAD`, `origin/main` and GitHub's advertised ref. Never stage `.mimosa/`, generated frontend output, `node_modules`, local databases, raw junit XML or either locked upstream checkout.
