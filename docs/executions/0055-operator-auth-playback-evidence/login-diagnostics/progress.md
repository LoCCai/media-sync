**English** | [中文](progress.zh.md)

# Login diagnostics progress

- Status: Implemented and locally verified; repair commit `1e487f4` published

Frozen plan `488ce20` is implemented. Login alone opts into `browser_launch_failed` at the actual Chromium launch awaits; creator/detail retain exception identity. The strict v1 two-field protocol accepts legacy frames and the new closed status, but older readers safely reject that new status. Parent cancellation/timeout/tree-cleanup precedence remains unchanged.

API and CLI now project an optional four-field diagnostic from at most two exact-session candidate Operations and at most two execution subjects. Canonical identities, the only execution subject, validated summary, terminal state and runner/error/auth/session consistency must all match; invalid stored JSON or ambiguous/malformed data yields null. No migration/backfill/raw-log parsing is performed. Recovery without the original disposition remains generic.

Accounts preserve latest-session explanations separately from readiness; Jobs show the same fixed explanation. Independent Operation/QR channels prevent a failed or hung image request from masking an observed terminal result. All terminal states stop polling, remove/revoke stale QR data, and render without an active spinner. No login write is retried automatically.

Independent review closed two projection issues (extra execution-subject types and contradictory completion tuples). Root runtime/Web review found no remaining blocking finding within this scope. Actual commands, failed first runs, reruns and residual/live limits are in [verification](verification.md). New deployed failures and the subsequent Node/QR omissions are handled by [runtime follow-up](../login-runtime-followup/progress.md). Pasted-Cookie login is accepted but not implemented; see its [draft plan](../cookie-login/plan.md).
