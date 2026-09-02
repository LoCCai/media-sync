**English** | [中文](goal.zh.md)

# Execution 0012 goal

- Status: Complete for the offline single-host foreground scope; live qualification remains `NOT_RUN`
- Started: 2026-08-31 03:46 +08:00
- Completed: 2026-08-31 04:54 +08:00
- Predecessor: Execution 0011 closeout commit `11ec5fd`
- Plan commit: `4494226`
- Implementation commit: `28655f8`

## Outcome

Deliver a locally resident, single-host foreground supervisor together with hard-parent-death containment for interactive MediaCrawler login and deadline-bound recovery of abandoned LoginSession state. A killed login parent must not leave its login child/browser tree running, an expired abandoned attempt must become retryable without manual SQLite edits, and one resident loop must drive due schedules through subscription sync and the already-durable download/Emby pipeline while applying phase-correct shutdown.

## Delivered evidence boundary

Execution 0012 closes the predecessor gaps for the documented local boundary. The login child now uses bounded request/result length frames, continuing START/CANCEL/EOF control and a post-result guardian. Windows and POSIX hard-parent-death contracts prove the owned child/grandchild tree exits before the inherited account lock becomes reusable, including the exact result-read/pre-control-close window. Deadline-expired durable state can be reconciled under the same account lock and exact repository CAS; rotating bounded enumeration prevents an early busy candidate from starving later accounts. The explicit `scheduler supervise` command fairly runs reconciliation, tick, subscription and pipeline phases, with cancellation-resilient exact joins.

Automated evidence is offline. The Fake supervisor integration proves durable sync and pipeline Jobs can reach success in one cycle, but it does not prove real creator traffic, signed CDN download, FFmpeg handling of real media or Emby/Jellyfin rescan/playback. The process remains a foreground local command, not daemonization, automatic restart, OS service integration, Docker or cross-host HA.

## Acceptance

1. **Start-gated parent control** — the login child accepts one bounded, versioned request frame and a separate START control before importing upstream code or creating browser/profile side effects. The parent keeps the control stream open; explicit CANCEL, unexpected EOF, malformed control and setup failure all fail closed.
2. **Hard-parent-death containment** — on POSIX and Windows, parent death causes the owned login child and descendant tree to exit within a bounded interval. Windows retains the outer kill-on-close Job and adds child-owned descendant containment; POSIX never targets an ambient process group. The account lock is unavailable while the owned tree lives and reusable only after the complete tree exits.
3. **Exact deadline recovery** — only the current MediaCrawler `pending|waiting_user` session whose `expires_at <= now` and exact Account is still `qr/authenticating` may be atomically changed to `expired` plus `qr/required`. Recovery runs only while holding the same per-account filesystem lock, is idempotent and CAS-fenced, rejects state/account/sibling drift, and requires no PID trust or schema migration.
4. **Reachable self-healing** — login start and redaction-safe login status reconcile an eligible expired attempt before acting; the resident supervisor also sweeps eligible accounts. A new login can then start one successor, and any late completion from the old attempt cannot overwrite the successor. Recovery before the durable deadline is explicitly not claimed.
5. **Resident full-chain boundary** — add one explicit local foreground supervisor command that fairly repeats stale-login reconciliation, bounded schedule materialization, bounded subscription sync and bounded `pipeline.subscription` work with the same MediaCrawler/download enable and license gates. A Fake end-to-end path reaches pipeline success without separate `scheduler run` or `pipeline run` invocations. Loop limits and intervals are bounded and validated.
6. **Phase-correct cooperative stop** — a stop request prevents every later tick and claim. An active subscription task is cancelled and awaited so its MediaCrawler parent-control path joins the child tree. An active thread-backed pipeline attempt is not falsely cancelled: heartbeats continue and the supervisor drains that one attempt to its authoritative result, then exits without claiming a successor. A second forceful operator interruption and hard-kill recovery remain lease-fenced rather than being called graceful completion.
7. **Truthful exclusion** — the command is a foreground local process, not automatic restart, daemonization, Windows Service/systemd integration, Docker or cross-host HA. REST and real browser/account/platform/CDN/Emby/Jellyfin qualification remain outside this execution; all seven live rows remain `NOT_RUN`.
8. **Closed observability and verification** — CLI output, SQLite, logs, docs and Git contain no QR bytes, Cookie, raw upstream output, tokens or profile paths. Focused race/process/CLI tests, the full suite, lint, formatting, typing, docs/upstream checks, build and retained-artifact/secret audits must pass before completion is claimed.

## Recovery timing decision

The retained login ordering releases the account lock before the application writes the final LoginSession/Account transition. Execution 0012 therefore uses the durable session deadline as recovery authority and never treats “the lock is currently free” as abandonment proof. An authenticated result that misses its durable deadline remains a timeout rather than gaining authority from child completion.
