**English** | [中文](progress.zh.md)

# Login integration follow-up progress

- Status: Plan recorded; implementation pending

The operator supplied configuration-valid and headed-persistent Chromium `151.0.7922.34` success. Read-only UI inspection then observed two new failed login Operations at 17:47 and 17:48; the latest Douyin attempt ran 17:48:36–17:48:45 with generic failed runner/session/auth state. No new login was started by the agent. Upstream `find_login_qrcode` returns a string consumed by `show_qrcode`, whereas our relay only accepts bytes. Upstream main imports Douyin's helper, which calls `execjs.compile` at module import; the final Docker stage currently has no explicit JS runtime.
