**English** | [中文](progress.zh.md)

# Progress

- Status: Login and Worker-display corrections implemented; local gates passed; authorized live canary failed.

Read-only production UI: Bilibili persisted account uses saved_session/authenticated; latest Operation, LoginSession and runner agree on success (18:42:03–18:42:48). The same accounts page displays blocked account_login_ineligible. Nine Operations exist (one success, eight historical failures), zero Jobs and zero subscriptions. No new login, Cookie extraction or production mutation was performed for this inspection.

Independent synthetic reproduction with original pong always False still reached authenticated after update_cookies; no real credential or platform was used. This proves a code path defect, not that this operator's login was false. Under frozen plan b018979, BILI-only post-update remote confirmation and authenticated-account neutral preflight are implemented. Backend re-login eligibility is unchanged; stale UI readiness cannot enable re-login.

## Authorized live canary

The operator selected author UID 252671524, explicitly accepted possible full-history traversal, and confirmed stopping the resident supervisor. The browser performed local-only author preview, created one test subscription, materialized one Job, and started one sync worker with the existing saved-session account. The form set max_items=1 and request delay=5 seconds, but this Bili upstream path ignores that item cap for both crawl and resulting metadata ingestion; it is not a one-item guarantee. No agent accepted a license, extracted a credential, started another login, retried the Job or dispatched download/export.

The attempt ran 18:53:18–18:57:14 (about 236 seconds), ending failed_terminal with zero content records. Its Worker Operation succeeded only in processing one Job; the summary reports processed_count=1 and status_counts.failed_terminal=1. The test subscription is paused and the queue has no pending Job or active Operation. The account remains authenticated/saved_session. Supervisor remains stopped per the operator; no pipeline Job was observed.

Two operator-run read-only queries are separate evidence: the initial SyncRun error query returned not_available (ambiguous absent row/null code); the subsequent exact Job-to-Run join confirmed Job exists, job_error=schema_invalid, Run exists, run_status=running, run_error=none. This does not prove invalid Cookie, missing author, or a platform-specific exception. Scheduler paths can fail/stop a Job without mirroring failure into its attached Run; heartbeat/result/finalization failures need more precise safe diagnosis. Do not manually rewrite that historical Run, mark qualification PASS, or automatically retry to hide it.

The observed Worker-success/Job-failure ambiguity motivated separately committed addendum 9602246. Its console projection now distinguishes Worker completion from strictly validated Job outcomes; durable Operation semantics are unchanged. There was no existing completion toast, so no notification lifecycle was added. Final Web gates pass for 269 tests and the static build. Live capture is FAILED, fresh-session authentication proof remains unqualified, download and Emby/Jellyfin playback remain NOT_RUN. Pasted-Cookie validation/save/reuse remains accepted and unimplemented; its independent vault and strict remote proof plan still needs to be frozen before implementation. Seven-platform scope is unchanged.

## Next execution order

1. Freeze precise scheduler diagnostics for heartbeat/storage/result/finalization failures, preserving successful Run truth, lease fencing and process cleanup. Diagnose the observed schema_invalid without guessing or rewriting historical data.
2. Verify an explicitly bounded creator path and the failed canary after an operator-controlled deployment; do not silently retry this paused subscription.
3. Deliver the independently planned pasted-Cookie validation/private save/reuse slice, then establish the other platform contracts and continue archive/playback qualification. Current UI changes do not implement Cookie entry.
