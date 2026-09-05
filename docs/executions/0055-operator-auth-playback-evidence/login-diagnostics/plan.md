**English** | [中文](plan.zh.md)

# Actionable login diagnostics plan

- Date: 2026-09-05
- Status: Frozen before implementation

1. Commit bilingual goal/plan/progress/verification before code. Preserve all previous frozen plans.
2. Add closed runner status `browser_launch_failed`, retaining the v1 two-field frame. Current readers accept old frames; older readers reject the new status safely (not forward-compatible). Shared browser policy preserves exception identity by default; login opts into classification only around the two real Chromium launch awaits. Preserve BaseException/cancellation and parent timeout/invalid-result/tree-cleanup precedence. Same-mode installation is idempotent; conflicting modes reject safely.
3. Add the new value to the fixed Operation summary contract and map it to `operation_login_browser_launch_failed`. Do not add result fields or DB columns. Restart recovery must retain generic failure when the original runner disposition is unavailable.
4. Project optional `diagnostic` on login-status (API and CLI): `{operation_id, operation_state, runner_status, error_code}` or null. Query at most two Operations by the exact latest session. Require one candidate, correct account target, one matching execution subject and consistent result account/session IDs. Unknown/missing/ambiguous/malformed data fails closed; use only fixed state/code allowlists, never raw persisted strings. No account-wide latest fallback, historical backfill or log parsing.
5. Add shared fixed Chinese UI explanations. Keep readiness explicitly separate from authentication; persist latest-session explanation after reload. Read Operation state independently of QR delivery, render all terminal states without a spinner, stop polling on an observed terminal state and clear stale QR data. No automatic retry writes or new login.
6. Cover runtime classification, legacy frames/recovery, exact identity/races/redaction, API/CLI and UI state handling. Run relevant broader Python regressions and serial Web format/test/check/build. Use synthetic/local browser fixtures only when practical; never use production credentials to test a patch.
7. Save measured results and remaining live gates, review independently, use bilingual local commits, push and verify GitHub identity/cleanliness. Keep the overall goal active and the actual deployed-image/platform outcome unverified until operator evidence arrives.
