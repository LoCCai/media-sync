**English** | [中文](next-delivery.zh.md)

# Next-version priority: log center and diagnosable QR login

Status: added by the user during0067; NOT_IMPLEMENTED. This precedes avatar expansion without replacing the subscription→history→download→incremental goal.

## Required result

1. One log center covers API, login/profile/crawl children, scheduler/supervisor, download/archive/directory publication. Filter by time/platform/account/severity and operation/session/job/run relationships; open directly from task details instead of aggregate error counts only.
2. Persist JSONL rolling segments in a private mounted directory. Define size/time rotation, retention and a total storage bound; separate process-owned segments or one collector prevents competing multi-process RotatingFileHandlers. Freeze defaults in the implementation plan and expose configuration. Rotation/truncation/loss must be visible; never fill the disk unboundedly.
3. Capture observable browser launch, platform navigation, login entry, QR acquisition, scan wait, self-session confirmation and save stages with elapsed time. Retain bounded action categories, allowed upstream module/function/line frames, exception types, allowed host/route templates and response status. Unobserved stages remain unknown; timeouts do not prove network or risk-control causes.
4. Do not merely unmute raw stdout/stderr. Add a bounded, versioned diagnostic side channel with closed fields, keeping the existing result frame strict and locked upstream files intact. No Cookie/Authorization/token/QR/signed query, response bodies, locals or raw exception messages in ordinary logs. Unknown text becomes fixed categories/discard counters; any deeper diagnostics require explicitly safe structures.
5. One-click operation-scoped diagnostic packages include app/upstream versions, stage events, safe stack frames, component segments and retention coverage. User-requested local download only, no automatic external upload. Plain-language failure/next-step views with expandable developer evidence.

## Acceptance gates

- Inject navigation/login-entry/QR/confirmation timeouts and child exits; distinguish stages through child→persistent segment→API→UI→downloaded diagnostic package.
- Test long/no-newline/multibyte fragments, truncation, duplicate events, concurrent writers, readers during rotation, restart, full disk and denied writes; bounded results must not block scheduling and lost/expired evidence must be visible.
- Scan logs/database/packages/UI for secret sentinels including overflow and exception paths. Reject arbitrary file selectors, traversal, links/reparse points and unauthenticated downloads; bounded paging/responses.
- Preserve authenticated accounts and do not auto-retry. After deployment, obtain scoped authorization for one controlled failed-platform retry per case; retain cause/fix/acceptance evidence, never convert offline tests into live success.

## Current evidence and limits

DY/KS/Tieba/WB show upstream_browser_timeout; WB lasted43seconds. Previously discarded exact actions/stacks cannot be recovered.0066 preserved fixed status classifications but did not implement full logs;0067 does not fix these live failures. Do not ask for another undiagnosed round of repeated scans.

After logging: exact-author subscription execution, bounded backfill progress and durable history-complete/incremental state, bounded live file delivery, remaining platform media shapes. Respect pacing and verification; logging/retries must not bypass risk-control.
