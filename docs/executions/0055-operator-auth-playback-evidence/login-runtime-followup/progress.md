**English** | [中文](progress.zh.md)

# Login integration follow-up progress

- Status: Implemented; local gates passed; new container/live QR pending

The operator supplied configuration-valid and headed-persistent Chromium `151.0.7922.34` success. Read-only UI inspection then observed two new failed login Operations at 17:47 and 17:48; the latest Douyin attempt ran 17:48:36–17:48:45 with generic failed runner/session/auth state. No new login was started by the agent. Upstream `find_login_qrcode` returns a string consumed by `show_qrcode`, whereas our relay only accepts bytes. Upstream main imports Douyin's helper, which calls `execjs.compile` at module import; the final Docker stage currently has no explicit JS runtime.

The operator then confirmed `NODE_MISSING`. Under plan `7268352`, the final image now installs Node.js and the doctor actually runs fixed JavaScript, while QR strings are safely normalized into PNG. The first paragraph describes the pre-fix baseline, not the new code. Focused and broader gates pass, including real local PyExecJS and Pillow execution; exact results and the hard-kill temporary-file limitation are recorded in [verification](verification.md). The image has not been rebuilt on the server by this agent, so the real platform outcome stays failed/unverified. The accepted Cookie-login addition is separately recorded as a [draft](../cookie-login/plan.md), not an implemented feature.
