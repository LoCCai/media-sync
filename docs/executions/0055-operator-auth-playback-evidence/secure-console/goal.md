**English** | [中文](goal.zh.md)

# Safe console and startup goal

- Date: 2026-09-05
- Baseline: `2e1949f`
- Status: Frozen before implementation

Restore the usable single-operator console without weakening authentication, and reject invalid operator configuration before container startup mutates the database. Follow the [delivery priorities](../delivery-priorities.md); preserve the seven-platform product goal.

Acceptance: anonymous browser entry and known deep-link navigation reach login; only a successful session bootstrap mounts private pages; unsafe Cookie requests receive memory-only CSRF; logout, expiry and late responses cannot revive private views. QR, direct media and SSE use same-origin cookies, never URL credentials. A final-image-user configuration-only command performs the same secret/origin validation as serve, with no app/database/bind/migration and fixed value-safe output; the serve entrypoint runs it before Xvfb and db init.

This increment excludes playback confirmation UI, evidence expansion, live account/server access, new platforms/media shapes and architectural rewrites. Legacy remains protected but becomes an explicit migration notice; without a v2 build the root shows a build/CLI notice, not a broken interactive legacy client. Final Linux image and live canary acceptance still require execution 0047 evidence.
