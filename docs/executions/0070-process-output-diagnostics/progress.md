[**English**](progress.md) | [中文](progress.zh.md)

# Progress

Status: implementation and offline release gates complete; implementation commit `b22e938` is published to `origin/main`, with this closeout record following in the documentation commit.

- Added one bounded process-output capture primitive on the existing private `state_dir/logs` JSONL store. Each child attempt is capped at 4 MiB, 4,096 lines, and 64 KiB per raw line. Invalid encoding, oversized lines, exhausted budgets, policy filtering, and rejected sink writes are retained only as fixed counters.
- Wired QR-login output without corrupting its result or event frames. The parent snapshots only canonical `operation_id` and `correlation_id`; the committed callback contributes the exact `login_session_id`; the child removes and validates the closed environment envelope before importing upstream code. Local account/platform facts override propagated input.
- Wired the generic MediaCrawler creator runner. Its safe events retain the exact manifest account, subscription, Job, Run, platform, and attempt, plus a canonical parent Operation correlation when present. Protocol stdout is drained and summarized but never stored as free text.
- Added the closed `process_output`, `process_output_summary`, and `process_output_dropped` events. Free-form text is allowed only for `process_output` and is independently revalidated at the event boundary.
- Added fail-closed filtering for Cookie objects, `Set-Cookie`, Authorization, storage state, QR/base64 material, JWT/opaque credentials, signed URLs, private Windows/POSIX paths, structured JSON, HTML/DOM, and likely creator-content fields. Unsafe lines become fixed `[REDACTED]` evidence or a drop count.
- Independent review found that the pinned MediaCrawler prefix (`timestamp MediaCrawler LEVEL (file:line) - message`) was initially policy-filtered. Capture and event validation now share one exact normalizer that converts it to `LEVEL message` before applying the same fail-closed content and secret filters. Real-format QR and creator-child contract tests cover both retained diagnostics and hostile payload rejection.
- Extended the authenticated log center to parse and display the safe message, stream, summary counts, and Chinese drop/error explanations. Normal failures and reconciled `interrupted` logins retain a unique trusted Operation ID and link directly from Accounts to the exact Operation-filtered log view; an interrupted state never invents a runner result.
- A read-only closeout inspection of the currently deployed log center found the latest Douyin attempt launching Chromium successfully in 199 ms, then timing out after 30,005 ms while opening the platform page; the Operation reached terminal failure after 40,501 ms. That deployed revision has no captured child-process output for the attempt, so it cannot distinguish proxy/network/page-response/upstream-adapter causes. No retry was triggered.
- No deployment, supervisor restart, production login, creator crawl, download, or media-server action was performed. The old deployment's discarded output remains unrecoverable.

## Remaining work

- Connect the same capture policy to independent Cookie-validation, creator-profile, detail, and download runners. Their existing closed lifecycle events remain available, but their child output is not yet retained.
- Deploy this revision and reproduce exactly one failed QR platform under operator control. Only that new run can establish whether the real cause is browser launch, navigation, network, platform challenge, timeout, or another runtime failure.
- Continue the seven-platform subscription, historical backfill, risk-aware download, incremental refresh, and Emby/Jellyfin-compatible directory objective. This observability increment supplies evidence; it does not itself repair a platform login.
