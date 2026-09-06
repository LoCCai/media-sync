**English** | [中文](progress.zh.md)

# Progress

Implemented, verified and pushed as `47eeb11`: final login397passed; broader workflow759passed/1Windows-inapplicable skip; Web705passed. Fresh fetch confirmed local/remote equality. Details and the following documentation-only publication record are in [verification](verification.md).

- QR results now distinguish `upstream_login_exited`, `upstream_browser_timeout` and `login_confirmation_failed`, without changing the frame shape or exposing exception text. Strict summaries and exact-session diagnostics preserve them through real session/operation persistence. Historical `failed` stays unknown rather than acquiring an invented cause. Authenticated accounts were not changed; a real-service API regression verifies another authenticated account stays unchanged.
- Accounts and Jobs explain the new statuses, distinguish an existing generic record from absent diagnostics, and show a neutral login phase instead of an unknown phase. Subscription/library guidance presents automatic local directory writes as the normal supervisor workflow; manual publishing is maintenance. Internal export/API compatibility is preserved.
- Bili continuation is configurable through `MEDIA_SYNC_BILI_SCAN_CONTINUATION_DELAY_SECONDS`: default300,0 disables, otherwise60..604800 and capped by the ordinary interval. Only an exact successful Job/Run with current authenticated account/author/upstream/scope/checkpoint and pending cursor context qualifies. Unknown, stale, paused/deleted or failed records retain existing behavior. Worker, API/CLI control paths, restart reconciliation and supervisor share the policy. An empty lane is not permanent historical completion.
- [Next delivery](next-delivery.md) prioritizes editable common/platform directories, one-subscription complete execution, permanent per-feed history-to-incremental state, partial verified-content publication and real acceptance. These are pending, not hidden behind renamed buttons.

Production inspection used the computer-use skill's browser route and read only Accounts, the exact DY operation and the diagnostics page. The page's environment preflight reported locked checkout/Chromium/tools ready; this does not identify the old46-second failure. No credentials/raw logs, new login, download, deployment or supervisor restart. Deferred avatar research remains lower priority.
