**English** | [中文](goal.zh.md)

# Login browser runtime goal

- Date: 2026-09-05
- Baseline: `db6c3c7`
- Status: Frozen before implementation

Repair the shared browser launch path implicated by the deployed login failures. Preserve all seven platforms, isolated persistent profiles, locked upstream identities, operator security, and the final subscriptions/capture/Emby-Jellyfin objective. This is a P0 deployment repair following [triage](../secure-console/login-runtime-triage.md), not successful live qualification.

Acceptance: login, creator and detail children retain only approved environment settings including the browser cache; all seven standard Playwright launch paths explicitly use the installed bundled Chromium without altering the upstream checkout; QR preflight exercises the same environment and headed persistent launch with a disposable, unauthenticated profile; the container waits for its X display before migrations/service startup, after operator configuration validation. Browser policy must retain upstream context options and lifecycle ownership. Failures remain redaction-safe.

Verification includes regressions across all seven pinned launch paths, secret-denying environments, headed preflight and startup ordering/failure. No platform login, user profile access, credential collection or production deployment is automatic. Actual Linux image and live canaries must remain pending until executed.
