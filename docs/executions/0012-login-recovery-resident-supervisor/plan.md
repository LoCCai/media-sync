**English** | [中文](plan.zh.md)

# Execution 0012 plan

- Status: Executed; all frozen acceptance boundaries retained
- Plan date: 2026-08-31
- Completion date: 2026-08-31
- Predecessor: Execution 0011 closeout commit `11ec5fd`
- Plan commit: `4494226`
- Implementation commit: `28655f8`

## Delivery sequence

1. **Freeze contracts and baseline**
   - Record all four bilingual execution files before implementation and correct the roadmap entry that still asks for the already-created 0011 commit.
   - Re-run the existing generic hard-parent-death and login normal timeout/cancellation tests as the starting baseline.
   - Create a bilingual local plan commit; do not push without a new explicit user instruction.

2. **Keep login under continuing parent control**
   - Reuse or extract the mature fixed control primitives from the scheduled MediaCrawler runner rather than defining an incompatible protocol.
   - Replace EOF-delimited login input with one bounded request frame plus START/CANCEL/EOF control. Attach parent-side containment before START and establish child-side containment/control watching before importing upstream modules. The delivered protocol also length-frames the result so Windows does not depend on standard-pipe EOF while the guardian remains alive.
   - Preserve join-before-lock-release for normal completion, timeout and cancellation, and prove true hard-parent-death cleanup with an owned child/grandchild contract.

3. **Add deadline-fenced durable reconciliation**
   - Add one repository transaction that validates the exact Account and active LoginSession tuple before atomically expiring the session and restoring `qr/required`.
   - Add an application reconciler that enumerates only public candidate identities, acquires each exact per-account lock, repeats repository validation inside the lock, and reports fixed redaction-safe counts/states.
   - Invoke the reconciler before login preflight/status decisions and from the resident supervisor. Cover deadline edges, state/account/profile drift, duplicate contenders, idempotency, successor fencing and transaction rollback.

4. **Add the bounded full-chain resident supervisor**
   - Put the loop in an application/service object with an injected clock/wait primitive so tick, idle and shutdown behavior are deterministic in tests.
   - Expose `scheduler supervise` with bounded idle interval/materialization/sync/pipeline capacities and the existing MediaCrawler plus download/license gates. Fair cycles reconcile expired logins, tick, run subscription work and then pipeline work so either backlog cannot starve the other.
   - On Ctrl+C or termination, stop later ticks/claims. Cancel and await an active subscription task through its child-control/join contract; if the thread-backed pipeline attempt is active, continue its heartbeat and drain only that attempt before returning.

5. **Verify, document and commit**
   - Run focused repository/application/protocol/process/supervisor/CLI gates and exercise Windows-specific hard-kill behavior on this host.
   - Run full pytest, Ruff lint/format, mypy, documentation and pinned-upstream checks, build, `git diff --check`, tracked/runtime artifact checks and a high-confidence secret scan.
   - Update goal/plan/progress/verification with exact commands and results, retain every live row as `NOT_RUN`, then create bilingual local implementation and closeout commits.

## Implementation notes

- Windows retains a standard stdout pipe until process exit even after the child closes CRT descriptor 1. The result channel was therefore upgraded to an exact 4-byte big-endian length plus bounded JSON payload. The parent reads one complete frame, begins control/tree shutdown immediately, then rejects any remainder after join. This preserves the one-frame contract without requiring guardian exit.
- Review found that `(expires_at, id) LIMIT` enumeration could let one permanently busy early account starve later candidates. The delivered reconciler keeps a serialized rotating keyset cursor for global sweeps, wraps at the end, and leaves exact per-account reconciliation cursor-free.
- Review also found that cancelling the supervisor task after a stop-triggered shield drain could orphan the thread-backed pipeline attempt. Subscription cancel/join and pipeline drain are now resilient to repeated task cancellation and propagate the first caller cancellation only after the exact attempt is done.

## Risks and rollback points

- Windows stdin monitoring must use the existing native pipe-read approach; competing buffered reads can block descendant spawning.
- A START handshake must occur only after all parent and child containment prerequisites are ready. Attach/setup failure is a closed start failure, never permission to launch upstream work.
- Deadline recovery deliberately trades immediate retry for race safety. Shortening the deadline or reclaiming merely because a lock is free is outside the frozen contract.
- Cancellation of the existing subscription worker is cooperative and its MediaCrawler handler owns a parent-control/join boundary. A synchronous pipeline handler cannot be force-stopped, so shutdown must drain one active attempt under heartbeat instead of cancelling its asyncio wrapper or releasing an immediate duplicate retry.
- Rollback is removal of the new supervisor/reconciler/control framing while retaining execution 0011 bounded commands and state machine. Existing accounts, subscriptions, Jobs and pipeline records require no destructive migration.
