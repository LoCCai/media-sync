**English** | [中文](goal.zh.md)

# Execution 0047 goal

- Status: Awaiting operator — this is the final gate of the original combined plan and stays open until live rows are recorded
- Date: 2026-09-03
- Predecessor: Execution 0046 (security review and release checklist); roadmap Phase 5 consolidated here by execution 0042
- Scope: Operator-assisted live qualification of all seven platforms on the Linux deployment host — QR/Cookie login, one creator subscription, incremental re-run, media download and Emby re-scan per platform — using user-authorized accounts only

## Outcome (to be recorded by the operator)

1. Per platform (`xhs`, `dy`, `ks`, `bili`, `wb`, `tieba`, `zhihu`): a reproducible smoke-test record in this directory — login method used, challenges encountered, creator scanned, item counts, media bytes archived, Emby tree output — or an explicit `BLOCKED_EXTERNAL` row when credentials are unavailable.
2. The platform-capabilities matrix ([`docs/platform-capabilities.md`](../../platform-capabilities.md)) updated from live truth instead of source-derived claims.
3. The completion archive ([`docs/archive/upstream-replication-review.md`](../../archive/upstream-replication-review.md)) live rows flipped from `NOT_RUN` to recorded outcomes.
4. Verification numbers for the full offline suite from the deployment host attached once, applying to all platform records.

## Acceptance boundaries

- Every row is recorded as it actually ran; `NOT_RUN`/`BLOCKED_EXTERNAL` never silently become pass. No simulated or fixture result may stand in for a live row.
- Accounts are the operator's own; crawl volumes stay bounded (small `max_items`, polite delays) per the SAFE requirements.
- No local deployment verification: all rows execute on the Linux host.

## Explicitly deferred

Multi-account fleets, long-duration soak tests, media-server playback tuning beyond a basic scan/play check.
