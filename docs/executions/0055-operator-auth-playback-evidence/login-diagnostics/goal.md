**English** | [中文](goal.zh.md)

# Actionable login diagnostics goal

- Date: 2026-09-05
- Baseline: `f61a3c4`
- Status: Frozen before implementation

Make login failures understandable during the operator-assisted seven-platform canary without leaking upstream data or changing authentication. Preserve the full subscriptions/capture/Emby-Jellyfin objective and the published browser-runtime repair. Previous work made progress: runtime fixes and validation were published, with Linux deployment/scan still pending.

Acceptance: a failure at the exact Chromium launch/persistent-initialization boundary has a fixed safe runner disposition; ordinary upstream failures stay unknown rather than guessed. The latest session may expose only its uniquely and correctly linked existing Operation diagnostic after reload. Accounts and QR views show fixed explanations and next actions, distinct from readiness. QR retrieval failure cannot mask an observed Operation terminal state. Existing profiles, auth lifecycle, process-tree fences, secret policies and historical records remain intact; no DB migration, raw logs or automatic live login.
