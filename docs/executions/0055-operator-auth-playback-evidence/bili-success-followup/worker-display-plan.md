**English** | [中文](worker-display-plan.zh.md)

# Addendum: distinguish worker completion from capture outcome

- Date: 2026-09-05
- Status: Frozen before implementation of this addendum
- Parent: [original plan](plan.md), committed as b018979

The authorized production canary completed one attempt in about 236 seconds: Job failed_terminal, no content records, but scheduler-run Operation succeeded with processed_count=1 and status_counts.failed_terminal=1. Subscription is now paused; the operator stopped supervisor. No retry, download or export was started. This observation justifies a narrow console correction, not changing durable Operation semantics.

For scheduler-run only, render succeeded Operation as “Worker completed”, and derive a separate fixed business-outcome notice from the existing bounded status_counts summary. Failures/waiting/empty/unknown results must never imply successful capture. Accept only the known summary keys, known statuses and nonnegative safe integer counts with matching totals; malformed summaries use fixed unavailable copy without reflecting values. Apply shared logic to operation table/detail and relevant completion toast. Do not change API, database, replay, cancellation or other Operation kinds.

Cover one failed-terminal, retryable/mixed/waiting, successful, idle/empty and malformed summaries; verify existing login diagnostics unaffected. Re-run serial Web gates and update the parent progress/verification. Actual capture failure diagnosis is separate and still awaiting its safe run error code. Pasted-Cookie implementation and seven-platform goal remain pending.
