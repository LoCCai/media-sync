**English** | [中文](login-runtime-triage.zh.md)

# Platform login runtime triage

- Date: 2026-09-05
- Local HEAD: `e3fe9db`; application-source baseline: `0fd7c17`
- Status: diagnosis only; confirmed source-level deployment mismatches; runtime causality and fixes pending

## Goal and execution plan

Investigate the operator's report that platform logins do not work after manual console login. Preserve the seven-platform product goal, existing accounts, profiles, credentials, authentication and frozen plans.

1. Read existing account and operation records through the authenticated UI, without starting another login.
2. Compare login preflight with the actual isolated child and the locked upstream browser launch.
3. Reproduce environment filtering locally without launching a child or contacting a platform.
4. Record evidence, limits and the proposed remediation; do not change the server or claim successful platform login.

## Observed deployment evidence

- After the operator manually logged in, the account page rendered three accounts for Bilibili, Douyin and Xiaohongshu, all with failed authentication/latest sessions. No agent entered or read credentials.
- The selected Bilibili login preflight showed all required checks passing. Its live-qualification label remained `NOT_RUN`.
- The operations view listed six historical account-login operations, all terminal failures in `authenticating` with `operation_login_failed`.
- The most recent operation ran from 16:27:59 to 16:28:07 (browser-displayed time). Its result summary contained `runner_status=failed`, `login_session_status=failed` and `auth_status=failed`; five events showed request, start, phase change, session association and failure.
- The UI displayed an event-stream connection and cursor 30. No new operation was triggered to verify live delivery, reconnection or replay.
- Account names, identifiers, deployed authority and session artifacts are omitted from this public record. The running image was not independently identified.

## Confirmed source-level findings

### Shared browser cache is dropped by execution children

`Dockerfile:145-152` installs bundled Chromium with `PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright`. `checkout.py:210-229` preserves that setting for runtime/browser preflight. However, `login_runner.py:73-98,271` excludes it from the real login child's environment. `bridge.py` and `detail_runner.py` have the same omission in their child environment allowlists.

The pinned Xiaohongshu and Douyin persistent launches use the default Chromium resolution. In an image with only the declared shared cache, a child that loses the setting searches a different default cache. This is a confirmed code/configuration mismatch, not direct inspection of the user's current container filesystem. An extra browser installation could alter the runtime outcome.

### Five pinned platforms request a browser channel the image does not install

The locked upstream commit `d6f7c5bb906b6dac40ddf343ef9e26438a3de092` explicitly passes `channel="chrome"` in its persistent launch for Bilibili (`core.py:518`), Kuaishou (`:373`), Weibo (`:382`), Tieba (`:631`) and Zhihu (`:448`). These are paths under each platform's `media_platform` directory in the pinned checkout.

The Dockerfile installs Playwright Chromium, not the system Google Chrome channel. The login adapter sets `SAVE_LOGIN_STATE=True` and `ENABLE_CDP_MODE=False`, and does not normalize the launch channel. Restoring the shared-cache variable alone therefore does not address these five platform launch requirements.

### Preflight and failure reporting conceal these differences

`checkout.py:42-49` launches a default, headless Chromium. Interactive QR login sets `HEADLESS=False` (`login_runner.py:639`) and uses an isolated persistent profile. Headless preflight does not validate that exact environment, channel or display.

`login_runner.py:456-457,575-585` intentionally suppresses upstream output, while `:831-832` maps general exceptions to `failed`. Existing UI evidence cannot distinguish missing browsers, display failures, network errors and platform rejection. Do not enable raw upstream logging: it could expose authentication material.

The earlier Xvfb `/tmp/.X11-unix` warning remains a hypothesis requiring runtime checks, not a proven fatal error. A tmpfs `/tmp` and a headless-only probe warrant checking display readiness, but do not establish failure by themselves.

## Verification and limitations

- Authenticated UI reads verified the states and timeline above; no agent-created account, platform login, subscription, download or server mutation occurred.
- Source inspection established the environment, channel and preflight differences against the locally pinned checkout.
- An independent local experiment supplied only synthetic environment values, intercepted the actual login spawn and detail `Popen` boundaries, and inspected the creator bridge specification and readiness environment. `PLAYWRIGHT_BROWSERS_PATH` was forwarded by readiness, but absent from login, creator and detail execution environments. `DISPLAY` remained present in all four. No real child was started. This confirms filtering, not an actual browser failure on the remote host.
- The pinned upstream HEAD matched the lock and its tracked worktree was clean.
- `.venv/Scripts/python.exe scripts/check_docs.py`: passed, 520 Markdown files. `git diff --check`: passed. No application changes were made, so the earlier full-suite counts were not rerun or claimed for this diagnosis.
- No local Docker runtime or remote shell session was available for this triage. No container browser launch, platform network login, QR display, scan, saved-session reuse, content capture or Emby/Jellyfin playback is qualified here.

## Proposed next implementation, not performed

1. Align safe browser environment propagation across login, creator and detail children, while retaining the secret-denying allowlist.
2. Define an explicit image/adapter browser policy for the five Chrome-channel platforms, without silently editing the locked upstream tree or assuming Chromium equivalence has been live-tested.
3. Add preflight checks that match the actual child environment, browser channel and headed-display prerequisites.
4. Add bounded, redaction-safe failure categories and persist them in the account/operation UI; never forward raw exception strings or cookies.
5. Run focused regressions, then verify the rebuilt image's real unprivileged headed browser. Finally, with the operator, qualify one QR login before trying the other platforms and saved-session/capture flows.

Before remediation is called successful, the running container must supply same-UID browser-path/channel/display evidence or a rebuilt-image launch test. A green preflight and unit tests alone are insufficient.

Related deployment chronology: [handoff](deployment-handoff.md).
